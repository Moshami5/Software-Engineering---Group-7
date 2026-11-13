"""Unit tests for src/servers/ai_server.py (Task 6 AI server).

The orchestrator is a fake HTTP endpoint (httpx.MockTransport) and the advisor is a
fake function, so these tests need no network, no models and no other server.
Run with:  python -m pytest tests/test_ai_server.py -q
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
import httpx  # noqa: E402

os.environ["AI_PRELOAD"] = "0"  # no models in unit tests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402

from src.servers import ai_server  # noqa: E402


class FakeOrchestrator:
    """Holds a list of waiting jobs and records the results sent back."""

    def __init__(self, jobs):
        self.jobs, self.results = list(jobs), {}

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/jobs/next":
            return httpx.Response(200, json=self.jobs.pop(0)) if self.jobs else httpx.Response(204)
        if request.method == "POST" and request.url.path.endswith("/result"):
            job_id = request.url.path.split("/")[2]
            self.results[job_id] = httpx.Response(200, content=request.content).json()
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(base_url="http://orchestrator", transport=httpx.MockTransport(self.handle))


@pytest.fixture(autouse=True)
def reset_stats():
    ai_server.stats.update(jobs_done=0, jobs_failed=0)


def test_empty_queue_returns_false_and_runs_nothing():
    calls = []
    orch = FakeOrchestrator([])
    assert ai_server.process_one(orch.client(), run=calls.append) is False
    assert calls == [] and orch.results == {}


def test_job_is_run_and_its_result_sent_back():
    orch = FakeOrchestrator([{"id": "j1", "request": {"interest": "data analysis"}}])
    fake_advise = lambda request: {"ok": True, "interest": request["interest"], "paths": []}  # noqa: E731

    assert ai_server.process_one(orch.client(), run=fake_advise) is True
    assert orch.results == {"j1": {"result": {"ok": True, "interest": "data analysis", "paths": []}}}
    assert ai_server.stats["jobs_done"] == 1


def test_advisor_crash_is_reported_as_failed_job():
    orch = FakeOrchestrator([{"id": "j2", "request": {"interest": "x"}}])

    def broken(request):
        raise RuntimeError("model file missing")

    assert ai_server.process_one(orch.client(), run=broken) is True
    assert orch.results == {"j2": {"error": "RuntimeError: model file missing"}}
    assert ai_server.stats["jobs_failed"] == 1


def test_jobs_are_taken_one_at_a_time_in_order():
    orch = FakeOrchestrator([{"id": "a", "request": {}}, {"id": "b", "request": {}}])
    client = orch.client()
    ai_server.process_one(client, run=lambda r: {"ok": True})
    assert list(orch.results) == ["a"]
    ai_server.process_one(client, run=lambda r: {"ok": True})
    assert list(orch.results) == ["a", "b"]


def test_health_endpoint_reports_status():
    with TestClient(ai_server.app) as client:  # starts the worker; no orchestrator is running
        body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["orchestrator"] == ai_server.ORCHESTRATOR_URL
    assert {"models_loaded", "jobs_done", "jobs_failed"} <= body.keys()
