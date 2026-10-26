"""Integration tests for Model 1 as a module (FR-14, AIR-1).

These run the real saved pipeline (data/processed/model1_tfidf-logreg.joblib)
through src/model_category.py, together with the data contract, the frozen
split and the recorded results. They fail if the saved model, the module's text
building, or the library versions stop producing the reported behaviour.
Run with:  python -m pytest tests/test_model_category_integration.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from sklearn.metrics import accuracy_score, f1_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_contract import (  # noqa: E402
    DATA_PROCESSED,
    ENGLISH_CATEGORIES,
    INTRO_COL,
    LABEL_COL,
    TITLE_COL,
)
from src.model_category import classify, load_model  # noqa: E402


def _classify_split(name: str) -> tuple[pd.DataFrame, list[str], list[float]]:
    df = pd.read_csv(DATA_PROCESSED / f"{name}.csv")
    results = [classify(t, i) for t, i in zip(df[TITLE_COL], df[INTRO_COL])]
    return df, [c for c, _ in results], [p for _, p in results]


def test_saved_model_predicts_the_contract_categories():
    """The saved pipeline's classes are exactly the 11 categories in data_contract."""
    assert sorted(load_model().classes_) == sorted(ENGLISH_CATEGORIES)


def test_classify_reproduces_recorded_test_metrics():
    """classify() over the frozen test split matches model1_results.json."""
    recorded = json.loads((DATA_PROCESSED / "model1_results.json").read_text(encoding="utf-8"))
    df, predicted, _ = _classify_split("test")

    assert round(accuracy_score(df[LABEL_COL], predicted), 4) == recorded["test_metrics"]["accuracy"]
    assert round(f1_score(df[LABEL_COL], predicted, average="macro"), 4) == recorded["test_metrics"]["macro_f1"]


def test_every_dev_course_gets_a_valid_category_and_confidence():
    """Every dev course gets one of the 11 categories and a confidence in [1/11, 1]."""
    _, predicted, confidence = _classify_split("dev")

    assert set(predicted) <= set(ENGLISH_CATEGORIES)
    # The top probability of 11 classes can never be below 1/11.
    assert all(1 / len(ENGLISH_CATEGORIES) <= p <= 1 for p in confidence)


@pytest.mark.parametrize("title, intro, expected", [
    ("Learn Spanish", "Speak Spanish with confidence in everyday conversations.", "Language Learning"),
    ("Introduction to Python", "Learn programming basics with Python.", "Computer Science"),
    ("Financial Accounting", "Understand balance sheets, income statements and cash flow.", "Business"),
    ("Anatomy of the human body", "Explore the organs, muscles and systems of the human body.", "Health"),
    ("Machine Learning", "Build predictive models from data using regression and classification.", "Data Science"),
])
def test_known_courses_get_expected_category(title, intro, expected):
    """Unambiguous unseen courses are classified into the obvious category."""
    category, _ = classify(title, intro)
    assert category == expected
