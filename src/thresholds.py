"""Withholding low-confidence AI outputs (SRS FR-13, AIR-3).

Interface agreed in Sprint 1 (docs/INTERFACES.md). The implementation belongs to
the card "[FR-13 · AIR-3] Threshold config + withholding low-confidence matches".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_contract import THRESHOLDS_JSON  # noqa: E402,F401

KINDS = ("category", "occupation", "retrieval", "skill")
UNCATEGORISED = "uncategorised"  # shown instead of a category below threshold
UNMATCHED = "unmatched"          # shown instead of a skill/occupation below threshold


def load_thresholds(path: Path = THRESHOLDS_JSON) -> dict[str, float]:
    """Read config/thresholds.json and return one float per kind in KINDS.

    Should fail loudly if a kind is missing or still null, so an unconfigured
    system never runs.
    """
    raise NotImplementedError("Threshold card")


def passes(score: float, kind: str, thresholds: dict[str, float] | None = None) -> bool:
    """True when ``score`` reaches the threshold for ``kind`` (score >= threshold)."""
    raise NotImplementedError("Threshold card")
