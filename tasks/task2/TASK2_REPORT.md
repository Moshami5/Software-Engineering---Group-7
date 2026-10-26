# Task 2 — From data to AI (Group 7)

_Draft for the one-page submission. Export to PDF and trim to one A4 before uploading.
Confirm the dataset-source clearance with the lecturer and remove this note._

## Data

Two sources: an online-course catalogue (Coursera, FutureLearn, Udacity, Simplilearn)
providing course text and subject labels, and the ESCO skill taxonomy providing the target
skill vocabulary. _(Dataset source to be confirmed with the lecturer.)_

- **Volume:** 8,092 raw course rows → **5,275** after cleaning/deduplication; **2,819** carry a
  subject label (Coursera only). ESCO: 13,960 skills, cleaned to **2,154** occupation-linked
  skills used as the match target; 619 ISCO groups.
- **Velocity:** static downloaded snapshot; course catalogues and ESCO change slowly (~yearly),
  so batch processing — no streaming pipeline needed.
- **Variety:** free text (titles, short intros, comma-separated skills), 11 subject categories
  plus a few non-English category labels; ESCO adds a structured multilingual taxonomy.
- **Veracity:** labels exist only for Coursera; classes are very uneven (Business 32%, Math &
  Logic 22); `skills` is filled on only 39.7% of rows; 306 rows share identical title+intro;
  **no gold course↔ESCO pairs exist.**

**Preprocessing (statistics collected):** aligned a source side (title+intro / skill string)
with a target side (category / ESCO skill); deduplicated on title+intro; mapped the 7 localised
category labels to their English class; built a **frozen stratified split** (1,805 / 386 / 386,
seed 42) guarded by a checksum test so results stay comparable. Recorded fill rates, class
distribution, duplicate counts, and the 7.4% exact-match finding.

## Model

We combine two models, each solving one part of the task. Model 1 sorts a course into a subject
so the system can narrow the catalogue; Model 2 matches a course's free-text skills to ESCO
skills so the system can explain where a study path leads.

**Model 1: Course → Category (supervised classification).** Input: course title + short intro.
Output: one of 11 categories + confidence. Data: the 2,577 labelled Coursera courses left after
removing duplicates; fixed stratified split of 1,805 train / 386 dev / 386 test (seed 42). Three
models were compared on dev; the best dev macro-F1 was selected and the test set was scored once.

| Model | Dev accuracy | Dev macro-F1 | Training | Inference |
|---|---|---|---|---|
| Majority-class baseline | 0.321 | 0.044 | – | <0.01 ms/item |
| TF-IDF + Logistic Regression (selected) | 0.806 | 0.752 | 0.62 s | 0.13 ms/item |
| TF-IDF → SVD(300) → MLP (256 hidden) | 0.811 | 0.724 | 7.18 s, 92 epochs, final loss 0.022 | 0.09 ms/item |

Test result (Logistic Regression): **accuracy 0.795, macro-F1 0.772.** Macro-F1 is reported next
to accuracy because classes are very uneven (Business 32%, Math & Logic only 22 courses); always
guessing Business already gives 32% accuracy. The weakest classes are the smallest (Social
Sciences F1 0.58, Personal Development 0.64). The MLP's training loss drops almost to zero while
its dev macro-F1 is lower, so it overfits the 1.8k training examples; we therefore kept the
simpler linear model.

**Model 2: Skill → ESCO (semantic retrieval).** Input: one free-text course skill. Output: top-5
ESCO skills + similarity score. Nothing is trained on our data: the 2,154 occupation-linked ESCO
skills are ranked by cosine similarity using a pretrained sentence encoder (`all-MiniLM-L6-v2`)
or word + character TF-IDF. Exact string matching links only 7.4% of the 4,229 distinct course
skills to ESCO, so a lookup table is not enough. With no labelled course–ESCO pairs, we held out
one alternative label per ESCO skill and used it as a query with a known answer.

| Method | Top-1 | Top-5 | MRR@5 |
|---|---|---|---|
| Exact string match (baseline) | 0.000 | – | – |
| Word + character TF-IDF cosine | 0.816 | 0.927 | 0.864 |
| Sentence embeddings (`all-MiniLM-L6-v2`) | 0.866 | 0.962 | 0.905 |

On the real course skills, 65.9% reach a similarity of at least 0.35 (TF-IDF).

**Model adequacy.** Both are standard machine-learning methods sized to the data. A keyword
lookup is too simple (matches only 7.4% of skills); fine-tuning or training a transformer on
~1.8k labelled texts would be too complex and would overfit. Everything runs on a CPU (Intel,
Windows 11) in seconds, no GPU needed.

## Software

**Language / environment:** Python 3.11, conda env (`environment.yml`, `CSAI`), Jupyter
(`ipykernel`), Git; CPU-only (Intel, Windows 11).

- **Data — collection, cleaning, exploration, split:** pandas (load/merge, dedup, statistics,
  split I/O), NumPy (numeric ops, seeded RNG), `re` (text normalisation), matplotlib + seaborn
  (exploratory charts), IPython.display (notebook tables), hashlib (split checksums), pathlib /
  json (paths, manifest).
- **Model — training, evaluation, retrieval:** scikit-learn (`TfidfVectorizer`, `TruncatedSVD`,
  `LogisticRegression`, `MLPClassifier`, `DummyClassifier`, `Pipeline`, `StandardScaler`,
  metrics + `cosine_similarity`, stratified split); sentence-transformers `all-MiniLM-L6-v2`
  (PyTorch backend) for embeddings; joblib (save fitted models); matplotlib (confusion matrix,
  loss curve); platform (capture run environment).
- **Reproducibility / dev:** Jupyter nbconvert (headless runs), Git (version control), conda
  `environment.yml` (pinned env), fixed seed 42.
