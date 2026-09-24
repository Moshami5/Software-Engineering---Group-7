# Pipeline audit & briefing — Task 2 (Group 7)

**Purpose of this file.** A self-contained snapshot of the model-side pipeline: the goal,
the data, both models, how they work, what has been built, what is blocked, and who does
what next. Anyone — a teammate or a fresh AI session — should be able to read *only this
file* plus [`MODEL_PLAN.md`](MODEL_PLAN.md) and be fully oriented. Numbers here were
verified directly against the CSVs in `data/` (see the appendix), not copied from the plan.

_Last audited: 2026-09-21. Regenerate the data numbers with `python scripts/profile_data.py`._

---

## 1. The goal

Task 2 must deliver **a trained, evaluated model with statistics presented, plus the data
work behind it, written up in one A4 page** (sections Data / Model / Software). The rubric
is 5 points: Data (2), Model (2), Model adequacy (1). "Adequacy" explicitly penalises a
model that is **too simple** *and* one that is **too complex** — that single line drives most
design choices.

We build on the data **already in this repo**: the Coursera/FutureLearn course catalogue and
the ESCO skill taxonomy. Two models are built on two parallel tracks, one owner each
(`MODEL_PLAN.md` §8).

**The product story (why two models):** Model 1 *filters* ~5,000 courses to a subject; Model 2
*explains* where a course's skills map in the European skill taxonomy. Neither is the product
alone.

---

## 2. Data assets (what is in `data/`, verified)

| File | Rows | What it is | Used by |
|---|---|---|---|
| `Online_Courses.csv` | 8,092 | Course catalogue, 45 columns (many junk). Sites: FutureLearn 4,843 · Coursera 2,819 · Udacity 282 · Simplilearn 148 | Model 1 + Model 2 |
| `skills_en.csv` | 13,960 | Full ESCO skills export (preferredLabel, altLabels, description, reuseLevel) | Model 2 |
| `skills_clean.csv` | 2,154 | A **cleaned subset** of ESCO skills — different taxonomy (see blocker §7) | Model 2 (disputed) |
| `occupations_clean.csv` | 320 | ESCO occupations | not used by either model yet |
| `relations_clean.csv` | 8,377 | Occupation↔skill graph | not used by either model yet |
| `ISCOGroups_en.csv` | — | ISCO occupation groups | not used by either model yet |

