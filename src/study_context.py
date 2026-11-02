""" Capture and validate a student's study context (FR-2), with missing-value labels (NFR-3)

Per the SRS (Task 3, FR-2):
    Stored language, hours per week (1-40), weeks available (1-52) and completed
    courses for the session. A missing field is shown as " not given" and its check
    in FR-5 is skipped.
Per NFR-3, missing values must be labelled predictably instead of crashing: a 
field the student left empty is "not given", and course data missing from the 
catalouge is "not listed" (see "label_missing).

Same style as src/interest.py (FR-1): pure, dependency-free, no I/0, and the 
validator returns a result object (".ok", then ".value" or ",error") rather than
raising, so it is unit-testable in isolation.
"""
from __future__ import annotations
import math
from dataclasses import dataclass

# Rules (single source of truth, so tests and callers agree)
MIN_HOURS_PER_WEEK, MAX_HOURS_PER_WEEK = 1, 40
MIN_WEEKS_AVAILABLE, MAX_WEEKS_AVAILABLE = 1,52

NOT_GIVEN = "not given"
NOT_LISTED = "not listed"

HOURS_MESSAGE = (f"Hours per week must be a number from "
                 f"{MIN_HOURS_PER_WEEK} to {MAX_HOURS_PER_WEEK}")
WEEKS_MESSAGE = (f"Weeks available must be a number from "
                 f"{MIN_WEEKS_AVAILABLE} to {MAX_WEEKS_AVAILABLE}")
LANGUAGE_MESSAGE = "Preferred language must be text, e.g. English"
COURSES_MESSAGE = "Completed courses must ne a list of course titles"


FIELDS = ("language", "hours_per_week", "weeks_available", "completed_courses")

def is_missing(value) -> bool:
    """None, '' or only spaces, and NaN all count as 'no value'. """
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False
@dataclass(frozen=True)
class StudyContext:
    """The student's context for one session. None / () means 'not given', """

    language: str | None = None
    hours_per_week: float | None = None
    weeks_available: float | None = None
    completed_courses: tuple[str,...] = ()

    def display(self) -> dict:
        """FR-2 every field as shown to the student, 'not given', where empty."""
        return {
            "language": self.language if self.language is not None else NOT_GIVEN,
            "hours_per_week": (self.hours_per_week
                               if self.hours_per_week is not None else NOT_GIVEN),
            "weeks_available": (self.weeks_available
                                if self.weeks_available is not None else NOT_GIVEN),
            "completed_courses": list(self.completed_courses) or NOT_GIVEN,
        }
    def missing_fields(self) -> list[str]:
        """ Names of the fields the student left empty."""
        return [name for name, shown in self.display().items() if shown == NOT_GIVEN]
    def is_given(self, field: str) -> bool:
        """FR-5 asks this before each check; a field that is not given is skipped."""
        if field not in FIELDS:
             raise KeyError(field)
        return field not in self.missing_fields()
@dataclass(frozen=True)
class StudyContextResult:
    """Outcome of validating the study context (same shape as interest.ValidationResult).

    ok     - True when every given is acceptable.
    value  - teh cleaned StudyContext, set only when ok.
    error  - the user-facing message for the first problem, set only when not ok.
    """

    ok: bool
    value: StudyContext | None = None
    error: str = ""

def _number_in_range(raw, low: float, high: float) -> tuple[bool, float | None]:
    """(ok, number). Missing -> (True, None). Text like '8' is accepted."""
    if is_missing(raw):
        return True, None
    if isinstance(raw, bool):
        return False, None
    try:
        number = float(raw.strip() if isinstance(raw, str) else raw)
    except (TypeError, ValueError):
        return False, None
    if math.isnan(number):
        return True, None
    if not low <= number <= high:
        return False, None
    return True, number

def _clean_courses(raw) -> tuple[bool, tuple[str,...]]:
    """Trim titles, drop blanks and repeats (case-insensitive). 'A, B' text is split"""
    if is_missing(raw):
        return True, ()
    if isinstance(raw, str):
        raw = raw.split(",")
    if not isinstance(raw, (list, tuple)):
        return False, ()
    cleaned, seen = [], set()
    for title in raw:
        if is_missing(title):
            continue
        if not isinstance(title, str):
            return False, ()
        title = title.strip()
        if title.lower() not in seen:
            seen.add(title.lower())
            cleaned.append(title)
    return True, tuple(cleaned)

def validate_study_context(language=None, hours_per_week=None, weeks_available=None,
                           completed_courses=None) -> StudyContextResult:
    """Validate teh study context against FR-2.

    Every field is optional. A given value must be valid; a missing one is stored 
    as None (shown as 'not given'). Returns a StudyContextResult; callers read
    '.ok', then '.value' or '.error'.
    """

    if is_missing(language):
        lang = None
    elif isinstance(language, str):
        lang = language.strip()
    else:
        return StudyContextResult(False, error=LANGUAGE_MESSAGE)

    ok, hours = _number_in_range(hours_per_week, MIN_HOURS_PER_WEEK, MAX_HOURS_PER_WEEK)
    if not ok:
        return StudyContextResult(False, error=HOURS_MESSAGE)

    ok, weeks = _number_in_range(weeks_available, MIN_WEEKS_AVAILABLE, MAX_WEEKS_AVAILABLE)
    if not ok:
        return StudyContextResult(False, error=WEEKS_MESSAGE)
    ok, courses = _clean_courses(completed_courses)
    if not ok:
        return StudyContextResult(False, error=COURSES_MESSAGE)

    return StudyContextResult(True, value=StudyContext(lang, hours, weeks, courses))
def label_missing(value, label: str = NOT_LISTED):
    """NFR-3: return the value, or a fixec label if the catalouge has none.

    Used when shwoing course data (duration, language, weekly hours) so a missing
    value is labelled instead of breaking the output.
    """

    return label if is_missing(value) else value