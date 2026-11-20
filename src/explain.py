"""FR-8 to FR-11 (+ NFR-6, AIR-5): explain each study path to the student.

Per path:
- FR-8  what it opens: up to 5 ESCO occupations whose essential skills the path's courses
        cover most, each with the share covered; "none matched" when it covers none.
- FR-9  what it closes off: the required skills (FR-3) the path does not cover; shown
        only when an occupation was matched, else None.
- FR-10 why each course is in it: the required ESCO skills the course contributes, each
        traced to the course's own skill text with its similarity score (AIR-5).
- FR-11 how long: each course's listed duration and its weeks; "not listed" if missing.
        (The path's total weeks is FR-6's StudyPath.weeks.)

Scores are cosine similarities between texts, not probabilities of being right (AIR-5);
SCORE_NOTE says so in every response. Everything here is plain functions over small
inputs, so the unit tests run on hand-made data; ``load_explain_data`` reads the real files.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.study_context import NOT_LISTED  # noqa: E402

MAX_OPENED = 5
NONE_MATCHED = "none matched"
SCORE_NOTE = "Scores are cosine similarities (0-1) between texts, not probabilities of being correct."
CATEGORY_FROM = {"label": "catalogue label", "model": "Model 1 prediction"}


@dataclass(frozen=True)
class Evidence:
    """One accepted AI match: course skill text -> ESCO skill, with its score (AIR-5)."""
    course_skill: str
    esco_id: str
    esco_label: str
    score: float


@dataclass(frozen=True)
class ExplainData:
    evidence: dict          # course_key -> {esco_id: Evidence}, best-scoring match per ESCO skill
    occupation_skills: dict  # occupation id -> frozenset of essential ESCO skill ids
    occupation_labels: dict  # occupation id -> ESCO preferred label
    category_source: dict    # course_key -> "label" | "model" (FR-14 batch output)


def course_evidence(catalogue: pd.DataFrame, skill_matches: pd.DataFrame, threshold: float,
                    separator: str = " | ") -> dict:
    """course_key -> {ESCO id: Evidence}: each course's accepted skill matches, best per ESCO id.

    Uses the same rule as FR-4 retrieval (score >= threshold), so every skill a path was
    built on can be traced back to the course skill text that produced it.
    """
    strong = skill_matches[skill_matches["score"] >= threshold]
    per_skill: dict[str, list] = {}
    for skill, esco_id, label, score in strong[["course_skill", "esco_id", "esco_label", "score"]].itertuples(index=False):
        per_skill.setdefault(skill, []).append(Evidence(skill, esco_id, label, float(score)))
    evidence = {}
    for key, joined in zip(catalogue["course_key"], catalogue["skills_normalised"]):
        if not isinstance(joined, str) or not joined:
            continue
        best: dict[str, Evidence] = {}
        for skill in joined.split(separator):
            for ev in per_skill.get(skill, ()):
                if ev.esco_id not in best or ev.score > best[ev.esco_id].score:
                    best[ev.esco_id] = ev
        if best:
            evidence[key] = best
    return evidence


def occupations_opened(skill_ids: set, occupation_skills: dict, occupation_labels: dict,
                       limit: int = MAX_OPENED) -> list[dict] | str:
    """FR-8: occupations whose essential skills the path covers most, with the share covered.

    Ranked by the number of essential skills covered, then by share, then by name, so a
    small occupation does not win on one lucky skill. "none matched" when nothing overlaps.
    """
    ranked = []
    for occ_id, essentials in occupation_skills.items():
        covered = len(skill_ids & essentials)
        if covered:
            ranked.append((-covered, -covered / len(essentials), occupation_labels.get(occ_id, occ_id), occ_id))
    if not ranked:
        return NONE_MATCHED
    ranked.sort()
    return [{"occupation": label, "esco_id": occ_id, "skills_covered": -neg,
             "essential_skills": len(occupation_skills[occ_id]), "share": round(-share, 3)}
            for neg, share, label, occ_id in ranked[:limit]]


def skill_gaps(required: list[tuple[str, str]], covered_ids) -> list[str]:
    """FR-9: labels of the required skills the path does not cover, in FR-3's order."""
    return [label for skill_id, label in required if skill_id not in covered_ids]


def duration_text(duration) -> str:
    """FR-11: a course's listed duration as the catalogue gives it, or "not listed"."""
    if duration is None:
        return NOT_LISTED
    value = f"{duration.value:g}"
    return f"{value} {duration.unit}" + ("" if value == "1" else "s")


def explain_course(course, data: ExplainData, duration, weeks) -> dict:
    """FR-10 + FR-11 + AIR-5 for one course in a path."""
    links = data.evidence.get(course.course_key, {})
    skill_links = []
    for esco_id, label in course.matched_skills:
        ev = links.get(esco_id)
        skill_links.append({"esco_skill": label, "esco_id": esco_id,
                            "from_course_skill": ev.course_skill if ev else NOT_LISTED,
                            "similarity": round(ev.score, 3) if ev else None})
    source = data.category_source.get(course.course_key)
    return {
        "duration": duration_text(duration),
        "weeks": round(float(weeks), 1) if weeks is not None else NOT_LISTED,
        "category_from": CATEGORY_FROM.get(source, NOT_LISTED),
        "skill_links": skill_links,
    }


def explain_path(path, required: list[tuple[str, str]], occupation_matched: bool,
                 data: ExplainData, durations: dict, weeks_of) -> dict:
    """FR-8 + FR-9 + per-course FR-10/FR-11 for one StudyPath.

    ``weeks_of(course)`` gives a course's duration in weeks (FR-6's conversion), so the
    numbers shown add up to the path's total.
    """
    path_skills = set().union(*(data.evidence.get(c.course_key, {}).keys() for c in path.courses))
    return {
        "opens": occupations_opened(path_skills, data.occupation_skills, data.occupation_labels),
        "closes": skill_gaps(required, path.covered) if occupation_matched else None,
        "course_details": [explain_course(c, data, durations.get(c.course_key), weeks_of(c))
                           for c in path.courses],
    }


@lru_cache(maxsize=1)
def load_explain_data() -> ExplainData:
    """The real files, read once per process (the AI server preloads this)."""
    from src.occupations import load_occupations, load_relations
    from src.retrieval import DEFAULT_SKILL_THRESHOLD, SKILL_MATCHES_CSV, SKILL_SEPARATOR, load_catalogue

    catalogue, _ = load_catalogue()
    evidence = course_evidence(catalogue, pd.read_csv(SKILL_MATCHES_CSV), DEFAULT_SKILL_THRESHOLD,
                               SKILL_SEPARATOR)
    relations = load_relations()
    occupation_skills = {occ: frozenset(group["skillUri"])
                         for occ, group in relations.groupby("occupationUri")}
    occupations = load_occupations()
    labels = dict(zip(occupations["conceptUri"], occupations["preferredLabel"]))
    source = dict(zip(catalogue["course_key"], catalogue["category_source"]))
    return ExplainData(evidence, occupation_skills, labels, source)
