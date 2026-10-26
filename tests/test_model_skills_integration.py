"""Integration tests for Model 2 as a module (FR-15, AIR-2).

These run the real encoder (all-MiniLM-L6-v2) over the real ESCO index
(data/skills_clean.csv) through src/model_skills.py. They are skipped where
sentence-transformers is not installed; the CSAI environment and CI have it.
The first run downloads the encoder (~90 MB) and embeds 2,154 skills.
Run with:  python -m pytest tests/test_model_skills_integration.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("sentence_transformers")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.model_skills import load_esco, load_index, match  # noqa: E402


def test_index_covers_every_esco_skill():
    """One vector per skill in the cleaned index (2,154 rows)."""
    assert len(load_index().ids) == len(load_esco()) == 2154


def test_course_phrasing_finds_the_obvious_skill():
    """An unambiguous course skill puts its ESCO skill in the top 5."""
    assert "Python (computer programming)" in [m.label for m in match("python programming")]


def test_preferred_labels_retrieve_their_own_skill():
    """Querying a skill's own preferred label returns that skill in the top 5.

    Catches ids, labels and vectors drifting out of line. Measured on 26 Oct on this
    fixed sample (seed 42): top-1 0.905, top-5 0.985; misses are near-duplicates such as
    "manage data" -> "manage quantitative data". The floor leaves margin for that.
    """
    esco = load_esco()
    sample = np.random.default_rng(42).choice(len(esco), 200, replace=False)
    hits = sum(
        esco.loc[i, "conceptUri"] in [m.esco_id for m in match(esco.loc[i, "preferredLabel"])]
        for i in sample
    )
    assert hits / len(sample) >= 0.95


def test_scores_are_cosine_similarities():
    """Normalised embeddings give scores in [-1, 1], sorted high to low."""
    scores = [m.score for m in match("statistics")]
    assert all(-1.0 <= s <= 1.0 for s in scores)
    assert scores == sorted(scores, reverse=True)
