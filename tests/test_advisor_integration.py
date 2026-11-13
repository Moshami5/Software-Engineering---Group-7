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
