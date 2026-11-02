"""FR-5: assess feasibility of the candidate courses against the student's study context.

Rule-based, per SRS FR-5 / UR6:
- removes courses the student has already completed (matched on title, case-insensitive),
- removes courses taught in another language than the preferred one,
- removes courses needing more weekly hours than the student has,
and lists every removal with its reason. A check whose field the student left empty is
skipped (FR-2), and a course whose own value is missing is kept and labelled "not listed"
(NFR-3). Uses src/study_context.py for the context and the labels.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_contract import COURSES_CSV  # noqa: E402
from src.study_context import StudyContext, is_missing, label_missing  # noqa: E402


@dataclass(frozen=True)
class CourseFacts:
    language: str | None
    weekly_hours: float | None


@dataclass(frozen=True)
class KeptCourse:
    course: object                # the FR-4 CourseCandidate
    language: str                 # the course language, or "not listed"
    weekly_hours: float | str     # hours per week, or "not listed"


@dataclass(frozen=True)
class RemovedCourse:
    course: object
    reason: str


@dataclass(frozen=True)
class FeasibilityResult:
    kept: list[KeptCourse]
    removed: list[RemovedCourse]


def base_language(language: str) -> str:
    """'Portuguese (Brazilian)' -> 'portuguese', so variants of a language count as one."""
    return language.split("(")[0].strip().lower()


def removal_reason(title: str, facts: CourseFacts, context: StudyContext) -> str | None:
    """Why the course breaks the student's context, or None when it does not."""
    if context.is_given("completed_courses") and \
            title.strip().lower() in {c.lower() for c in context.completed_courses}:
        return "already completed"
    if context.is_given("language") and facts.language is not None and \
            base_language(facts.language) != base_language(context.language):
        return f"taught in {facts.language}, not {context.language}"
    if context.is_given("hours_per_week") and facts.weekly_hours is not None and \
            facts.weekly_hours > context.hours_per_week:
        return f"needs {facts.weekly_hours:g} hours per week, you have {context.hours_per_week:g}"
    return None


def assess(candidates, context: StudyContext, facts: dict[str, CourseFacts]) -> FeasibilityResult:
    """Split FR-4 candidates into kept and removed courses, in their original order."""
    kept, removed = [], []
    for course in candidates:
        f = facts.get(course.course_key, CourseFacts(None, None))
        reason = removal_reason(str(course.title), f, context)
        if reason:
            removed.append(RemovedCourse(course, reason))
        else:
            kept.append(KeptCourse(course, label_missing(f.language), label_missing(f.weekly_hours)))
    return FeasibilityResult(kept, removed)


@lru_cache(maxsize=1)
def load_facts(path: Path = COURSES_CSV) -> dict[str, CourseFacts]:
    """course_key -> language and weekly study hours from the cleaned catalogue."""
    data = pd.read_csv(path, usecols=["course_key", "language", "weekly_study_hours"], low_memory=False)
    return {
        key: CourseFacts(None if is_missing(lang) else str(lang).strip(),
                         None if is_missing(hours) else float(hours))
        for key, lang, hours in data.itertuples(index=False)
    }
