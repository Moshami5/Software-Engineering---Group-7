"""
I3 - Integration test: batch catalogue preparation
Covers FR-14 (classify courses), FR-15 (map course skills to ESCO), FR-13 (thresholds),
FR-4 (batch output is consumable), AIR-8 / NFR-4 (real-time lookups < 500 ms).

Scenario
    10 sample courses (test data) that list skills go through the REAL batch script
    (scripts/prepare_catalogue.prepare) with the REAL Model 1 (src.model_category) and the
    REAL Model 2 (src.model_skills). The results are written to file in the same format as
    the script's main(). Each course must end up with a category and ESCO skills.


Test data
    The 10 courses are real rows from Online_Courses_ml_features.csv (Coursera), with three
    deliberate changes so the edge cases of the real catalogue are exercised:
      * five courses have their category blanked  -> the model must predict them
        (FutureLearn and Udacity courses have no category in the real data)
      * one course has its category replaced by a non-canonical label ("Finance")
        -> must be ignored and predicted (Simplilearn labels are not in the 11 either)
      * one course has its skills blanked -> lists no skills (29% of Coursera courses)
      * one label is replaced by a localised variant ("Negocios") -> must map to Business
    Two courses have an empty short_intro, as ~2% of the real catalogue does.

Skips (instead of failing) when Model 1's .joblib, the ESCO index or sentence-transformers
are missing, and, for the threshold tests, when config/thresholds.json is not filled in yet.

Note: prepare() stores RAW scores and does not apply thresholds (FR-13 applies them when
results are shown). So "uncategorised" / "unmatched" are checked through src.thresholds.
"""
import importlib
import importlib.util
import json
import re
import time
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

pytest.importorskip("sentence_transformers", reason="Model 2 needs sentence-transformers")

from src.data_contract import ENGLISH_CATEGORIES, ESCO_INDEX_CSV, MODEL1_PATH  # noqa: E402
from src.model_category import classify  # noqa: E402
from src.model_skills import match  # noqa: E402
from src.thresholds import UNCATEGORISED, load_thresholds, passes  # noqa: E402

if not MODEL1_PATH.exists():
    pytest.skip(f"Model 1 artefact missing: {MODEL1_PATH}", allow_module_level=True)
if not ESCO_INDEX_CSV.exists():
    pytest.skip(f"ESCO index missing: {ESCO_INDEX_CSV}", allow_module_level=True)


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _from_src(func_name):
    """Import `func_name` from whichever src/ module defines it."""
    for path in sorted((REPO_ROOT / "src").glob("*.py")):
        if re.search(rf"^def {func_name}\(", path.read_text(encoding="utf-8"), re.M):
            return getattr(importlib.import_module(f"src.{path.stem}"), func_name)
    pytest.skip(f"no src module defines {func_name}()", allow_module_level=True)


prep = _load_script("prepare_catalogue")
derive_required_skills = _from_src("derive_required_skills")  # FR-3
course_esco_links = _from_src("course_esco_links")            # FR-4
retrieve = _from_src("retrieve")                              # FR-4

TOP_K = 5
LATENCY_LIMIT_S = 0.5  # AIR-8 / NFR-4
BASE = "https://www.coursera.org/specializations/"

