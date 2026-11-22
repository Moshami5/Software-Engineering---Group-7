"""Data + model update pipeline (SRS FR-16, NFR-5, NFR-9, AIR-7).

Takes a new course catalogue and/or ESCO skills file, builds and checks everything in
data/staging/<run_id>/, and only replaces the live files if all acceptance checks pass.
Otherwise the previous version stays in use. Every run writes a version record.

Run from the repo root:
  python scripts/update_pipeline.py --catalogue NEW_courses.csv --catalogue-version 2026-12 \
      [--esco NEW_skills.csv --esco-release "ESCO v1.x.x"] [--dry-run]

Exit code: 0 = activated (or dry run passed), 1 = rejected, 2 = error.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from src import data_contract as dc  # noqa: E402


@dataclass
class Paths:
    processed: Path = dc.DATA_PROCESSED
    live_catalogue: Path = dc.COURSES_CSV
    live_esco: Path = dc.ESCO_INDEX_CSV
    model: Path = dc.MODEL1_PATH
    thresholds: Path = dc.THRESHOLDS_JSON
    criteria: Path = REPO_ROOT / "config" / "acceptance_criteria.json"
    staging_root: Path = dc.DATA_RAW / "staging"
    releases_root: Path = dc.DATA_RAW / "releases"

    @property
    def enriched(self) -> Path:
        return self.processed / "catalogue_enriched.csv"

    @property
    def skill_matches(self) -> Path:
        return self.processed / "skill_matches.csv"

    @property
    def version_record(self) -> Path:
        return self.processed / "version_record.json"


@dataclass
class Result:
    run_id: str
    activated: bool
    checks: list = field(default_factory=list)
    record: dict = field(default_factory=dict)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_prepare_module():
    path = REPO_ROOT / "scripts" / "prepare_catalogue.py"
    spec = importlib.util.spec_from_file_location("prepare_catalogue", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail}


def validate_inputs(courses: pd.DataFrame, esco: pd.DataFrame | None, crit: dict, prep) -> list[dict]:
    checks = []
    needed = [dc.ID_COL, dc.SITE_COL, dc.TITLE_COL, dc.INTRO_COL, dc.LABEL_COL, dc.SKILLS_COL]
    missing = [c for c in needed if c not in courses.columns]
    checks.append(check("catalogue has the expected columns", not missing,
                        f"missing: {missing}" if missing else f"all {len(needed)} present"))
    if missing:
        return checks

    checks.append(check("catalogue is big enough", len(courses) >= crit["min_courses"],
                        f"{len(courses)} courses (minimum {crit['min_courses']})"))
    labels = courses[dc.LABEL_COL].map(prep.known_label).dropna()
    counts = labels.value_counts()
    short = [c for c in dc.ENGLISH_CATEGORIES if counts.get(c, 0) < crit["min_labelled_per_category"]]
    checks.append(check("every category has enough labelled courses", not short,
                        f"too few in: {short}" if short else
                        f"smallest category has {int(counts.min())} (minimum {crit['min_labelled_per_category']})"))
    if esco is not None:
        esco_missing = [c for c in ("conceptUri", "preferredLabel", "altLabels") if c not in esco.columns]
        checks.append(check("ESCO file has the expected columns", not esco_missing,
                            f"missing: {esco_missing}" if esco_missing else "conceptUri, preferredLabel, altLabels"))
        if not esco_missing:
            checks.append(check("ESCO file is big enough", len(esco) >= crit["min_esco_skills"],
                                f"{len(esco)} skills (minimum {crit['min_esco_skills']})"))
    return checks


def train_model1(courses: pd.DataFrame, prep, seed: int):
    """Retrain Model 1 like the notebook: same settings, 70/15/15 stratified split, test scored once."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline

    df = courses.copy()
    df["label"] = df[dc.LABEL_COL].map(prep.known_label)
    df = df.dropna(subset=["label"]).drop_duplicates(subset=dc.DEDUP_KEYS)
    df["text"] = (df[dc.TITLE_COL].fillna("") + ". " + df[dc.INTRO_COL].fillna("")).str.strip()

    held_out = dc.DEV_FRAC + dc.TEST_FRAC
    train, rest = train_test_split(df, test_size=held_out, stratify=df["label"], random_state=seed)
    dev, test = train_test_split(rest, test_size=dc.TEST_FRAC / held_out, stratify=rest["label"], random_state=seed)

    model = Pipeline([
        ("tfidf", TfidfVectorizer(sublinear_tf=True, min_df=2, ngram_range=(1, 2), stop_words="english")),
        ("clf", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=seed)),
    ])
    t0 = time.perf_counter()
    model.fit(train["text"], train["label"])
    train_s = time.perf_counter() - t0

    def score(part):
        pred = model.predict(part["text"])
        return (round(float(accuracy_score(part["label"], pred)), 4),
                round(float(f1_score(part["label"], pred, average="macro")), 4))

    dev_acc, dev_f1 = score(dev)
    test_acc, test_f1 = score(test)
    metrics = {
        "model": "tfidf-logreg",
        "split_sizes": {"train": len(train), "dev": len(dev), "test": len(test)},
        "train_seconds": round(train_s, 2),
        "dev_accuracy": dev_acc, "dev_macro_f1": dev_f1,
        "test_accuracy": test_acc, "test_macro_f1": test_f1,
    }
    return model, metrics


