"""Unit tests for src/model_category.py (FR-14, AIR-1).

Each test checks one function on its own. classify() is tested against a fake
model (fixed probabilities) instead of the saved pipeline, so these tests cover
the module's own logic - text building, input checks, picking the top class -
and nothing else. The real pipeline is covered in
test_model_category_integration.py.
Run with:  python -m pytest tests/test_model_category.py -q
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import model_category  # noqa: E402
from src.model_category import build_text, classify  # noqa: E402


class FakeModel:
    """Stands in for the sklearn pipeline: fixed classes and probabilities."""

    classes_ = np.array(["Business", "Computer Science", "Health"])

    def __init__(self, proba):
        self.proba = np.array([proba])
        self.seen = None

    def predict_proba(self, texts):
        self.seen = texts
        return self.proba


@pytest.fixture
def fake_model(monkeypatch):
    model = FakeModel([0.2, 0.7, 0.1])
    monkeypatch.setattr(model_category, "load_model", lambda: model)
    return model


# --- build_text -----------------------------------------------------------

def test_build_text_joins_title_and_intro():
    """Title and intro are joined with ". ", as in the training notebook."""
    assert build_text("Python", "Learn the basics") == "Python. Learn the basics"


@pytest.mark.parametrize("missing", [None, float("nan")])
def test_build_text_treats_missing_intro_as_empty(missing):
    """A missing intro (None, or NaN from a CSV) gives the title alone."""
    assert build_text("Python", missing) == "Python."


# --- classify -------------------------------------------------------------

def test_classify_returns_top_class_and_its_probability(fake_model):
    """The category is the highest-probability class; confidence is that probability."""
    category, confidence = classify("Python", "Learn the basics")
    assert category == "Computer Science"
    assert confidence == pytest.approx(0.7)


def test_classify_sends_built_text_to_model(fake_model):
    """The model receives exactly the text build_text produces."""
    classify("Python", "Learn the basics")
    assert fake_model.seen == ["Python. Learn the basics"]


def test_classify_returns_plain_python_types(fake_model):
    """Callers get str and float, not numpy types."""
    category, confidence = classify("Python", "Learn the basics")
    assert type(category) is str
    assert type(confidence) is float


@pytest.mark.parametrize("title, intro", [
    ("", ""),
    (None, None),
    ("   ", "\t"),
    (float("nan"), None),
])
def test_classify_refuses_empty_input(monkeypatch, title, intro):
    """No title and no intro raises ValueError before the model is touched."""
    def must_not_load():
        raise AssertionError("model loaded for empty input")

    monkeypatch.setattr(model_category, "load_model", must_not_load)
    with pytest.raises(ValueError):
        classify(title, intro)


def test_classify_accepts_title_without_intro(fake_model):
    """A title alone is enough to classify."""
    category, confidence = classify("Python", None)
    assert category == "Computer Science"
    assert not math.isnan(confidence)
