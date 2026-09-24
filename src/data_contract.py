"""Shared data contract for the model task.

Single source of truth for paths, column names, the label vocabulary and the
localised-label mapping, so the profiling and splitting scripts cannot drift
apart. See docs/MODEL_PLAN.md sections 2, 6 and 7.

Model 1 now trains on the team's cleaned, ML-ready course file
(Online_Courses_ml_features.csv), not the raw export.
"""
from pathlib import Path

# --- Paths ---------------------------------------------------------------
# Resolve relative to this file so scripts work from any working directory.
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = REPO_ROOT / "data"
DATA_PROCESSED = REPO_ROOT / "data" / "processed"

# Model 1 input: the cleaned, deduplicated, feature-engineered course table.
COURSES_CSV = DATA_RAW / "Online_Courses_ml_features.csv"
COURSES_RAW_CSV = DATA_RAW / "Online_Courses.csv"  # original export, kept for reference

# ESCO — full export vs the occupation-graph cleaned tables.
ESCO_SKILLS_FULL_CSV = DATA_RAW / "skills_en.csv"        # full ESCO export
ESCO_SKILLS_CLEAN_CSV = DATA_RAW / "skills_clean.csv"    # skills linked to occupations
OCCUPATIONS_CLEAN_CSV = DATA_RAW / "occupations_clean.csv"
RELATIONS_CLEAN_CSV = DATA_RAW / "relations_clean.csv"   # essential occupation-skill links
ISCO_CLEAN_CSV = DATA_RAW / "isco_clean.csv"             # ISCO occupation hierarchy

# --- Reproducibility -----------------------------------------------------
SEED = 42

# --- Course column names (snake_case, from the ML-features file) ----------
ID_COL = "course_key"
TITLE_COL = "title"
INTRO_COL = "short_intro"
LABEL_COL = "category"
SKILLS_COL = "skills"
URL_COL = "url"
SITE_COL = "site"

# Model 1 input text = title + short intro. Only Coursera rows carry a label.
TEXT_COLS = [TITLE_COL, INTRO_COL]
LABEL_SITE = "Coursera"

# Columns carried into the frozen split files (kept lean and traceable).
SPLIT_KEEP_COLS = [ID_COL, TITLE_COL, INTRO_COL, LABEL_COL, SKILLS_COL, URL_COL]

# Deduplicate on course text, not just URL (MODEL_PLAN.md section 7).
DEDUP_KEYS = [TITLE_COL, INTRO_COL]

# Fill-rate / profiling columns.
KEY_COLS = [TITLE_COL, INTRO_COL, LABEL_COL, SKILLS_COL, URL_COL]

# The 11 canonical English categories.
ENGLISH_CATEGORIES = [
    "Business",
    "Computer Science",
    "Data Science",
    "Health",
    "Information Technology",
    "Physical Science and Engineering",
    "Arts and Humanities",
    "Language Learning",
    "Social Sciences",
    "Personal Development",
    "Math and Logic",
]

# Decision (MODEL_PLAN.md section 7): a handful of rows carry the category in
# another language. These are unambiguous translations of existing English
# classes, so we MAP them (rather than drop) to keep every labelled row.
LOCALISED_LABEL_MAP = {
    "计算机科学": "Computer Science",                    # zh
    "Ciencias de la Computación": "Computer Science",   # es
    "Ciencia de Datos": "Data Science",                 # es
    "データサイエンス": "Data Science",                   # ja
    "Negocios": "Business",                             # es
    "Negócios": "Business",                             # pt
    "Tecnologia da informação": "Information Technology",  # pt
}

# --- Split proportions ---------------------------------------------------
DEV_FRAC = 0.15
TEST_FRAC = 0.15
# train gets the remainder (0.70).
