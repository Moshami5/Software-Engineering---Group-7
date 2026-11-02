"""FR-4: retrieve candidate courses for the required skills or the stated interest.

Courses are linked to ESCO through their own skills: scripts/prepare_catalogue.py matched
every course skill to its top-5 ESCO skills (data/processed/skill_matches.csv). A course is
a candidate when at least one of its linked ESCO skills is a required one, and candidates
are ranked by how many required skills they cover. The required skills come from the
matched occupations (FR-3); when no occupation matched, from the ESCO skills closest to
the interest text itself. Results can be narrowed to categories (FR-14).

Only courses that list skills can be retrieved (about 40% of the catalogue).
"""
from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_contract import DATA_PROCESSED  # noqa: E402

CATALOGUE_CSV = DATA_PROCESSED / "catalogue_enriched.csv"
SKILL_MATCHES_CSV = DATA_PROCESSED / "skill_matches.csv"
SKILL_SEPARATOR = " | "  # as written by scripts/prepare_catalogue.py

NO_COURSES = "no matching courses"
MAX_COURSES = 50
INTEREST_SKILLS = 10

# Default until the team's threshold config (FR-13) holds a "skill" value. Measured on
# 3 Nov: matching interests straight to ESCO, "marketing and branding" scores 0.52-0.59
# for marketing skills, while "electrician" reaches only noise at 0.37-0.39 and "I like
# cooking and baking" 0.36. 0.45 keeps the first and drops the noise; it is inside the
# 0.3-0.65 range agreed for the skill threshold.
DEFAULT_SKILL_THRESHOLD = 0.45


@dataclass(frozen=True)
class CourseCandidate:
    course_key: str
    title: str
    category: str | None
    matched_skills: tuple[tuple[str, str], ...]  # required (ESCO id, label) this course covers
    coverage: float                              # share of the required skills it covers


@dataclass(frozen=True)
class RetrievalResult:
    courses: list[CourseCandidate]
    message: str | None  # NO_COURSES when nothing was found


def course_esco_links(catalogue: pd.DataFrame, skill_matches: pd.DataFrame,
                      threshold: float = DEFAULT_SKILL_THRESHOLD) -> dict[str, set[str]]:
    """course_key -> ESCO skill ids its own skills link to with a score >= ``threshold``."""
    strong = skill_matches[skill_matches["score"] >= threshold]
    per_skill = strong.groupby("course_skill")["esco_id"].apply(set).to_dict()
    links = {}
    for key, joined in zip(catalogue["course_key"], catalogue["skills_normalised"]):
        if isinstance(joined, str) and joined:
            ids = set().union(*(per_skill.get(s, set()) for s in joined.split(SKILL_SEPARATOR)))
            if ids:
                links[key] = ids
    return links


def retrieve(required: list[tuple[str, str]], catalogue: pd.DataFrame, links: dict[str, set[str]],
             categories: set[str] | None = None, limit: int = MAX_COURSES) -> RetrievalResult:
    """Courses covering at least one required skill, most covered first, at most ``limit``.

    ``required`` is a list of (ESCO id, label). Ties are broken by course title so the
    order is stable.
    """
    if not required:
        return RetrievalResult([], NO_COURSES)
    labels = dict(required)
    by_key = catalogue.set_index("course_key")
    found = []
    for key, ids in links.items():
        hit = ids & labels.keys()
        if not hit:
            continue
        row = by_key.loc[key]
        category = row["category"] if isinstance(row["category"], str) else None
        if categories is not None and category not in categories:
            continue
        matched = tuple(sorted(((i, labels[i]) for i in hit), key=lambda x: x[1]))
        found.append(CourseCandidate(key, row["title"], category, matched, len(hit) / len(labels)))
    found.sort(key=lambda c: (-len(c.matched_skills), str(c.title)))
    found = found[:limit]
    return RetrievalResult(found, None if found else NO_COURSES)


def skills_from_interest(interest: str, match, k: int = INTEREST_SKILLS,
                         threshold: float = DEFAULT_SKILL_THRESHOLD) -> list[tuple[str, str]]:
    """Fallback for FR-3 "no occupation matched": the ESCO skills closest to the interest."""
    return [(m.esco_id, m.label) for m in match(interest, k) if m.score >= threshold]


@lru_cache(maxsize=1)
def load_catalogue() -> tuple[pd.DataFrame, dict[str, set[str]]]:
    """The enriched catalogue and its course -> ESCO links, read once per process."""
    catalogue = pd.read_csv(CATALOGUE_CSV)
    return catalogue, course_esco_links(catalogue, pd.read_csv(SKILL_MATCHES_CSV))


def retrieve_for(interest: str, required: list[tuple[str, str]],
                 categories: set[str] | None = None) -> RetrievalResult:
    """FR-4 entry point: use FR-3's required skills, or fall back to the interest text."""
    from src.model_skills import match

    catalogue, links = load_catalogue()
    if not required:
        required = skills_from_interest(interest, match)
    return retrieve(required, catalogue, links, categories)
