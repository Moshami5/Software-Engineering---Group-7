"""Task 6 AI server: runs the advisor when the orchestrator sends it a job.

The AI server never receives student requests directly and never asks for work: the
orchestrator decides when to call it (POST /run), checks its health (GET /health), and
starts, restarts or stops it. Between jobs it does nothing. The interface server only
talks to the orchestrator.

Endpoints:
    POST /run      body {"id": "<job id>", "request": {...}}
                   -> 200 {"id", "result": {...}}   advise() answered
                   -> 200 {"id", "error": "..."}    advise() crashed: the job failed, the server is fine
                   -> 409 when already running a job (the orchestrator sends one at a time)
    GET  /health   ready?, busy?, models loaded?, jobs done/failed

Run (from the repo root; normally the orchestrator starts it):
    python -m uvicorn src.servers.ai_server:app --port 8002
Settings (environment variables):
    AI_PRELOAD     "0" skips loading the models at start-up (tests only)
"""
from __future__ import annotations

import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.advisor import advise  # noqa: E402

PRELOAD = os.environ.get("AI_PRELOAD", "1") != "0"

stats = {"models_loaded": False, "jobs_done": 0, "jobs_failed": 0}
run_advisor = advise                       # tests swap in a fake advisor here
_busy = threading.Lock()


def preload_models() -> None:
    """Load both models, the indices and the catalogue once, so the first job is fast."""
    from src.explain import load_explain_data
    from src.feasibility import load_facts
    from src.model_skills import load_encoder
    from src.occupations import load_occupation_index, load_relations
    from src.paths import load_durations
    from src.retrieval import load_catalogue

    load_encoder()
    load_occupation_index()
    load_relations()
    load_catalogue()
    load_facts()
    load_durations()
    load_explain_data()  # FR-8 to FR-11: course evidence and occupation skills
    stats["models_loaded"] = True


def run_job(job_id: str, request: dict) -> dict:
    """Run the advisor on one request. A crash becomes {"error"}, so the job is marked
    failed instead of the orchestrator taking this server for broken."""
    try:
        body = {"id": job_id, "result": run_advisor(request)}
        stats["jobs_done"] += 1
    except Exception as exc:  # noqa: BLE001 - any advisor failure must reach the orchestrator
        body = {"id": job_id, "error": f"{type(exc).__name__}: {exc}"}
        stats["jobs_failed"] += 1
    return body


@asynccontextmanager
async def lifespan(app: FastAPI):
    if PRELOAD:
        preload_models()          # the server answers only once this is done
    yield


app = FastAPI(title="Study-path advisor: AI server", lifespan=lifespan)


@app.post("/run")
def run(body: dict = Body(...)):
    job_id, request = body.get("id"), body.get("request")
    if not isinstance(job_id, str) or not isinstance(request, dict):
        return JSONResponse(status_code=422, content={"error": 'body must be {"id": "...", "request": {...}}'})
    if not _busy.acquire(blocking=False):
        return JSONResponse(status_code=409, content={"error": "already running a job"})
    try:
        return run_job(job_id, request)
    finally:
        _busy.release()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "ready": stats["models_loaded"] or not PRELOAD,
            "busy": _busy.locked(), **stats}
