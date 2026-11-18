# Task 6 — Scaling (up) the system

**Due:** Fri 13 Nov 2026, 18:00 · **Points:** 3 · **Status:** submitted 13 Nov; after the
lecturer's feedback (17 Nov) the middle server was turned from a passive job queue into a
real orchestrator (see below). Report: [`Task6_Group7_Report_v2.pdf`](Task6_Group7_Report_v2.pdf)
(current); [`Task6_Group7_Report.pdf`](Task6_Group7_Report.pdf) is v1 as submitted.

| Card | Owner(s) | PR |
|---|---|---|
| `advise()` + AI server (port 8002) | Mohamed | #29, #31 |
| Orchestrator (port 8001) + agreed API | Musaed (API with Melat, Mohamed) | #32 |
| Interface server (port 8000) | Melat | #36 |
| CI dependencies | Alexia, Raluca | #33, #34 |
| Start script + end-to-end check | Bilgin | #35 |
| Fixes from the end-to-end run, one-page report | Musaed | #37 |
| Integration test across the three servers | Musaed | #41 |
| Real orchestrator after the feedback (push, health, restart, scale) | Musaed, building on Mohamed's AI server and Bilgin's start script | this branch |

## What was asked

Turn the components into a distributed system with at least:

- an **interface server** that handles user requests, checks for errors and stores data —
  it must **not** call the AI component directly;
- one or more **AI servers** hosting the models;
- one or more **orchestrator** servers between them (e.g. a queue such as RabbitMQ, or a
  database).

The servers may run on one machine as separate logical servers, locally or in the cloud
(tell the lecturer if using the cloud). Preliminary report: 1 page.

## Rubric

| Criterion | Points | Full marks when |
|---|---:|---|
| Distribution | 1.5 | each component is hosted on a different server |
| Interfacing | 1.5 | components communicate through a central point, peer-to-peer, or APIs — not interface → AI directly |

## Architecture

```
student ──HTTP──▶ interface :8000 ──HTTP──▶ orchestrator :8001 ──HTTP──▶ AI server :8002 (, :8003)
                  (validate, store)          (job queue + AI pool)        (models, advise())
                                             starts / checks / restarts / stops the AI servers
```

Three FastAPI servers, each its own process and port. The interface and the AI servers
never talk to each other: the orchestrator is the central point between them, and it
**decides** when and where each job runs. Its AI pool (`src/servers/ai_pool.py`):

| Decision | What the orchestrator does |
|---|---|
| Dispatch | sends the oldest waiting job to a free, healthy AI server: `POST {ai}/run` |
| Health | checks every AI server every 5 s: `GET {ai}/health` (and whether its process is alive) |
| Recover | an AI server that crashes or stops answering is removed; its job goes back to waiting and runs on another one (at most 2 attempts, then the job is marked failed) |
| Scale | starts an AI server when jobs wait and none is free (at most 2), stops one that has been idle for 5 min |

With no jobs, no AI server runs. Two modes: **managed** (default, the orchestrator starts
and stops AI server processes itself) and **external** (`AI_SERVERS` lists AI servers run
elsewhere, e.g. on other machines; the orchestrator checks and uses them but cannot start them).

## Feedback (17 Nov) and what changed

The lecturer noted that the first version's middle server was a job queue, not an
orchestrator: both servers called it, and the AI server polled `GET /jobs/next` every 0.5 s.

| Question | First version | Now |
|---|---|---|
| Is it an orchestrator? | No: a passive queue | Yes: it pushes jobs and manages the AI servers |
| Is it ok to keep the AI server idle? | It ran all day, polling every 0.5 s | No AI server runs without jobs; an idle one is stopped after 5 min |
| If the AI server goes down, who starts a new one? | Nobody | The orchestrator notices (health check) and starts a new one; the job is retried |
| Can two servers change one database entry at once? | No | Still no: the interface has its own database; the orchestrator is the only writer of the queue, every change is one `BEGIN IMMEDIATE` transaction, a job is given out once (tested with 8 parallel takers), and a late result for a job that is no longer running is ignored |

## Agreed API

Card "Agree the API" (owners: Musaed, Melat, Mohamed). Request and result JSON are exactly
what `advise()` in `src/advisor.py` takes and returns, passed through unchanged.

### Interface server — port 8000 (Melat) · `src/interface_server.py`

| Endpoint | Body | Response |
|---|---|---|
| `POST /advice` | the student request (below) | `202 {"id", "status": "waiting"}`; bad input → `422 {"error"}`, no job; orchestrator down → `503 {"error"}` |
| `GET /advice/{id}` | — | `{"id", "status"}` from the orchestrator, plus `"result"` when done or `"error"` when failed; `404` if unknown |

Every checked request is also stored in the interface's own SQLite database
(`data/processed/interface_requests.sqlite`, not committed).

### Orchestrator — port 8001 (Musaed) · `src/servers/orchestrator.py`

