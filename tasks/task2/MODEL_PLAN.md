# Model plan — Task 2

**Owners:** Mohamed Elshami, Musaed Al-Fareh — Group 7, model task.
**Deadline:** Fri 25 Sep, 18:00.
**Status:** waiting on the processed data. This is the guide we follow once it lands.

Repo layout we work in: raw data in `data/`, processed output in `data/processed/`, our code in
`src/` and `scripts/`, tests in `tests/`.

---

## 1. What we are building

Two models. Different shapes, and neither is the product on its own.

| | Model 1 | Model 2 |
|---|---|---|
| Task | course text → `Category` | course skill string → ESCO concept |
| Type | supervised classification | retrieval / ranking |
| Input | Title + Short Intro | one free-text skill string |
| Output | 1 of 11 categories + confidence | ranked ESCO concepts + similarity score |
| Labels | Coursera rows only; final count after cleaning | **none exist — see §5** |
| Job in the product | narrows ~5,000 courses to a few | explains where a path leads |

Model 1 alone returns a category name and no sense of what it opens up. Model 2 alone has no
way to narrow the catalogue down to what is worth matching.

---

## 2. What the data needs to meet before modelling starts

Modelling can begin once these exist in `data/processed/` as **files, not notebook cells**:

- [ ] `train.csv` / `dev.csv` / `test.csv` — a **frozen, stratified** split
- [ ] The **seed** used, written down and committed
- [ ] Row counts per split, and the class distribution in each
- [ ] The list of columns kept and dropped, with fill rates — this is a Data-criterion
      deliverable, not just our input
- [ ] Confirmation of how duplicates were handled (see §7)

Once the split is committed it **must not change**. If it changes after modelling starts, every
number reported becomes worthless and the work is done twice.

**In the meantime,** until the data is ready, we can already work on the evaluation code, the
baselines and the tests. None of that needs the final data — only the agreed column names — so
it is worth starting now rather than waiting.

---

## 3. Model 1 — options

| Approach | Verdict |
|---|---|
| Keyword / rule mapping | ✗ **too simple** — not a learned model, fails the adequacy line |
| Majority class | floor only — but we must report it |
| TF-IDF + logistic regression / linear SVM | solid baseline; **on its own** reads as too simple |
| TF-IDF → SVD → small neural net (MLP) | ✓ good target — a real trained model, trains in seconds |
| Sentence embeddings + classifier | ✓ likely the strongest for the effort |
| Fine-tuned DistilBERT / MiniLM | defensible, ~1 day, only if data lands early |
| Transformer from scratch, or LLM fine-tune | ✗ **too complex** — overfits ~2.7k rows, unevaluable in the time |

**Plan:** majority baseline → TF-IDF + logistic regression → one neural approach. Report all
three in one table. The comparison *is* the "training statistics" the rubric asks for, so the
baselines are not wasted work.

---

## 4. Model 2 — options

| Approach | Verdict |
|---|---|
| Exact string match against ESCO labels | baseline — must be reported, it *is* the finding |
| Fuzzy / Levenshtein | marginal, still surface-level |
| Character + word n-gram TF-IDF, cosine retrieval | ✓ strong, cheap, no downloads needed |
| Sentence-transformer embeddings | ✓ likely better; needs a model download — **test this early** |
| + cross-encoder re-ranker on top-k | strongest, ~2 days, only if everything else is done |
| LLM scoring every pair | ✗ too slow, nothing trained, nothing to report |

**Restrict the target space** to the transversal (453) + cross-sector (3,788) ESCO concepts —
4,241 total. Occupation-specific skills ("supervise correctional procedures") cannot appear in
a course blurb and only add distractors.

**The finding this model exists to justify:** our own profiling already shows exact string
matching links only ~4–8% of the catalogue's ~4,274 distinct skill strings to ESCO — roughly
**92% unmatched**. That is the empirical argument for using a model instead of a lookup table,
and the baseline any matcher has to beat. Reproduce it in code so it can be cited.

---

## 5. How to evaluate Model 2 without labels

This is the hard part and it needs deciding early. We have **no annotated course↔ESCO pairs**,
and annotating them properly in a week is not realistic.

**Proposed approach — held-out alternative labels.** ESCO ships `altLabels`: human-written
paraphrases of each concept. Hold one out per concept, **remove it from the search index**, and
use it as a query whose correct answer we already know. That yields several thousand labelled
test queries at zero annotation cost.

