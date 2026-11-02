"""Batch catalogue preparation (SRS FR-14, FR-15, NFR-4, AIR-8).

Runs both models once over the cleaned catalogue, ahead of time, so the system can
look results up when a student asks instead of running the models per request:

- Model 1 (src/model_category.classify): every course gets a category. A course that
  already has a label keeps it; the others get the predicted one (FR-14).
- Model 2 (src/model_skills.match): every distinct course skill gets its top-k ESCO
  skills (FR-15). There are ~4.2k distinct strings, each matched once and reused.

Scores are stored raw. Thresholds (FR-13) are applied when results are shown, so this
step does not depend on them.

Writes to data/processed/:
  catalogue_enriched.csv    one row per course
  skill_matches.csv         one row per (course skill, rank)
  catalogue_prep_stats.json counts and run times (input for the Task 7 carbon footprint)

Run from the repo root:  python scripts/prepare_catalogue.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_contract import (  # noqa: E402
    COURSES_CSV,
    DATA_PROCESSED,
    ENGLISH_CATEGORIES,
    ID_COL,
    INTRO_COL,
    LABEL_COL,
    LOCALISED_LABEL_MAP,
    SITE_COL,
    SKILLS_COL,
    TITLE_COL,
)

TOP_K = 5
SKILL_SEPARATOR = " | "  # joins a course's normalised skills in catalogue_enriched.csv


def normalise_skill(text: str) -> str:
    """Lower-case and collapse whitespace, as the Model 2 notebook did."""
    return re.sub(r"\s+", " ", str(text).strip().lower())


def split_skills(cell) -> list[str]:
    """A course's comma-separated skills, normalised, empties and repeats dropped.

    Same splitting as notebooks/model2_esco_matcher.ipynb (newlines count as commas),
    so the distinct strings are the ones its 4,229 figure counts.
    """
    if not isinstance(cell, str):
        return []
    seen = []
    for part in cell.replace("\n", ",").split(","):
        skill = normalise_skill(part)
        if skill and skill not in seen:
            seen.append(skill)
    return seen


def known_label(label) -> str | None:
    """The course's own category in English, or None if it has no usable label."""
    if not isinstance(label, str):
        return None
    label = LOCALISED_LABEL_MAP.get(label, label)
    return label if label in ENGLISH_CATEGORIES else None


def prepare(courses: pd.DataFrame, classify, match, k: int = TOP_K):
    """Enrich ``courses`` using ``classify(title, intro)`` and ``match(skill, k)``.

    Returns (catalogue, skill_matches, stats). The models are passed in so this can be
    tested with fakes.
    """
    rows = []
    t0 = time.perf_counter()
    for course in courses.itertuples(index=False):
        title, intro = getattr(course, TITLE_COL), getattr(course, INTRO_COL)
        try:
            predicted, confidence = classify(title, intro)
        except ValueError:  # no title and no intro: nothing to classify
            predicted, confidence = None, None
        label = known_label(getattr(course, LABEL_COL))
        skills = split_skills(getattr(course, SKILLS_COL))
        rows.append({
            ID_COL: getattr(course, ID_COL),
            SITE_COL: getattr(course, SITE_COL),
            TITLE_COL: title,
            "category": label or predicted,
            "category_source": "label" if label else ("model" if predicted else "none"),
            "predicted_category": predicted,
            "predicted_confidence": confidence,
            "skills_normalised": SKILL_SEPARATOR.join(skills),
        })
    classify_s = time.perf_counter() - t0
    catalogue = pd.DataFrame(rows)

    distinct = sorted({s for joined in catalogue["skills_normalised"] if joined
                       for s in joined.split(SKILL_SEPARATOR)})
    t0 = time.perf_counter()
    match_rows = [
        {"course_skill": skill, "rank": rank, "esco_id": m.esco_id, "esco_label": m.label, "score": m.score}
        for skill in distinct
        for rank, m in enumerate(match(skill, k), start=1)
    ]
    match_s = time.perf_counter() - t0
    skill_matches = pd.DataFrame(match_rows, columns=["course_skill", "rank", "esco_id", "esco_label", "score"])

    stats = {
        "courses": int(len(catalogue)),
        "category_source": {k_: int(v) for k_, v in catalogue["category_source"].value_counts().items()},
        "courses_with_skills": int((catalogue["skills_normalised"] != "").sum()),
        "distinct_course_skills": len(distinct),
        "top_k": k,
        "classify_seconds": round(classify_s, 2),
        "match_seconds": round(match_s, 2),
    }
    return catalogue, skill_matches, stats


def main() -> None:
    from src.model_category import classify
    from src.model_skills import load_index, match

    courses = pd.read_csv(COURSES_CSV, low_memory=False)
    t0 = time.perf_counter()
    load_index()  # build the ESCO embedding index once, timed separately
    index_s = time.perf_counter() - t0

    catalogue, skill_matches, stats = prepare(courses, classify, match)
    stats["index_build_seconds"] = round(index_s, 2)
    stats["total_seconds"] = round(index_s + stats["classify_seconds"] + stats["match_seconds"], 2)

    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    catalogue.to_csv(DATA_PROCESSED / "catalogue_enriched.csv", index=False, encoding="utf-8")
    skill_matches.to_csv(DATA_PROCESSED / "skill_matches.csv", index=False, encoding="utf-8")
    (DATA_PROCESSED / "catalogue_prep_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
