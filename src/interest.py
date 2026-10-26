"""Capture and validate a student's stated interest (FR-1).

The system accepts an interest or destination as free text in the student's own
words. Per the SRS (Task 3, FR-1):

    Accepts 1-500 characters of free text and keeps it for the session.
    Empty input is refused with "Please describe an interest".

This module is deliberately pure and dependency-free: `validate_interest` takes a
string and returns a `ValidationResult`, with no I/O, so it is unit-testable in
isolation. FR-2 (study context) will be added alongside it as the next card.
"""
from __future__ import annotations

from dataclasses import dataclass

# --- Rules (single source of truth, so tests and callers agree) -----------
MAX_INTEREST_CHARS = 500
EMPTY_INTEREST_MESSAGE = "Please describe an interest"
TOO_LONG_MESSAGE = f"Please keep your interest under {MAX_INTEREST_CHARS} characters"


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating one field.

    ok     - True when the input is acceptable.
    value  - the cleaned (trimmed) interest, set only when ok.
    error  - the user-facing message, set only when not ok.
    """

    ok: bool
    value: str = ""
    error: str = ""


def validate_interest(raw: str | None) -> ValidationResult:
    """Validate a free-text interest against FR-1.

    Leading/trailing whitespace is trimmed, and the 1-500 character bound is
    measured on the trimmed text (the content actually kept). Returns a
    ValidationResult; callers read `.ok`, then `.value` or `.error`.
    """
    if raw is None:
        return ValidationResult(False, error=EMPTY_INTEREST_MESSAGE)

    text = raw.strip()
    if not text:
        return ValidationResult(False, error=EMPTY_INTEREST_MESSAGE)
    if len(text) > MAX_INTEREST_CHARS:
        return ValidationResult(False, error=TOO_LONG_MESSAGE)

    return ValidationResult(True, value=text)
