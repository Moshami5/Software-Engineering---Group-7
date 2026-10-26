"""Model 1 as a module: classify a course into one of the 11 categories (FR-14, AIR-1).

Loads the dev-selected pipeline (TF-IDF + logistic regression, saved by
notebooks/model1_classifier.ipynb) and exposes

    classify(title, intro) -> (category, confidence)

where confidence is the top predict_proba score (0-1). Withholding
low-confidence results as "uncategorised" is FR-13 and lives in its own card;
this module returns the raw prediction so that threshold can be chosen on
validation data (AIR-3).
"""
from __future__ import annotations

from functools import lru_cache

import joblib

from src.data_contract import MODEL1_PATH


def _as_text(value) -> str:
    """Missing values become "" - None, and NaN as pandas reads empty CSV cells."""
    return value if isinstance(value, str) else ""


def build_text(title: str | None, intro: str | None) -> str:
    """Build the model input exactly as the training notebook did.

    Notebook: (title.fillna("") + ". " + intro.fillna("")).str.strip()
    Any drift here is training/serving skew, so it is unit-tested on its own.
    """
    return (_as_text(title) + ". " + _as_text(intro)).strip()


@lru_cache(maxsize=1)
def load_model():
    """Load the saved pipeline once; later calls reuse it."""
    return joblib.load(MODEL1_PATH)


def classify(title: str | None, intro: str | None) -> tuple[str, float]:
    """Return (category, confidence) for one course.

    Raises ValueError when both title and intro are empty: the model would
    still return a category, but it would mean nothing.
    """
    if not _as_text(title).strip() and not _as_text(intro).strip():
        raise ValueError("classify needs a title or an intro")

    model = load_model()
    proba = model.predict_proba([build_text(title, intro)])[0]
    best = proba.argmax()
    return str(model.classes_[best]), float(proba[best])
