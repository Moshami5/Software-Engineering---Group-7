"""Unit tests for scripts/prepare_catalogue.py (FR-14, FR-15, AIR-8).

The models are replaced by fakes, so these tests cover the preparation logic only:
splitting skills, choosing between a known label and a prediction, and matching each
distinct skill once. Running the real models over the catalogue is integration test I3.
Run with:  python -m pytest tests/test_prepare_catalogue.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_catalogue import known_label, prepare, split_skills  # noqa: E402
from src.model_skills import SkillMatch  # noqa: E402


def fake_classify(title, intro):
    if not title and not intro:
        raise ValueError("no text")
    return "Data Science", 0.8


class FakeMatch:
    """Returns one fixed ESCO skill per query and records every query it gets."""

    def __init__(self):
        self.queries = []

    def __call__(self, skill, k):
        self.queries.append(skill)
        return [SkillMatch(f"esco:{skill}", skill.title(), 0.9)][:k]


def courses(*rows):
    cols = ["course_key", "site", "title", "short_intro", "category", "skills"]
    return pd.DataFrame(rows, columns=cols)


def test_split_skills_normalises_and_drops_repeats():
    assert split_skills("Python, data  Analysis,python,\n SQL ,") == ["python", "data analysis", "sql"]


def test_split_skills_missing_cell_is_empty():
    assert split_skills(None) == []
    assert split_skills(float("nan")) == []


def test_known_label_maps_localised_labels():
    assert known_label("Negocios") == "Business"
    assert known_label("Health") == "Health"
    assert known_label(None) is None
    assert known_label("Not a category") is None


def test_labelled_course_keeps_its_label():
    catalogue, _, _ = prepare(courses(("c1", "Coursera", "Intro", "x", "Health", None)), fake_classify, FakeMatch())
    row = catalogue.iloc[0]
    assert (row["category"], row["category_source"]) == ("Health", "label")
    assert row["predicted_category"] == "Data Science"  # prediction kept for comparison


def test_unlabelled_course_gets_the_prediction():
    catalogue, _, _ = prepare(courses(("c1", "Udacity", "Intro", "x", None, None)), fake_classify, FakeMatch())
    row = catalogue.iloc[0]
    assert (row["category"], row["category_source"], row["predicted_confidence"]) == ("Data Science", "model", 0.8)


def test_course_without_text_is_marked_none():
    catalogue, _, _ = prepare(courses(("c1", "Udacity", None, None, None, None)), fake_classify, FakeMatch())
    assert catalogue.iloc[0]["category_source"] == "none"


def test_each_distinct_skill_is_matched_once():
    fake = FakeMatch()
    data = courses(("c1", "Coursera", "A", "x", None, "Python, SQL"),
                   ("c2", "Coursera", "B", "y", None, "python"))
    _, matches, stats = prepare(data, fake_classify, fake)
    assert sorted(fake.queries) == ["python", "sql"]
    assert stats["distinct_course_skills"] == 2
    assert list(matches.columns) == ["course_skill", "rank", "esco_id", "esco_label", "score"]


@pytest.mark.parametrize("key", ["courses", "classify_seconds", "match_seconds"])
def test_stats_report_counts_and_timings(key):
    _, _, stats = prepare(courses(("c1", "Coursera", "A", "x", None, "sql")), fake_classify, FakeMatch())
    assert key in stats
