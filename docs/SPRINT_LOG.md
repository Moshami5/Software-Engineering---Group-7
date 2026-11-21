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
  - **Re-evaluated 20 Nov (Mohamed, Sprint 4 card "Decide on the Task 2 Model 2 numbers"):**
    the notebook now uses the module's `alt_labels()`, so the held-out query is one real
    synonym instead of the whole synonym list. Clean index, embeddings: top-1 0.866 → 0.770,
    top-5 0.962 → 0.929, MRR@5 0.905 → 0.835; TF-IDF: 0.816 / 0.927 / 0.864 →
    0.770 / 0.911 / 0.827; exact match on the course vocabulary 2.4% → 4.2%; course skills
    clearing 0.35 similarity 65.9% → 61.0%. The full-ESCO run gives exactly the old numbers,
    as expected. Source: `data/processed/model2_results_clean.json`. The final report uses
    the new numbers; the submitted Task 2 report keeps its original ones.
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

### FR-5: feasibility filter — Mohamed, 3 Nov · branch `feature/fr5-feasibility` (builds on FR-4) · Trello "[FR-5 · NFR-3] Feasibility filter"

- **What:** `src/feasibility.py`, rule-based. `assess(candidates, context, facts)` removes
  courses already completed (title, case-insensitive), taught in another language
  ("Portuguese (Brazilian)" counts as Portuguese), or needing more hours per week than the
  student has — each with its reason. A check whose field the student left empty is
  skipped (FR-2); a course with missing language or hours is kept and labelled
  "not listed" (NFR-3). Uses Melat's `src/study_context.py` (`is_given`, `label_missing`)
  unchanged.
- **Real example (3 Nov):** "software developer", English, 4 h/week, Meta Android
  certificate completed → 50 candidates, 45 kept, 5 removed (1 "already completed",
  4 "needs 6/7/10 hours per week, you have 4").
- **Data limit:** weekly hours are listed for only 40% of courses (42 of the 45 kept here
  are "not listed"), so the hours check rarely applies; language is listed for 53%.
- **Tests:** `tests/test_feasibility.py`, 7 unit tests (each reason, skipped checks,
  "not listed", language variants, order kept); `tests/test_feasibility_integration.py`,
  1 test with real courses and a context validated by `study_context.py`.
  Whole suite with the real encoder: 128 passed.

### FR-6 + FR-7: study paths and ranking — Mohamed, 3 Nov · branch `feature/fr6-fr7-paths` (builds on FR-5) · Trello "[FR-6] Path composition", "[FR-7] Ranking + shortlist of 3-5 paths"

- **What:** `src/paths.py`. `build_paths()` starts a path from each feasible course and keeps
  adding the course that covers the most still-missing *required* skills while the total
  fits the weeks available (FR-6); courses without a duration are left out and counted.
  Paths are scored by the share of required skills covered, ordered by score with ties to
  the shorter path, and 3–5 are returned, or fewer with "only N paths fit your
  constraints" (FR-7).
- **Durations → weeks** (agreed 3 Nov): weeks as listed, months × 4.3, days ÷ 7; hours and
  minutes are total study time (duration basis "study_time" in the data) ÷ the student's
  hours per week. Two defaults chosen while building: 5 hours/week when the student gave
  none (so hour-based courses, 44% of the catalogue, still count), and at most 5 courses
  per path when no weeks were given.
- **Found and fixed while testing:** (1) a course was added for skills that were not
  required — now only required skills count; (2) the catalogue lists some courses twice
  under different keys, which produced two identical-looking paths — paths with the same
  titles now count once. Both have unit tests.
- **Real example (3 Nov):** "marketing and branding", English, 4 h/week, 12 weeks → 5 paths
  covering all marketing skills in 3–6.5 weeks. "software developer", 6 h/week, 20 weeks →
  5 paths covering 26–28% of its 46 required skills in ~19 weeks. Whole chain FR-3→FR-7:
  47 ms once loaded.
- **Tests:** `tests/test_paths.py`, 16 unit tests (unit conversion, budget, required-only
  skills, ties, left-out count, messages, at most 5, duplicates);
  `tests/test_advisor_chain_integration.py`, 1 test running FR-3→FR-7 on real data.
  Whole suite with the real encoder: 145 passed.

---

## Sprint 3 — 9 – 15 Nov 2026 (Task 6, scrum master: Melat)

