"""Measure data volume, load/query performance and veracity cross-checks.

Answers the lecturer's Task 2 feedback (1 Oct): real data size and the resources
needed to work with it (Volume), how fast the software processes it (Velocity),
and cross-checks that the data is truthful (Veracity). Reads only from data/
and writes data/processed/data_resources.json, so every number the report
quotes can be regenerated.

Run from the repo root:  python scripts/data_resources.py
"""
from __future__ import annotations

import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_contract import (  # noqa: E402
    COURSES_CSV,
    COURSES_RAW_CSV,
    DATA_PROCESSED,
    DATA_RAW,
    DEDUP_KEYS,
    ESCO_SKILLS_CLEAN_CSV,
    ESCO_SKILLS_FULL_CSV,
    ISCO_CLEAN_CSV,
    LABEL_COL,
    LABEL_SITE,
    OCCUPATIONS_CLEAN_CSV,
    RELATIONS_CLEAN_CSV,
    SITE_COL,
    TITLE_COL,
)

OUT = DATA_PROCESSED / "data_resources.json"
REPEATS = 5
MB = 1024 * 1024

FILES = {
    "Online_Courses.csv": COURSES_RAW_CSV,
    "Online_Courses_ml_features.csv": COURSES_CSV,
    "skills_en.csv": ESCO_SKILLS_FULL_CSV,
    "skills_clean.csv": ESCO_SKILLS_CLEAN_CSV,
    "occupationSkillRelations_en.csv": DATA_RAW / "occupationSkillRelations_en.csv",
    "relations_clean.csv": RELATIONS_CLEAN_CSV,
    "occupations_clean.csv": OCCUPATIONS_CLEAN_CSV,
    "ISCOGroups_en.csv": DATA_RAW / "ISCOGroups_en.csv",
    "isco_clean.csv": ISCO_CLEAN_CSV,
}

# Domain each catalogue site is expected to live on (Veracity: URL vs declared site).
SITE_DOMAINS = {
    "Coursera": "coursera.org",
    "Future Learn": "futurelearn.com",  # spelled with a space in the raw export
    "Udacity": "udacity.com",
    "Simplilearn": "simplilearn.com",
}


def median_seconds(fn, repeats: int = REPEATS) -> float:
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        times.append(time.perf_counter() - start)
    return statistics.median(times)


def volume() -> dict:
    out = {}
    for name, path in FILES.items():
        df = pd.read_csv(path, low_memory=False)
        out[name] = {
            "disk_mb": round(path.stat().st_size / MB, 2),
            "memory_mb": round(df.memory_usage(deep=True).sum() / MB, 2),
            "rows": int(len(df)),
            "columns": int(df.shape[1]),
            "load_s_median": round(median_seconds(lambda p=path: pd.read_csv(p, low_memory=False)), 3),
        }
    out["_total"] = {
        "disk_mb": round(sum(v["disk_mb"] for v in out.values()), 1),
        "memory_mb": round(sum(v["memory_mb"] for v in out.values()), 1),
        "load_s_median": round(sum(v["load_s_median"] for v in out.values()), 2),
    }
    return out


def query_speed() -> dict:
    courses = pd.read_csv(COURSES_CSV, low_memory=False)
    relations = pd.read_csv(RELATIONS_CLEAN_CSV)
    occupation = relations["occupationUri"].iloc[0]
    return {
        "filter_courses_by_category_ms": round(1000 * median_seconds(
            lambda: courses[courses[LABEL_COL] == "Data Science"]), 3),
        "keyword_search_titles_ms": round(1000 * median_seconds(
            lambda: courses[courses[TITLE_COL].str.contains("python", case=False, na=False)]), 3),
        "skills_of_one_occupation_ms": round(1000 * median_seconds(
            lambda: relations[relations["occupationUri"] == occupation]), 3),
    }


def veracity() -> dict:
    raw = pd.read_csv(COURSES_RAW_CSV, low_memory=False)
    raw = raw.dropna(subset=["URL", "Site"])
    domain_ok = raw.apply(
        lambda r: SITE_DOMAINS.get(r["Site"], "?") in urlparse(str(r["URL"])).netloc, axis=1)

    courses = pd.read_csv(COURSES_CSV, low_memory=False)
    labelled = courses[(courses[SITE_COL] == LABEL_SITE) & courses[LABEL_COL].notna()]
    per_text = labelled.groupby(DEDUP_KEYS)[LABEL_COL].nunique()
    repeated = labelled.groupby(DEDUP_KEYS).size()

    skills = pd.read_csv(ESCO_SKILLS_CLEAN_CSV)
    occupations = pd.read_csv(OCCUPATIONS_CLEAN_CSV)
    relations = pd.read_csv(RELATIONS_CLEAN_CSV)
    isco = pd.read_csv(ISCO_CLEAN_CSV)
    isco_codes = set(isco["code"].astype(str))

    return {
        "course_url_matches_declared_site": {
            "checked": int(len(raw)),
            "matching": int(domain_ok.sum()),
            "share": round(float(domain_ok.mean()), 4),
        },
        "labelled_courses_repeated_text": {
            "texts_listed_more_than_once": int((repeated > 1).sum()),
            "texts_with_conflicting_category": int((per_text > 1).sum()),
        },
        "esco_referential_integrity": {
            "relation_skills_found_in_skills": round(float(relations["skillUri"].isin(skills["conceptUri"]).mean()), 4),
            "relation_occupations_found_in_occupations": round(float(relations["occupationUri"].isin(occupations["conceptUri"]).mean()), 4),
            "occupation_isco_groups_found_in_isco": round(float(occupations["iscoGroup"].astype(str).isin(isco_codes).mean()), 4),
        },
    }


def machine() -> dict:
    info = {"python": platform.python_version(), "pandas": pd.__version__,
            "os": f"{platform.system()} {platform.release()}", "cpu": platform.processor(),
            "logical_cpus": os.cpu_count()}
    try:
        import psutil
        info["ram_gb"] = round(psutil.virtual_memory().total / 1024 ** 3, 1)
    except ImportError:
        pass
    return info


def main() -> None:
    result = {"machine": machine(), "volume": volume(), "query_speed": query_speed(), "veracity": veracity()}
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nwritten: {OUT.relative_to(DATA_RAW.parent.parent)}")


if __name__ == "__main__":
    main()