| Endpoint | Body | Response |
|---|---|---|
| `POST /jobs` | `{"request": {...}}` | `201 {"id", "status": "waiting"}`; the job is dispatched at once |
| `GET /jobs/{id}` | — | `{"id", "status", "result", "error", "attempts", "worker", "created_at", "started_at", "finished_at"}` |
| `GET /health` | — | `{"status": "ok", "jobs": {"waiting", "running", "done", "failed"}, "mode", "jobs_run", "workers": [{"url", "state", "job", ...}]}` |
| `POST /ai/shutdown` | — | stops the AI servers it started (used by the start script) |

Job life cycle: `waiting → running → done | failed`, and `running → waiting` when its AI
server fails. Jobs survive an orchestrator restart; jobs that were running go back to waiting.
Code: `src/servers/orchestrator.py` (queue, API) and `src/servers/ai_pool.py` (decisions).

### AI server — port 8002 (Mohamed) · `src/servers/ai_server.py`

Started by the orchestrator. Loads both models and the catalogue once at start-up, then
does nothing until the orchestrator sends a job. No endpoints for students.

| Endpoint | Body | Response |
|---|---|---|
| `POST /run` | `{"id", "request": {...}}` | `200 {"id", "result": {...}}`; an advisor crash → `200 {"id", "error": "<Type>: <message>"}` (the job failed, the server is fine); `409` if already running a job |
| `GET /health` | — | `{"ready", "busy", "models_loaded", "jobs_done", "jobs_failed"}` |

### Request and result JSON

```json
{"interest": "software developer", "language": "English",
 "hours_per_week": 6, "weeks_available": 20, "completed_courses": []}
```

Only `interest` is required. The result is `{"ok": true, "context", "occupations",
"required_skills", "paths", "removed", "left_out_no_duration", "message"}`, or
`{"ok": false, "error"}` for input `advise()` rejects. Each path is
`{"fit", "weeks", "courses": [{"course_key", "title", "category", "skills"}], "covered_skills"}`.

## Running it

From the repo root, in the CSAI environment (fastapi, uvicorn and httpx are in
`environment.yml`). Ports 8000–8002 must be free.

**Everything with one command** (Ctrl+C stops it all). The script starts the orchestrator
and the interface; the orchestrator starts the AI server when the first job arrives:

```bash
python scripts/run_servers.py
```

**End-to-end check** (starts the servers, sends requests like a student, stops them; exit
code 0 when it passes; the first job waits ~20 s while the AI server loads the models):

```bash
python scripts/run_servers.py --check
#   ok  invalid input rejected by the interface (422), no job created
#   ok  request accepted: http://127.0.0.1:8000/advice/<id>
#   ok  5 study paths returned, computed by an AI server the orchestrator started and sent the job to
# PASSED
```

**Or by hand**, in two terminals (the orchestrator starts the AI server itself):

```bash
python -m uvicorn src.servers.orchestrator:app --port 8001
python -m uvicorn src.interface_server:app    --port 8000
```

Then, as a student:

```bash
curl -X POST localhost:8000/advice -H "content-type: application/json" \
     -d '{"interest": "software developer", "weeks_available": 20}'
curl localhost:8000/advice/<id>        # status "done" with 3-5 paths in "result"
curl localhost:8001/health             # the AI servers the orchestrator is running
```

Checked live on 18 Nov: with no jobs no AI server runs; the first job starts one; after
killing it by hand, the next job made the orchestrator start a new one and the job
finished; with no jobs for the idle time, the AI server was stopped.

Settings (orchestrator): `ORCHESTRATOR_DB` (SQLite file, default
`runtime/orchestrator.sqlite3`, not committed), `AI_SERVERS` (external mode), `AI_BASE_PORT`
(8002), `AI_MAX_WORKERS` (2), `AI_MIN_WORKERS` (0), `AI_IDLE_STOP_SECONDS` (300),
`AI_JOB_TIMEOUT` (120), `JOB_MAX_ATTEMPTS` (2). Interface: `ORCHESTRATOR_URL`.

## Tests

| File | What |
|---|---|
| `tests/test_orchestrator.py` | queue and API, plus every orchestrator decision (start, dispatch, crash and retry, give up, idle stop, scale to 2, external mode, shutdown) with fake AI servers and a fake clock |
| `tests/test_ai_server.py` | `POST /run`, advisor crash, one job at a time, health |
| `tests/test_interface_server.py` | the interface on its own |
| `tests/test_servers_integration.py` | the real interface, orchestrator and AI server together, in memory |
| `tests/test_run_servers.py` | the start script's end-to-end check |

## Files

| File | What |
|---|---|
| [`Task6_Group7_Report_v2.pdf`](Task6_Group7_Report_v2.pdf) | **current**: revised 18 Nov after the lecturer's feedback (real orchestrator) — use this one for the Task 7 final report |
| [`Task6_Group7_Report.pdf`](Task6_Group7_Report.pdf) | v1, the one-page preliminary report as submitted on 13 Nov |
