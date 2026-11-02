"""Unit tests for src/feasibility.py (FR-5, NFR-3).

Candidates and course facts are small hand-made values, so these tests cover the rules
only: each removal reason, skipped checks for fields the student left empty, and courses
with missing data kept as "not listed". The real catalogue is covered in
test_feasibility_integration.py.
Run with:  python -m pytest tests/test_feasibility.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.feasibility import CourseFacts, assess, base_language  # noqa: E402
from src.study_context import NOT_LISTED, StudyContext  # noqa: E402


def course(key, title):
    return SimpleNamespace(course_key=key, title=title)


PYTHON = course("c1", "Python for Everybody")
SPANISH = course("c2", "Introducción a Python")
HEAVY = course("c3", "Deep Learning")
UNKNOWN = course("c4", "Mystery Course")
FACTS = {
    "c1": CourseFacts("English", 4.0),
    "c2": CourseFacts("Spanish", 3.0),
    "c3": CourseFacts("English", 10.0),
    # c4 has no facts at all
}
CONTEXT = StudyContext(language="English", hours_per_week=6, weeks_available=12,
                       completed_courses=("python for everybody",))


def reasons(result):
    return {r.course.course_key: r.reason for r in result.removed}


def test_completed_course_is_removed_case_insensitive():
    assert reasons(assess([PYTHON], CONTEXT, FACTS)) == {"c1": "already completed"}


def test_other_language_is_removed_with_reason():
    assert reasons(assess([SPANISH], CONTEXT, FACTS)) == {"c2": "taught in Spanish, not English"}


def test_too_many_weekly_hours_is_removed_with_reason():
    assert reasons(assess([HEAVY], CONTEXT, FACTS)) == {"c3": "needs 10 hours per week, you have 6"}


def test_missing_course_data_is_kept_and_labelled_not_listed():
    result = assess([UNKNOWN], CONTEXT, FACTS)
    assert result.removed == []
    assert (result.kept[0].language, result.kept[0].weekly_hours) == (NOT_LISTED, NOT_LISTED)


def test_checks_for_fields_not_given_are_skipped():
    """Empty context: nothing is removed, whatever the course data."""
    result = assess([PYTHON, SPANISH, HEAVY], StudyContext(), FACTS)
    assert result.removed == [] and len(result.kept) == 3


def test_language_variants_count_as_the_same_language():
    assert base_language("Portuguese (Brazilian)") == base_language("portuguese") == "portuguese"


def test_kept_courses_keep_their_order_and_data():
    result = assess([HEAVY, UNKNOWN], StudyContext(language="English"), FACTS)
    assert [k.course.course_key for k in result.kept] == ["c3", "c4"]
    assert (result.kept[0].language, result.kept[0].weekly_hours) == ("English", 10.0)
