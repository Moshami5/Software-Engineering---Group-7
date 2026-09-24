"""Frozen-split guard (MODEL_PLAN.md section 6, rule 1).

Once the split is committed it must not change. These tests fail the moment the
committed train/dev/test.csv stop matching the fingerprint recorded in
split_manifest.json, or if the split develops leakage or shape drift. A failure
means: do NOT trust any metric produced after the split changed.

Runs with pytest, or directly:  python tests/test_frozen_split.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_contract import DATA_PROCESSED, DEDUP_KEYS, LABEL_COL, SEED

SPLITS = ("train", "dev", "test")


def _manifest() -> dict:
    return json.loads((DATA_PROCESSED / "split_manifest.json").read_text(encoding="utf-8"))


def _load(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA_PROCESSED / f"{name}.csv")


def test_split_files_exist():
    for name in SPLITS:
        assert (DATA_PROCESSED / f"{name}.csv").exists(), f"missing {name}.csv"
    assert (DATA_PROCESSED / "split_manifest.json").exists(), "missing split_manifest.json"


def test_checksums_match_manifest():
    """The core tripwire: file bytes must match the recorded sha256."""
    recorded = _manifest()["checksums_sha256"]
    for name in SPLITS:
        actual = hashlib.sha256((DATA_PROCESSED / f"{name}.csv").read_bytes()).hexdigest()
        assert actual == recorded[f"{name}.csv"], (
            f"{name}.csv changed since it was frozen - reported metrics are no "
            f"longer comparable. Re-freeze deliberately and update the manifest."
        )


def test_seed_matches_contract():
    assert _manifest()["seed"] == SEED, "manifest seed differs from data_contract.SEED"


def test_split_sizes_match_manifest():
    sizes = _manifest()["split_sizes"]
    for name in SPLITS:
        assert len(_load(name)) == sizes[name], f"{name} row count drifted from manifest"


def test_no_text_leakage_across_splits():
    """No course text may appear in more than one split (section 7 leakage guard)."""
    keyed = {name: set(map(tuple, _load(name)[DEDUP_KEYS].fillna("").values)) for name in SPLITS}
    assert not (keyed["train"] & keyed["dev"]), "train/dev overlap"
    assert not (keyed["train"] & keyed["test"]), "train/test overlap"
    assert not (keyed["dev"] & keyed["test"]), "dev/test overlap"


def test_all_classes_present_in_every_split():
    labels = {name: set(_load(name)[LABEL_COL]) for name in SPLITS}
    assert labels["train"] == labels["dev"] == labels["test"], (
        "a category is missing from one of the splits"
    )


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests)-failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
