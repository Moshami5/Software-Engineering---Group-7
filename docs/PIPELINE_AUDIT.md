# Pipeline audit & briefing — Task 2 (Group 7)

**Purpose of this file.** A self-contained snapshot of the model-side pipeline: the goal,
the data, both models, how they work, what has been built, what is blocked, and who does
what next. Anyone — a teammate or a fresh AI session — should be able to read *only this
file* plus [`MODEL_PLAN.md`](MODEL_PLAN.md) and be fully oriented. Numbers here were
verified directly against the CSVs in `data/` (see the appendix), not copied from the plan.

_Last audited: 2026-09-24. Regenerate the data numbers with `python scripts/profile_data.py`
and `python scripts/make_split.py`; regenerate the model numbers by running the two notebooks
in `notebooks/`._

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
| `Online_Courses_ml_features.csv` | 5,275 | **Model 1's input.** Cleaned, deduplicated, feature-engineered course table (24 snake_case cols + numeric features). Sites: Coursera 2,819 · Future Learn 2,031 · Udacity 277 · Simplilearn 148 | **Model 1 + Model 2** |
| `Online_Courses.csv` | 8,092 | Original raw export (45 cols, many junk). **Retained for reference; the pipeline no longer reads it.** | — (raw ref) |
| `skills_en.csv` | 13,960 | Full ESCO skills export (preferredLabel, altLabels, description, reuseLevel) | Model 2 (`full_filtered`) |
| `skills_clean.csv` | 2,154 | ESCO skills **essential-linked to occupations** (the occupation-graph design) | Model 2 (`clean`) |
| `occupations_clean.csv` | 320 | ESCO occupations | occupation-graph (see §8.1) |
| `relations_clean.csv` | 8,377 | Essential occupation↔skill links | occupation-graph (see §8.1) |
| `isco_clean.csv` | 619 | ISCO occupation hierarchy (4-level code) | occupation-graph reference |

