"""Shared data contract for the model task.

Single source of truth for paths, column names, the label vocabulary and the
localised-label mapping, so the profiling and splitting scripts cannot drift
apart. See docs/MODEL_PLAN.md sections 2, 6 and 7.
"""
from pathlib import Path

# --- Paths ---------------------------------------------------------------
# Resolve relative to this file so scripts work from any working directory.
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = REPO_ROOT / "data"
DATA_PROCESSED = REPO_ROOT / "data" / "processed"

COURSES_CSV = DATA_RAW / "Online_Courses.csv"
ESCO_SKILLS_FULL_CSV = DATA_RAW / "skills_en.csv"      # full ESCO export
ESCO_SKILLS_CLEAN_CSV = DATA_RAW / "skills_clean.csv"  # cleaned subset

# --- Reproducibility -----------------------------------------------------
SEED = 42

# --- Model 1: course -> Category -----------------------------------------
# Only Coursera rows carry a Category label.
LABEL_SITE = "Coursera"

TEXT_COLS = ["Title", "Short Intro"]  # Model 1 input
LABEL_COL = "Category"

# Columns carried into the frozen split files (kept lean and traceable).
SPLIT_KEEP_COLS = ["Title", "Short Intro", "Category", "Skills", "URL"]

# Deduplicate on course text, not just URL (MODEL_PLAN.md section 7).
DEDUP_KEYS = ["Title", "Short Intro"]

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
    "计算机科学": "Computer Science",              # zh
    "Ciencias de la Computación": "Computer Science",  # es
    "Ciencia de Datos": "Data Science",           # es
    "データサイエンス": "Data Science",             # ja
    "Negocios": "Business",                       # es
    "Negócios": "Business",                       # pt
    "Tecnologia da informação": "Information Technology",  # pt
}

# --- Split proportions ---------------------------------------------------
DEV_FRAC = 0.15
TEST_FRAC = 0.15
# train gets the remainder (0.70).
