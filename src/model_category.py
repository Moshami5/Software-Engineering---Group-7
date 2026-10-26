"""Model 1: course text -> category (SRS FR-14, AIR-1).

Interface agreed in Sprint 1 (docs/INTERFACES.md). The implementation belongs to
the card "[FR-14 · AIR-1] Package Model 1 (category classifier) as a module":
load MODEL1_PATH once and answer from predict_proba.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_contract import ENGLISH_CATEGORIES, MODEL1_PATH  # noqa: E402,F401

CATEGORIES = ENGLISH_CATEGORIES


def course_text(title: str, intro: str | None) -> str:
    """Build Model 1's input exactly as in training: ``title + ". " + intro``.

    A missing intro becomes an empty string, as in notebooks/model1_classifier.ipynb.
    """
    title = "" if title is None else str(title)
    intro = "" if intro is None or intro != intro else str(intro)  # NaN != NaN
    return f"{title}. {intro}".strip()


def classify(title: str, intro: str | None) -> tuple[str, float]:
    """Return ``(category, confidence)`` for one course.

    category   -- one of the 11 entries in CATEGORIES
    confidence -- the highest class probability, between 0 and 1

    No thresholding here: deciding "uncategorised" is src/thresholds.py's job,
    so the raw confidence stays available for explanations (FR-10).
    """
    raise NotImplementedError("Model 1 card: load MODEL1_PATH and use predict_proba")
