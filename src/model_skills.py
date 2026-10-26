"""Model 2: free-text course skill -> ESCO skills (SRS FR-15, AIR-2).

Interface agreed in Sprint 1 (docs/INTERFACES.md). The implementation belongs to
the card "[FR-15 · AIR-2] Package Model 2 (ESCO skill matcher) as a module":
embed the ESCO_INDEX_CSV labels once with all-MiniLM-L6-v2 (normalised), then
rank by cosine similarity, as in notebooks/model2_esco_matcher.ipynb.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_contract import ESCO_INDEX_CSV  # noqa: E402,F401


class SkillMatch(NamedTuple):
    esco_id: str   # ESCO conceptUri
    label: str     # ESCO preferredLabel
    score: float   # cosine similarity; higher is closer


def match(skill_text: str, k: int = 5) -> list[SkillMatch]:
    """Return at most ``k`` ESCO skills for one course skill, best first.

    Scores are sorted from high to low. No thresholding here: dropping weak
    matches is src/thresholds.py's job (FR-13).
    """
    raise NotImplementedError("Model 2 card: build the ESCO embedding index and rank by cosine")
