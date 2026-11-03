"""Integration test for the whole advisor chain FR-3 -> FR-7 on real data.

interest -> required skills (src/occupations.py) -> candidate courses (src/retrieval.py)
-> feasible courses (src/feasibility.py, context from src/study_context.py)
-> ranked study paths (src/paths.py). Skipped where sentence-transformers is not installed.
Run with:  python -m pytest tests/test_advisor_chain_integration.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("sentence_transformers")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.feasibility import assess, load_facts  # noqa: E402
from src.occupations import derive_required_skills  # noqa: E402
from src.paths import MAX_PATHS, MIN_PATHS, build_paths, load_durations  # noqa: E402
from src.retrieval import retrieve_for  # noqa: E402
from src.study_context import validate_study_context  # noqa: E402


def test_software_developer_gets_three_to_five_paths_that_fit():
    context = validate_study_context(language="English", hours_per_week=6, weeks_available=20).value
    required = derive_required_skills("software developer").skills
    candidates = retrieve_for("software developer", required).courses
    feasible = [k.course for k in assess(candidates, context, load_facts()).kept]

    result = build_paths(feasible, required, context, load_durations())

    assert MIN_PATHS <= len(result.paths) <= MAX_PATHS
    assert all(p.weeks <= 20 for p in result.paths)
    fits = [p.fit for p in result.paths]
    assert fits == sorted(fits, reverse=True) and all(0 < f <= 1 for f in fits)
