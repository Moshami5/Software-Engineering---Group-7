"""Unit tests for src/servers/orchestrator.py (Task 6 orchestrator).

Each test gets its own SQLite file in a temporary folder, so no other server, no
network and no models are needed.
Run with:  python -m pytest tests/test_orchestrator.py -q
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402

from src.servers.orchestrator import JobQueue, create_app  # noqa: E402

REQUEST = {"interest": "I want to work with data", "context": {"weeks": 20}}


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path / "queue.sqlite3"))


def add(client, request=REQUEST) -> str:
    response = client.post("/jobs", json={"request": request})
    assert response.status_code == 201
    assert response.json()["status"] == "waiting"
    return response.json()["id"]


def test_new_job_is_waiting(client):
    job_id = add(client)
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "waiting"
    assert job["result"] is None and job["error"] is None


def test_empty_queue_gives_204(client):
    response = client.get("/jobs/next")
    assert response.status_code == 204
    assert response.content == b""


def test_next_gives_oldest_job_and_marks_it_running(client):
    first = add(client, {"interest": "first"})
    second = add(client, {"interest": "second"})

    job = client.get("/jobs/next").json()
    assert job == {"id": first, "request": {"interest": "first"}}
    assert client.get(f"/jobs/{first}").json()["status"] == "running"
    assert client.get(f"/jobs/{second}").json()["status"] == "waiting"
    assert client.get("/jobs/next").json()["id"] == second


def test_job_is_never_given_out_twice(client):
    add(client)
    assert client.get("/jobs/next").status_code == 200
    assert client.get("/jobs/next").status_code == 204


def test_result_marks_job_done(client):
    job_id = add(client)
    client.get("/jobs/next")
    result = {"ok": True, "paths": [{"courses": ["A", "B"], "weeks": 12}]}

    response = client.post(f"/jobs/{job_id}/result", json={"result": result})
    assert response.status_code == 200
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "done"
    assert job["result"] == result
    assert job["finished_at"] is not None


def test_error_marks_job_failed(client):
    job_id = add(client)
    client.get("/jobs/next")

    client.post(f"/jobs/{job_id}/result", json={"error": "RuntimeError: boom"})
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert job["error"] == "RuntimeError: boom"
    assert job["result"] is None


def test_result_for_job_that_is_not_running_is_refused(client):
    job_id = add(client)
    # still waiting: nobody took it yet
    assert client.post(f"/jobs/{job_id}/result", json={"result": {}}).status_code == 409
    client.get("/jobs/next")
    client.post(f"/jobs/{job_id}/result", json={"result": {"ok": True}})
    # already done: a second result must not overwrite the first
    assert client.post(f"/jobs/{job_id}/result", json={"error": "late"}).status_code == 409
    assert client.get(f"/jobs/{job_id}").json()["status"] == "done"


def test_unknown_job_gives_404(client):
    assert client.get("/jobs/nope").status_code == 404
    assert client.post("/jobs/nope/result", json={"result": {}}).status_code == 404


@pytest.mark.parametrize(
    "path, body",
    [
        ("/jobs", {}),                                  # no request
        ("/jobs", {"request": "not a dict"}),           # request must be an object
        ("/jobs/x/result", {}),                         # neither result nor error
        ("/jobs/x/result", {"result": {}, "error": "both"}),
    ],
)
def test_malformed_bodies_give_422(client, path, body):
    assert client.post(path, json=body).status_code == 422


def test_jobs_survive_a_restart(tmp_path):
    db = tmp_path / "queue.sqlite3"
    job_id = add(TestClient(create_app(db)))
    assert TestClient(create_app(db)).get("/jobs/next").json()["id"] == job_id


def test_parallel_takers_never_share_a_job(tmp_path):
    """Several AI servers asking at once: every job is given out exactly once."""
    queue = JobQueue(tmp_path / "queue.sqlite3")
    ids = {queue.add({"n": n}) for n in range(40)}
    taken, lock = [], threading.Lock()

    def worker():
        while (job := queue.take_next()) is not None:
            with lock:
                taken.append(job["id"])

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(taken) == sorted(ids)


def test_health_counts_jobs_per_status(client):
    done, _waiting = add(client), add(client)
    client.get("/jobs/next")
    client.post(f"/jobs/{done}/result", json={"result": {}})
    assert client.get("/health").json()["jobs"] == {
        "waiting": 1, "running": 0, "done": 1, "failed": 0,
    }
