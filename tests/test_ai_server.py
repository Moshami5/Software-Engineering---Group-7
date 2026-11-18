"""Unit tests for src/servers/ai_server.py (Task 6 AI server).

The orchestrator sends jobs with POST /run; here the test plays the orchestrator. The
advisor is a fake function, so these tests need no models and no other server.
Run with:  python -m pytest tests/test_ai_server.py -q
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

os.environ["AI_PRELOAD"] = "0"  # no models in unit tests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402

from src.servers import ai_server  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    ai_server.stats.update(jobs_done=0, jobs_failed=0)
    monkeypatch.setattr(ai_server, "run_advisor",
                        lambda request: {"ok": True, "interest": request["interest"], "paths": []})
    return TestClient(ai_server.app)


def test_job_is_run_and_its_result_returned(client):
    response = client.post("/run", json={"id": "j1", "request": {"interest": "data analysis"}})

    assert response.status_code == 200
    assert response.json() == {"id": "j1", "result": {"ok": True, "interest": "data analysis", "paths": []}}
    assert ai_server.stats["jobs_done"] == 1


def test_advisor_crash_is_returned_as_a_failed_job(client, monkeypatch):
    def broken(request):
        raise RuntimeError("model file missing")
    monkeypatch.setattr(ai_server, "run_advisor", broken)

    response = client.post("/run", json={"id": "j2", "request": {"interest": "x"}})

    # 200: the server itself is fine, only this job failed, so the orchestrator must not
    # treat the server as broken.
    assert response.status_code == 200
    assert response.json() == {"id": "j2", "error": "RuntimeError: model file missing"}
    assert ai_server.stats["jobs_failed"] == 1


def test_only_one_job_at_a_time(client, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow(request):
        started.set()
        release.wait(5)
        return {"ok": True}
    monkeypatch.setattr(ai_server, "run_advisor", slow)

    first = threading.Thread(target=client.post, args=("/run",), kwargs={"json": {"id": "a", "request": {}}})
    first.start()
    assert started.wait(5)
    try:
        assert client.get("/health").json()["busy"] is True
        second = client.post("/run", json={"id": "b", "request": {}})
        assert second.status_code == 409
    finally:
        release.set()
        first.join(5)
    assert client.get("/health").json()["busy"] is False


@pytest.mark.parametrize("body", [{}, {"id": "j"}, {"request": {}}, {"id": 3, "request": {}},
                                  {"id": "j", "request": "text"}])
def test_malformed_job_gives_422(client, body):
    assert client.post("/run", json=body).status_code == 422


def test_health_reports_ready_and_counts(client):
    client.post("/run", json={"id": "j", "request": {"interest": "x"}})
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["ready"] is True              # AI_PRELOAD=0: nothing to load
    assert body["busy"] is False
    assert body["jobs_done"] == 1 and body["jobs_failed"] == 0


def test_the_ai_server_never_asks_for_work():
    """It has no worker loop and no orchestrator address: it only answers POST /run."""
    assert not hasattr(ai_server, "ORCHESTRATOR_URL")
    assert not hasattr(ai_server, "process_one")
    paths = {route.path for route in ai_server.app.routes}
    assert {"/run", "/health"} <= paths
