"""Unit tests for src/model_skills.py (FR-15, AIR-2).

Each test checks one function on its own. Ranking is tested against a fake
encoder (fixed keyword vectors) instead of all-MiniLM-L6-v2, so these tests
cover the module's own logic - label parsing, ranking, input checks - and run
without torch. The real encoder is covered in test_model_skills_integration.py.
Run with:  python -m pytest tests/test_model_skills.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import model_skills  # noqa: E402
from src.model_skills import (  # noqa: E402
    SkillMatch,
    alt_labels,
    build_index,
    index_document,
    match,
    rank,
)

VOCAB = ["python", "programming", "teamwork", "cooking"]


class FakeEncoder:
    """Bag-of-keywords vectors over VOCAB, normalised like the real encoder."""

    def encode(self, texts, batch_size=64, normalize_embeddings=True):
        rows = []
        for text in texts:
            v = np.array([text.count(word) for word in VOCAB], dtype=float) + 1e-9
            rows.append(v / np.linalg.norm(v))
        return np.vstack(rows)


ESCO = pd.DataFrame({
    "conceptUri": ["esco:python", "esco:teamwork", "esco:cooking"],
    "preferredLabel": ["Python (computer programming)", "teamwork principles", "cooking techniques"],
    "altLabels": ["python;python programming", "work in teams\ncollaboration", None],
})


@pytest.fixture
def fake_index():
    return build_index(ESCO, FakeEncoder())


def test_alt_labels_split_on_semicolons():
    """skills_clean.csv separates alt labels with ';' - each becomes its own label."""
    assert alt_labels("python;Python Programming") == ["python", "python programming"]


def test_alt_labels_split_on_newlines():
    """skills_en.csv separates alt labels with newlines."""
    assert alt_labels("work in teams\ncollaboration") == ["work in teams", "collaboration"]


def test_alt_labels_missing_cell_is_empty():
    assert alt_labels(None) == []
    assert alt_labels(float("nan")) == []


def test_index_document_puts_preferred_label_first():
    assert index_document("Teamwork Principles", "work in teams") == "teamwork principles . work in teams"


def test_rank_returns_best_match_first(fake_index):
    """The skill sharing the query's keywords ranks first, scores descending."""
    result = rank("python programming", fake_index, FakeEncoder(), k=3)
    assert result[0] == SkillMatch("esco:python", "Python (computer programming)", pytest.approx(result[0].score))
    scores = [m.score for m in result]
    assert scores == sorted(scores, reverse=True)


def test_rank_returns_at_most_k(fake_index):
    assert len(rank("python", fake_index, FakeEncoder(), k=2)) == 2


def test_rank_k_larger_than_index_returns_whole_index(fake_index):
    assert len(rank("python", fake_index, FakeEncoder(), k=50)) == 3


def test_match_returns_at_most_five_sorted(monkeypatch, fake_index):
    """U5: "python programming" -> at most 5 ESCO skills, sorted by score."""
    monkeypatch.setattr(model_skills, "load_index", lambda: fake_index)
    monkeypatch.setattr(model_skills, "load_encoder", lambda: FakeEncoder())
    result = match("python programming")
    assert 1 <= len(result) <= 5
    assert [m.score for m in result] == sorted((m.score for m in result), reverse=True)
    assert all(isinstance(m.score, float) for m in result)


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_match_refuses_empty_skill(monkeypatch, bad):
    """Empty input raises ValueError before any model is loaded."""
    monkeypatch.setattr(model_skills, "load_index", lambda: pytest.fail("index loaded"))
    with pytest.raises(ValueError):
        match(bad)


def test_match_refuses_k_below_one():
    with pytest.raises(ValueError):
        match("python", k=0)
