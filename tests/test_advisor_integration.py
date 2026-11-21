"""Integration test for src/advisor.py: one request through FR-1 -> FR-7 on real data.

This is the call the Task 6 AI server makes for every message it takes off the queue.
Skipped where sentence-transformers is not installed.
Run with:  python -m pytest tests/test_advisor_integration.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("sentence_transformers")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.advisor import advise  # noqa: E402
from src.paths import MAX_PATHS, MIN_PATHS  # noqa: E402


def test_request_in_json_paths_out_json():
    request = json.loads('{"interest": "software developer", "language": "English", '
                         '"hours_per_week": 6, "weeks_available": 20}')

    response = json.loads(json.dumps(advise(request)))

    assert response["ok"] and response["occupations"]
    assert MIN_PATHS <= len(response["paths"]) <= MAX_PATHS
    for path in response["paths"]:
        assert path["weeks"] <= 20 and 0 < path["fit"] <= 1 and path["courses"]


def test_paths_on_real_data_are_explained():
    response = advise({"interest": "software developer", "language": "English",
                       "hours_per_week": 6, "weeks_available": 20})

    for path in response["paths"]:
        # FR-8: occupations from real ESCO relations, each with a share between 0 and 1.
        assert path["opens"] and len(path["opens"]) <= 5
        assert all(0 < o["share"] <= 1 and o["skills_covered"] <= o["essential_skills"] for o in path["opens"])
        # FR-9: an occupation was matched, so the gap is a list of required skills.
        assert set(path["closes"]) <= set(response["required_skills"])
        assert len(path["closes"]) <= path["closes_total"]
        # FR-10 + AIR-5: every skill link traced to the course's own text with a score.
        details = path["course_details"]
        assert len(details) == len(path["courses"])
        for detail in details:
            for link in detail["skill_links"]:
                assert link["from_course_skill"] and 0.45 <= link["similarity"] <= 1
        # FR-11: the course weeks add up to the path's total.
        assert abs(sum(d["weeks"] for d in details) - path["weeks"]) < 0.2
