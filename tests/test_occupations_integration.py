"""Integration tests for FR-3 with the real encoder and ESCO occupation data.

Runs src/occupations.py with all-MiniLM-L6-v2, data/occupations_clean.csv (319 occupations)
and data/relations_clean.csv. Skipped where sentence-transformers is not installed; CI has it.
Run with:  python -m pytest tests/test_occupations_integration.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("sentence_transformers")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.occupations import NO_OCCUPATION, derive_required_skills  # noqa: E402


def test_named_occupation_gives_its_essential_skills():
    result = derive_required_skills("software developer")
    assert result.occupations[0].label == "software developer"
    assert len(result.skills) > 0
    assert result.message is None


@pytest.mark.parametrize("interest", [
    "electrician",                # not among the 319 professional occupations
    "I like cooking and baking",  # not an occupation at all
])
def test_unmatched_interest_says_no_occupation(interest):
    """With the default threshold these return no occupation instead of a wrong guess."""
    result = derive_required_skills(interest)
    assert result.message == NO_OCCUPATION
    assert result.skills == []
