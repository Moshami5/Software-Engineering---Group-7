"""Task 6 orchestrator: the job queue between the interface server and the AI server.

The interface server adds a job for each valid student request and later asks for its
status. The AI server takes the oldest waiting job, runs the advisor and sends the
result back. The two never talk to each other: everything goes through this queue
(Task 6 rubric, Interfacing). The queue is a SQLite table (decided 9 Nov: no Redis,
no Docker), so jobs survive a restart of this server.

Job life cycle:  waiting -> running -> done | failed

Endpoints (agreed API, see tasks/task6/README.md):
    POST /jobs               body {"request": {...}}           -> 201 {"id", "status": "waiting"}
    GET  /jobs/next          oldest waiting job, now running   -> 200 {"id", "request"}  or  204
    POST /jobs/{id}/result   body {"result": {...}} -> done,  or  {"error": "..."} -> failed
    GET  /jobs/{id}          -> {"id", "status", "result", "error", timestamps}
    GET  /health             -> number of jobs per status

Run (from the repo root):
    python -m uvicorn src.servers.orchestrator:app --port 8001
Settings (environment variables):
    ORCHESTRATOR_DB   SQLite file, default runtime/orchestrator.sqlite3
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Response

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
    created_at  TEXT    NOT NULL,
    started_at  TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS jobs_waiting ON jobs (status, seq);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobQueue:
    """The job table. Each call opens its own connection, so it is safe across threads
    and across several orchestrator processes sharing one file."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        # isolation_level=None: we open transactions ourselves with BEGIN IMMEDIATE.
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, request: dict) -> str:
        job_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO jobs (id, status, request, created_at) VALUES (?, 'waiting', ?, ?)",
                (job_id, json.dumps(request), _now()),
            )
        return job_id

    def take_next(self) -> dict | None:
        """Give out the oldest waiting job and mark it running, or None if none waits.

        BEGIN IMMEDIATE takes the write lock before reading, so two AI servers asking
        at the same moment can never get the same job.
        """
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id, request FROM jobs WHERE status = 'waiting' ORDER BY seq LIMIT 1"
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            conn.execute(
                "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?",
                (_now(), row["id"]),
            )
            conn.execute("COMMIT")
            return {"id": row["id"], "request": json.loads(row["request"])}
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def finish(self, job_id: str, result: Any = None, error: str | None = None) -> str:
        """Store the outcome of a running job. Returns the new status.

        Raises KeyError for an unknown job and ValueError if the job is not running
        (a result for a job that is waiting, or already finished, is refused).
        """
        status = "failed" if error is not None else "done"
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] != "running":
                raise ValueError(f"job {job_id} is {row['status']}, not running")
            conn.execute(
                "UPDATE jobs SET status = ?, result = ?, error = ?, finished_at = ? WHERE id = ?",
                (status, None if error is not None else json.dumps(result), error, _now(), job_id),
            )
            conn.execute("COMMIT")
            return status
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

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
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }

    def counts(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").fetchall()
        found = {r["status"]: r["n"] for r in rows}
        return {s: found.get(s, 0) for s in STATUSES}


def create_app(db_path: str | Path | None = None) -> FastAPI:
    queue = JobQueue(db_path or os.environ.get("ORCHESTRATOR_DB", DEFAULT_DB))
    app = FastAPI(title="Study-path advisor: orchestrator")
    app.state.queue = queue

    @app.post("/jobs", status_code=201)
    def add_job(body: dict = Body(...)) -> dict:
        request = body.get("request")
        if not isinstance(request, dict):
            raise HTTPException(422, 'body must be {"request": {...}}')
        return {"id": queue.add(request), "status": "waiting"}

    @app.get("/jobs/next")
    def next_job():
        job = queue.take_next()
        return job if job is not None else Response(status_code=204)

    @app.post("/jobs/{job_id}/result")
    def job_result(job_id: str, body: dict = Body(...)) -> dict:
        has_result, has_error = "result" in body, "error" in body
        if has_result == has_error:
            raise HTTPException(422, 'body must be {"result": {...}} or {"error": "..."}')
        try:
            if has_error:
                status = queue.finish(job_id, error=str(body["error"]))
            else:
                status = queue.finish(job_id, result=body["result"])
        except KeyError:
            raise HTTPException(404, f"no job {job_id}") from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {"id": job_id, "status": status}

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        job = queue.get(job_id)
        if job is None:
            raise HTTPException(404, f"no job {job_id}")
        return job

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "db": str(queue.path), "jobs": queue.counts()}

    return app


app = create_app()
