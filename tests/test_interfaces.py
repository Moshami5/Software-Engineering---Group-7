"""Guards for the module interfaces agreed in Sprint 1 (docs/INTERFACES.md).

These pin the contract the other cards build against, so a change to it shows
up as a failing test instead of a surprise in someone else's code.

Runs with pytest:  python -m pytest tests/test_interfaces.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_contract import THRESHOLDS_JSON  # noqa: E402
from src.model_category import CATEGORIES, course_text  # noqa: E402
from src.model_skills import SkillMatch  # noqa: E402
from src.thresholds import KINDS  # noqa: E402


def test_course_text_joins_title_and_intro_like_training():
    assert course_text("Intro to Python", "Learn the basics.") == "Intro to Python. Learn the basics."


def test_course_text_handles_missing_intro():
    assert course_text("Intro to Python", None) == "Intro to Python."
    assert course_text("Intro to Python", float("nan")) == "Intro to Python."


def test_eleven_categories():
    assert len(CATEGORIES) == 11


def test_skill_match_fields():
    m = SkillMatch(esco_id="http://data.europa.eu/esco/skill/x", label="Python", score=0.9)
    assert (m.esco_id, m.label, m.score) == ("http://data.europa.eu/esco/skill/x", "Python", 0.9)


def test_thresholds_config_has_every_kind_in_range_or_unset():
    config = json.loads(THRESHOLDS_JSON.read_text(encoding="utf-8"))
    for kind in KINDS:
        assert kind in config, f"missing threshold: {kind}"
        value = config[kind]
        assert value is None or 0.0 <= value <= 1.0, f"{kind} out of range: {value}"
