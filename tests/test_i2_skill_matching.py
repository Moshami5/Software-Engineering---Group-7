"""I2 (integration): Model 2 + ESCO index + thresholds  [FR-13, FR-15, AIR-2]

Real encoder, real ESCO index (skills_clean.csv), real thresholds.json: no mocks.
Uses the held-out altLabel method from Task 2: the query label is REMOVED from the
index first, so the skill has to be found by meaning, not by looking the label up.

Checks:
  1. a held-out alt label finds its skill in the top 5, ranked by score (FR-15)
  2. every accepted match carries an ESCO id and a score in 0-1 (AIR-2)
  3. nonsense input is rejected, i.e. "unmatched" (FR-13)
  4. a clear match (a skill's own name) is kept by the threshold (FR-13)
"""
import numpy as np
import pytest

from src.data_contract import SEED
from src.model_skills import ENCODER_NAME, alt_labels, build_index, load_esco, rank
from src.thresholds import load_thresholds, passes

N_CASES = 25       # fixed sample of skills (seed 42)
MIN_TOP5 = 0.85    # Task 2 measured about 0.93; AIR-2's minimum is still TBD, so this is
                   # a regression guard below the measured value, not an SRS target
ESCO_SKILL_PREFIX = "http://data.europa.eu/esco/skill/"


@pytest.fixture(scope="module")
def encoder():
    """The real production encoder (all-MiniLM-L6-v2)."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(ENCODER_NAME)


@pytest.fixture(scope="module")
def setup(encoder):
    esco = load_esco()
    rng = np.random.default_rng(SEED)
    eligible = [i for i, cell in enumerate(esco["altLabels"]) if len(alt_labels(cell)) >= 2]
    picked = rng.choice(eligible, size=N_CASES, replace=False)

    held_out = esco.copy()
    cases = []                                    # (query, expected ESCO id)
    for i in picked:
        alts = alt_labels(esco.at[i, "altLabels"])
        query = alts[rng.integers(len(alts))]
        held_out.at[i, "altLabels"] = ";".join(a for a in alts if a != query)
        cases.append((query, esco.at[i, "conceptUri"]))
    return cases, build_index(held_out, encoder)


def accepted(text, index, encoder, thresholds):
    """Matches that survive the skill threshold (FR-13, AIR-2)."""
    return [m for m in rank(text, index, encoder, k=5) if passes(m.score, "skill", thresholds)]


def test_i2_heldout_alt_label_found_in_top5(setup, encoder):
    cases, index = setup
    hits = 0
    for query, expected_id in cases:
        top = rank(query, index, encoder, k=5)
        scores = [m.score for m in top]
        assert len(top) <= 5
        assert scores == sorted(scores, reverse=True)       # sorted by score
        hits += expected_id in [m.esco_id for m in top]
    assert hits / len(cases) >= MIN_TOP5


def test_i2_accepted_matches_carry_esco_id_and_score(setup, encoder):
    cases, index = setup
    thresholds = load_thresholds()                          # config/thresholds.json
    for query, _ in cases:
        for m in accepted(query, index, encoder, thresholds):
            assert m.esco_id.startswith(ESCO_SKILL_PREFIX)  # ESCO identifier
            assert 0 <= m.score <= 1                        # similarity score
            assert m.score >= thresholds["skill"]


def test_i2_nonsense_is_unmatched(setup, encoder):
    _, index = setup
    assert accepted("qzxv jkwp", index, encoder, load_thresholds()) == []   # nothing accepted


def test_i2_clear_match_is_kept(setup, encoder):
    _, index = setup
    thresholds = load_thresholds()
    for label in index.labels[:20]:                         # a skill's own name is a clear match
        top = rank(label, index, encoder, k=5)
        assert any(m.label == label and passes(m.score, "skill", thresholds) for m in top)
