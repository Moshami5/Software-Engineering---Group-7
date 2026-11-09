"""Task 6 AI server: runs the advisor for jobs it takes from the orchestrator.

The AI server never receives student requests directly. A worker loop asks the
orchestrator for the next job, runs ``advise()`` (FR-1 -> FR-7) on its request and
sends the result back. The interface server only talks to the orchestrator.

Orchestrator API this server relies on (proposal in the Task 6 shared doc, to be
confirmed by the group; change only ``take_job`` and ``send_result`` if it moves):

    GET  /jobs/next          200 {"id": "<job id>", "request": {...}}  or  204 when empty
    POST /jobs/{id}/result   body {"result": {...}}  or  {"error": "<message>"}

Endpoints of this server:
    GET /health   models loaded?, jobs done/failed, orchestrator URL

Run (from the repo root):
    python -m uvicorn src.servers.ai_server:app --port 8002
Settings (environment variables):
    ORCHESTRATOR_URL   default http://localhost:8001
    AI_POLL_SECONDS    wait between polls when the queue is empty, default 0.5
    AI_PRELOAD         "0" skips loading the models at start-up (tests only)
"""
from __future__ import annotations

import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.advisor import advise  # noqa: E402

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://localhost:8001")
POLL_SECONDS = float(os.environ.get("AI_POLL_SECONDS", "0.5"))
PRELOAD = os.environ.get("AI_PRELOAD", "1") != "0"

stats = {"models_loaded": False, "jobs_done": 0, "jobs_failed": 0}


def preload_models() -> None:
    """Load both models, the indices and the catalogue once, so the first job is fast."""
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
    stats["models_loaded"] = True


def take_job(client: httpx.Client) -> dict | None:
    """The next waiting job from the orchestrator, or None when the queue is empty."""
    response = client.get("/jobs/next")
    if response.status_code == 204:
        return None
    response.raise_for_status()
    return response.json()


def send_result(client: httpx.Client, job_id: str, body: dict) -> None:
    client.post(f"/jobs/{job_id}/result", json=body).raise_for_status()


def process_one(client: httpx.Client, run=advise) -> bool:
    """Take one job, run the advisor on it and send the result back.

    Returns False when there was no job. A crash inside the advisor is sent back as
    {"error": ...} so the job is marked failed instead of hanging in the queue.
    """
    job = take_job(client)
    if job is None:
        return False
    try:
        body = {"result": run(job["request"])}
        stats["jobs_done"] += 1
    except Exception as exc:  # noqa: BLE001 - any failure must reach the orchestrator
        body = {"error": f"{type(exc).__name__}: {exc}"}
        stats["jobs_failed"] += 1
    send_result(client, job["id"], body)
    return True


def work(stop: threading.Event, client: httpx.Client) -> None:
    """Worker loop: keep taking jobs until stopped; wait a little when the queue is empty."""
    while not stop.is_set():
        try:
            if not process_one(client):
                stop.wait(POLL_SECONDS)
        except httpx.HTTPError:
            stop.wait(POLL_SECONDS * 4)  # orchestrator not reachable yet: try again later


@asynccontextmanager
async def lifespan(app: FastAPI):
    if PRELOAD:
        preload_models()
    stop = threading.Event()
    client = httpx.Client(base_url=ORCHESTRATOR_URL, timeout=10)
    worker = threading.Thread(target=work, args=(stop, client), daemon=True)
    worker.start()
    yield
    stop.set()
    worker.join(timeout=5)
    client.close()


app = FastAPI(title="Study-path advisor: AI server", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "orchestrator": ORCHESTRATOR_URL, **stats}