def make_classify(model):
    def classify(title, intro):
        text = ((title if isinstance(title, str) else "") + ". " +
                (intro if isinstance(intro, str) else "")).strip(". ").strip()
        if not text:
            raise ValueError("classify needs a title or an intro")
        proba = model.predict_proba([text])[0]
        best = int(proba.argmax())
        return str(model.classes_[best]), float(proba[best])
    return classify


def acceptance_checks(crit, metrics, baseline_f1, catalogue, skill_matches, stats, courses,
                      live_enriched_cols, live_matches_cols, lookup_ms_max) -> list[dict]:
    checks = []
    checks.append(check("Model 1 test macro-F1 above the minimum",
                        metrics["test_macro_f1"] >= crit["min_test_macro_f1"],
                        f"{metrics['test_macro_f1']} (minimum {crit['min_test_macro_f1']})"))
    if baseline_f1 is None:
        checks.append(check("Model 1 not worse than the active model", True,
                            "skipped: no active evaluation found"))
    else:
        floor = round(baseline_f1 - crit["max_macro_f1_drop_vs_active"], 4)
        checks.append(check("Model 1 not worse than the active model",
                            metrics["test_macro_f1"] >= floor,
                            f"{metrics['test_macro_f1']} vs active {baseline_f1} (allowed drop "
                            f"{crit['max_macro_f1_drop_vs_active']}, floor {floor})"))
    checks.append(check("every course is in the batch output", len(catalogue) == len(courses),
                        f"{len(catalogue)} of {len(courses)} courses"))
    bad_cats = set(catalogue["category"].dropna()) - set(dc.ENGLISH_CATEGORIES)
    checks.append(check("every category is one of the 11 defined", not bad_cats,
                        f"unknown: {sorted(bad_cats)}" if bad_cats else "ok"))
    unmatched = stats["distinct_course_skills"] - skill_matches["course_skill"].nunique()
    checks.append(check("every course skill got ESCO matches", unmatched == 0,
                        f"{unmatched} course skills without any match"))
    scores_ok = bool(skill_matches["score"].between(-1.0001, 1.0001).all()) if len(skill_matches) else False
    checks.append(check("similarity scores are valid (-1 to 1)", scores_ok, f"{len(skill_matches)} rows"))
    if live_enriched_cols is not None:
        same = list(catalogue.columns) == live_enriched_cols and list(skill_matches.columns) == live_matches_cols
        checks.append(check("output files keep the same columns as the active version", same,
                            "interfaces unchanged" if same else "columns differ from the active files"))
    checks.append(check("lookups are fast enough (NFR-4)", lookup_ms_max < crit["max_lookup_ms"],
                        f"slowest lookup {lookup_ms_max:.1f} ms (limit {crit['max_lookup_ms']} ms)"))
    return checks