Entries for each teammate's card are short facts from their pull request; owners, add
your decisions and findings to your own entry.

### `advise()` + AI server — Mohamed, 9 Nov · PRs #29, #31 · Trello "[T6 · NFR-4] AI server"

- `src/advisor.py`: the whole FR-1 → FR-7 chain behind one JSON-in, JSON-out call
  (6 unit tests with fake steps, 1 integration test on real data).
- `src/servers/ai_server.py`: loads both models and the catalogue once; in this first
  version a worker loop pulled jobs from the orchestrator (`GET /jobs/next`). Local check
  9 Nov: models load in ~10 s; "software developer" → 5 paths in 1.4 s.

### Orchestrator (job queue) + agreed API — Musaed, 13 Nov · PR #32 · Trello "[T6] Orchestrator", "[T6] Agree the API"

- **What:** `src/servers/orchestrator.py`, FastAPI on port 8001; jobs in a SQLite table
  (decided 9 Nov: no Redis, no Docker); `POST /jobs`, `GET /jobs/next`,
  `POST /jobs/{id}/result`, `GET /jobs/{id}`. The agreed API for all three servers is
  written in `tasks/task6/README.md`.
- **Decisions:** taking a job is one `BEGIN IMMEDIATE` transaction, so a job is never given
  out twice; a result for a job that is not running is refused (409).
- **Tests:** 15 unit tests, including 8 parallel takers sharing 40 jobs.

### Interface server — Melat, 13 Nov · PRs #36, #38, #40

- `src/interface_server.py`, port 8000: checks FR-1/FR-2, stores requests in its own
  SQLite database, sends valid ones to the orchestrator, never calls the AI server.
  #38: status name "waiting" as agreed. #40 (Sprint 4): `POST /flags`, report a wrong
  match (FR-17), no personal data stored (NFR-8).

### CI dependencies — Alexia, Raluca, 13 Nov · PRs #33, #34

- fastapi, uvicorn and httpx added to `requirements-ci.txt` and `environment.yml`, so CI
  runs the server tests.

### Start script + end-to-end check — Bilgin, 13 Nov · PR #35

- `scripts/run_servers.py` starts the servers with one command; `--check` sends a bad and
  a real request like a student would and checks that study paths come back.

### First full run: two faults no unit test could see — Musaed, 13 Nov · PR #37

- **Found:** running all three servers together failed twice, although every server's own
  tests passed (each faked the others): (1) the interface sent the request without the
  agreed `{"request": ...}` wrapper, so the orchestrator answered 422 to every job;
  (2) the start script looked for the interface in `src/servers/`, Melat's file is in `src/`.
- **Fixed:** (1) by Melat in #36 before merging; (2) and a YAML indentation slip in
  `environment.yml` in #37. `--check` then PASSED: 5 study paths.
- **Lesson:** a test that runs the real servers together is needed → next entry.

---

## Sprint 4 — 16 – 22 Nov 2026 (Task 7, scrum master: Musaed)

### Integration test across the three servers — Musaed, 18 Nov · PR #41 (merged into #42) · Trello "[T7] Code clean-up" checklist

- **What:** `tests/test_servers_integration.py` runs the real interface, orchestrator and
  AI server together, in memory (fake advisor, no ports or models, ~1 s), so it runs in CI.
- **Checked:** with the 13 Nov request-format bug put back, 3 of its tests fail.

### Real orchestrator after the Task 6 feedback — Musaed, 18 Nov · PR #42 · builds on Mohamed's AI server (#31) and Bilgin's start script (#35)

- **Feedback (lecturer, 17 Nov):** the middle server was a job queue, not an orchestrator:
  both servers called it and it never decided anything; the AI server polled every 0.5 s
  even with no jobs; nobody restarted a crashed AI server; can two servers change one
  database entry at once?
- **What:** `src/servers/ai_pool.py` (new) holds the orchestrator's decisions:
  - **dispatch:** the oldest waiting job goes to a free, healthy AI server, `POST /run`;
  - **health:** every AI server checked every 5 s (and whether its process is alive);
  - **recover:** a crashed or silent AI server is removed and its job goes back to
    waiting; after 2 attempts the job is marked failed instead of retried forever;
  - **scale:** start an AI server when jobs wait and none is free (max 2), stop one idle
    for 5 min; with no jobs, none runs.
  The AI server lost its poll loop and gained `POST /run` (409 when busy); its model
  loading and `advise()` are unchanged. The start script starts the orchestrator and the
  interface only; the orchestrator starts the AI server.
