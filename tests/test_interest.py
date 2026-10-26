"""Unit tests for interest validation (FR-1).

Each test exercises `validate_interest` in isolation - one function, a known
input, an asserted output - so these are true unit tests, not component tests.
Run with:  python -m pytest tests/test_interest.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.interest import (  # noqa: E402
    EMPTY_INTEREST_MESSAGE,
    MAX_INTEREST_CHARS,
    TOO_LONG_MESSAGE,
    validate_interest,
)


def test_valid_interest_is_accepted():
    """A normal interest is accepted and returned unchanged."""
    result = validate_interest("I want to work in data science")
    assert result.ok is True
    assert result.value == "I want to work in data science"
    assert result.error == ""


def test_surrounding_whitespace_is_trimmed():
    """Leading/trailing whitespace is stripped from the kept value."""
    result = validate_interest("  machine learning  ")
    assert result.ok is True
    assert result.value == "machine learning"


def test_empty_string_is_refused_with_exact_message():
    """Empty input is refused with the SRS-mandated message (FR-1)."""
    result = validate_interest("")
    assert result.ok is False
    assert result.error == EMPTY_INTEREST_MESSAGE
    assert result.value == ""


def test_whitespace_only_is_refused():
    """Whitespace-only input counts as empty and is refused."""
    result = validate_interest("   \t\n ")
    assert result.ok is False
    assert result.error == EMPTY_INTEREST_MESSAGE


def test_none_is_refused():
    """A missing (None) interest is refused, not an exception."""
    result = validate_interest(None)
    assert result.ok is False
    assert result.error == EMPTY_INTEREST_MESSAGE


def test_interest_at_max_length_is_accepted():
    """Exactly 500 characters is the upper boundary and is accepted."""
    text = "a" * MAX_INTEREST_CHARS
    result = validate_interest(text)
    assert result.ok is True
    assert len(result.value) == MAX_INTEREST_CHARS


def test_interest_over_max_length_is_refused():
    """501 characters exceeds the bound and is refused with the length message."""
    text = "a" * (MAX_INTEREST_CHARS + 1)
    result = validate_interest(text)
    assert result.ok is False
    assert result.error == TOO_LONG_MESSAGE
