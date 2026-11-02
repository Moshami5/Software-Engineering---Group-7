"""Unit tests for src/paths.py (FR-6 path composition, FR-7 ranking).

Courses are small hand-made candidates with known skills and durations, so each expected
path can be worked out by hand. The full chain on real data is in
test_advisor_chain_integration.py.
Run with:  python -m pytest tests/test_paths.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.paths import NO_PATHS, Duration, build_paths, to_weeks  # noqa: E402
from src.study_context import StudyContext  # noqa: E402


def course(key, *skills):
    return SimpleNamespace(course_key=key, title=key, matched_skills=tuple((s, s) for s in skills))


REQUIRED = [("a", "a"), ("b", "b"), ("c", "c"), ("d", "d")]
A, B, C, AB = course("A", "a"), course("B", "b"), course("C", "c", "d"), course("AB", "a", "b")
DURATIONS = {"A": Duration(4, "week"), "B": Duration(4, "week"), "C": Duration(1, "month"),
             "AB": Duration(6, "week")}


@pytest.mark.parametrize("duration, hours, weeks", [
    (Duration(3, "week"), None, 3.0),
    (Duration(2, "month"), None, 8.6),
    (Duration(14, "day"), None, 2.0),
    (Duration(20, "hour"), 4, 5.0),        # total study hours / hours per week
    (Duration(20, "hour"), None, 4.0),     # default 5 hours per week
    (Duration(300, "minute"), 5, 1.0),
])
def test_to_weeks_converts_each_unit(duration, hours, weeks):
    assert to_weeks(duration, hours) == pytest.approx(weeks)


def test_unknown_or_missing_duration_cannot_be_converted():
    assert to_weeks(None, 5) is None
    assert to_weeks(Duration(3, "fortnight"), 5) is None


def test_path_stays_within_the_weeks_available():
    result = build_paths([A, B, C], REQUIRED, StudyContext(weeks_available=9), DURATIONS)
    assert all(p.weeks <= 9 for p in result.paths)


def test_best_path_covers_most_required_skills():
    """With 13 weeks A + B + C fit and cover all four skills."""
    best = build_paths([A, B, C], REQUIRED, StudyContext(weeks_available=13), DURATIONS).paths[0]
    assert {c.course_key for c in best.courses} == {"A", "B", "C"}
    assert best.fit == 1.0


def test_course_adding_no_new_skill_is_not_added():
    """After AB, adding A or B covers nothing new."""
    path = build_paths([AB, A, B], REQUIRED, StudyContext(weeks_available=52), DURATIONS).paths
    assert all(len(p.courses) == 1 or {"A", "B"}.isdisjoint(c.course_key for c in p.courses[1:])
               for p in path if p.courses[0].course_key == "AB")


def test_ties_go_to_the_shorter_path():
    """Only skill a is required: path [A] (4 weeks) and path [AB] (6 weeks) both cover it,
    so they tie on fit and the shorter one comes first. AB's skill b is not required, so it
    is never a reason to add AB to A."""
    result = build_paths([AB, A], [("a", "a")], StudyContext(weeks_available=52), DURATIONS)
    assert [p.courses[0].course_key for p in result.paths] == ["A", "AB"]  # 4 weeks before 6


def test_courses_without_duration_are_left_out_and_counted():
    result = build_paths([A, course("X", "a")], REQUIRED, StudyContext(), DURATIONS)
    assert result.left_out_no_duration == 1
    assert all("X" not in [c.course_key for c in p.courses] for p in result.paths)


def test_fewer_than_three_paths_says_so():
    result = build_paths([A], REQUIRED, StudyContext(weeks_available=10), DURATIONS)
    assert result.message == "only 1 paths fit your constraints"


def test_nothing_fits_says_no_path():
    result = build_paths([AB], REQUIRED, StudyContext(weeks_available=2), DURATIONS)
    assert (result.paths, result.message) == ([], NO_PATHS)


def test_at_most_five_paths_ordered_by_fit():
    many = [course(f"K{i}", f"s{i}") for i in range(8)]
    durations = {c.course_key: Duration(1, "week") for c in many}
    required = [(f"s{i}", f"s{i}") for i in range(8)]
    result = build_paths(many, required, StudyContext(weeks_available=2), durations)
    assert len(result.paths) == 5
    fits = [p.fit for p in result.paths]
    assert fits == sorted(fits, reverse=True)


def test_paths_with_the_same_course_titles_count_once():
    """The catalogue lists some courses twice under different keys; a student would see the
    same path twice, so it is returned once."""
    twin = SimpleNamespace(course_key="A-relisted", title="A", matched_skills=A.matched_skills)
    durations = {**DURATIONS, "A-relisted": Duration(4, "week")}
    result = build_paths([A, twin], [("a", "a")], StudyContext(weeks_available=10), durations)
    assert len(result.paths) == 1
