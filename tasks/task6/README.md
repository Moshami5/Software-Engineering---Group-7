# Task 6 — Scaling (up) the system

**Due:** Fri 13 Nov 2026, 18:00 · **Points:** 3 · **Status:** done — all three servers
and the start script are on `main` (PRs #29, #31, #32, #33–#37); 221 tests pass and the
end-to-end check passes. Report: [`Task6_Group7_Report.pdf`](Task6_Group7_Report.pdf).

| Card | Owner(s) | PR |
|---|---|---|
| `advise()` + AI server (port 8002) | Mohamed | #29, #31 |
| Orchestrator (port 8001) + agreed API | Musaed (API with Melat, Mohamed) | #32 |
| Interface server (port 8000) | Melat | #36 |
| CI dependencies | Alexia, Raluca | #33, #34 |
| Start script + end-to-end check | Bilgin | #35 |
| Fixes from the end-to-end run, one-page report | Musaed | #37 |

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
student ──HTTP──▶ interface :8000 ──HTTP──▶ orchestrator :8001 ◀──HTTP── AI server :8002
                  (validate, store)          (SQLite job queue)          (models, advise())
```

Three FastAPI servers, each its own process and port. The interface and the AI server
never talk to each other: the orchestrator is the central point between them. The AI
server *pulls* work (`GET /jobs/next`), so more AI servers can be started against the same
orchestrator and each job still goes to exactly one of them.

## Agreed API

Card "Agree the API" (owners: Musaed, Melat, Mohamed). Request and result JSON are exactly
what `advise()` in `src/advisor.py` takes and returns, passed through unchanged.

### Interface server — port 8000 (Melat) · `src/interface_server.py`

| Endpoint | Body | Response |
|---|---|---|
| `POST /advice` | the student request (below) | `202 {"id", "status": "queued"}`; bad input → `422 {"error"}`, no job; orchestrator down → `503 {"error"}` |
| `GET /advice/{id}` | — | `{"id", "status"}` from the orchestrator, plus `"result"` when done or `"error"` when failed; `404` if unknown |

Every checked request is also stored in the interface's own SQLite database
(`data/processed/interface_requests.sqlite`, not committed).

### Orchestrator — port 8001 (Musaed) · `src/servers/orchestrator.py`

| Endpoint | Body | Response |
|---|---|---|
| `POST /jobs` | `{"request": {...}}` | `201 {"id", "status": "waiting"}` |
| `GET /jobs/next` | — | `200 {"id", "request"}`, job now `running`; `204` when nothing waits |
| `POST /jobs/{id}/result` | `{"result": {...}}` or `{"error": "..."}` | `200 {"id", "status": "done" \| "failed"}`; `404` unknown; `409` if the job is not running |
| `GET /jobs/{id}` | — | `{"id", "status", "result", "error", "created_at", "started_at", "finished_at"}` |
| `GET /health` | — | `{"status": "ok", "jobs": {"waiting", "running", "done", "failed"}}` |

Job life cycle: `waiting → running → done | failed`. A job is given out once only (the take
is one SQLite `BEGIN IMMEDIATE` transaction) and jobs survive an orchestrator restart.

### AI server — port 8002 (Mohamed) · `src/servers/ai_server.py`

No endpoints for students. A worker loop calls `GET /jobs/next`, runs `advise(request)` and
posts `{"result": ...}`; a crash is posted as `{"error": "<Type>: <message>"}`.
`GET /health` shows whether the models are loaded and jobs done/failed.

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

**All three servers with one command** (Ctrl+C stops them):

```bash
python scripts/run_servers.py
```

**End-to-end check** (starts the servers, sends requests like a student, stops them; exit
code 0 when it passes):

```bash
python scripts/run_servers.py --check
#   ok  invalid input rejected by the interface (422), no job created
#   ok  request accepted: http://127.0.0.1:8000/advice/<id>
#   ok  5 study paths returned, computed by the AI server
# PASSED
```

**Or each server by hand**, in three terminals:

```bash
python -m uvicorn src.servers.orchestrator:app --port 8001
python -m uvicorn src.servers.ai_server:app   --port 8002   # loads the models first
python -m uvicorn src.interface_server:app    --port 8000
```

Then, as a student:

```bash
curl -X POST localhost:8000/advice -H "content-type: application/json" \
     -d '{"interest": "software developer", "weeks_available": 20}'
curl localhost:8000/advice/<id>        # status "done" with 3-5 paths in "result"
```

Settings: `ORCHESTRATOR_DB` (SQLite file, default `runtime/orchestrator.sqlite3`, not
committed), `ORCHESTRATOR_URL` (interface and AI server) and `AI_POLL_SECONDS` (AI server).

## Files

| File | What |
|---|---|
| [`Task6_Group7_Report.pdf`](Task6_Group7_Report.pdf) | the one-page preliminary report |
