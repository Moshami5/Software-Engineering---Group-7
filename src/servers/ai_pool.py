"""The orchestrator's AI pool: decides when and where each job runs.

The orchestrator is the active part of the system. The AI servers never ask for work;
this pool sends it to them:

    dispatch   a waiting job goes to a free, healthy AI server  ->  POST {ai}/run
    health     every AI server is checked every few seconds     ->  GET  {ai}/health
    recover    a job on an AI server that fails goes back to the queue (at most
               ``max_attempts`` tries, then the job is marked failed)
    scale      managed mode only: start an AI server when jobs wait and none is free,
               restart one that died, stop one that has been idle for ``idle_stop`` s

Two modes:
    managed    (default) the pool starts and stops AI server processes itself, on
               ports base_port, base_port + 1, ... (at most ``max_workers``)
    external   ``urls`` lists AI servers someone else runs (other machines, Docker);
               the pool checks and uses them but cannot start or stop them

Every decision happens in ``tick()``, one pass under one lock. ``run()`` calls it in a
loop on a background thread; tests call it directly, so they need no sleeping or timing.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "runtime" / "logs"
HOST = "127.0.0.1"

STARTING, IDLE, BUSY, DOWN = "starting", "idle", "busy", "down"


@dataclass
class Worker:
    """One AI server as the pool sees it."""

    url: str
    port: int | None = None        # managed workers only
    handle: object = None          # the launcher's handle (a process), managed only
    state: str = STARTING
    job_id: str | None = None
    since: float = 0.0             # when the current state began
    last_check: float = float("-inf")
    failed_checks: int = 0
    jobs_done: int = 0
    jobs_failed: int = 0
    note: str = ""

    def view(self) -> dict:
        return {"url": self.url, "state": self.state, "job": self.job_id,
                "jobs_done": self.jobs_done, "jobs_failed": self.jobs_failed, "note": self.note}


class SubprocessLauncher:
    """Starts each AI server as its own process: ``python -m uvicorn src.servers.ai_server:app``."""

    def start(self, port: int) -> subprocess.Popen:
        LOGS.mkdir(parents=True, exist_ok=True)
        log = open(LOGS / f"ai_server_{port}.log", "w", encoding="utf-8")  # noqa: SIM115 - lives as long as the process
        cmd = [sys.executable, "-m", "uvicorn", "src.servers.ai_server:app",
               "--host", HOST, "--port", str(port)]
        return subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)

    def alive(self, handle: subprocess.Popen) -> bool:
        return handle.poll() is None

    def stop(self, handle: subprocess.Popen) -> None:
        if handle.poll() is None:
            handle.terminate()
            try:
                handle.wait(timeout=10)
            except subprocess.TimeoutExpired:
                handle.kill()


@dataclass
class AIPool:
    queue: object                          # orchestrator.JobQueue
    urls: list[str] | None = None          # None = managed mode
    launcher: object = None
    client: httpx.Client | None = None
    base_port: int = 8002
    max_workers: int = 2
    min_workers: int = 0
    idle_stop: float = 300.0               # seconds; 0 = never stop an idle AI server
    health_every: float = 5.0
    start_timeout: float = 180.0           # loading the models takes ~10-30 s
    job_timeout: float = 120.0
    max_attempts: int = 2
    max_failed_checks: int = 3
    run_async: bool = True                 # tests set False: a job runs inside tick()
    clock: Callable[[], float] = time.monotonic
    workers: list[Worker] = field(default_factory=list)
    jobs_run: int = 0                      # jobs the AI servers finished (done or failed)

    def __post_init__(self):
        self.managed = self.urls is None
        if self.managed and self.launcher is None:
            self.launcher = SubprocessLauncher()
        if self.client is None:
            self.client = httpx.Client()
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self.stopped = False
        for url in self.urls or []:
            self.workers.append(Worker(url=url.rstrip("/"), since=self.clock()))

    # ------------------------------------------------------------------ public API

    def wake(self) -> None:
        """Called when a job arrives, so it is dispatched at once instead of next tick."""
        self._wake.set()

    def run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001 - the supervisor must keep running
                print(f"ai_pool: tick failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            self._wake.wait(0.5)
            self._wake.clear()

    def tick(self) -> None:
        with self._lock:
            if self.stopped:
                return
            now = self.clock()
            self._check_health(now)
            self._scale(now)
            ready = self._dispatch(now)
        for worker, job in ready:
            if self.run_async:
                threading.Thread(target=self._run_job, args=(worker, job), daemon=True).start()
            else:
                self._run_job(worker, job)

    def status(self) -> dict:
        with self._lock:
            return {"mode": "managed" if self.managed else "external",
                    "jobs_run": self.jobs_run,
                    "workers": [w.view() for w in self.workers]}

    def shutdown(self) -> int:
        """Stop every AI server this pool started (managed mode) and start no new ones.
        Returns how many AI servers were stopped."""
        with self._lock:
            self.stopped = True
            stopped = sum(1 for w in self.workers if self.managed and w.handle is not None)
            for worker in self.workers:
                if self.managed and worker.handle is not None:
                    self.launcher.stop(worker.handle)
                worker.state = DOWN
            if self.managed:
                self.workers.clear()
            return stopped

    # ------------------------------------------------------------------ health

    def _check_health(self, now: float) -> None:
        for worker in list(self.workers):
            if self.managed and not self.launcher.alive(worker.handle):
                self._lose(worker, now, "process stopped")
                continue
            if now - worker.last_check < self.health_every:
                continue
            worker.last_check = now
            healthy = self._healthy(worker)
            if healthy:
                worker.failed_checks = 0
                if worker.state in (STARTING, DOWN):
                    self._set(worker, IDLE, now, "")
            elif worker.state == STARTING:
                if now - worker.since > self.start_timeout:
                    self._lose(worker, now, f"not ready after {self.start_timeout:.0f} s")
            elif worker.state != DOWN:
                worker.failed_checks += 1
                if worker.failed_checks >= self.max_failed_checks:
                    self._lose(worker, now, f"{worker.failed_checks} failed health checks")

    def _healthy(self, worker: Worker) -> bool:
        try:
            response = self.client.get(worker.url + "/health", timeout=2)
            return response.status_code == 200 and response.json().get("ready") is True
        except (httpx.HTTPError, ValueError):
            return False

    def _lose(self, worker: Worker, now: float, why: str) -> None:
        """An AI server failed: give its job back to the queue and, if managed, replace it."""
        if worker.job_id is not None:
            self._give_back(worker.job_id, f"AI server {worker.url} failed: {why}")
            worker.job_id = None
        self._set(worker, DOWN, now, why)
        if self.managed:
            if worker.handle is not None:
                self.launcher.stop(worker.handle)
            self.workers.remove(worker)          # _scale starts a fresh one if needed

    def _give_back(self, job_id: str, why: str) -> None:
        job = self.queue.get(job_id)
        if job is None or job["status"] != "running":
            return
        if job["attempts"] >= self.max_attempts:
            self.queue.finish(job_id, error=f"{why}; gave up after {job['attempts']} attempts")
        else:
            self.queue.requeue(job_id)

    # ------------------------------------------------------------------ scaling

    def _scale(self, now: float) -> None:
        if not self.managed:
            return
        waiting = self.queue.counts()["waiting"]
        live = [w for w in self.workers if w.state != DOWN]
        free = [w for w in live if w.state in (STARTING, IDLE)]

        if (waiting and not free and len(live) < self.max_workers) or len(live) < self.min_workers:
            self._start_worker(now)
            return
        if self.idle_stop and not waiting and len(live) > self.min_workers:
            for worker in live:
                if worker.state == IDLE and now - worker.since >= self.idle_stop:
                    self.launcher.stop(worker.handle)
                    self.workers.remove(worker)
                    break                        # one at a time

    def _start_worker(self, now: float) -> None:
        used = {w.port for w in self.workers}
        port = next(p for p in range(self.base_port, self.base_port + self.max_workers) if p not in used)
        handle = self.launcher.start(port)
        self.workers.append(Worker(url=f"http://{HOST}:{port}", port=port, handle=handle,
                                   since=now, note="started by the orchestrator"))

    # ------------------------------------------------------------------ dispatch

    def _dispatch(self, now: float) -> list[tuple[Worker, dict]]:
        ready = []
        for worker in self.workers:
            if worker.state != IDLE:
                continue
            job = self.queue.take_next(worker=worker.url)
            if job is None:
                break
            worker.job_id = job["id"]
            self._set(worker, BUSY, now, "")
            ready.append((worker, job))
        return ready

    def _run_job(self, worker: Worker, job: dict) -> None:
        """Send one job to one AI server and store what comes back."""
        try:
            response = self.client.post(worker.url + "/run", json=job, timeout=self.job_timeout)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            with self._lock:
                if self._still_assigned(worker, job):
                    self._lose(worker, self.clock(), f"{type(exc).__name__} during a job")
            self.wake()
            return

        with self._lock:
            if not self._still_assigned(worker, job):
                return                           # the job was given to another AI server meanwhile
            if "error" in body:
                self.queue.finish(job["id"], error=str(body["error"]))
                worker.jobs_failed += 1
            else:
                self.queue.finish(job["id"], result=body.get("result"))
                worker.jobs_done += 1
            self.jobs_run += 1
            worker.job_id = None
            self._set(worker, IDLE, self.clock(), "")
        self.wake()

    @staticmethod
    def _still_assigned(worker: Worker, job: dict) -> bool:
        return worker.state == BUSY and worker.job_id == job["id"]

    @staticmethod
    def _set(worker: Worker, state: str, now: float, note: str) -> None:
        worker.state, worker.since, worker.note = state, now, note
