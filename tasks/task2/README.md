# Task 2 — From data to AI

**Due:** Fri 25 Sep 2026, 18:00 · **Points:** 5 · **Status:** submitted 25 Sep; feedback (1 Oct) not yet applied

## What was asked

Collect and explore the data (volume, velocity, variety, veracity), preprocess it, split it
into train/dev/test, train and evaluate a supervised model, and combine models into the full
intelligence. One A4 page with three sections: Data, Model (with statistics: evaluation
metrics, training time, inference time, epochs), Software used.

## Rubric

| Criterion | Points | Full marks when |
|---|---:|---|
| Data | 2 | collected, analysed, statistics collected, preprocessed adequately |
| Model | 2 | trained and evaluated, statistics presented |
| Model adequacy | 1 | ML/DL approach that fits the task; not too simple, not too complex |

## Lecturer feedback (1 Oct) — to apply before the Task 7 final report

- Too long: aim for at most 1.5 pages; replace Table 1 with inline text.
- Number all tables.
- Data: add a short introduction to the data.
  - Volume: give the real size (MB/GB) and the resources needed to load and work with it;
    add interesting statistics (class imbalance, features).
  - Velocity: how fast must the data be processed, and how does the software perform
    (loading into memory, querying)?
  - Veracity: any cross-check that the data is truthful?
- Model: "in general, a good analysis".
- Model adequacy: the skill matcher is a simple sentence-embedding model but works; explain
  how it generalises to real-world data.

## Files

| File | What it is |
|---|---|
| `Task2_Group7.docx` / `.pdf` | as submitted on 25 Sep |
| `TASK2_REPORT.md` | source text of the report |

Model code, results and the frozen split live in `notebooks/`, `src/` and `data/processed/`.