**Key facts about the course data (verified):**
- `Category` (Model 1's label) exists on **only the 2,819 Coursera rows** — every other site is
  unlabelled. Fill rate overall: 34.8%.
- `Skills` (Model 2's input) is present on only **2,099 rows** (25.9%).
- **11 canonical English categories**, plus 7 rows whose label is in another language
  (Chinese/Spanish/Portuguese/Japanese) — unambiguous translations, so we **map** them.
- Heavy class imbalance: Business 895 → Math & Logic 22.
- **Duplication is severe:** 3,103 rows share an identical `Title + Short Intro`. Dedup on
  text, *not just URL*, or the same course lands on both sides of the split and inflates every
  score (`MODEL_PLAN.md` §7).

---

## 3. Model 1 — Course → Category classifier

**Job:** narrow the catalogue by subject. **Input:** `Title + Short Intro` (free text).
**Output:** 1 of 11 categories + confidence. **Type:** **supervised multi-class text
classification** — the model that is genuinely *trained* in the ML sense.

**Labels:** the 2,577 deduplicated Coursera rows (after mapping localised labels and dropping
text-duplicates).

**How it works, mechanically:**
1. **Text → numbers.** TF-IDF (sparse weighted word-frequency vector per course) *or*
   sentence-embeddings (a pretrained encoder maps the text to a ~384-dim dense meaning vector).
2. **Learn a mapping** feature-vector → category. Logistic regression learns a weight per word
   per class; an MLP learns non-linear combinations.
3. **Train** on `(features, label)` pairs from `train.csv`; weights adjust to reduce error.
4. **Predict:** new course → features → probability per class → argmax + its probability as
   confidence.

**Three tiers (the comparison *is* the required "training statistics"):**
1. **Majority baseline** — always predict "Business". Floor: ~32% accuracy, ~0 macro-F1 →
   proves accuracy alone is meaningless here.
2. **TF-IDF + Logistic Regression** — the linear baseline.
3. **The trained model** — TF-IDF → SVD → MLP, *or* sentence-embeddings + a classifier.

**Discipline:** fit on `train.csv` (1,805), tune on `dev.csv` (386), score **once** on
`test.csv` (386). Report **accuracy + macro-F1 side by side**, per-class P/R/F1, confusion
matrix. Macro-F1 > 0.90 on this data → suspect leakage before celebrating.

---

## 4. Model 2 — Skill → ESCO matcher

**Job:** map a course's skill strings onto the official ESCO taxonomy. **Input:** one
free-text skill string. **Output:** ranked ESCO concepts + similarity score. **Type:**
**unsupervised semantic retrieval / ranking.** There are **no course↔ESCO gold labels** — that
absence defines the whole design.

**How it works, mechanically:**
1. **Build an index:** encode every ESCO concept (label + description) into a vector.
2. **Encode the query:** the course skill string through the same encoder → its vector.
3. **Rank by cosine similarity** and return top-k. This is nearest-neighbour search — the
   "intelligence" lives in the pretrained encoder; nothing is trained on our data.
4. *(Optional stretch)* **cross-encoder re-ranker** reads each `(query, candidate)` pair jointly
   and re-scores the top-k. This one *can* be fine-tuned.

**Tiers:**
1. **Exact string match** — the baseline. Links only **7.4%** of course skill strings to ESCO
   (**92.6% unmatched**). *That number is the entire argument for a model over a lookup table.*
2. **Char + word n-gram TF-IDF cosine** — cheap, no downloads.
3. **Sentence-transformer embeddings** — likely the strongest.

**Evaluating with no labels (the clever bit, §5):** ESCO ships `altLabels` (human paraphrases,
99.6% populated). Hold one out per concept, remove it from the index, use it as a query whose
answer is known → thousands of free test queries. Metrics: **top-1, top-5, MRR@5**. Also report
on the *real* course vocabulary: what share clears a confidence threshold, with good/bad
examples. (Paraphrase test measures the method; course vocabulary measures the product.)

---

## 5. Rules the pipeline must not break (`MODEL_PLAN.md` §6)

1. **Frozen split.** One seed (42), committed; the split must not change once modelling starts.
2. **Macro-F1 next to accuracy, always.** Imbalance makes accuracy alone meaningless.
3. **Always compare against a baseline** (majority / exact-match).
4. **Dev selects, test reports.** Tune on dev; score test once, at the end.
5. **No notebook-only results.** Every reported number comes from a script in `scripts/` that
   writes to a file in `data/processed/`.
6. **Raw data is read-only.** Nothing writes back into `data/*.csv`.
7. **Log from the first run:** epochs · wall-clock train time · inference time/item · per-epoch
   loss · seed · hardware.

---

## 6. Repo layout & what has been built

```
data/                  raw CSVs (read-only)
data/processed/        generated outputs (frozen split + reports)
src/data_contract.py   shared paths, columns, label map, seed  [BUILT]
scripts/profile_data.py  fill rates, dupes, exact-match finding  [BUILT]
scripts/make_split.py    dedup + stratified 70/15/15 split       [BUILT]
docs/MODEL_PLAN.md     the plan this pipeline follows
docs/PIPELINE_AUDIT.md this file
```

**Already built and committed (branch `model/frozen-split-and-profiling`):**
- `src/data_contract.py` — single source of truth so the scripts can't drift apart.
- `scripts/profile_data.py` → writes `profile_report.md` + `profile_stats.json`.
- `scripts/make_split.py` → writes frozen `train/dev/test.csv`, `split_manifest.json`,
  `split_report.md`. Deterministic (seed 42); re-running gives identical output.

Both scripts need **only pandas + numpy** and run in the current env.

---

## 7. Current state

| Piece | Status |
|---|---|
| Cleaned raw data (courses + ESCO) | ✅ committed |
| Frozen train/dev/test split + profiling | ✅ built (branch, PR pending) |
| Model 1 (baselines + neural) | ⬜ not started |
| Model 2 (exact-match + retrieval + eval) | ⬜ not started |
| `scikit-learn` / `sentence-transformers` installed | ❌ not in env |
| ESCO target-space decision | ⚠️ **blocked** |

---

## 8. Blockers & open decisions (raise with the group)

1. **⚠️ ESCO target-space mismatch — blocks Model 2.** The plan (§4) wants to restrict the
   search space to *transversal (453) + cross-sector (3,788) = 4,241* concepts from
   `skills_en.csv`. But the committed `skills_clean.csv` has only **2,154 rows and no
   `transversal` level at all** (its taxonomy is cross-sector/sector-specific/occupation-
   specific). **Decide which file Model 2 indexes against before it starts.**
2. **Environment.** `pip install scikit-learn sentence-transformers` before any baseline runs.
   Confirm a sentence-transformer model actually downloads (do this early, not late).
3. **Dataset reuse not cleared with the lecturer** — required by the brief, still open. A
   Data-criterion risk no modelling fixes.
4. **Unused data.** `occupations_clean.csv` / `relations_clean.csv` / `ISCOGroups_en.csv` are in
   the repo but referenced by neither model — clarify whether they are a Data deliverable or an
   intended richer Model 2 (skill → occupation → "where a path leads").
5. **Distribution shift.** Model 1 is trained on Coursera only but the catalogue is mostly
   FutureLearn — note that the classifier generalises across sites unverified.

---

## 9. Roles & next steps

Two owners (Musaed, Mohamed), one model each (`MODEL_PLAN.md` §8).

**Shared, do first:**
1. Get the frozen split merged (PR) so everyone trains on the same rows.
2. Install `scikit-learn` + `sentence-transformers`.
3. Resolve blocker §8.1 with the group.

**Then, per track:**
- **Model 1 owner** → `scripts/baseline_model1.py` (majority + TF-IDF/LogReg on the frozen
  split) → then the neural model → per-class metrics + confidence intervals.
- **Model 2 owner** → `scripts/baseline_exact_match.py` (formalise the 7.4% floor) → TF-IDF
  cosine → embedding retrieval → the altLabel evaluation harness (§5).

Every script writes its numbers to `data/processed/` so the one-page report is assembled from
files, never notebook cells.

---

## Appendix — verified numbers (source of truth)

Run `python scripts/profile_data.py` and `python scripts/make_split.py` to regenerate.

| Quantity | Value |
|---|---|
| Course rows / columns | 8,092 / 45 |
| Coursera (labelled) rows | 2,819 |
| Labelled rows after dedup + label mapping | 2,577 |
| Text-duplicate rows dropped | 242 (within labelled set) |
| Duplicate `Title+Short Intro` (whole catalogue) | 3,103 |
| Localised category labels mapped to English | 7 |
| Split — train / dev / test | 1,805 / 386 / 386 |
| Biggest / smallest class (post-split total) | Business 824 / Math & Logic 22 |
| Distinct course skill strings | 4,229 |
| Model-2 exact-match rate | 7.4% (92.6% unmatched) |
| ESCO full skills (`skills_en.csv`) | 13,960 |
| ESCO transversal / cross-sector (in `skills_en`) | 453 / 3,788 |
| ESCO cleaned subset (`skills_clean.csv`) | 2,154 (no `transversal` level) |
| Seed | 42 |
