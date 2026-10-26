"""Model 1: course text -> category (SRS FR-14, AIR-1).

Interface agreed in Sprint 1 (docs/INTERFACES.md), implemented by the card
"[FR-14 · AIR-1] Package Model 1 (category classifier) as a module": load
MODEL1_PATH once and answer from predict_proba.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import joblib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_contract import ENGLISH_CATEGORIES, MODEL1_PATH  # noqa: E402

CATEGORIES = ENGLISH_CATEGORIES


def course_text(title: str, intro: str | None) -> str:
    """Build Model 1's input exactly as in training: ``title + ". " + intro``.

    A missing title or intro (None, or NaN from a CSV cell) becomes an empty
    string, as fillna("") did in notebooks/model1_classifier.ipynb.
    """
    title = "" if title is None or title != title else str(title)  # NaN != NaN
    intro = "" if intro is None or intro != intro else str(intro)
    return f"{title}. {intro}".strip()


@lru_cache(maxsize=1)
def load_model():
    """Load the saved pipeline once; later calls reuse it."""
    return joblib.load(MODEL1_PATH)


def classify(title: str, intro: str | None) -> tuple[str, float]:
    """Return ``(category, confidence)`` for one course.

    category   -- one of the 11 entries in CATEGORIES
    confidence -- the highest class probability, between 0 and 1

    No thresholding here: deciding "uncategorised" is src/thresholds.py's job,
    so the raw confidence stays available for explanations (FR-10).
    Raises ValueError when title and intro are both empty: the model would
    still return a category, but it would mean nothing.
    """
    text = course_text(title, intro)
    if text == ".":  # nothing but the separator
        raise ValueError("classify needs a title or an intro")

    model = load_model()
    proba = model.predict_proba([text])[0]
    best = proba.argmax()
    return str(model.classes_[best]), float(proba[best])
