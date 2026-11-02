"""Integration tests for FR-3 + FR-4 with the real encoder and catalogue.

Runs src/occupations.py and src/retrieval.py together on data/processed/catalogue_enriched.csv
and skill_matches.csv. Skipped where sentence-transformers is not installed; CI has it.
Run with:  python -m pytest tests/test_retrieval_integration.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("sentence_transformers")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_contract import ENGLISH_CATEGORIES  # noqa: E402
from src.occupations import derive_required_skills  # noqa: E402
from src.retrieval import MAX_COURSES, NO_COURSES, retrieve_for  # noqa: E402


def test_occupation_interest_returns_categorised_courses_with_matched_skills():
    """'software developer' -> FR-3 skills -> at most 50 courses, each categorised and explained."""
    result = retrieve_for("software developer", derive_required_skills("software developer").skills)
    assert 0 < len(result.courses) <= MAX_COURSES
    assert all(c.category in ENGLISH_CATEGORIES and c.matched_skills for c in result.courses)


def test_interest_without_occupation_falls_back_to_interest_text():
    """'marketing and branding' names no occupation but still finds courses."""
    assert derive_required_skills("marketing and branding").skills == []
    assert len(retrieve_for("marketing and branding", []).courses) > 0


def test_unrelated_interest_finds_no_courses():
    assert retrieve_for("I like cooking and baking", []).message == NO_COURSES
