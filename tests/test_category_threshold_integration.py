"""I1: Model 1 + threshold logic (FR-13, FR-14)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.model_category import CATEGORIES, classify
from src.thresholds import UNCATEGORISED, passes


def test_low_confidence_category_is_withheld():
    # Deliberately vague course text.
    title = "General introduction"
    intro = "Explore a selection of topics and ideas."

    # Fixed test threshold, not the production configuration.
    thresholds = {"category": 1.0}

    # Run the real saved Model 1 pipeline.
    category, confidence = classify(title, intro)

    assert category in CATEGORIES
    assert 0.0 <= confidence < thresholds["category"]

    # Apply the real threshold function to the model output.
    displayed_category = (
        category
        if passes(confidence, "category", thresholds=thresholds)
        else UNCATEGORISED
    )

    assert displayed_category == "uncategorised"