- **Decisions:**
  - Jobs are pushed with one blocking HTTP call per job (simple; the result comes back in
    the answer), each in its own thread, so two AI servers can work at once.
  - All decisions happen in `tick()` under one lock; tests call it directly with a fake
    clock, so every decision is tested exactly, without sleeping.
  - Managed mode (the orchestrator starts processes) by default; external mode
    (`AI_SERVERS`) for AI servers on other machines.
  - On Windows a stopped process cannot clean up, so the start script first calls
    `POST /ai/shutdown`; no AI server is left running.
  - Concurrency answer: the interface has its own database; the orchestrator is the only
    writer of the queue; every change is one `BEGIN IMMEDIATE` transaction; a late result
    for a job that is no longer running is ignored.
- **Tests:** `tests/test_orchestrator.py` 30 (queue, API, every decision with fake AI
  servers), `tests/test_ai_server.py` rewritten for `POST /run`, integration test updated.
  Whole suite: 253 passed.
- **Checked live (18 Nov, real models):** `--check` PASSED in 28 s with the orchestrator
  starting the AI server itself. No jobs → no AI server; first job → one started, 5 paths;
  AI server killed by hand → next job: a new one started, 5 paths; idle → stopped.
- **Open:** Task 7 report sections 6 and 8.2 still describe the first version.

### FR-8 to FR-11: path explanation — Mohamed, 20 Nov · branch `feature/fr8-fr11-path-explanation` · Trello "[FR-8 · FR-9 · FR-10 · FR-11 · NFR-6 · AIR-5] Path explanation"

- **What:** `src/explain.py` (new); `advise()` adds an explanation to every path:
  - **FR-8 `opens`:** up to 5 ESCO occupations whose essential skills the path's courses
    cover most, with "skills covered / essential skills" and the share; "none matched" if none;
  - **FR-9 `closes`:** the required skills (FR-3) the path does not cover; `null` when no
    occupation was matched, as the SRS says;
  - **FR-10 + AIR-5 `course_details[].skill_links`:** each required skill a course brings,
    traced to the course's own skill text, its ESCO id and the similarity score;
    `category_from` says whether the category is a catalogue label or a Model 1 prediction;
  - **FR-11 `course_details[].duration` / `weeks`:** the listed duration ("4 weeks",
    "17 hours") and its weeks, which add up to the path's total; "not listed" if missing;
  - `score_note` in every response: scores are cosine similarities, not probabilities (AIR-5).
  All earlier fields stay, so the servers and their tests are unchanged. The AI server
  preloads the explanation data with the models.
- **Decisions:**
  - FR-8 ranks occupations by the number of essential skills covered, then by share, so a
    small occupation cannot win on one lucky skill (every occupation has at least 5).
  - The skill evidence uses the same threshold as FR-4 retrieval (0.45), so every link
    shown is one the path was built on.
- **Tests:** `tests/test_explain.py` 8 unit tests (hand-made courses and occupations);
  `tests/test_advisor.py` +1 (explanation in the response, gap with 4 weeks);
  `tests/test_advisor_integration.py` +1 on real data (shares in range, gap ⊆ required
  skills, every link traced with score ≥ 0.45, course weeks add up). Whole suite: 270 passed.
- **Seen on real data:** "I want to work with data" → first path opens data scientist
  (13/63 skills), data analyst (12/36), data engineer (8/23); "software developer" → paths
  cover about a quarter of the required skills, and `closes` lists the rest (33 skills).
- **Follow-up after review (Musaed, 21 Nov, branch `fix/path-explanation-ranking`):**
  - FR-8 now ranks by count x share (covered² / essential skills). Ranking by count first
    let large occupations win: "software developer" opened "numerical tool and process
    control programmer" (12/51) on every path, above "software architect" (10/19). Now:
    software architect, cloud software developer, cloud DevOps engineer; "data analyst"
    opens data analyst (21/36) first.
  - FR-9 `closes` shows the first 10 missing skills in FR-3's order, and the new
    `closes_total` says how many there are ("data analyst": 10 of 60), so nothing is hidden.
  - Tests: +2 unit tests (large vs small occupation, gap cap); whole suite 272 passed.
