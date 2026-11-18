"""Unit tests for the Task 6 orchestrator: src/servers/orchestrator.py and src/servers/ai_pool.py.

Two parts:
  * the job queue and the HTTP API (each test has its own SQLite file);
  * the AI pool, i.e. the decisions the orchestrator makes: when to start an AI server,
    which one gets a job, what happens when one fails, when an idle one is stopped.
    AI servers are fakes behind httpx.MockTransport, processes are fakes, and the clock
    is a number the test moves, so every decision is checked exactly, with no waiting.

Run with:  python -m pytest tests/test_orchestrator.py -q
"""
from __future__ import annotations

import sqlite3
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402

from src.servers.ai_pool import AIPool  # noqa: E402
from src.servers.orchestrator import JobQueue, create_app  # noqa: E402

REQUEST = {"interest": "I want to work with data", "weeks_available": 20}


# ======================================================================= fakes


class FakeAI:
    """One AI server: answers /health and /run like src/servers/ai_server.py."""

    def __init__(self, ready=True):
        self.ready, self.alive = ready, True
        self.mode = "ok"            # ok | error | crash | hold
        self.release = threading.Event()
        self.runs = []

    def answer(self, path, body):
        if not self.alive:
            raise httpx.ConnectError("connection refused")
        if path == "/health":
            return httpx.Response(200, json={"status": "ok", "ready": self.ready})
        self.runs.append(body["id"])
        if self.mode == "crash":    # the process dies in the middle of the job
            self.alive = False
            raise httpx.RemoteProtocolError("server disconnected")
        if self.mode == "hold":
            self.release.wait(5)
        if self.mode == "error":
            return httpx.Response(200, json={"id": body["id"], "error": "RuntimeError: boom"})
        return httpx.Response(200, json={"id": body["id"], "result": {"ok": True, "paths": ["p1", "p2", "p3"]}})


class Network:
    """Routes http://127.0.0.1:<port>/... to the FakeAI on that port."""

    def __init__(self):
        self.ai: dict[int, FakeAI] = {}

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = urlsplit(str(request.url))
        ai = self.ai.get(url.port)
        if ai is None:
            raise httpx.ConnectError("connection refused")
        body = __import__("json").loads(request.content) if request.content else None
        return ai.answer(url.path, body)


class FakeProcess:
    def __init__(self, port):
        self.port, self.running = port, True


class FakeLauncher:
    """Instead of starting real processes, puts a FakeAI on the network."""

    def __init__(self, network, ready=True):
        self.network, self.ready = network, ready
        self.started, self.stopped = [], []

    def start(self, port):
        self.started.append(port)
        self.network.ai[port] = FakeAI(ready=self.ready)
        return FakeProcess(port)

    def alive(self, handle):
        return handle.running and self.network.ai[handle.port].alive

    def stop(self, handle):
        handle.running = False
        self.stopped.append(handle.port)
        self.network.ai[handle.port].alive = False


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def queue(tmp_path):
    return JobQueue(tmp_path / "queue.sqlite3")


@pytest.fixture
def net():
    return Network()


@pytest.fixture
def clock():
    return Clock()


def make_pool(queue, net, clock, **kw):
    launcher = kw.pop("launcher", None) or (None if "urls" in kw else FakeLauncher(net))
    defaults = dict(launcher=launcher, client=httpx.Client(transport=httpx.MockTransport(net.handle)),
                    health_every=0, run_async=False, clock=clock, idle_stop=300)
    defaults.update(kw)
    return AIPool(queue, **defaults)


# ================================================================ the job queue


def test_new_job_is_waiting(queue):
    job = queue.get(queue.add(REQUEST))
    assert job["status"] == "waiting"
    assert job["attempts"] == 0 and job["worker"] is None
    assert job["result"] is None and job["error"] is None


def test_take_next_gives_oldest_job_and_records_attempt_and_worker(queue):
    first, second = queue.add({"n": 1}), queue.add({"n": 2})

    job = queue.take_next(worker="http://ai-1")
    assert job == {"id": first, "request": {"n": 1}}
    stored = queue.get(first)
    assert stored["status"] == "running" and stored["attempts"] == 1 and stored["worker"] == "http://ai-1"
    assert queue.get(second)["status"] == "waiting"


