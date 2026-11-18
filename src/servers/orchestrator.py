"""Task 6 orchestrator: the only point between the interface server and the AI servers.

The interface server adds a job for each valid student request and later asks for its
status. The orchestrator then DECIDES when and where the job runs: its AI pool
(``src/servers/ai_pool.py``) pushes the job to a free, healthy AI server, checks every AI
server's health, puts the job back in the queue if its AI server fails, starts AI servers
when jobs wait and stops them when they sit idle. The interface and the AI servers never
talk to each other, and the AI servers never ask for work (Task 6 feedback, 17 Nov).

Jobs live in a SQLite table, so they survive a restart; jobs that were running when the
orchestrator stopped go back to waiting when it starts again.

Job life cycle:  waiting -> running -> done | failed   (running -> waiting if its AI server fails)

Endpoints (agreed API, see tasks/task6/README.md):
    POST /jobs        body {"request": {...}}   -> 201 {"id", "status": "waiting"}
    GET  /jobs/{id}   -> {"id", "status", "result", "error", "attempts", "worker", timestamps}
    GET  /health      -> jobs per status, jobs run, and every AI server with its state
    POST /ai/shutdown -> stop the AI servers it started (used when stopping the system)

Run (from the repo root):
    python -m uvicorn src.servers.orchestrator:app --port 8001
Settings (environment variables):
    ORCHESTRATOR_DB        SQLite file, default runtime/orchestrator.sqlite3
    AI_SERVERS             comma-separated URLs of AI servers run elsewhere (external
                           mode); unset = the orchestrator starts its own (managed mode)
    AI_BASE_PORT           first port for AI servers it starts, default 8002
    AI_MAX_WORKERS         most AI servers at once, default 2
    AI_MIN_WORKERS         AI servers kept running even with no jobs, default 0
    AI_IDLE_STOP_SECONDS   stop an AI server idle this long, default 300 (0 = never)
    AI_JOB_TIMEOUT         seconds one job may take, default 120
    JOB_MAX_ATTEMPTS       tries per job before it is marked failed, default 2
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException

from src.servers.ai_pool import AIPool

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "runtime" / "orchestrator.sqlite3"
STATUSES = ("waiting", "running", "done", "failed")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,  -- arrival order (oldest first)
    id          TEXT    NOT NULL UNIQUE,
    status      TEXT    NOT NULL,
    request     TEXT    NOT NULL,                   -- JSON
    result      TEXT,                               -- JSON, when done
    error       TEXT,                               -- message, when failed
    attempts    INTEGER NOT NULL DEFAULT 0,         -- times given to an AI server
    worker      TEXT,                               -- AI server running it, or that ran it
    created_at  TEXT    NOT NULL,
    started_at  TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS jobs_waiting ON jobs (status, seq);
"""
ADDED_COLUMNS = {"attempts": "INTEGER NOT NULL DEFAULT 0", "worker": "TEXT"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobQueue:
    """The job table. Each call opens its own connection, and every change is one
    ``BEGIN IMMEDIATE`` transaction, so two writers can never change a job at once."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            have = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
            for column, kind in ADDED_COLUMNS.items():   # a queue file from the first version
                if column not in have:
                    conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {kind}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _write(self, change):
        """Run ``change(conn)`` inside one write transaction and return its result."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            value = change(conn)
            conn.execute("COMMIT")
            return value
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def add(self, request: dict) -> str:
        job_id = uuid.uuid4().hex
        self._write(lambda conn: conn.execute(
            "INSERT INTO jobs (id, status, request, created_at) VALUES (?, 'waiting', ?, ?)",
            (job_id, json.dumps(request), _now())))
        return job_id

    def take_next(self, worker: str | None = None) -> dict | None:
        """Mark the oldest waiting job running on ``worker`` and return it, or None.

        The read and the update are one transaction, so a job is never given out twice.
        """
        def take(conn):
            row = conn.execute(
                "SELECT id, request FROM jobs WHERE status = 'waiting' ORDER BY seq LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE jobs SET status = 'running', started_at = ?, worker = ?, "
                "attempts = attempts + 1 WHERE id = ?", (_now(), worker, row["id"]))
            return {"id": row["id"], "request": json.loads(row["request"])}
        return self._write(take)

    def requeue(self, job_id: str) -> bool:
        """Put a running job back to waiting (its AI server failed). False if not running."""
        return self._write(lambda conn: conn.execute(
            "UPDATE jobs SET status = 'waiting', started_at = NULL, worker = NULL "
            "WHERE id = ? AND status = 'running'", (job_id,)).rowcount == 1)

    def recover_running(self) -> int:
        """At start-up: jobs left running by a stopped orchestrator go back to waiting."""
        return self._write(lambda conn: conn.execute(
            "UPDATE jobs SET status = 'waiting', started_at = NULL, worker = NULL "
            "WHERE status = 'running'").rowcount)

    def finish(self, job_id: str, result=None, error: str | None = None) -> str:
        """Store the outcome of a running job. Returns the new status.

        Raises KeyError for an unknown job and ValueError if the job is not running,
        so a late result can never overwrite a finished job.
        """
        status = "failed" if error is not None else "done"

        def store(conn):
            row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] != "running":
                raise ValueError(f"job {job_id} is {row['status']}, not running")
            conn.execute(
                "UPDATE jobs SET status = ?, result = ?, error = ?, finished_at = ? WHERE id = ?",
                (status, None if error is not None else json.dumps(result), error, _now(), job_id))
            return status
        return self._write(store)

    def get(self, job_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "status": row["status"],
            "result": json.loads(row["result"]) if row["result"] is not None else None,
            "error": row["error"],
            "attempts": row["attempts"],
            "worker": row["worker"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }

    def counts(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").fetchall()
        found = {r["status"]: r["n"] for r in rows}
        return {s: found.get(s, 0) for s in STATUSES}


def pool_from_env(queue: JobQueue) -> AIPool:
    env = os.environ.get
    urls = [u.strip() for u in env("AI_SERVERS", "").split(",") if u.strip()] or None
    return AIPool(
        queue,
        urls=urls,
        base_port=int(env("AI_BASE_PORT", "8002")),
        max_workers=int(env("AI_MAX_WORKERS", "2")),
        min_workers=int(env("AI_MIN_WORKERS", "0")),
        idle_stop=float(env("AI_IDLE_STOP_SECONDS", "300")),
        job_timeout=float(env("AI_JOB_TIMEOUT", "120")),
        max_attempts=int(env("JOB_MAX_ATTEMPTS", "2")),
    )


def create_app(db_path: str | Path | None = None, pool: AIPool | None = None) -> FastAPI:
    queue = JobQueue(db_path or os.environ.get("ORCHESTRATOR_DB", DEFAULT_DB))
    queue.recover_running()
    pool = pool or pool_from_env(queue)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop = threading.Event()
        supervisor = threading.Thread(target=pool.run, args=(stop,), daemon=True)
        supervisor.start()
        yield
        stop.set()
        pool.wake()
        supervisor.join(timeout=5)
        pool.shutdown()                          # stop the AI servers this orchestrator started

    app = FastAPI(title="Study-path advisor: orchestrator", lifespan=lifespan)
    app.state.queue, app.state.pool = queue, pool

    @app.post("/jobs", status_code=201)
    def add_job(body: dict = Body(...)) -> dict:
        request = body.get("request")
        if not isinstance(request, dict):
            raise HTTPException(422, 'body must be {"request": {...}}')
        job_id = queue.add(request)
        pool.wake()                              # dispatch now, not at the next tick
        return {"id": job_id, "status": "waiting"}

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        job = queue.get(job_id)
        if job is None:
            raise HTTPException(404, f"no job {job_id}")
        return job

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "db": str(queue.path), "jobs": queue.counts(), **pool.status()}

    @app.post("/ai/shutdown")
    def ai_shutdown() -> dict:
        """Stop the AI servers this orchestrator started and start no new ones. Used by
        scripts/run_servers.py before it stops the orchestrator (on Windows a stopped
        process gets no chance to clean up after itself)."""
        return {"stopped": pool.shutdown()}

    return app


app = create_app()
