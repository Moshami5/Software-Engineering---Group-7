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
    db.execute(
        "CREATE TABLE IF NOT EXISTS flags ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " flagged_at TEXT NOT NULL,"
        " item_type TEXT NOT NULL,"
        " item TEXT NOT NULL,"
        " course TEXT,"
        " path INTEGER,"
        " job_id TEXT)"
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

FLAG_TYPES = ("skill", "occupation")
FLAGGED_MESSAGE = "flagged for review"
FLAG_TYPE_ERROR = "Type must be 'skill' or 'occupation'"
FLAG_ITEM_ERROR = "Please name the skill or occupation you think is wrong"
FLAG_WHERE_ERROR = "Please say which course or path it was shown for"


def check_flag(payload):
    """FR-17: the flagged item and where it was shown. Returns (flag, "") or (None, error)."""
    item_type = payload.get("type")
    if item_type not in FLAG_TYPES:
        return None, FLAG_TYPE_ERROR

    item = payload.get("item")
    if not isinstance(item, str) or not item.strip():
        return None, FLAG_ITEM_ERROR

    course = payload.get("course")
    path = payload.get("path")
    if not isinstance(course, str) or not course.strip():
        course = None
    if not isinstance(path, int) or isinstance(path, bool) or path < 1:
        path = None
    if course is None and path is None:
        return None, FLAG_WHERE_ERROR

    job_id = payload.get("job_id")
    return {
        "item_type": item_type,
        "item": item.strip(),
        "course": course.strip() if course else None,
        "path": path,
        "job_id": str(job_id) if job_id is not None else None,
    }, ""


def store_flag(flag):
    """Save one flag with a timestamp; returns its id. No personal data (NFR-8)."""
    now = datetime.now(timezone.utc).isoformat()
    cur = db.execute(
        "INSERT INTO flags (flagged_at, item_type, item, course, path, job_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (now, flag["item_type"], flag["item"], flag["course"], flag["path"], flag["job_id"]),
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

    set_job(row, job_id, "waiting")
    return {"id": job_id, "status": "waiting"}


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


@app.post("/flags", status_code=201)
def post_flag(payload: dict = Body(...)):
    flag, error = check_flag(payload)
    if flag is None:
        return JSONResponse(status_code=422, content={"error": error})

    flag_id = store_flag(flag)
    return {"id": flag_id, "message": FLAGGED_MESSAGE}