def test_job_is_never_given_out_twice(queue):
    queue.add(REQUEST)
    assert queue.take_next() is not None
    assert queue.take_next() is None


def test_parallel_takers_never_share_a_job(queue):
    """Several takers at once: every job is given out exactly once."""
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


def test_finish_marks_done_or_failed_and_refuses_late_results(queue):
    done, failed = queue.add(REQUEST), queue.add(REQUEST)
    queue.take_next(), queue.take_next()

    assert queue.finish(done, result={"ok": True}) == "done"
    assert queue.finish(failed, error="RuntimeError: boom") == "failed"
    assert queue.get(done)["result"] == {"ok": True}
    assert queue.get(failed)["error"] == "RuntimeError: boom"
    with pytest.raises(ValueError):          # a second result never overwrites the first
        queue.finish(done, error="late")
    with pytest.raises(KeyError):
        queue.finish("nope", result={})


def test_requeue_puts_a_running_job_back(queue):
    job_id = queue.add(REQUEST)
    assert queue.requeue(job_id) is False     # waiting: nothing to put back
    queue.take_next(worker="http://ai-1")
    assert queue.requeue(job_id) is True
    job = queue.get(job_id)
    assert job["status"] == "waiting" and job["worker"] is None and job["attempts"] == 1


def test_jobs_survive_a_restart_and_running_ones_go_back_to_waiting(tmp_path, net, clock):
    db = tmp_path / "queue.sqlite3"
    first = JobQueue(db)
    waiting, running = first.add({"n": 1}), first.add({"n": 2})
    first.take_next()                          # running when the orchestrator "stops"

    app = create_app(db, pool=make_pool(JobQueue(db), net, clock))
    jobs = TestClient(app).get("/health").json()["jobs"]
    assert jobs == {"waiting": 2, "running": 0, "done": 0, "failed": 0}
    assert JobQueue(db).get(waiting)["status"] == "waiting"


def test_queue_file_from_the_first_version_is_upgraded(tmp_path):
    db = tmp_path / "old.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE jobs (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, "
                     "status TEXT NOT NULL, request TEXT NOT NULL, result TEXT, error TEXT, "
                     "created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT)")
    queue = JobQueue(db)
    assert queue.get(queue.add(REQUEST))["attempts"] == 0


# ==================================================================== the HTTP API


@pytest.fixture
def api(tmp_path, net, clock):
    queue = JobQueue(tmp_path / "queue.sqlite3")
    return TestClient(create_app(tmp_path / "queue.sqlite3", pool=make_pool(queue, net, clock)))


def test_post_job_returns_its_id_and_status(api):
    response = api.post("/jobs", json={"request": REQUEST})
    assert response.status_code == 201
    assert response.json()["status"] == "waiting"
    assert api.get(f"/jobs/{response.json()['id']}").json()["status"] == "waiting"


@pytest.mark.parametrize("body", [{}, {"request": "not a dict"}])
def test_malformed_job_gives_422(api, body):
    assert api.post("/jobs", json=body).status_code == 422


def test_unknown_job_gives_404(api):
    assert api.get("/jobs/nope").status_code == 404


def test_health_shows_jobs_and_ai_servers(api):
    body = api.get("/health").json()
    assert body["jobs"] == {"waiting": 0, "running": 0, "done": 0, "failed": 0}
    assert body["mode"] == "managed" and body["workers"] == [] and body["jobs_run"] == 0


def test_ai_servers_cannot_pull_work_any_more(api):
    """The orchestrator pushes jobs; the old pull endpoints are gone."""
    assert api.get("/jobs/next").status_code == 404
    assert api.post("/jobs/x/result", json={"result": {}}).status_code in (404, 405)


# ========================================================= the orchestrator's decisions


def test_no_ai_server_runs_while_there_is_no_work(queue, net, clock):
    pool = make_pool(queue, net, clock)
    for _ in range(3):
        pool.tick()
    assert pool.launcher.started == [] and pool.workers == []


