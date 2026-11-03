"""Unit tests for src/occupations.py (FR-3).

The encoder, occupation index and skill links are small fakes, so these tests cover the
module's own logic only: thresholding, collecting essential skills without repeats, and
the "no occupation matched" result. The real encoder is covered in
test_occupations_integration.py.
Run with:  python -m pytest tests/test_occupations.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.model_skills import build_index  # noqa: E402
from src.occupations import (  # noqa: E402
    NO_OCCUPATION,
    derive_required_skills,
    match_occupations,
    skills_for,
)

VOCAB = ["software", "data", "law"]
# With these fakes a real match scores 1.0 and text with none of the words ~0.58
# against everything, so the tests use threshold 0.9 to separate the two.


class FakeEncoder:
    """Bag-of-keywords vectors over VOCAB, normalised like the real encoder."""

    def encode(self, texts, batch_size=64, normalize_embeddings=True):
        rows = []
        for text in texts:
            v = np.array([text.count(word) for word in VOCAB], dtype=float) + 1e-9
            rows.append(v / np.linalg.norm(v))
        return np.vstack(rows)


OCCUPATIONS = pd.DataFrame({
    "conceptUri": ["occ:dev", "occ:data", "occ:law"],
    "preferredLabel": ["software developer", "data scientist", "lawyer"],
    "altLabels": ["software engineer", "data analyst", "law practitioner"],
})
RELATIONS = pd.DataFrame({
    "occupationUri": ["occ:dev", "occ:dev", "occ:data", "occ:data", "occ:law"],
    "skillUri": ["sk:python", "sk:testing", "sk:python", "sk:statistics", "sk:contracts"],
    "skillLabel": ["Python", "software testing", "Python", "statistics", "contract law"],
})


@pytest.fixture
def index():
    return build_index(OCCUPATIONS, FakeEncoder())


def test_clear_interest_matches_its_occupation_first(index):
    result = match_occupations("software", index, FakeEncoder(), threshold=0.5)
    assert result[0].label == "software developer"


def test_occupations_below_threshold_are_dropped(index):
    """With a threshold above every score, nothing is returned."""
    assert match_occupations("software", index, FakeEncoder(), threshold=1.01) == []


def test_skills_for_unions_without_repeats():
    """Python is essential for both occupations but appears once, in occupation order."""
    assert skills_for(["occ:dev", "occ:data"], RELATIONS) == [
        ("sk:python", "Python"), ("sk:testing", "software testing"), ("sk:statistics", "statistics")]


def test_skills_for_unknown_occupation_is_empty():
    assert skills_for(["occ:unknown"], RELATIONS) == []


def test_derive_returns_occupation_and_its_skills(index):
    result = derive_required_skills("law", threshold=0.9, index=index, encoder=FakeEncoder(), relations=RELATIONS)
    assert [o.label for o in result.occupations] == ["lawyer"]
    assert result.skills == [("sk:contracts", "contract law")]
    assert result.message is None


def test_derive_without_match_says_no_occupation(index):
    """FR-3: when nothing clears the threshold the result says so instead of guessing."""
    result = derive_required_skills("cooking", threshold=0.9, index=index, encoder=FakeEncoder(), relations=RELATIONS)
    assert (result.occupations, result.skills, result.message) == ([], [], NO_OCCUPATION)


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_derive_refuses_empty_interest(bad):
    with pytest.raises(ValueError):
        derive_required_skills(bad)
