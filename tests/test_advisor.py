"""Unit tests for src/advisor.py (FR-1 -> FR-7 behind one call).

The model steps (FR-3, FR-4) and the catalogue facts are replaced by small fakes, so each
expected response can be worked out by hand and the tests run without the models.
The same call on real data is in test_advisor_integration.py.
Run with:  python -m pytest tests/test_advisor.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.advisor import advise  # noqa: E402
from src.feasibility import CourseFacts  # noqa: E402
from src.interest import EMPTY_INTEREST_MESSAGE  # noqa: E402
from src.occupations import NO_OCCUPATION, OccupationMatch, RequiredSkills  # noqa: E402
from src.paths import Duration  # noqa: E402
from src.retrieval import NO_COURSES, CourseCandidate, RetrievalResult  # noqa: E402
from src.study_context import HOURS_MESSAGE  # noqa: E402

PY, SQL, ML = ("s:py", "Python"), ("s:sql", "SQL"), ("s:ml", "machine learning")
REQUIRED = [PY, SQL, ML]


def course(key, title, *skills):
    return CourseCandidate(key, title, "Data Science", tuple(skills), len(skills) / len(REQUIRED))


COURSES = [
    course("c1", "Python basics", PY),
    course("c2", "Databases", SQL),
    course("c3", "Intro to ML", ML, PY),
    course("c4", "Aprendizaje automatico", ML),
]
FACTS = {"c1": CourseFacts("English", 3), "c2": CourseFacts("English", 3),
         "c3": CourseFacts("English", 4), "c4": CourseFacts("Spanish", 3)}
DURATIONS = {k: Duration(4, "week") for k in FACTS}


class Spy:
    """A fake step that records whether it was called."""

    def __init__(self, result):
        self.result, self.calls = result, 0

    def __call__(self, *args):
        self.calls += 1
        return self.result


def run(request, required=REQUIRED, courses=COURSES, message=None):
    derive = Spy(RequiredSkills([OccupationMatch("o:1", "data analyst", 0.7)] if required else [],
                                required, None if required else NO_OCCUPATION))
    retrieve = Spy(RetrievalResult(courses, message))
    response = advise(request, derive=derive, retrieve=retrieve, facts=FACTS, durations=DURATIONS)
    return response, derive


def test_empty_interest_is_rejected_before_any_model_runs():
    response, derive = run({"interest": "   "})
    assert response == {"ok": False, "error": EMPTY_INTEREST_MESSAGE}
    assert derive.calls == 0


def test_invalid_hours_per_week_is_rejected():
    response, derive = run({"interest": "data analysis", "hours_per_week": "lots"})
    assert response == {"ok": False, "error": HOURS_MESSAGE}
    assert derive.calls == 0


def test_valid_request_returns_ranked_paths_as_json():
    response, _ = run({"interest": "  data analysis ", "language": "English", "weeks_available": 12})

    json.dumps(response)  # must survive the trip through the orchestrator queue
    assert response["ok"] and response["interest"] == "data analysis"
    assert response["required_skills"] == ["Python", "SQL", "machine learning"]
    assert response["removed"] == [{"title": "Aprendizaje automatico",
                                    "reason": "taught in Spanish, not English"}]
    best = response["paths"][0]
    # Intro to ML + Databases covers all three skills in 8 weeks.
    assert sorted(c["title"] for c in best["courses"]) == ["Databases", "Intro to ML"]
    assert best["fit"] == 1.0 and best["weeks"] == 8.0
    assert sorted(best["covered_skills"]) == ["Python", "SQL", "machine learning"]
    fits = [p["fit"] for p in response["paths"]]
    assert fits == sorted(fits, reverse=True)


def test_missing_context_is_shown_as_not_given():
    response, _ = run({"interest": "data analysis"})
    assert response["context"]["language"] == "not given"
    assert response["context"]["weeks_available"] == "not given"


def test_no_occupation_falls_back_and_scores_against_the_matched_skills():
    response, _ = run({"interest": "something vague"}, required=[])
    assert response["ok"] and response["occupations"] == []
    assert response["message"] == NO_OCCUPATION
    assert response["paths"] and response["paths"][0]["fit"] == 1.0


def test_no_courses_gives_no_paths_and_says_why():
    response, _ = run({"interest": "underwater basket weaving"}, courses=[], message=NO_COURSES)
    assert response["paths"] == [] and response["message"] == NO_COURSES
