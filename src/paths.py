"""FR-6 + FR-7: compose whole study paths and return the best 3-5.

FR-6 (compose): each path starts from a different candidate course and repeatedly adds
the course that covers the most still-missing required skills, as long as the total
duration fits the weeks available. A course is only added when it covers at least one new
required skill. Courses without a listed duration are left out, and the student is told how many.

FR-7 (rank): a path's fit score is the share of the required skills it covers (0-1).
Paths are ordered by fit, ties going to the shorter path; 3-5 are returned, or fewer with
"only N paths fit your constraints".

Durations are converted to weeks: weeks as listed, months x 4.3, days / 7; hours and
minutes are total study time, divided by the student's hours per week.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_contract import COURSES_CSV  # noqa: E402
from src.study_context import StudyContext, is_missing  # noqa: E402

WEEKS_PER_MONTH = 4.3
# Assumed when the student gave no hours per week, so hour-based courses (44% of the
# catalogue) can still be placed in a path. Median weekly load of listed courses is 3 h.
DEFAULT_HOURS_PER_WEEK = 5.0
MAX_COURSES_PER_PATH = 5   # caps a path when the student gave no weeks available
MIN_PATHS, MAX_PATHS = 3, 5
NO_PATHS = "no path fits your constraints"


@dataclass(frozen=True)
class Duration:
    value: float
    unit: str  # hour, minute, day, week or month


@dataclass(frozen=True)
class StudyPath:
    courses: tuple            # FR-4 CourseCandidates, in the order they were added
    weeks: float              # total duration in weeks
    covered: frozenset        # required ESCO skill ids the path covers (only required ones)
    fit: float                # share of the required skills covered, 0-1


@dataclass(frozen=True)
class PathsResult:
    paths: list[StudyPath]
    left_out_no_duration: int  # FR-6: courses left out because they list no duration
    message: str | None        # "only N paths fit your constraints" or NO_PATHS


def to_weeks(duration: Duration | None, hours_per_week: float | None) -> float | None:
    """A course duration in weeks, or None when it cannot be converted."""
    if duration is None:
        return None
    hours = hours_per_week or DEFAULT_HOURS_PER_WEEK
    per_unit = {"week": 1.0, "month": WEEKS_PER_MONTH, "day": 1 / 7,
                "hour": 1 / hours, "minute": 1 / (60 * hours)}
    factor = per_unit.get(duration.unit)
    return None if factor is None else duration.value * factor


def _skills(course) -> frozenset:
    return frozenset(skill_id for skill_id, _ in course.matched_skills)


def compose_path(seed, pool, weeks_of: dict, budget: float | None, required_ids: frozenset) -> tuple:
    """Grow one path from ``seed``: add the course covering most missing required skills that still fits."""
    path, total, covered = [seed], weeks_of[seed.course_key], set(_skills(seed) & required_ids)
    while len(path) < MAX_COURSES_PER_PATH:
        best, best_new = None, 0
        for course in pool:
            if course in path:
                continue
            new = len((_skills(course) & required_ids) - covered)
            fits = budget is None or total + weeks_of[course.course_key] <= budget
            if fits and new > best_new:
                best, best_new = course, new
        if best is None:
            break
        path.append(best)
        total += weeks_of[best.course_key]
        covered |= _skills(best) & required_ids
    return tuple(path), total, frozenset(covered)


def build_paths(candidates, required: list[tuple[str, str]], context: StudyContext,
                durations: dict[str, Duration]) -> PathsResult:
    """FR-6 + FR-7 for the feasible candidates (FR-5 output, best first)."""
    weeks_of = {}
    for c in candidates:
        weeks = to_weeks(durations.get(c.course_key), context.hours_per_week)
        if weeks is not None:
            weeks_of[c.course_key] = weeks
    pool = [c for c in candidates if c.course_key in weeks_of]
    left_out = len(candidates) - len(pool)
    budget = context.weeks_available

    required_ids = frozenset(skill_id for skill_id, _ in required)
    seen, paths = set(), []
    for seed in pool:
        if budget is not None and weeks_of[seed.course_key] > budget:
            continue
        courses, weeks, covered = compose_path(seed, pool, weeks_of, budget, required_ids)
        # The catalogue lists some courses twice under different keys; paths with the
        # same course titles look identical to a student, so count them once.
        key = frozenset(str(c.title).strip().lower() for c in courses)
        if key in seen:
            continue
        seen.add(key)
        fit = len(covered) / len(required_ids) if required_ids else 0.0
        paths.append(StudyPath(courses, weeks, covered, fit))

    paths.sort(key=lambda p: (-p.fit, p.weeks))
    paths = paths[:MAX_PATHS]
    if not paths:
        message = NO_PATHS
    elif len(paths) < MIN_PATHS:
        message = f"only {len(paths)} paths fit your constraints"
    else:
        message = None
    return PathsResult(paths, left_out, message)


@lru_cache(maxsize=1)
def load_durations(path: Path = COURSES_CSV) -> dict[str, Duration]:
    """course_key -> listed duration (the longer end when a range is given)."""
    data = pd.read_csv(path, usecols=["course_key", "duration_max", "duration_unit"], low_memory=False)
    return {key: Duration(float(value), str(unit)) for key, value, unit in data.itertuples(index=False)
            if not is_missing(value) and not is_missing(unit)}
