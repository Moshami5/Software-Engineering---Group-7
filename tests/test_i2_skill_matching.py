"""I2 (integration): Model 2 + ESCO index + thresholds  [FR-15, AIR-2, FR-13]

Real encoder, real ESCO index (skills_clean.csv), real thresholds.json: no mocks.
Uses the held-out altLabel method from Task 2: the query label is REMOVED from the
index first, so the skill has to be found by meaning, not by looking the label up.
"""
import numpy as np
import pytest

from src.data_contract import SEED
from src.model_skills import alt_labels, build_index, load_esco, rank
from src.thresholds import load_thresholds, passes

N_CASES = 25       # fixed sample of skills (seed 42)
MIN_TOP5 = 0.85    # Task 2 measured about 0.93; the margin keeps CI from being flaky


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


def test_i2_threshold_withholds_weak_matches(setup, encoder):
    _, index = setup
    thresholds = load_thresholds()                          # config/thresholds.json
    weak = rank("qzxv jkwp", index, encoder, k=5)           # nonsense: nothing should pass
    assert not any(passes(m.score, "skill", thresholds) for m in weak)