def time_lookups(skill_matches, rank_fn, n: int = 20) -> float:
    skills = list(skill_matches["course_skill"].drop_duplicates().head(n))
    if not skills:
        return float("inf")
    rank_fn(skills[0])
    times = []
    for s in skills:
        t0 = time.perf_counter()
        rank_fn(s)
        times.append((time.perf_counter() - t0) * 1000)
    return max(times)


def activate(pairs: list[tuple[Path, Path]], backup_dir: Path) -> None:
    """Replace each live file with its staged copy, keeping a backup; undo if anything fails."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    replaced: list[Path] = []
    try:
        for dest, src in pairs:
            if dest.exists():
                shutil.copy2(dest, backup_dir / dest.name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".new")
            shutil.copy2(src, tmp)
            os.replace(tmp, dest)
            replaced.append(dest)
    except Exception:
        for dest in replaced:
            saved = backup_dir / dest.name
            if saved.exists():
                shutil.copy2(saved, dest)
            else:
                dest.unlink(missing_ok=True)
        raise


def run_update(paths: Paths, catalogue_path: Path, esco_path: Path | None, catalogue_version: str,
               esco_release: str, dry_run: bool = False, encoder=None, run_id: str | None = None) -> Result:
    import joblib
    from src import model_skills as ms

    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # Load the encoder (PyTorch) before Model 1 is trained: on Windows, importing torch
    # after scikit-learn has trained fails with "WinError 127 ... torch\lib\shm.dll".
    encoder = encoder or ms.load_encoder()
    crit = json.loads(paths.criteria.read_text(encoding="utf-8"))
    prep = load_prepare_module()
    stage = paths.staging_root / run_id
    stage.mkdir(parents=True, exist_ok=True)

    staged_catalogue = stage / "catalogue.csv"
    shutil.copy2(catalogue_path, staged_catalogue)
    staged_esco = None
    if esco_path is not None:
        staged_esco = stage / "esco_skills.csv"
        shutil.copy2(esco_path, staged_esco)
    esco_for_index = staged_esco or paths.live_esco

    courses = pd.read_csv(staged_catalogue, low_memory=False)
    esco_df = pd.read_csv(staged_esco, low_memory=False) if staged_esco else None
    checks = validate_inputs(courses, esco_df, crit, prep)

    metrics, stats, record_extra = {}, {}, {}
    candidate_files: list[tuple[Path, Path]] = []
    if all(c["passed"] for c in checks):
        model, metrics = train_model1(courses, prep, dc.SEED)
        staged_model = stage / paths.model.name
        joblib.dump(model, staged_model, compress=3)

        t0 = time.perf_counter()
        esco_table = ms.load_esco(esco_for_index)
        index = ms.build_index(esco_table, encoder)
        index_s = time.perf_counter() - t0
        rank_fn = lambda skill, k=prep.TOP_K: ms.rank(skill, index, encoder, k)  # noqa: E731
        catalogue, skill_matches, stats = prep.prepare(courses, make_classify(model), rank_fn, prep.TOP_K)
        stats["index_build_seconds"] = round(index_s, 2)
        stats["esco_skills_indexed"] = len(esco_table)
        catalogue.to_csv(stage / "catalogue_enriched.csv", index=False, encoding="utf-8")
        skill_matches.to_csv(stage / "skill_matches.csv", index=False, encoding="utf-8")

        baseline = None
        if paths.version_record.exists():
            baseline = json.loads(paths.version_record.read_text(encoding="utf-8")).get(
                "evaluation", {}).get("test_macro_f1")
        legacy = paths.processed / "model1_results.json"
        if baseline is None and legacy.exists():
            baseline = json.loads(legacy.read_text(encoding="utf-8")).get("test_metrics", {}).get("macro_f1")
        live_enriched_cols = list(pd.read_csv(paths.enriched, nrows=0).columns) if paths.enriched.exists() else None
        live_matches_cols = list(pd.read_csv(paths.skill_matches, nrows=0).columns) if paths.skill_matches.exists() else None
        lookup_ms = time_lookups(skill_matches, rank_fn)
        checks += acceptance_checks(crit, metrics, baseline, catalogue, skill_matches, stats, courses,
                                    live_enriched_cols, live_matches_cols, lookup_ms)
        record_extra = {"active_test_macro_f1_before": baseline, "slowest_lookup_ms": round(lookup_ms, 2)}
        candidate_files = [
            (paths.model, staged_model),
            (paths.enriched, stage / "catalogue_enriched.csv"),
            (paths.skill_matches, stage / "skill_matches.csv"),
            (paths.live_catalogue, staged_catalogue),
        ]
        if staged_esco is not None:
            candidate_files.append((paths.live_esco, staged_esco))

    passed = all(c["passed"] for c in checks)
    thresholds = json.loads(paths.thresholds.read_text(encoding="utf-8")) if paths.thresholds.exists() else None

    import sklearn
    record = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "activated" if (passed and not dry_run) else ("dry-run passed" if passed else "rejected"),
        "classifier": {"name": "tfidf-logreg", "version": f"model1-{run_id}", "seed": dc.SEED,
                       "scikit_learn": sklearn.__version__},
        "semantic_model": ms.ENCODER_NAME,
        "esco": {"release": (esco_release or "not stated (identified by file hash)") if esco_path is not None
                   else "unchanged (previous release kept)",
                 "file": (esco_path.name if esco_path is not None else paths.live_esco.name),
                 "sha256": sha256(esco_for_index) if Path(esco_for_index).exists() else None,
                 "skills_indexed": stats.get("esco_skills_indexed")},
        "catalogue": {"version": catalogue_version, "file": catalogue_path.name,
                      "sha256": sha256(staged_catalogue), "courses": len(courses)},
        "thresholds": thresholds,
        "evaluation": metrics,
        "batch_stats": stats,
        "acceptance_criteria": crit,
        "checks": checks,
        **record_extra,
    }
    release_dir = paths.releases_root / run_id
    release_dir.mkdir(parents=True, exist_ok=True)
    (release_dir / "version_record.json").write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")

    activated = False
    if passed and not dry_run:
        staged_record = stage / "version_record.json"
        staged_record.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        activate(candidate_files + [(paths.version_record, staged_record)], release_dir / "previous")
        activated = True
    return Result(run_id=run_id, activated=activated, checks=checks, record=record)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalogue", type=Path, required=True, help="new course catalogue CSV (same columns as the current one)")
    ap.add_argument("--catalogue-version", required=True, help="label for this catalogue, e.g. 2026-12")
    ap.add_argument("--esco", type=Path, help="new ESCO skills CSV (needs conceptUri, preferredLabel, altLabels)")
    ap.add_argument("--esco-release", help='ESCO release name, e.g. "ESCO v1.2.0" (optional; the file hash is always recorded)')
    ap.add_argument("--dry-run", action="store_true", help="run every step and check, but do not replace anything")
    args = ap.parse_args(argv)
    result = run_update(Paths(), args.catalogue, args.esco, args.catalogue_version,
                        args.esco_release or "", dry_run=args.dry_run)
    for c in result.checks:
        print(f"[{'PASS' if c['passed'] else 'FAIL'}] {c['name']}: {c['detail']}")
    print(f"\nRun {result.run_id}: {result.record['status'].upper()}")
    print(f"Version record: {Paths().releases_root / result.run_id / 'version_record.json'}")
    if not result.activated and not all(c["passed"] for c in result.checks):
        print("The previous version stays in use.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