SAMPLE = [
    ("machine-learning-introduction", "Machine Learning Specialization",
     "#BreakIntoAI with Machine Learning Specialization. Master fundamental AI concepts and develop practical machine learning skills in the beginner-friendly, 3-course program by AI visionary Andrew Ng",
     "Data Science",
     "Decision Trees, Artificial Neural Network, Logistic Regression, Recommender Systems, Linear Regression, Regularization to Avoid Overfitting, Gradient Descent, Supervised Learning, Logistic Regression for Classification, Xgboost, Tensorflow, Tree Ensembles,"),
    ("python", "Python for Everybody Specialization",
     "Learn to Program and Analyze Data with Python. Develop programs to gather, clean, analyze, and visualize data.",
     "Computer Science",
     "Json, Xml, Python Programming, Database (DBMS), Python Syntax And Semantics, Basic Programming Language, Computer Programming, Data Structure, Tuple, Web Scraping, Sqlite, SQL,"),
    ("finance-accounting", "Introduction to Finance and Accounting Specialization",
     "Learn the basics of finance and accounting. Build a foundation of core business skills in finance and accounting",
     "Negocios",                                                   
     "Corporate Finance, Financial Accounting, Financial Statement, Accounting, Decision-Making, Discounted Cash Flow, Cash Flow Analysis, Balance Sheet, Generally Accepted Accounting Principles, Accounting Terminology,"),
    ("graphic-design", "Graphic Design Specialization",
     "Make Compelling Design. Learn and apply the principles of graphic design towards a comprehensive branding project.",
     "Arts and Humanities",
     "Visual Communication, Branding Communication, Graphic Design, Art History, Typography, Creativity, Graphics, Design Theory, Color Theory, Adobe Illustrator, History, Adobe Indesign,"),
    ("improve-english", "Improve Your English Communication Skills Specialization",
     "Improve Your English Communication Skills. Write and speak more professionally in English to increase your business success.",
     None,                                                         # blanked label
     None),                                                        # blanked skills: lists no skills
    ("it-fundamentals-cybersecurity", "IT Fundamentals for Cybersecurity Specialization",
     "Launch your career in Cybersecurity. Acquire the knowledge you need to work in Cybersecurity",
     None,
     "Operating System Security, database vulnerabilities, Cybersecurity, networking basics, Cyber Attacks, Information Security (INFOSEC), IBM New Collar, Malware, Network Security, Sql Injection,"),
    ("devops-cloud-and-agile-foundations", "DevOps, Cloud, and Agile Foundations Specialization",
     None,                                                         # empty short_intro, as in the real data
     None,
     "Cloud Native, Devops, Scrum, Cloud Computing, agile, Test-Driven Development, CI/CD, Behavior-Driven Development, Iaas PaaS Saas, Hybrid Multicloud, Agile Software Development, Scrum Methodology,"),
    ("excel", "Excel Skills for Business Specialization",
     "Learn Excel Skills for Business. Master Excel to add a highly valuable asset to your employability portfolio.",
     None,
     "Data Validation, Microsoft Excel, Microsoft Excel Macro, Pivot Table, Graphs, Spreadsheet, Chart, Concatenation, Consolization, Pivot Chart, Lookup Table, Microsoft Excel Vba,"),
    ("materiality-esg-factors", "The Materiality of ESG Factors Specialization",
     "Learn about ESG Factors When Investing. Analyze the importance of ESG investing. Identify how the ESG approach should be an essential piece of your strategy based on various factors impacting and driving value.",
     "Finance",                                                    # non-canonical label: not one of the 11
     "ESG, Investment, Climate Change, Finance, social activism,"),
    ("data-engineering-foundations", "Data Engineering Foundations Specialization",
     "Build the Foundation for a Data Engineering Career. Develop hands-on experience with Python, SQL, and Relational Databases and master the fundamentals of the Data Engineering ecosystem.",
     "Information Technology",
     "Information Engineering, Python Programming, Extraction, Transformation And Loading (ETL), Relational Database Management System (RDBMS), SQL, Data Science, Database (DBMS), NoSQL, Data Analysis, Pandas, Numpy, Jupyter notebooks,"),
]
KEYS = [f"Coursera::{BASE}{row[0]}" for row in SAMPLE]
K_ML, K_PY, K_FIN, K_ART, K_NOSKILLS, K_CYBER, K_DEVOPS, K_EXCEL, K_ESG, K_DE = KEYS

LABELLED = {K_ML, K_PY, K_FIN, K_ART, K_DE}           
MODEL_PREDICTED = set(KEYS) - LABELLED                 
EMPTY_INTRO = {K_DEVOPS}
EXPECTED_DISTINCT_SKILLS = 95   
EXPECTED_SHARED = {"python programming", "sql", "database (dbms)"}
COLUMNS = ["course_key", "site", "title", "short_intro", "category", "skills"]


def sample_frame():
    return pd.DataFrame(
        [(key, "Coursera", row[1], row[2], row[3], row[4]) for key, row in zip(KEYS, SAMPLE)],
        columns=COLUMNS,
    )