def test_a_job_starts_an_ai_server_and_is_pushed_to_it(queue, net, clock):
    pool = make_pool(queue, net, clock)
    job_id = queue.add(REQUEST)

    pool.tick()                                # job waiting, no AI server -> start one
    assert pool.launcher.started == [8002]
    assert pool.status()["workers"][0]["state"] == "starting"

    pool.tick()                                # healthy -> idle -> the job is sent to it
    job = queue.get(job_id)
    assert job["status"] == "done"
    assert job["result"] == {"ok": True, "paths": ["p1", "p2", "p3"]}
    assert job["worker"] == "http://127.0.0.1:8002" and job["attempts"] == 1
    assert net.ai[8002].runs == [job_id]
    assert pool.jobs_run == 1 and pool.status()["workers"][0]["state"] == "idle"


def test_no_job_is_sent_before_the_ai_server_is_ready(queue, net, clock):
    pool = make_pool(queue, net, clock, launcher=FakeLauncher(net, ready=False))
    job_id = queue.add(REQUEST)
    pool.tick()
    pool.tick()                                # still loading the models
    assert queue.get(job_id)["status"] == "waiting" and net.ai[8002].runs == []

    net.ai[8002].ready = True
    pool.tick()
    assert queue.get(job_id)["status"] == "done"


def test_ai_server_that_never_gets_ready_is_replaced(queue, net, clock):
    pool = make_pool(queue, net, clock, launcher=FakeLauncher(net, ready=False), start_timeout=60)
    queue.add(REQUEST)
    pool.tick()
    clock.now += 61
    pool.tick()                                # too slow: stopped, and a new one started
    assert pool.launcher.stopped == [8002]
    assert pool.launcher.started == [8002, 8002]


def test_advisor_error_fails_the_job_but_keeps_the_ai_server(queue, net, clock):
    pool = make_pool(queue, net, clock)
    job_id = queue.add(REQUEST)
    pool.tick()
    net.ai[8002].mode = "error"
    pool.tick()

    job = queue.get(job_id)
    assert job["status"] == "failed" and job["error"] == "RuntimeError: boom"
    assert pool.launcher.stopped == []         # the server itself is fine
    assert pool.status()["workers"][0]["state"] == "idle"


def test_ai_server_crash_during_a_job_puts_it_back_and_a_new_server_runs_it(queue, net, clock):
    pool = make_pool(queue, net, clock)
    job_id = queue.add(REQUEST)
    pool.tick()
    net.ai[8002].mode = "crash"
    pool.tick()                                # the job is lost with the server ...

    job = queue.get(job_id)
    assert job["status"] == "waiting" and job["attempts"] == 1
    assert pool.launcher.stopped == [8002] and pool.workers == []

    pool.tick()                                # ... a fresh AI server is started ...
    pool.tick()                                # ... and runs it
    job = queue.get(job_id)
    assert job["status"] == "done" and job["attempts"] == 2
    assert pool.launcher.started == [8002, 8002]


def test_job_fails_after_the_last_attempt_instead_of_looping(queue, net, clock):
    pool = make_pool(queue, net, clock, max_attempts=2)
    job_id = queue.add(REQUEST)
    for _ in range(2):
        pool.tick()                            # start an AI server
        net.ai[8002].mode = "crash"
        pool.tick()                            # it crashes on the job

    job = queue.get(job_id)
    assert job["status"] == "failed" and job["attempts"] == 2
    assert "gave up after 2 attempts" in job["error"]


def test_dead_process_is_noticed_by_the_health_check(queue, net, clock):
    pool = make_pool(queue, net, clock)
    pool.min_workers = 1
    pool.tick(); pool.tick()                   # one AI server, idle
    net.ai[8002].alive = False                 # killed from outside

    pool.tick()                                # noticed, removed and replaced in one pass
    assert pool.launcher.stopped == [8002]
    assert pool.launcher.started == [8002, 8002]
    pool.tick()
    assert pool.status()["workers"][0]["state"] == "idle"


def test_idle_ai_server_is_stopped_after_idle_stop_seconds(queue, net, clock):
    pool = make_pool(queue, net, clock, idle_stop=300)
    queue.add(REQUEST)
    pool.tick(); pool.tick()                   # started, ran the job, now idle

    clock.now += 299
    pool.tick()
    assert pool.launcher.stopped == []
    clock.now += 2
    pool.tick()
    assert pool.launcher.stopped == [8002] and pool.workers == []


