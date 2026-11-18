"""Integration test across the three Task 6 servers: interface -> orchestrator -> AI server.

Each server's own tests fake the other two, so none of them can see a mismatch between
servers (on 13 Nov two such mismatches passed every unit test). Here the REAL code of all
three runs together, in memory:

    student --HTTP--> interface (real) --HTTP--> orchestrator (real) --HTTP--> AI server (real)

Only two things are swapped, so the test is fast and needs no ports or models:
  * the network: HTTP calls go to the other apps in memory instead of over sockets;
  * the advisor: the AI server runs a fake advise() that returns study paths at once.
The orchestrator's supervisor is driven by calling ``tick()``, so each step is explicit.

Run with:  python -m pytest tests/test_servers_integration.py -q
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

os.environ["AI_PRELOAD"] = "0"  # the AI server must not load the real models here
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402

import src.interface_server as interface  # noqa: E402
from src.servers import ai_server  # noqa: E402
from src.servers.ai_pool import AIPool  # noqa: E402
from src.servers.orchestrator import JobQueue, create_app  # noqa: E402

PATHS = [
    {"fit": 0.8, "weeks": 12.0, "courses": [{"course_key": "c1", "title": "Learn Python"}],
     "covered_skills": ["Python (computer programming)"]},
    {"fit": 0.6, "weeks": 18.0, "courses": [{"course_key": "c2", "title": "SQL Basics"}],
     "covered_skills": ["SQL"]},
    {"fit": 0.5, "weeks": 9.0, "courses": [{"course_key": "c3", "title": "Git for Teams"}],
     "covered_skills": ["use version control"]},
]
GOOD_REQUEST = {"interest": "software developer", "language": "English",
                "hours_per_week": 6, "weeks_available": 20}
AI_URL = "http://testserver"          # the AI server app, reached in memory


def fake_advise(request: dict) -> dict:
    """Stands in for advise(): echoes the request so the test can see what arrived."""
    return {"ok": True, "interest": request["interest"], "paths": PATHS, "message": None}


@pytest.fixture
def system(monkeypatch, tmp_path):
    """The real interface, orchestrator and AI server, wired together in memory.

    The interface keeps its own create_job() / get_job() code and the orchestrator its own
    dispatching code; only the network under them is replaced, so the request formats
    they send each other are the ones being tested.
    """
    monkeypatch.setattr(ai_server, "run_advisor", fake_advise)
    ai_server.stats.update(jobs_done=0, jobs_failed=0)
    ai = TestClient(ai_server.app)                      # the orchestrator's line to the AI server

    queue = JobQueue(tmp_path / "queue.sqlite3")
    pool = AIPool(queue, urls=[AI_URL], client=ai, run_async=False, health_every=0)
    orchestrator = TestClient(create_app(tmp_path / "queue.sqlite3", pool=pool))

    base, calls = interface.ORCHESTRATOR_URL, []

    def route(method):
        def call(url, json=None, timeout=None):
            calls.append(url)
            assert url.startswith(base), f"interface called {url}, not the orchestrator"
            return orchestrator.request(method, url[len(base):], json=json)
        return call

    network = types.SimpleNamespace(post=route("POST"), get=route("GET"), HTTPError=httpx.HTTPError)
    monkeypatch.setattr(interface, "httpx", network)
    monkeypatch.setattr(interface, "db", interface.open_db(":memory:"))
    return {"student": TestClient(interface.app), "orchestrator": orchestrator,
            "pool": pool, "queue": queue, "calls": calls}


def jobs(system) -> dict:
    return system["orchestrator"].get("/health").json()["jobs"]


def test_request_goes_through_all_three_servers_and_paths_come_back(system):
    student, pool = system["student"], system["pool"]

    # 1. The student sends a request to the interface; it reaches the orchestrator's queue.
    sent = student.post("/advice", json=GOOD_REQUEST)
    assert sent.status_code == 202
    job_id = sent.json()["id"]
    assert sent.json()["status"] == "waiting"
    assert jobs(system) == {"waiting": 1, "running": 0, "done": 0, "failed": 0}
    assert student.get(f"/advice/{job_id}").json()["status"] == "waiting"

    # 2. The orchestrator checks the AI server's health and sends it the job.
    pool.tick()

    # 3. The student reads the result through the interface.
    answer = student.get(f"/advice/{job_id}").json()
    assert answer["status"] == "done"
    assert answer["result"]["ok"] is True
    assert answer["result"]["interest"] == "software developer"  # the request arrived intact
    assert 3 <= len(answer["result"]["paths"]) <= 5
    assert answer["result"]["paths"] == PATHS
    assert jobs(system) == {"waiting": 0, "running": 0, "done": 1, "failed": 0}
    assert ai_server.stats["jobs_done"] == 1
    assert system["queue"].get(job_id)["worker"] == AI_URL


def test_bad_input_is_stopped_at_the_interface_and_never_reaches_the_queue(system):
    response = system["student"].post("/advice", json={"interest": ""})

    assert response.status_code == 422
    assert response.json() == {"error": "Please describe an interest"}
    system["pool"].tick()
    assert jobs(system) == {"waiting": 0, "running": 0, "done": 0, "failed": 0}
    assert system["calls"] == []       # the orchestrator was not even contacted
    assert ai_server.stats["jobs_done"] == 0


def test_advisor_crash_reaches_the_student_as_a_failed_job(system, monkeypatch):
    def broken(request):
        raise RuntimeError("model file missing")
    monkeypatch.setattr(ai_server, "run_advisor", broken)

    job_id = system["student"].post("/advice", json=GOOD_REQUEST).json()["id"]
    system["pool"].tick()

    answer = system["student"].get(f"/advice/{job_id}").json()
    assert answer["status"] == "failed"
    assert answer["error"] == "RuntimeError: model file missing"
    assert ai_server.stats["jobs_failed"] == 1


def test_interface_only_ever_talks_to_the_orchestrator(system):
    job_id = system["student"].post("/advice", json=GOOD_REQUEST).json()["id"]
    system["pool"].tick()
    system["student"].get(f"/advice/{job_id}")

    base = interface.ORCHESTRATOR_URL
    assert system["calls"] == [f"{base}/jobs", f"{base}/jobs/{job_id}"]


def test_the_ai_server_works_only_when_the_orchestrator_sends_a_job(system):
    """No job, no work: the AI server never asks for work on its own."""
    for _ in range(3):
        system["pool"].tick()
    assert ai_server.stats["jobs_done"] == 0
    assert system["pool"].status()["workers"][0]["state"] == "idle"