# fixtures
@pytest.fixture(scope="module")
def batch(tmp_path_factory):
    """Run the real batch step and write its three outputs, as scripts/prepare_catalogue.main() does."""
    out_dir = tmp_path_factory.mktemp("i3")
    catalogue, skill_matches, stats = prep.prepare(sample_frame(), classify, match, TOP_K)

    catalogue.to_csv(out_dir / "catalogue_enriched.csv", index=False, encoding="utf-8")
    skill_matches.to_csv(out_dir / "skill_matches.csv", index=False, encoding="utf-8")
    (out_dir / "catalogue_prep_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return out_dir


@pytest.fixture(scope="module")
def catalogue(batch):
    return pd.read_csv(batch / "catalogue_enriched.csv")


@pytest.fixture(scope="module")
def skill_matches(batch):
    return pd.read_csv(batch / "skill_matches.csv")


@pytest.fixture(scope="module")
def stats(batch):
    return json.loads((batch / "catalogue_prep_stats.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def thresholds():
    try:
        return load_thresholds()
    except (ValueError, FileNotFoundError) as exc:
        pytest.skip(f"thresholds not configured (FR-13): {exc}")


def test_outputs_written_to_file(batch, catalogue):
    for name in ("catalogue_enriched.csv", "skill_matches.csv", "catalogue_prep_stats.json"):
        assert (batch / name).stat().st_size > 0, name
    assert len(catalogue) == 10
    assert set(catalogue["course_key"]) == set(KEYS)


def test_each_course_has_a_category(catalogue):
    assert catalogue["category"].notna().all(), "every course must get a category"
    assert (catalogue["category_source"] != "none").all()


def test_fr14_category_is_one_of_the_eleven(catalogue):
    assert set(catalogue["category"]) <= set(ENGLISH_CATEGORIES)
    assert len(set(ENGLISH_CATEGORIES)) == 11


def test_fr14_own_label_kept_and_localised_label_mapped(catalogue):
    by_key = catalogue.set_index("course_key")
    assert by_key.loc[K_ML, "category"] == "Data Science"
    assert by_key.loc[K_FIN, "category"] == "Business"            # "Negocios" -> Business
    for key in LABELLED:
        assert by_key.loc[key, "category_source"] == "label"


def test_fr14_blank_or_non_canonical_label_gets_a_model_prediction(catalogue):
    predicted = catalogue[catalogue["course_key"].isin(MODEL_PREDICTED)]
    assert (predicted["category_source"] == "model").all()        # incl. "Finance", not one of the 11
    assert (predicted["category"] == predicted["predicted_category"]).all()


def test_fr14_course_without_intro_is_still_classified(catalogue):
    row = catalogue.set_index("course_key").loc[next(iter(EMPTY_INTRO))]
    assert row["category_source"] == "model"
    assert 0.0 <= row["predicted_confidence"] <= 1.0


def test_fr14_confidence_is_stored_raw_between_0_and_1(catalogue):
    conf = catalogue["predicted_confidence"]
    assert conf.notna().all()
    assert conf.between(0.0, 1.0).all()


def test_fr14_below_threshold_is_shown_as_uncategorised(catalogue, thresholds):
    """Thresholds are applied at display time (FR-13) to the stored raw confidence."""
    for row in catalogue[catalogue["category_source"] == "model"].itertuples():
        shown = row.category if passes(row.predicted_confidence, "category", thresholds) else UNCATEGORISED
        if row.predicted_confidence < thresholds["category"]:
            assert shown == UNCATEGORISED
        else:
            assert shown in ENGLISH_CATEGORIES


def test_fr15_each_distinct_skill_matched_once_with_top_k(skill_matches, stats):
    per_skill = skill_matches.groupby("course_skill")["rank"].apply(list)
    assert len(per_skill) == EXPECTED_DISTINCT_SKILLS == stats["distinct_course_skills"]
    assert all(ranks == list(range(1, TOP_K + 1)) for ranks in per_skill), "ranks must be 1..k"
    assert len(skill_matches) == EXPECTED_DISTINCT_SKILLS * TOP_K


def test_fr15_skills_are_normalised_and_deduplicated(catalogue, skill_matches):
    by_key = catalogue.set_index("course_key")
    devops = by_key.loc[K_DEVOPS, "skills_normalised"].split(" | ")
    assert len(devops) == 12, "trailing comma must not create an empty skill"
    assert all(s == s.lower() and s.strip() == s and s for s in devops)
    assert "devops" in devops and "agile" in devops and "agile software development" in devops

    assert pd.isna(by_key.loc[K_NOSKILLS, "skills_normalised"]) or by_key.loc[K_NOSKILLS, "skills_normalised"] == ""
    counts = skill_matches["course_skill"].value_counts()
    for shared in EXPECTED_SHARED:
        assert counts[shared] == TOP_K, f"{shared!r} is listed by two courses but must be matched once"


def test_fr15_scores_sorted_best_first_and_at_most_1(skill_matches):
    for _, group in skill_matches.groupby("course_skill"):
        scores = group.sort_values("rank")["score"].tolist()
        assert scores == sorted(scores, reverse=True)
        assert max(scores) <= 1.0001  # cosine of normalised vectors


def test_fr15_every_listed_skill_has_esco_candidates(catalogue, skill_matches):
    matched_skills = set(skill_matches["course_skill"])
    for row in catalogue.itertuples():
        if isinstance(row.skills_normalised, str) and row.skills_normalised:
            assert set(row.skills_normalised.split(" | ")) <= matched_skills, row.course_key
    assert skill_matches["esco_id"].notna().all() and skill_matches["esco_label"].notna().all()


def test_fr15_below_threshold_matches_are_dropped_and_skill_marked_unmatched(skill_matches, thresholds):
    shown = skill_matches[skill_matches["score"].map(lambda s: passes(s, "skill", thresholds))]
    assert (shown["score"] >= thresholds["skill"]).all()
    unmatched = set(skill_matches["course_skill"]) - set(shown["course_skill"])
    for skill in unmatched:  # a skill with nothing left only had weak candidates
        assert skill_matches.loc[skill_matches["course_skill"] == skill, "score"].max() < thresholds["skill"]


def test_stats_are_consistent(stats):
    assert stats["courses"] == 10
    assert sum(stats["category_source"].values()) == 10
    assert stats["category_source"].get("label", 0) == len(LABELLED)
    assert stats["category_source"].get("model", 0) == len(MODEL_PREDICTED)
    assert stats["courses_with_skills"] == 9          # one course lists no skills
    assert stats["top_k"] == TOP_K
    assert stats["classify_seconds"] >= 0 and stats["match_seconds"] >= 0


def test_batch_output_feeds_retrieval(catalogue, skill_matches):
    links = course_esco_links(catalogue, skill_matches)  # default skill threshold
    assert links, "no course got any ESCO link from the batch output"
    assert set(links) <= set(catalogue["course_key"])
    assert K_NOSKILLS not in links, "a course without skills cannot be retrieved"
    assert all(ids for ids in links.values())


def _slowest(fn, queries):
    fn(queries[0])  # warm-up: loading the encoder / index is not a per-query cost
    slowest = 0.0
    for q in queries:
        t0 = time.perf_counter()
        fn(q)
        slowest = max(slowest, time.perf_counter() - t0)
    return slowest


def test_air8_skill_similarity_lookup_under_500ms():
    queries = [s.strip() for row in SAMPLE if row[4] for s in row[4].split(",") if s.strip()]
    slowest = _slowest(lambda q: match(q, TOP_K), queries)
    assert slowest < LATENCY_LIMIT_S, f"slowest skill lookup {slowest * 1000:.0f} ms"


def test_air8_occupation_linking_under_500ms():
    slowest = _slowest(derive_required_skills,
                       ["data scientist", "software developer", "lawyer", "I like cooking and baking"])
    assert slowest < LATENCY_LIMIT_S, f"slowest occupation lookup {slowest * 1000:.0f} ms"


@pytest.mark.skipif(
    not (prep.DATA_PROCESSED / "catalogue_enriched.csv").exists()
    or not (prep.DATA_PROCESSED / "skill_matches.csv").exists(),
    reason="run scripts/prepare_catalogue.py first to time lookups on the full catalogue",
)
def test_air8_retrieval_over_full_precomputed_catalogue_under_500ms():
    """The point of batch preparation: a real-time query only reads precomputed tables."""
    full_catalogue = pd.read_csv(prep.DATA_PROCESSED / "catalogue_enriched.csv")
    full_links = course_esco_links(full_catalogue, pd.read_csv(prep.DATA_PROCESSED / "skill_matches.csv"))
    required = derive_required_skills("data scientist").skills
    assert required, "expected 'data scientist' to resolve to an occupation with skills"

    retrieve(required, full_catalogue, full_links)  # warm-up
    t0 = time.perf_counter()
    retrieve(required, full_catalogue, full_links)
    elapsed = time.perf_counter() - t0
    assert elapsed < LATENCY_LIMIT_S, f"retrieval {elapsed * 1000:.0f} ms"