**Key facts about the course data (verified against the ML-features file):**
- `category` (Model 1's label) exists on **only the 2,819 Coursera rows** — every other site is
  unlabelled. Fill rate overall: 56.2%.
- `skills` (Model 2's input) is present on **39.7%** of rows (up from 25.9% in the raw export —
  the cleaning improved it).
- **11 canonical English categories**, plus 7 rows whose label is in another language
  (Chinese/Spanish/Portuguese/Japanese) — unambiguous translations, so we **map** them.
- Heavy class imbalance: Business 895 → Math & Logic 22.
- **Global dedup already applied by the data track** (8,092 → 5,275 rows), so only **306** rows
  now share an identical `title + short_intro` catalogue-wide. We still dedup on text within the
  Coursera label set (drops 242) before splitting — *not just URL* — so no course straddles the
  split (`MODEL_PLAN.md` §7).

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
data/                    raw CSVs (read-only), incl. team cleaning notebooks
data/processed/          generated outputs (frozen split + reports + model results)
src/data_contract.py     shared paths, snake_case column consts, label map, seed  [BUILT]
scripts/profile_data.py  fill rates, dupes, exact-match finding                   [BUILT]
scripts/make_split.py    dedup + stratified 70/15/15 split + sha256 checksums     [BUILT]
notebooks/model1_classifier.ipynb   majority → TF-IDF/LogReg → TF-IDF/SVD/MLP     [BUILT, RUN]
notebooks/model2_esco_matcher.ipynb exact → TF-IDF cosine → embeddings + altLabel [BUILT, RUN]
tests/test_frozen_split.py  guards the split (sha256 + leakage + shape)           [BUILT, 6/6]
docs/MODEL_PLAN.md       the plan this pipeline follows
docs/PIPELINE_AUDIT.md   this file
```

**Built and committed (branch `model/frozen-split-and-profiling`):**
- `src/data_contract.py` — single source of truth so scripts and notebooks can't drift apart.
- `scripts/profile_data.py` → `profile_report.md` + `profile_stats.json`.
- `scripts/make_split.py` → frozen `train/dev/test.csv`, `split_manifest.json` (with per-file
  sha256), `split_report.md`. Deterministic (seed 42).
- `tests/test_frozen_split.py` → fails if the committed split changes, leaks, or drifts.
- `notebooks/` → both models, executed; results written to `data/processed/`.

**Team files pulled in from `main`:** `Online_Courses_ml_features.csv`, `isco_clean.csv`, and the
two cleaning notebooks (`Online_Courses_Cleaning_Complete.ipynb`,
`ESCO_profile_cleaning_complete (1).ipynb`).

Scripts need only pandas + numpy. The notebooks additionally need scikit-learn, matplotlib, and
(for the Model 2 embedding tier) sentence-transformers.

---

## 7. Current state

| Piece | Status |
|---|---|
| Cleaned course data (ML-features) + ESCO tables | ✅ committed (merged from `main`) |
| Frozen train/dev/test split + profiling + test | ✅ built, retargeted to ML-features, 6/6 |
| Model 1 (baselines + neural) | ✅ **run** — best tfidf-logreg, test macro-F1 0.772 |
| Model 2 (exact-match + retrieval + eval) | ✅ **run** — both ESCO sources, altLabel eval |
| `scikit-learn` / `sentence-transformers` | ✅ available in base Anaconda (used to run) |
| ESCO design decision | ⚠️ **open** — plan vs implementation (see §8.1) |

---

## 8. Blockers & open decisions (raise with the group)

1. **⚠️ ESCO design: plan vs implementation — the one decision that matters.** This is *not*
   "which file has the right taxonomy" — it is two different products, both defensible:
   - **The plan (`MODEL_PLAN.md` §4)** specifies free-text matching against *transversal (453) +
     cross-sector (3,788) = 4,241* concepts from `skills_en.csv` — a general skill-matching index
     that drops occupation-specific distractors. (Notebook toggle: `ESCO_SOURCE="full_filtered"`.)
   - **The data track built** `skills_clean.csv` (2,154) as the skills **essential-linked to ISCO
     occupations** — an *occupation-anchored graph* (`isco_clean` + `skills_clean` +
     `relations_clean`), i.e. "occupation → required skills → course". (Toggle: `ESCO_SOURCE="clean"`.)

   Model 2 **runs under both** (numbers in the appendix), so nothing is blocked from executing —
   but the report can only present one, and the group must pick. **This also resolves what used to
   be a separate "unused data" blocker:** `occupations_clean` / `relations_clean` / `isco_clean`
   are not orphans — they *are* the occupation-graph design. Choosing it makes them central;
   choosing the plan's version makes them out of scope. Whichever is picked, update `MODEL_PLAN.md`
   §4 so the plan and the code agree.
2. **Dataset reuse not cleared with the lecturer** — required by the brief, still open. A
   Data-criterion risk no modelling fixes.
3. **Distribution shift.** Model 1 is trained on Coursera only but the catalogue is mostly
   non-Coursera — the classifier's generalisation across sites is unverified.

---

## 9. Roles & next steps

Two owners (Musaed, Mohamed), one model each (`MODEL_PLAN.md` §8).

**Done:** frozen split (retargeted to the ML-features file), both model notebooks built and
**executed**, all results written to `data/processed/`, frozen-split test passing 6/6.

**Remaining:**
1. **Push the branch and open the PR** so everyone shares the frozen split. (Squash-merge to keep
   history clean.)
2. **Resolve the ESCO design decision (§8.1)** with the group, then update `MODEL_PLAN.md` §4 and
   re-run Model 2 under the chosen source only for the report.
3. **Write the one A4 page** (Data / Model / Software), assembled from the result files in
   `data/processed/` — every number already lives there, never in a notebook cell.
4. **Clear dataset reuse with the lecturer** (§8.2).

Optional polish: 3-seed spread / confidence intervals for Model 1; a cross-encoder re-ranker tier
for Model 2.

---

## Appendix — verified numbers (source of truth)

Regenerate: `python scripts/profile_data.py`, `python scripts/make_split.py`, then run the two
notebooks. All figures below are from the actual reruns on the ML-features file (2026-09-24).

**Data & split**

| Quantity | Value |
|---|---|
| Course rows / columns (ML-features) | 5,275 / 24 |
| Coursera (labelled) rows | 2,819 |
| Labelled rows after dedup + label mapping | 2,577 |
| Text-duplicate rows dropped (within labelled set) | 242 |
| Duplicate `title+short_intro` (whole catalogue, post team-dedup) | 306 |
| Localised category labels mapped to English | 7 |
| Split — train / dev / test | 1,805 / 386 / 386 |
| Biggest / smallest class (post-split total) | Business 824 / Math & Logic 22 |
| Seed | 42 |

**Model 1 — Course → Category** (dev selects, test reports)

| Model | Dev accuracy | Dev macro-F1 |
|---|---|---|
| majority-baseline | 0.321 | 0.044 |
| **tfidf-logreg** (best) | **0.806** | **0.752** |
| tfidf-svd-mlp | 0.811 | 0.724 |

Test (best = tfidf-logreg): **accuracy 0.795, macro-F1 0.772**, inference 0.11 ms/item.
0.772 < 0.90 → no leakage smell.

**Model 2 — Skill → ESCO** (altLabel held-out eval; both sources, side by side)

| Metric | `full_filtered` (4,241) | `clean` (2,154) |
|---|---|---|
| Index size | 4,241 | 2,154 |
| Distinct course skill strings | 4,229 | 4,229 |
| Exact-match on vocab (vs this index) | 4.3% | 2.4% |
| TF-IDF cosine — top1 / top5 / MRR@5 | 0.758 / 0.926 / 0.826 | 0.816 / 0.927 / 0.864 |
| Embeddings — top1 / top5 / MRR@5 | 0.730 / 0.927 / 0.810 | 0.866 / 0.962 / 0.905 |
| Course-vocab share ≥ 0.35 sim | 61.5% | 65.9% |

The `clean` index scores higher throughout — it is smaller, so there are fewer distractors to
rank against; this is a property of the index, not evidence one design is "better" for the
product. Embeddings beat TF-IDF on `clean` but not on `full_filtered`.

**The headline exact-match finding is stable at 7.4%.** That number is course vocabulary vs the
**full** ESCO label set (`skills_en.csv`, 99,624 pref+alt labels) — computed by
`scripts/profile_data.py`: 312 / 4,229 distinct strings = **7.4% matched, 92.6% unmatched**. It
did **not** move despite the switch to the deduped 5,275-row file, because deduping *rows* barely
changes the *set* of distinct skill strings (still 4,229). The lower per-index numbers above (4.3%
/ 2.4%) are exact-match against the *restricted* index only — restricting the target space can
only lower exact coverage, which strengthens, not weakens, the case for a retriever.

**ESCO reference sizes**

| Quantity | Value |
|---|---|
| ESCO full skills (`skills_en.csv`) | 13,960 |
| ESCO transversal / cross-sector (in `skills_en`) | 453 / 3,788 |
| ESCO occupation-linked skills (`skills_clean.csv`) | 2,154 |
| ISCO groups (`isco_clean.csv`) | 619 |
