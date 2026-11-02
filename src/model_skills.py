"""Model 2: free-text course skill -> ESCO skills (SRS FR-15, AIR-2).

Interface agreed in Sprint 1 (docs/INTERFACES.md), implemented by the card
"[FR-15 · AIR-2] Package Model 2 (ESCO skill matcher) as a module".

Each ESCO skill is indexed as one document, "preferred label . alt label . ...",
lower-cased, as in notebooks/model2_esco_matcher.ipynb, and embedded once with
all-MiniLM-L6-v2 (normalised). A course skill is embedded the same way and the
skills are ranked by cosine similarity (a dot product of normalised vectors).
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data_contract import ESCO_INDEX_CSV  # noqa: E402

ENCODER_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Alt labels are newline-separated in the full ESCO export (skills_en.csv) but
# semicolon-separated in the cleaned index (skills_clean.csv); accept both.
_ALT_SEPARATORS = re.compile(r"[\n;]")


class SkillMatch(NamedTuple):
    esco_id: str   # ESCO conceptUri
    label: str     # ESCO preferredLabel
    score: float   # cosine similarity; higher is closer


@dataclass(frozen=True)
class SkillIndex:
    ids: list[str]
    labels: list[str]
    vectors: np.ndarray  # one normalised row per skill


def normalise(text: str) -> str:
    """Lower-case and collapse whitespace, as the notebook's norm() did."""
    return re.sub(r"\s+", " ", str(text).strip().lower())


def alt_labels(cell) -> list[str]:
    """Split an ESCO altLabels cell into normalised labels (newline or ';')."""
    if not isinstance(cell, str):
        return []
    return [normalise(a) for a in _ALT_SEPARATORS.split(cell) if a.strip()]


def index_document(preferred: str, alts) -> str:
    """The text one ESCO skill is indexed by: preferred label first, then its alt labels."""
    return " . ".join([normalise(preferred), *alt_labels(alts)])


def load_esco(path: Path = ESCO_INDEX_CSV) -> pd.DataFrame:
    """The ESCO skills that form the index (rows without a preferred label dropped)."""
    esco = pd.read_csv(path, usecols=["conceptUri", "preferredLabel", "altLabels"])
    return esco.dropna(subset=["preferredLabel"]).reset_index(drop=True)


def build_index(esco: pd.DataFrame, encoder) -> SkillIndex:
    """Embed every ESCO skill once; ``encoder`` needs a sentence-transformers-style encode()."""
    docs = [index_document(p, a) for p, a in zip(esco["preferredLabel"], esco["altLabels"])]
    vectors = np.asarray(encoder.encode(docs, batch_size=64, normalize_embeddings=True))
    return SkillIndex(ids=list(esco["conceptUri"]), labels=list(esco["preferredLabel"]), vectors=vectors)


def rank(skill_text: str, index: SkillIndex, encoder, k: int = 5) -> list[SkillMatch]:
    """Top-``k`` skills in ``index`` for ``skill_text``, highest score first."""
    query = np.asarray(encoder.encode([normalise(skill_text)], normalize_embeddings=True))[0]
    scores = index.vectors @ query
    top = np.argsort(-scores, kind="stable")[: min(k, len(scores))]
    return [SkillMatch(index.ids[i], index.labels[i], float(scores[i])) for i in top]


@lru_cache(maxsize=1)
def load_encoder():
    """Load all-MiniLM-L6-v2 once (imported here so the module loads without torch)."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(ENCODER_NAME)


@lru_cache(maxsize=1)
def load_index() -> SkillIndex:
    """Build the ESCO index once per process."""
    return build_index(load_esco(), load_encoder())


def match(skill_text: str, k: int = 5) -> list[SkillMatch]:
    """Return at most ``k`` ESCO skills for one course skill, best first.

    Scores are sorted from high to low. No thresholding here: dropping weak
    matches is src/thresholds.py's job (FR-13).
    Raises ValueError for an empty skill or k < 1.
    """
    if not isinstance(skill_text, str) or not skill_text.strip():
        raise ValueError("match needs a non-empty skill text")
    if k < 1:
        raise ValueError("k must be at least 1")
    return rank(skill_text, load_index(), load_encoder(), k)
