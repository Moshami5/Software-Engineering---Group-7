"""FR-3: derive the required skills from a stated interest.

If the student's interest names an occupation, match it to ESCO occupations and take the
essential skills linked to them. If no occupation clears the threshold, return
"no occupation matched" so course retrieval (FR-4) can fall back to the interest text.

Occupations are indexed exactly like ESCO skills in src/model_skills.py ("preferred label .
alt labels", all-MiniLM-L6-v2, cosine similarity), reusing its functions. The cleaned
occupation file (data/occupations_clean.csv) holds the 319 ESCO occupations in ISCO major
group 2 (professionals); data/relations_clean.csv links them to their essential skills.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_contract import OCCUPATIONS_CLEAN_CSV, RELATIONS_CLEAN_CSV  # noqa: E402
from src.model_skills import SkillIndex, build_index, load_encoder, rank  # noqa: E402

NO_OCCUPATION = "no occupation matched"

# Default until the team's threshold config (FR-13, src/thresholds.py) holds an
# "occupation" value. Measured on 3 Nov with the real encoder: clear occupations score
# 0.53-0.72 (software developer 0.72, lawyer 0.61, data scientist 0.59); vague interests
# 0.40-0.46; unrelated text <= 0.33. "electrician" (not among the 319) wrongly scores 0.51
# for data scientist, so 0.5 would let that through; 0.55 does not.
DEFAULT_OCCUPATION_THRESHOLD = 0.55
MAX_OCCUPATIONS = 3


class OccupationMatch(NamedTuple):
    esco_id: str   # ESCO occupation conceptUri
    label: str     # ESCO preferredLabel
    score: float   # cosine similarity to the interest


class RequiredSkills(NamedTuple):
    occupations: list[OccupationMatch]  # empty when nothing cleared the threshold
    skills: list[tuple[str, str]]       # (ESCO skill id, label), essential skills, no repeats
    message: str | None                 # NO_OCCUPATION when occupations is empty


def load_occupations(path: Path = OCCUPATIONS_CLEAN_CSV) -> pd.DataFrame:
    """The occupations that form the index (rows without a preferred label dropped)."""
    occ = pd.read_csv(path, usecols=["conceptUri", "preferredLabel", "altLabels"])
    return occ.dropna(subset=["preferredLabel"]).reset_index(drop=True)


def load_relations(path: Path = RELATIONS_CLEAN_CSV) -> pd.DataFrame:
    """Occupation -> essential skill links."""
    return pd.read_csv(path, usecols=["occupationUri", "skillUri", "skillLabel"])


@lru_cache(maxsize=1)
def load_occupation_index() -> SkillIndex:
    """Embed every occupation once per process."""
    return build_index(load_occupations(), load_encoder())


def match_occupations(interest: str, index: SkillIndex, encoder, k: int = MAX_OCCUPATIONS,
                      threshold: float = DEFAULT_OCCUPATION_THRESHOLD) -> list[OccupationMatch]:
    """Up to ``k`` occupations scoring at least ``threshold``, best first."""
    return [OccupationMatch(*m) for m in rank(interest, index, encoder, k) if m.score >= threshold]


def skills_for(occupation_ids: list[str], relations: pd.DataFrame) -> list[tuple[str, str]]:
    """Union of the essential skills of ``occupation_ids``, in occupation order, no repeats."""
    seen, skills = set(), []
    for occ_id in occupation_ids:
        for skill_id, label in relations.loc[relations["occupationUri"] == occ_id, ["skillUri", "skillLabel"]].itertuples(index=False):
            if skill_id not in seen:
                seen.add(skill_id)
                skills.append((skill_id, label))
    return skills


def derive_required_skills(interest: str, threshold: float = DEFAULT_OCCUPATION_THRESHOLD,
                           index: SkillIndex | None = None, encoder=None,
                           relations: pd.DataFrame | None = None) -> RequiredSkills:
    """FR-3: occupations matching ``interest`` and the essential skills they require.

    ``index``, ``encoder`` and ``relations`` default to the real ones; tests pass fakes.
    Raises ValueError for an empty interest (validate it with src/interest.py first).
    """
    if not isinstance(interest, str) or not interest.strip():
        raise ValueError("derive_required_skills needs a non-empty interest")
    encoder = encoder if encoder is not None else load_encoder()
    index = index if index is not None else load_occupation_index()
    relations = relations if relations is not None else load_relations()

    occupations = match_occupations(interest, index, encoder, threshold=threshold)
    if not occupations:
        return RequiredSkills([], [], NO_OCCUPATION)
    return RequiredSkills(occupations, skills_for([o.esco_id for o in occupations], relations), None)