- Metrics: top-1 accuracy, top-5 accuracy, MRR@5
- The exact-match baseline will score near zero on this by construction — it cannot retrieve a
  phrasing it has never seen. That is precisely the product problem, so it is a fair framing,
  but say so explicitly rather than presenting it as a crushing win.
- Also report behaviour on the **real course vocabulary**: what share of strings clear the
  confidence threshold, with a few concrete examples of good and bad matches. The paraphrase
  test measures the method; the course vocabulary measures the product.

Alternative if this is rejected: hand-annotate ~200 pairs between us using written guidelines.
More defensible, and considerably more work.

---

## 6. Rules we must not break

1. **Frozen split.** One seed, committed, with a test that fails if it changes.
2. **Macro-F1 next to accuracy, always.** Business is ~32% of the labelled data and Math and
   Logic is 22 rows — a majority guesser scores ~32% accuracy and near-zero macro-F1. Accuracy
   alone is meaningless here, and saying so in the report earns marks.
3. **Always compare against a baseline.** Majority class and a linear model, every time.
4. **Dev selects, test reports.** Tune on dev; score test once, at the end.
5. **No notebook-only results.** Every number in the report comes from a script in `scripts/`
   that writes its output to a file. The report is built from those files.
6. **Raw data is read-only.** Nothing writes back into `data/`.

**Statistics to log from the first run, not the last** — the brief names these explicitly, and
they are painful to reconstruct afterwards:
epochs · wall-clock training time · inference time per item · per-epoch loss · seed · hardware.

---

## 7. Things to watch for on this dataset

- **Near-duplicate leakage.** The catalogue has ~4,318 duplicate rows. Deduplicating on `URL`
  alone may not catch courses re-listed under a different URL with identical title and blurb.
  If those land on both sides of the split, every score is inflated. Check for duplicate
  title+intro text, not just duplicate URLs, and note which of the two was done.
- **A suspiciously good score is a bug, not a result.** If Model 1 macro-F1 comes out above
  ~0.90 on 11 imbalanced classes with this little data, suspect leakage before celebrating.
- **The `Skills` column is not a controlled vocabulary.** It contains numbered learning
  objectives ("1. understand the meaning of...") and some German entries. Clean before matching.
- **Localised category labels.** A handful of rows have the category in Chinese, Spanish,
  Portuguese or Japanese. Map them to their English class or drop them — decide, and write the
  decision down.
- **Test the baselines too.** A silent bug in a baseline makes the model look better than it is,
  and it is the number the whole report rests on.

---

## 8. Splitting the work

Two tracks that can run in parallel, one each — to be divided between us:

- **Model 1** — classifier: baselines, neural approach, per-class metrics, confidence intervals
- **Model 2** — ESCO matching: exact-match baseline, the matcher, the confidence threshold, and
  the evaluation design in §5

Both write results to files in a shared format so the report can be assembled from them.

---

## 9. How we get there

Phases rather than fixed days — we sync as a team at the practical session and adjust from there.

| Phase | Work |
|---|---|
| **Before the data lands** | Agree this plan. Write the evaluation and baseline code against the agreed column names. **Check that `sentence-transformers` installs and a model downloads** — better to find out early than late |
| **When the data lands** | Verify the split: no leakage, class balance sane, counts match those reported |
| **First pass** | Baselines for both models — majority class, and the exact-match baseline. Everything else is measured against these |
| **Second pass** | Neural approaches, then the threshold sweep and any ablations. Tune **on dev** |
| **Final** | Freeze the numbers, rerun the tests, write the one page, check it line by line against the rubric wording. Leave buffer before the deadline |

---

## 10. Open questions — raise these with the group

- **Dataset reuse has not been cleared with the lecturer.** Required by the brief, open since
  the start. This is a Data-criterion risk that no amount of modelling fixes.
- **Does a content-based approach with no student behaviour data satisfy "model adequacy"?**
  Worth asking in the workshop before we commit.
- **The UniSkill proposal.** The retrieve-then-validate architecture in it is a good idea and
  maps well onto our Model 2. Before we schedule work around it, someone should confirm the
  dataset is actually downloadable — the plan depends entirely on it, and reusing it would also
  need the lecturer's sign-off like any other external dataset.
- **Task 1 KPIs 4.1 and 4.2 measure nearly the same thing.** Not urgent for Task 2, but the
  final report is built from all seven sections, so it has to be fixed at some point.