def test_min_workers_stay_running_when_idle(queue, net, clock):
    pool = make_pool(queue, net, clock, idle_stop=300, min_workers=1)
    pool.tick()
    assert pool.launcher.started == [8002]     # started without any job
    pool.tick()
    clock.now += 10_000
    pool.tick()
    assert pool.launcher.stopped == []


def test_more_jobs_start_a_second_ai_server_but_never_more_than_max(queue, net, clock):
    pool = make_pool(queue, net, clock, run_async=True, max_workers=2)
    jobs = [queue.add({"n": n}) for n in range(3)]
    pool.tick()                                # start AI server 1
    net.ai[8002].mode = "hold"
    pool.tick()                                # job 1 -> AI 1 (busy, holding)
    pool.tick()                                # jobs still waiting, none free -> start AI 2
    assert pool.launcher.started == [8002, 8003]
    net.ai[8003].mode = "hold"
    pool.tick()                                # job 2 -> AI 2
    pool.tick()                                # job 3 waits: already at max_workers
    assert pool.launcher.started == [8002, 8003]
    assert [w["state"] for w in pool.status()["workers"]] == ["busy", "busy"]

    net.ai[8002].release.set(); net.ai[8003].release.set()
    for _ in range(50):                        # let the two job threads finish
        if queue.counts()["done"] == 2:
            break
        threading.Event().wait(0.05)
    pool.tick()                                # job 3 -> a free AI server
    for _ in range(50):
        if queue.counts()["done"] == 3:
            break
        threading.Event().wait(0.05)
    assert all(queue.get(j)["status"] == "done" for j in jobs)


def test_external_ai_servers_are_used_but_never_started(queue, net, clock):
    net.ai[9000] = FakeAI()
    pool = make_pool(queue, net, clock, urls=["http://127.0.0.1:9000"])
    job_id = queue.add(REQUEST)
    pool.tick()                                # healthy -> idle -> job sent
    assert queue.get(job_id)["status"] == "done"
    assert pool.status()["mode"] == "external"


def test_external_ai_server_that_stops_answering_is_skipped_until_it_is_back(queue, net, clock):
    net.ai[9000] = FakeAI()
    pool = make_pool(queue, net, clock, urls=["http://127.0.0.1:9000"], max_failed_checks=3)
    pool.tick()
    net.ai[9000].alive = False
    for _ in range(3):
        pool.tick()
    assert pool.status()["workers"][0]["state"] == "down"

    job_id = queue.add(REQUEST)
    pool.tick()
    assert queue.get(job_id)["status"] == "waiting"    # not sent to a server that is down
    net.ai[9000].alive = True
    pool.tick()
    assert queue.get(job_id)["status"] == "done"


def test_shutdown_stops_the_ai_servers_and_starts_no_new_ones(queue, net, clock):
    pool = make_pool(queue, net, clock)
    queue.add(REQUEST)
    pool.tick(); pool.tick()
    assert pool.shutdown() == 1
    assert pool.launcher.stopped == [8002]

    queue.add(REQUEST)
    pool.tick()
    assert pool.launcher.started == [8002]     # nothing new after shutdown


def test_stopping_the_orchestrator_stops_its_ai_servers(tmp_path, net, clock):
    queue = JobQueue(tmp_path / "queue.sqlite3")
    pool = make_pool(queue, net, clock, min_workers=1)
    with TestClient(create_app(tmp_path / "queue.sqlite3", pool=pool)) as api:
        pool.tick()
        assert api.get("/health").json()["workers"][0]["url"] == "http://127.0.0.1:8002"
    assert pool.launcher.stopped == [8002]     # the lifespan shut the pool down


def test_ai_shutdown_endpoint(tmp_path, net, clock):
    queue = JobQueue(tmp_path / "queue.sqlite3")
    pool = make_pool(queue, net, clock, min_workers=1)
    api = TestClient(create_app(tmp_path / "queue.sqlite3", pool=pool))
    pool.tick()
    assert api.post("/ai/shutdown").json() == {"stopped": 1}
    assert pool.launcher.stopped == [8002]
