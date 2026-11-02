"""Unit tests for src/retrieval.py (FR-4).

The catalogue, the course -> ESCO skill matches and Model 2 are small fakes, so these
tests cover the retrieval logic only: linking courses to ESCO, ranking by covered skills,
narrowing by category, the result limit and "no matching courses". The real data is
covered in test_retrieval_integration.py.
Run with:  python -m pytest tests/test_retrieval.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.model_skills import SkillMatch  # noqa: E402
from src.retrieval import (  # noqa: E402
    NO_COURSES,
    course_esco_links,
    retrieve,
    skills_from_interest,
)

CATALOGUE = pd.DataFrame({
    "course_key": ["c1", "c2", "c3", "c4"],
    "title": ["Python for Everybody", "Data Science Basics", "Contract Law", "Watercolour"],
    "category": ["Computer Science", "Data Science", "Social Sciences", "Arts and Humanities"],
    "skills_normalised": ["python | testing", "python | statistics", "contracts", ""],
})
SKILL_MATCHES = pd.DataFrame({
    "course_skill": ["python", "testing", "statistics", "contracts", "python"],
    "rank": [1, 1, 1, 1, 2],
    "esco_id": ["sk:python", "sk:testing", "sk:statistics", "sk:contracts", "sk:weak"],
    "esco_label": ["Python", "software testing", "statistics", "contract law", "weak match"],
    "score": [0.9, 0.8, 0.7, 0.9, 0.2],
})
REQUIRED = [("sk:python", "Python"), ("sk:testing", "software testing")]


@pytest.fixture
def links():
    return course_esco_links(CATALOGUE, SKILL_MATCHES, threshold=0.45)


def test_links_drop_weak_matches_and_courses_without_skills(links):
    """sk:weak scores 0.2, below the threshold; c4 lists no skills."""
    assert links == {"c1": {"sk:python", "sk:testing"}, "c2": {"sk:python", "sk:statistics"}, "c3": {"sk:contracts"}}


def test_course_covering_more_required_skills_ranks_first(links):
    result = retrieve(REQUIRED, CATALOGUE, links)
    assert [c.course_key for c in result.courses] == ["c1", "c2"]
    assert result.courses[0].coverage == 1.0 and result.courses[1].coverage == 0.5
    assert result.message is None


def test_candidate_shows_title_category_and_matched_skills(links):
    first = retrieve(REQUIRED, CATALOGUE, links).courses[0]
    assert (first.title, first.category) == ("Python for Everybody", "Computer Science")
    assert first.matched_skills == (("sk:python", "Python"), ("sk:testing", "software testing"))


def test_categories_narrow_the_result(links):
    result = retrieve(REQUIRED, CATALOGUE, links, categories={"Data Science"})
    assert [c.course_key for c in result.courses] == ["c2"]


def test_limit_caps_the_number_of_courses(links):
    assert len(retrieve(REQUIRED, CATALOGUE, links, limit=1).courses) == 1


def test_no_overlap_says_no_matching_courses(links):
    result = retrieve([("sk:painting", "painting")], CATALOGUE, links)
    assert (result.courses, result.message) == ([], NO_COURSES)


def test_no_required_skills_says_no_matching_courses(links):
    assert retrieve([], CATALOGUE, links).message == NO_COURSES


def test_skills_from_interest_keeps_only_strong_matches():
    def fake_match(text, k):
        return [SkillMatch("sk:a", "marketing mix", 0.59), SkillMatch("sk:b", "manage a team", 0.37)]
    assert skills_from_interest("marketing", fake_match, threshold=0.45) == [("sk:a", "marketing mix")]
