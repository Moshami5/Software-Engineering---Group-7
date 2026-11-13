"""Unit tests for scripts/run_servers.py (Task 6 start script + end-to-end check).

The three servers are faked with httpx.MockTransport, so these tests need no models,
no open ports and no subprocesses. They check that the end-to-end check passes on the
agreed API (tasks/task6/README.md) and fails loudly when any server breaks it.
The real run is:  python scripts/run_servers.py --check
Run with:  python -m pytest tests/test_run_servers.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

httpx = pytest.importorskip("httpx")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_servers import (  # noqa: E402
    AI_SERVER,
    INTERFACE,
    ORCHESTRATOR,
    CheckFailed,
    check_result,
    run_check,
)

PATH = {"fit": 0.8, "weeks": 12.0, "courses": [{"course_key": "c1"}], "covered_skills": []}
GOOD_RESULT = {"ok": True, "paths": [PATH] * 3, "message": None}


class FakeSystem:
    """Interface, orchestrator and AI server behind one MockTransport.

    A job posted to the queue is finished straight away, as if the AI server took it.
    The attributes switch on one fault at a time.
    """

    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.ai_handled = 0
        self.result = GOOD_RESULT
        self.interface_accepts_bad_input = False
        self.interface_queues_bad_input = False
        self.ai_counts_job = True

    def _queue(self, request: dict) -> str:
        job_id = f"job{len(self.jobs) + 1}"
        self.jobs[job_id] = {"id": job_id, "status": "done", "result": self.result, "error": None}
        if self.ai_counts_job:
            self.ai_handled += 1
        return job_id

    def handler(self, request: httpx.Request) -> httpx.Response:
        url, method = str(request.url), request.method
        body = json.loads(request.content) if request.content else None

        if url == AI_SERVER.url + "/health":
            return httpx.Response(200, json={"jobs_done": self.ai_handled, "jobs_failed": 0})
        if url == ORCHESTRATOR.url + "/health":
            return httpx.Response(200, json={"status": "ok", "jobs": {"done": len(self.jobs)}})
        if url == ORCHESTRATOR.url + "/jobs" and method == "POST":
            return httpx.Response(201, json={"id": self._queue(body["request"]), "status": "waiting"})
        if url.startswith(ORCHESTRATOR.url + "/jobs/"):
            return httpx.Response(200, json=self.jobs[url.rsplit("/", 1)[1]])

        if url == INTERFACE.url + "/advice" and method == "POST":
            if not body.get("interest"):
                if self.interface_queues_bad_input:
                    self._queue(body)
                if not self.interface_accepts_bad_input:
                    return httpx.Response(422, json={"error": "interest is empty"})
            return httpx.Response(202, json={"id": self._queue(body), "status": "waiting"})
        if url.startswith(INTERFACE.url + "/advice/"):
            job = self.jobs.get(url.rsplit("/", 1)[1])
            return httpx.Response(200, json=job) if job else httpx.Response(404)
        return httpx.Response(404)


@pytest.fixture
def system():
    return FakeSystem()


@pytest.fixture
def client(system):
    return httpx.Client(transport=httpx.MockTransport(system.handler))


@pytest.mark.parametrize("via_interface", [True, False])
def test_check_passes_on_the_agreed_api(client, via_interface):
    assert run_check(client, via_interface=via_interface, timeout=5) == GOOD_RESULT


def test_interface_accepting_bad_input_fails(system, client):
    system.interface_accepts_bad_input = True
    with pytest.raises(CheckFailed, match="422"):
        run_check(client, timeout=5)


def test_bad_input_reaching_the_queue_fails(system, client):
    system.interface_queues_bad_input = True
    with pytest.raises(CheckFailed, match="reached the queue"):
        run_check(client, timeout=5)


def test_job_not_handled_by_ai_server_fails(system, client):
    system.ai_counts_job = False
    with pytest.raises(CheckFailed, match="AI server"):
        run_check(client, timeout=5)


@pytest.mark.parametrize("job, reason", [
    ({"id": "j", "status": "failed", "error": "ValueError: boom"}, "failed"),
    ({"id": "j", "status": "done", "result": {"ok": False, "error": "no interest"}}, "refused"),
    ({"id": "j", "status": "done", "result": {"ok": True, "paths": []}}, "1-5"),
    ({"id": "j", "status": "done", "result": {"ok": True, "paths": [PATH] * 6}}, "1-5"),
    ({"id": "j", "status": "done", "result": {"ok": True, "paths": [{"courses": []}]}}, "no courses"),
])
def test_check_result_rejects_bad_results(job, reason):
    with pytest.raises(CheckFailed, match=reason):
        check_result(job)
