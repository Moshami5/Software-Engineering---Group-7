"""I1: Model 1 + threshold logic (FR-13, FR-14)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.model_category import classify
from src.thresholds import UNCATEGORISED, load_thresholds, passes


def test_low_confidence_course_is_withheld_and_clear_one_is_kept():
    thresholds = load_thresholds()  # the real config, category = 0.20

    # Vague course: Model 1 is unsure (confidence ~0.15) -> shown as "uncategorised".
    category, confidence = classify("General introduction", "Explore a selection of topics and ideas.")
    shown = category if passes(confidence, "category", thresholds) else UNCATEGORISED
    assert shown == UNCATEGORISED

    # Clear course: confident (~0.69) -> keeps its category.
    category, confidence = classify("Python for Data Science",
                                    "Learn Python, pandas and data analysis for data science projects.")
    assert passes(confidence, "category", thresholds)
    assert category == "Data Science"
