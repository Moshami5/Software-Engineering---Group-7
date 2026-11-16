"""Unit tests for the interface server (Task 6, card "[T6 · NFR-8] Interface server").

No other server runs: the orchestrator calls are replaced by fakes, and requests
are stored in an in-memory database, so each test checks only this server's code.

Test data: typed by hand. Bad input reuses the FR-1 / FR-2 limits (empty interest,
41 hours per week); job answers use the agreed statuses waiting / running / done / failed.
"""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import httpx
from fastapi.testclient import TestClient

import src.interface_server as server

PATHS = {"paths": ["Intro to Python -> SQL Basics"]}


@pytest.fixture
def fake(monkeypatch):
    """Swap in an empty in-memory database and a fake orchestrator."""
    monkeypatch.setattr(server, "db", server.open_db(":memory:"))
    sent, jobs = [], {}

    def create_job(request):
        sent.append(request)
        return str(len(sent))

    def get_job(job_id):
        return jobs.get(job_id)

    monkeypatch.setattr(server, "create_job", create_job)
    monkeypatch.setattr(server, "get_job", get_job)
    return {"client": TestClient(server.app), "sent": sent, "jobs": jobs}


def stored():
    """(job_id, status) of every stored request."""
    return server.db.execute("SELECT job_id, status FROM requests").fetchall()


def down(*args):
    raise httpx.ConnectError("connection refused")


def test_valid_request_is_cleaned_stored_and_sent(fake):
    response = fake["client"].post("/advice", json={"interest": "  software developer ",
                                                    "hours_per_week": "4"})

    assert response.status_code == 202
    assert response.json() == {"id": "1", "status": "waiting"}
    assert fake["sent"] == [{"interest": "software developer", "language": None,
                             "hours_per_week": 4.0, "weeks_available": None,
                             "completed_courses": []}]
    assert stored() == [("1", "waiting")]


@pytest.mark.parametrize("payload, message", [
    ({"interest": ""}, "Please describe an interest"),
    ({}, "Please describe an interest"),
    ({"interest": "data science", "hours_per_week": 41},
     "Hours per week must be a number from 1 to 40"),
])
def test_bad_input_is_refused_and_no_job_is_made(fake, payload, message):
    response = fake["client"].post("/advice", json=payload)

    assert response.status_code == 422
    assert response.json() == {"error": message}
    assert fake["sent"] == []
    assert stored() == []


def test_orchestrator_down_gives_503_and_keeps_the_request(fake, monkeypatch):
    monkeypatch.setattr(server, "create_job", down)

    response = fake["client"].post("/advice", json={"interest": "data science"})

    assert response.status_code == 503
    assert response.json() == {"error": server.DOWN_MESSAGE}
    assert stored() == [(None, "not sent")]


def test_done_job_returns_the_study_paths(fake):
    fake["jobs"]["7"] = {"id": "7", "status": "done", "result": PATHS}

    response = fake["client"].get("/advice/7")

    assert response.status_code == 200
    assert response.json() == {"id": "7", "status": "done", "result": PATHS}


@pytest.mark.parametrize("status", ["waiting", "running"])
def test_unfinished_job_returns_status_only(fake, status):
    fake["jobs"]["7"] = {"id": "7", "status": status}

    assert fake["client"].get("/advice/7").json() == {"id": "7", "status": status}


def test_failed_job_returns_its_error(fake):
    fake["jobs"]["7"] = {"id": "7", "status": "failed", "error": "AI server crashed"}

    assert fake["client"].get("/advice/7").json() == {"id": "7", "status": "failed",
                                                      "error": "AI server crashed"}


def test_unknown_id_is_404(fake):
    response = fake["client"].get("/advice/99")

    assert response.status_code == 404
    assert response.json() == {"error": server.UNKNOWN_ID_MESSAGE}


def test_stored_status_follows_the_job(fake):
    fake["client"].post("/advice", json={"interest": "data science"})
    fake["jobs"]["1"] = {"id": "1", "status": "done", "result": PATHS}

    fake["client"].get("/advice/1")

    assert stored() == [("1", "done")]


def test_get_with_orchestrator_down_gives_503(fake, monkeypatch):
    monkeypatch.setattr(server, "get_job", down)

    assert fake["client"].get("/advice/1").status_code == 503


def test_create_job_calls_only_the_orchestrator(monkeypatch):
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json))
        return httpx.Response(201, json={"id": "abc"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(server.httpx, "post", fake_post)

    assert server.create_job({"interest": "x"}) == "abc"
    assert calls == [("http://localhost:8001/jobs", {"request": {"interest": "x"}})]



def flags():
    """Every stored flag, as (item_type, item, course, path, job_id)."""
    return server.db.execute(
        "SELECT item_type, item, course, path, job_id FROM flags").fetchall()


def test_flag_on_a_course_is_stored(fake):
    response = fake["client"].post("/flags", json={
        "type": "skill", "item": " Python (computer programming) ",
        "course": "Intro to Python", "job_id": "7"})

    assert response.status_code == 201
    assert response.json() == {"id": 1, "message": "flagged for review"}
    assert flags() == [("skill", "Python (computer programming)", "Intro to Python", None, "7")]


def test_flag_on_a_path_is_stored(fake):
    response = fake["client"].post("/flags", json={
        "type": "occupation", "item": "software developer", "path": 2})

    assert response.status_code == 201
    assert flags() == [("occupation", "software developer", None, 2, None)]


@pytest.mark.parametrize("payload, message", [
    ({"type": "teacher", "item": "x", "path": 1}, server.FLAG_TYPE_ERROR),
    ({"type": "skill", "item": "   ", "path": 1}, server.FLAG_ITEM_ERROR),
    ({"type": "skill", "item": "Python"}, server.FLAG_WHERE_ERROR),
    ({"type": "skill", "item": "Python", "path": 0}, server.FLAG_WHERE_ERROR),
])
def test_bad_flag_is_refused_and_not_stored(fake, payload, message):
    response = fake["client"].post("/flags", json=payload)

    assert response.status_code == 422
    assert response.json() == {"error": message}
    assert flags() == []


def test_flag_stores_no_personal_data(fake):
    fake["client"].post("/flags", json={
        "type": "skill", "item": "Python", "path": 1,
        "name": "Student", "email": "student@example.com"})

    stored = server.db.execute("SELECT * FROM flags").fetchone()
    assert "Student" not in stored and "student@example.com" not in stored