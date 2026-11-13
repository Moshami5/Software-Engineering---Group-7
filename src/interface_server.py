"""Interface server (Task 6): the server students talk to. Port 8000."""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse

from src.interest import validate_interest
from src.study_context import validate_study_context

app = FastAPI(title="Study-path advisor: interface server")

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "processed" / "interface_requests.sqlite"


def open_db(path=DB_PATH):
    """Open (or create) the database and make sure the table exists."""
    db = sqlite3.connect(path, check_same_thread=False)
    db.execute(
        "CREATE TABLE IF NOT EXISTS requests ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " received_at TEXT NOT NULL,"
        " request_json TEXT NOT NULL,"
        " job_id TEXT,"
        " status TEXT NOT NULL)"
    )
    db.commit()
    return db


db = open_db()


def store_request(request):
    """Save one checked request; returns its row id."""
    now = datetime.now(timezone.utc).isoformat()
    cur = db.execute(
        "INSERT INTO requests (received_at, request_json, status) VALUES (?, ?, ?)",
        (now, json.dumps(request), "received"),
    )
    db.commit()
    return cur.lastrowid


ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://localhost:8001")
DOWN_MESSAGE = "The advice service is not available right now, please try again later"
UNKNOWN_ID_MESSAGE = "No advice request with this id"


def create_job(request):
    """POST /jobs at the orchestrator; returns the new job id."""
    response = httpx.post(f"{ORCHESTRATOR_URL}/jobs", json={"request": request}, timeout=5)
    response.raise_for_status()
    return str(response.json()["id"])


def get_job(job_id):
    """GET /jobs/{id} at the orchestrator; returns the job, or None if unknown."""
    response = httpx.get(f"{ORCHESTRATOR_URL}/jobs/{job_id}", timeout=5)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def set_job(row, job_id, status):
    """Write the job id and status into the stored request."""
    db.execute("UPDATE requests SET job_id = ?, status = ? WHERE id = ?",
               (job_id, status, row))
    db.commit()


def update_status(job_id, status):
    """Keep the stored request's status up to date."""
    db.execute("UPDATE requests SET status = ? WHERE job_id = ?", (status, job_id))
    db.commit()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/advice", status_code=202)
def post_advice(payload: dict = Body(...)):
    interest = validate_interest(payload.get("interest"))
    if not interest.ok:
        return JSONResponse(status_code=422, content={"error": interest.error})

    context = validate_study_context(
        language=payload.get("language"),
        hours_per_week=payload.get("hours_per_week"),
        weeks_available=payload.get("weeks_available"),
        completed_courses=payload.get("completed_courses"),
    )
    if not context.ok:
        return JSONResponse(status_code=422, content={"error": context.error})

    ctx = context.value
    request = {
        "interest": interest.value,
        "language": ctx.language,
        "hours_per_week": ctx.hours_per_week,
        "weeks_available": ctx.weeks_available,
        "completed_courses": list(ctx.completed_courses),
    }

    row = store_request(request)
    try:
        job_id = create_job(request)
    except (httpx.HTTPError, KeyError, ValueError):
        set_job(row, None, "not sent")
        return JSONResponse(status_code=503, content={"error": DOWN_MESSAGE})

    set_job(row, job_id, "queued")
    return {"id": job_id, "status": "queued"}


@app.get("/advice/{job_id}")
def get_advice(job_id: str):
    try:
        job = get_job(job_id)
    except (httpx.HTTPError, ValueError):
        return JSONResponse(status_code=503, content={"error": DOWN_MESSAGE})
    if job is None:
        return JSONResponse(status_code=404, content={"error": UNKNOWN_ID_MESSAGE})

    status = job.get("status", "unknown")
    update_status(job_id, status)

    answer = {"id": job_id, "status": status}
    if status == "done":
        answer["result"] = job.get("result")
    elif status == "failed":
        answer["error"] = job.get("error")
    return answer