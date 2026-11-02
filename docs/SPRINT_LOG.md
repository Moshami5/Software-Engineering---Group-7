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
- **Open:** none on this card. Merged via PR #8 on 2 Nov (approved by Musaed).

### Study context (FR-2, NFR-3) — Melat, 2 Nov · PR #10 (approved by Musaed)

- `src/study_context.py` and `tests/test_study_context.py`; missing fields shown as
  "not given".

### Batch catalogue preparation — Mohamed, 2 Nov · branch `feature/batch-catalogue-prep` · Trello "[FR-14 · FR-15 · NFR-4 · AIR-8] Batch catalogue preparation"

- **What:** `scripts/prepare_catalogue.py` runs both models once over the 5,275 cleaned
  courses and writes the results to `data/processed/` for look-up at query time (AIR-8):
  - `catalogue_enriched.csv`: one row per course. `category` is the course's own label
    when it has one (2,819 Coursera courses), otherwise Model 1's prediction (2,456);
    0 courses left without a category. The prediction and its confidence are kept for
    every course.
  - `skill_matches.csv`: top-5 ESCO skills per distinct course skill. 4,229 distinct
    skills, the same count as the Task 2 notebook, each matched once.
  - `catalogue_prep_stats.json`: counts and run times.
- **Decision:** scores are stored raw; thresholds (FR-13) are applied when results are
  shown, so this step does not wait for the threshold card.
- **Run time** (2 Nov, CPU, Windows 11): 104.5 s in total — 61.7 s building the ESCO
  index, 38.9 s matching skills, 3.9 s classifying. Input for the Task 7 carbon footprint.
- **Tests:** `tests/test_prepare_catalogue.py`, 10 unit tests with fake models (skill
  splitting, label vs prediction, each distinct skill matched once, stats). Running the
  real models end to end is integration test I3.
- **Observed:** some predictions have low confidence, e.g. "Get Creative with People to
  Solve Problems" → Computer Science at 0.16. These are the cases the category threshold
  should turn into "uncategorised" (useful example for I1).

---

## Sprint 2 — 2 – 8 Nov 2026 (Task 5)

### FR-3: required skills from the stated interest — Mohamed, 3 Nov · branch `feature/fr3-required-skills` · Trello "[FR-3] Match interest to ESCO occupation -> required skills"

- **What:** `src/occupations.py`. `derive_required_skills(interest)` matches the interest
  to the 319 ESCO occupations in `data/occupations_clean.csv` and returns the best ones
  (at most 3) with the union of their essential skills from `data/relations_clean.csv`.
  If no occupation clears the threshold it returns "no occupation matched", so course
  retrieval (FR-4) falls back to the interest text. Occupations are indexed with the
  Model 2 functions in `src/model_skills.py` (same encoder, same document format).
- **Threshold:** default 0.55, a parameter until the team's threshold config has an
  "occupation" value. Measured with the real encoder: clear occupations score 0.53–0.72
  (software developer 0.72, lawyer 0.61, data scientist 0.59), vague interests 0.40–0.46,
  unrelated text ≤ 0.33. "electrician" is not among the 319 professional occupations but
  scores 0.51 for "data scientist", so 0.5 would accept a wrong match; 0.55 does not.
- **Limit:** only professional occupations (ISCO major group 2) are in the cleaned data,
  so trades such as electrician never match an occupation.
- **Tests:** `tests/test_occupations.py`, 9 unit tests with a fake encoder and fake
  occupations (threshold, skills without repeats, "no occupation matched", empty input);
  `tests/test_occupations_integration.py`, 3 tests with the real encoder ("software
  developer" → its skills; "electrician" and "I like cooking and baking" → no occupation).
  Whole suite with the real encoder: 109 passed.

### FR-4: course retrieval — Mohamed, 3 Nov · branch `feature/fr4-course-retrieval` (builds on FR-3) · Trello "[FR-4] Course retrieval"

- **What:** `src/retrieval.py`. A course is a candidate when one of its own skills links
  to a required ESCO skill (links from `data/processed/skill_matches.csv`, the batch
  preparation output). Candidates are ranked by how many required skills they cover, can
  be narrowed by category, and at most 50 are returned, each with title, category and the
  required skills it covers. No candidates → "no matching courses".
  Required skills come from FR-3; when no occupation matched, from the ESCO skills closest
  to the interest text (Model 2).
- **Threshold:** skill links need a score ≥ 0.45 (parameter until the threshold config has
  a "skill" value). Measured: "marketing and branding" → marketing skills at 0.52–0.59;
  "electrician" only reaches noise at 0.37–0.39 and "I like cooking and baking" 0.36, so
  both now return "no matching courses" instead of unrelated courses.
- **Real results (3 Nov):** "software developer" → 50 courses led by DevOps, C programming
  and Android developer certificates; "lawyer" → 50 led by European Business Law;
  "marketing and branding" (no occupation, interest-text route) → 50 marketing and brand
  courses. Retrieval takes 4–21 ms once the data is loaded (catalogue 0.1 s).
- **Limit:** only courses that list skills can be retrieved (2,047 of 5,275 have ESCO links).
- **Tests:** `tests/test_retrieval.py`, 8 unit tests with fake data; 
  `tests/test_retrieval_integration.py`, 3 tests with real data and encoder (FR-3 + FR-4
  together). Whole suite with the real encoder: 120 passed.
