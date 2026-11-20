"""Unit tests for src/explain.py (FR-8 to FR-11, AIR-5).

Small hand-made courses, skills and occupations, so each expected explanation can be
worked out on paper. The same functions on the real data are covered by
test_advisor_integration.py.
Run with:  python -m pytest tests/test_explain.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.explain import (NONE_MATCHED, Evidence, ExplainData, course_evidence,  # noqa: E402
                         duration_text, explain_path, occupations_opened, skill_gaps)
from src.paths import Duration  # noqa: E402
from src.study_context import NOT_LISTED  # noqa: E402

PY, SQL, ML, STATS = "s:py", "s:sql", "s:ml", "s:stats"

# Two occupations: data analyst needs 4 skills, web developer needs 2.
OCC_SKILLS = {"o:analyst": frozenset({PY, SQL, ML, STATS}), "o:web": frozenset({PY, "s:html"})}
OCC_LABELS = {"o:analyst": "data analyst", "o:web": "web developer"}


def test_course_evidence_keeps_matches_above_threshold_best_score_per_skill():
    catalogue = pd.DataFrame({"course_key": ["c1", "c2"],
                              "skills_normalised": ["python | python programming", None]})
    matches = pd.DataFrame({
        "course_skill": ["python", "python programming", "python", "python"],
        "esco_id": [PY, PY, SQL, "s:snake"],
        "esco_label": ["Python", "Python", "SQL", "snake care"],
        "score": [0.70, 0.90, 0.30, 0.50],
    })
    evidence = course_evidence(catalogue, matches, threshold=0.45)

    assert set(evidence) == {"c1"}                          # c2 lists no skills
    assert set(evidence["c1"]) == {PY, "s:snake"}           # SQL at 0.30 is below threshold
    assert evidence["c1"][PY] == Evidence("python programming", PY, "Python", 0.90)  # best of 0.70/0.90


def test_occupations_opened_ranks_by_skills_covered_then_share():
    opened = occupations_opened({PY, SQL, ML}, OCC_SKILLS, OCC_LABELS)

    assert [o["occupation"] for o in opened] == ["data analyst", "web developer"]
    assert opened[0] == {"occupation": "data analyst", "esco_id": "o:analyst", "skills_covered": 3,
                         "essential_skills": 4, "share": 0.75}
    assert opened[1]["skills_covered"] == 1 and opened[1]["share"] == 0.5


def test_occupations_opened_says_none_matched_and_caps_at_limit():
    assert occupations_opened({"s:cooking"}, OCC_SKILLS, OCC_LABELS) == NONE_MATCHED
    assert len(occupations_opened({PY}, OCC_SKILLS, OCC_LABELS, limit=1)) == 1


def test_skill_gaps_lists_uncovered_required_skills_in_order():
    required = [(PY, "Python"), (SQL, "SQL"), (STATS, "statistics")]
    assert skill_gaps(required, {SQL}) == ["Python", "statistics"]
    assert skill_gaps(required, {PY, SQL, STATS}) == []


def test_duration_text_shows_listed_duration_or_not_listed():
    assert duration_text(Duration(4, "week")) == "4 weeks"
    assert duration_text(Duration(1, "month")) == "1 month"
    assert duration_text(Duration(2.5, "hour")) == "2.5 hours"
    assert duration_text(None) == NOT_LISTED


def course(key, title, *skills):
    return SimpleNamespace(course_key=key, title=title, matched_skills=tuple(skills))


DATA = ExplainData(
    evidence={"c1": {PY: Evidence("python basics", PY, "Python", 0.81)},
              "c2": {SQL: Evidence("sql queries", SQL, "SQL", 0.66), ML: Evidence("ml", ML, "ML", 0.5)}},
    occupation_skills=OCC_SKILLS, occupation_labels=OCC_LABELS,
    category_source={"c1": "label", "c2": "model"},
)
REQUIRED = [(PY, "Python"), (SQL, "SQL"), (STATS, "statistics")]
PATH = SimpleNamespace(courses=(course("c1", "Python basics", (PY, "Python")),
                                course("c2", "Databases", (SQL, "SQL"))),
                       covered=frozenset({PY, SQL}), weeks=8.0, fit=2 / 3)
DURATIONS = {"c1": Duration(4, "week"), "c2": Duration(1, "month")}


def test_explain_path_with_an_occupation_match():
    out = explain_path(PATH, REQUIRED, True, DATA, DURATIONS, weeks_of=lambda c: {"c1": 4.0, "c2": 4.3}[c.course_key])

    # FR-8: the path's courses cover Python, SQL and ML -> 3 of the analyst's 4 skills.
    assert out["opens"][0]["occupation"] == "data analyst" and out["opens"][0]["share"] == 0.75
    # FR-9: statistics is required but not covered.
    assert out["closes"] == ["statistics"]
    # FR-10 + AIR-5: each course's skill traced to its own text, with the similarity score.
    first, second = out["course_details"]
    assert first["skill_links"] == [{"esco_skill": "Python", "esco_id": PY,
                                     "from_course_skill": "python basics", "similarity": 0.81}]
    assert second["skill_links"][0]["from_course_skill"] == "sql queries"
    # FR-11: listed duration and its weeks; AIR-5: where the category came from.
    assert (first["duration"], first["weeks"], first["category_from"]) == ("4 weeks", 4.0, "catalogue label")
    assert (second["duration"], second["category_from"]) == ("1 month", "Model 1 prediction")


def test_explain_path_without_an_occupation_match_hides_the_gap():
    out = explain_path(PATH, [], False, DATA, DURATIONS, weeks_of=lambda c: 4.0)
    assert out["closes"] is None          # FR-9 is shown only when an occupation was matched
    assert out["opens"] != NONE_MATCHED   # FR-8 still works from the courses' own skills


def test_course_without_evidence_or_duration_is_marked_not_listed():
    bare = SimpleNamespace(courses=(course("c9", "Unknown", (PY, "Python")),), covered=frozenset({PY}))
    out = explain_path(bare, REQUIRED, True, DATA, {}, weeks_of=lambda c: None)
    detail = out["course_details"][0]
    assert detail["duration"] == NOT_LISTED and detail["weeks"] == NOT_LISTED
    assert detail["category_from"] == NOT_LISTED
    assert detail["skill_links"][0]["from_course_skill"] == NOT_LISTED
    assert out["opens"] == NONE_MATCHED
