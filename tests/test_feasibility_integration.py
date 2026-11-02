"""Integration test for FR-5 with the real catalogue and Melat's study-context validation.

Validates a study context with src/study_context.py, then assesses real courses from
data/Online_Courses_ml_features.csv with src/feasibility.py. No encoder needed.
Run with:  python -m pytest tests/test_feasibility_integration.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_contract import COURSES_CSV  # noqa: E402
from src.feasibility import assess, load_facts  # noqa: E402
from src.study_context import NOT_LISTED, validate_study_context  # noqa: E402


def test_real_courses_are_filtered_by_a_validated_context():
    courses = pd.read_csv(COURSES_CSV, usecols=["course_key", "title", "language", "weekly_study_hours"], low_memory=False)
    spanish = courses[courses["language"] == "Spanish"].iloc[0]
    heavy = courses[courses["weekly_study_hours"] > 5].iloc[0]
    no_data = courses[courses["language"].isna() & courses["weekly_study_hours"].isna()].iloc[0]
    candidates = [SimpleNamespace(course_key=r.course_key, title=r.title) for r in (spanish, heavy, no_data)]

    context = validate_study_context(language="English", hours_per_week="5").value
    result = assess(candidates, context, load_facts())

    removed = {r.course.course_key: r.reason for r in result.removed}
    assert removed[spanish.course_key].startswith("taught in Spanish")
    assert removed[heavy.course_key].startswith("needs")
    assert [k.course.course_key for k in result.kept] == [no_data.course_key]
    assert result.kept[0].language == NOT_LISTED
