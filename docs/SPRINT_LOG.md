# Sprint log

One entry per finished piece of work, newest at the bottom of each sprint. Keep entries
short: what was done, where, which decisions were made, how it is tested, and what is still
open. Add your own entry in the same pull request as the work.

---

## Sprint 1 — 26 Oct – 1 Nov 2026 (scrum master: Mohamed)

### Module interfaces — Mohamed, 26 Oct · PR #7 · Trello "[T5] Agree module interfaces"

- **What:** agreed the signatures the Sprint 1 cards build against, so they can be worked
  on in parallel. Described in `docs/INTERFACES.md`.
- **Files:** `src/model_category.py`, `src/model_skills.py`, `src/thresholds.py` (stubs),
  `config/thresholds.json`, three new paths in `src/data_contract.py`,
  `tests/test_interfaces.py` (5 tests).
- **Decisions:**
  - Thresholds live in JSON, not YAML: no new dependency.
  - Models return raw scores; only `thresholds.py` decides "uncategorised" / "unmatched".
  - Model 2's index is `data/skills_clean.csv` (2,154 skills), the index used in the reports.

### Model 1 module + FR-1 validation — Musaed, 26 Oct · commits 16c9e1a, ef28ee1, d0f23e7

- **What:** `classify()` implemented with `predict_proba`; FR-1 interest validation in
  `src/interest.py`; `environment.yml` pinned to the versions that produced the results.
- **Tests:** unit tests with a fake model, integration tests with the real saved pipeline,
  FR-1 boundary tests. 35 tests passing at that point.
- **Note:** pushed directly to main (PR #6 closed). `main` is branch-protected since:
  every change now needs a pull request with one approval.

### Model 2 module — Mohamed, 26 Oct · branch `feature/fr15-model2-module` · Trello "[FR-15 · AIR-2] Package Model 2"

- **What:** `match(skill_text, k=5)` returns at most `k` ESCO skills, best first. Each ESCO
  skill is indexed as "preferred label . alt labels", lower-cased, embedded once with
  all-MiniLM-L6-v2 (normalised) and ranked by cosine similarity, as in
  `notebooks/model2_esco_matcher.ipynb`. The encoder is loaded on first use, so the module
  imports without torch.
- **Files:** `src/model_skills.py`, `tests/test_model_skills.py`,
  `tests/test_model_skills_integration.py`.
- **Tests:**
  - 12 unit tests with a fake encoder, including U5 ("python programming" → at most 5
    skills, sorted by score), input checks, and alt-label parsing.
  - Integration tests with the real encoder and ESCO index (skipped where
    sentence-transformers is not installed): index size 2,154; "python programming" finds
    "Python (computer programming)"; a skill's own preferred label returns it in the top 5
    for ≥ 95% of a fixed sample of 200 skills (measured: top-1 0.905, top-5 0.985; misses
    are near-duplicates such as "manage data" → "manage quantitative data"); scores are
    cosine values.
  - Run on 26 Oct with the real encoder: **51 passed** (whole suite).
- **Finding (bug caught while writing the tests):** `skills_clean.csv` separates alt labels
  with `;`, `skills_en.csv` with newlines. The notebook splits on newlines only, so for the
  clean index each skill's synonyms were read as one label. The module splits on both
  (`alt_labels()`, covered by unit tests).
  - Effect on reported numbers: the clean-index evaluation in Task 2 (top-1 0.866,
    top-5 0.962, exact match 2.4%) was run with the unsplit labels. Team decision (26 Oct):
    earlier reports keep their numbers; re-evaluate before they are reused.
  - The full-ESCO results (4,241 skills, newline-separated) are not affected.
- **Observed on real phrasings (input for thresholds and Task 7):** "working together in a
  team" returns "cooperate with colleagues" but not "teamwork principles" in the top 5;
  "data analysis" returns "data analytics" (2nd) but not "perform data analysis". Results
  are sensible, but paraphrases do not always reach the most specific ESCO skill.
- **Open:** none on this card; ready for review.
