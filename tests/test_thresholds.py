"""U3: threshold comparison tests (FR-13, AIR-3)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.thresholds import passes


@pytest.mark.parametrize(
    "score, expected",
    [
        (0.30, False),  # Below threshold: withhold
        (0.35, True),   # Exactly at threshold: keep
        (0.50, True),   # Above threshold: keep
    ],
)
def test_passes_compares_score_to_threshold(score, expected):
    thresholds = {"skill": 0.35}

    assert passes(score, "skill", thresholds=thresholds) is expected
