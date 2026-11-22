"""Tests for scripts/bias_eval.py (AIR-6, NFR-7: paired-input bias evaluation).

The unit tests use hand-made advise() responses, so they check the pairing and the
comparison logic only. The last test runs one real pair through the whole chain.
Run with:  python -m pytest tests/test_bias_eval.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.bias_eval import (  # noqa: E402
    DIMENSIONS,
    INTERESTS,
    TEMPLATES,
    build_pairs,
    compare,
    differences,
    evaluate,
    score_gaps,
    summarise,
)
from src.interest import MAX_INTEREST_CHARS  # noqa: E402


def response(occupations=(), paths=()):
    """A minimal advise() response: occupation labels and paths as lists of course keys."""
    return {"ok": True, "message": None,
            "occupations": [{"label": o, "score": 0.6} for o in occupations],
            "paths": [{"courses": [{"course_key": k} for k in p]} for p in paths]}


def test_pairs_cover_every_interest_dimension_and_template():
    pairs = build_pairs()
    assert len(pairs) == len(INTERESTS) * len(DIMENSIONS) * len(TEMPLATES)


def test_paired_inputs_differ_only_in_the_descriptor():
    for pair in build_pairs():
        a, b = DIMENSIONS[pair.dimension]
        assert pair.text_a.replace(a, "{d}") == pair.text_b.replace(b, "{d}")
        assert pair.interest in pair.text_a and pair.interest in pair.text_b
        assert len(pair.text_a) <= MAX_INTEREST_CHARS  # valid FR-1 input


def test_identical_responses_are_identical():
    r = summarise(response(["software developer"], [["c1", "c2"], ["c3"]]))
    result = compare(r, r)
    assert result["identical"] and differences(result) == []
    assert result["course_jaccard"] == 1.0


def test_same_courses_in_another_order_is_a_ranking_difference():
    a = summarise(response(["x"], [["c1"], ["c2"]]))
    b = summarise(response(["x"], [["c2"], ["c1"]]))
    result = compare(a, b)
    assert result["same_courses"] and not result["same_ranking"]
    assert differences(result) == ["ranking"]


def test_losing_all_paths_differs_in_everything():
    a = summarise(response(["software developer"], [["c1", "c2"]]))
    b = summarise(response([], []))
    result = compare(a, b)
    assert differences(result) == ["occupations", "courses", "ranking"]
    assert result["n_paths"] == [1, 0] and result["course_jaccard"] == 0.0


def test_occupation_order_counts():
    a = summarise(response(["data scientist", "data engineer"]))
    b = summarise(response(["data engineer", "data scientist"]))
    result = compare(a, b)
    assert not result["same_occupations"] and result["occupation_jaccard"] == 1.0


def test_evaluate_runs_each_input_once_and_finds_the_difference():
    """A fake chain that only recommends when the text says "man" must be caught."""
    calls = []

    def run(text):
        calls.append(text)
        return response(["software developer"], [["c1"]]) if " man" in text else response()

    pairs = [p for p in build_pairs(interests=("software developer",)) if p.dimension == "gender"]
    result = evaluate(pairs, run, lambda text: [("software developer", 0.6)])

    assert len(calls) == len(set(calls))  # every distinct input is run once
    assert all(not r["a_vs_b"]["identical"] for r in result["records"])
    assert all(r["a_vs_b"]["n_paths"] == [0, 1] for r in result["records"])


def test_score_gaps_show_a_systematic_lean():
    pairs = [p for p in build_pairs(interests=("software developer", "web developer"))
             if p.dimension == "gender"]
    scores = {p.text_a: 0.50 for p in pairs} | {p.text_b: 0.55 for p in pairs}
    result = evaluate(pairs, lambda t: response(), lambda t: [("x", scores.get(t, 0.6))])

    gender = next(g for g in score_gaps(result["records"], result["outcomes"])
                  if g["dimension"] == "gender")
    assert gender["a_higher"] == 0 and gender["mean_gap"] == pytest.approx(-0.05)


def test_real_chain_records_a_pair():
    """One real pair through advise(): the record has every field AIR-6 asks for."""
    pytest.importorskip("sentence_transformers")
    from scripts.bias_eval import real_runner

    pairs = [p for p in build_pairs(interests=("software developer",))
             if p.dimension == "gender" and p.template == "suffix"]
    result = evaluate(pairs, *real_runner())

    record = result["records"][0]
    for key in ("a_vs_b", "a_vs_neutral", "b_vs_neutral"):
        assert {"same_occupations", "same_courses", "same_ranking", "identical"} <= set(record[key])
    assert result["outcomes"]["software developer"]["raw_top3"][0][0] == "software developer"
