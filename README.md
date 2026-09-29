# Software-Engineering---Group-7

SE4CSAI course project, Tilburg University — **study-path advisor**.

A student describes an interest in their own words; the system returns a few coherent
study paths, each with concrete courses and the skills they lead to. The system narrows
and explains — it does not enrol or apply on anyone's behalf.

The part that needs intelligence: student interests and course descriptions are
inconsistent free text written for different purposes, and no fixed rule maps one onto
the other.

**Group 7:** Musaed Al-Fareh, Melat Assefa, Alexia Cobzaru, Raluca Costache,
Mohamed Elshami, Bilgin Eren.

## Status

| Task | Due | Status | Where |
|---|---|---|---|
| 1 — Problem definition, goals, measurements | 11 Sep | submitted, then revised after lecturer feedback | `reports/Task1_Group7.*` (as submitted), `reports/Task1_Group7_revised.*` (use this one for the final report) |
| 2 — From data to AI | 25 Sep | submitted | `reports/Task2_Group7.*` |
| 3 — Analysis (SRS) | 9 Oct | in progress (draft) | `reports/Task3_Group7_SRS.*` |
| 4 — Project management and implementation | 23 Oct | not started | |
| 5 — Implementation and testing | 6 Nov | not started | |
| 6 — Scaling up | 13 Nov | not started | |
| 7 — Wrap up | 20 Nov | not started | |

## Repository layout

```
data/                         source tables — read-only for everything except the
│                             cleaning notebooks that live alongside them
├── Online_Courses.csv            raw MOOC catalogue export
├── skills_en.csv                 raw ESCO skills export
├── ISCOGroups_en.csv             raw ISCO-08 hierarchy export
├── occupationSkillRelations_en.csv  raw ESCO occupation ↔ skill links
├── Online_Courses_ml_features.csv   cleaned course table — Model 1 input
├── skills_clean.csv              cleaned ESCO tables — Model 2 index
├── occupations_clean.csv
├── relations_clean.csv
├── isco_clean.csv
└── *.ipynb                       the notebooks that produced the cleaned tables
data/processed/               everything derived from the source tables
├── train.csv, dev.csv, test.csv  the frozen split
├── split_manifest.json           seed + checksums the split is verified against
├── split_report.md, profile_*    data profiling
└── model1_*, model2_*            model results, figures, saved pipelines
src/data_contract.py          single source of truth: paths, columns, labels, seed
scripts/                      make_split.py, profile_data.py
notebooks/                    model1_classifier.ipynb, model2_esco_matcher.ipynb
tests/                        automated tests (pytest)
docs/                         plans, audits and working drafts
reports/                      submitted deliverables, one per task
environment.yml               conda environment (CSAI)
```

## Setup and reproducing results

```bash
conda env create -f environment.yml
conda activate CSAI

python -m pytest tests -q          # verifies the frozen split against its manifest
```

Run the model notebooks **from the repo root** — see `notebooks/README.md` for the
order and the one setting (`ESCO_SOURCE`) that has to be chosen in Model 2.
`scripts/make_split.py` rebuilds the split, but **do not re-run it casually**: every
reported number depends on the committed split, and the test fails if it changes.

## Working agreements

- **Source tables are read-only.** Only the cleaning notebooks in `data/` write there.
  Everything derived — the split, profiling, model results — goes to `data/processed/`.
- **The split is frozen and committed.** `train.csv`, `dev.csv`, `test.csv` and
  `split_manifest.json` are checked in on purpose: everyone trains and evaluates on the
  same rows, or no two results are comparable. `tests/test_frozen_split.py` fails if the
  files no longer match the manifest.
- **Paths come from `src/data_contract.py`.** Scripts, notebooks and tests all import
  their paths from there, so a file only ever needs moving in one place.
- **Numbers come from files, not from notebook cells.** Anything quoted in a report is
  written to `data/processed/` by the script or notebook that produced it.
- **What is committed is deliberate.** `.gitignore` lists each committed output
  explicitly; everything else under `data/processed/` is regenerated.

## Documents

| File | What it is |
|---|---|
| `docs/MODEL_PLAN.md` | guide for the modelling work in Task 2 |
| `docs/PIPELINE_AUDIT.md` | audit of the data and model pipeline |
| `docs/TASK2_REPORT.md` | source text of the Task 2 report |



## Data

| File | Rows | Contents |
|---|---:|---|
| `Online_Courses.csv` | 8,092 | raw MOOC catalogue, 45 columns, four sites |
| `Online_Courses_ml_features.csv` | 5,275 | cleaned and deduplicated, 24 columns |
| `skills_en.csv` | 13,960 | ESCO skills pillar, full export |
| `skills_clean.csv` | 2,154 | skills linked to the selected occupations |
| `occupations_clean.csv` | 319 | ESCO occupations, ISCO major group 2 |
| `relations_clean.csv` | 8,376 | occupation ↔ skill links for those occupations |
| `ISCOGroups_en.csv` / `isco_clean.csv` | 619 | ISCO-08 occupation hierarchy |
| `occupationSkillRelations_en.csv` | 126,051 | all ESCO occupation ↔ skill links |

Only the Coursera rows in the catalogue carry a `Category` label, so the supervised
problem is defined on that subset: 2,577 courses after deduplication, split
1,805 / 386 / 386 with seed 42.

Reuse of these datasets needs to be cleared with the lecturer, as the brief requires.
