# Task 2 — From data to AI

**Due:** Fri 25 Sep 2026, 18:00 · **Points:** 5 · **Status:** submitted 25 Sep; revised to v2 after feedback (1 Oct)

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

## Lecturer feedback (1 Oct) and what v2 changed

| Feedback | Change in v2 |
|---|---|
| Too long (aim for ≤ 1.5 pages); replace Table 1 with inline text | ~1.45 pages; the data table became one paragraph per V |
| Number all tables | Table 1 (Model 1, dev) and Table 2 (Model 2) with captions |
| Add a short introduction to the data | Opening paragraph: what data the system needs and which sources provide it |
| Volume: real size (MB) and resources; interesting statistics | 52.5 MB on disk, 115.8 MB in memory, fits a 16 GB laptop; class imbalance and skill fill rate |
| Velocity: how fast must data be processed; software performance | Batch data, per-query budget from the SRS (NFR-1, NFR-4); measured load and query times |
| Veracity: any cross-check that the data is truthful? | URL-vs-site check (8,092/8,092), label consistency of repeated courses (0 conflicts), ESCO referential integrity (100%) |
| Model: "in general, a good analysis" | Unchanged apart from tightening |
| Model adequacy: how does Model 2 generalise to real data? | New paragraph: why Table 2 is optimistic, 65.9% of real course skills clear 0.35, thresholding (FR-13), planned manual check (AIR-2) |

Also fixed: the 7.4% exact-match figure now says what it is measured against (all 99,624
ESCO labels; 2.4% against our 2,154-skill index), and the relations count is corrected
(8,376, not 9,376). New figures come from `scripts/data_resources.py`, which writes
`data/processed/data_resources.json`.

## Files

| File | What it is |
|---|---|
| `Task2_Group7_v1_submitted.docx` / `.pdf` | as submitted on 25 Sep |
| `Task2_Group7_v2.docx` / `.pdf` | current version — **use this one for the Task 7 final report** |
| `TASK2_REPORT.md` | source text of v1 |

Model code, results and the frozen split live in `notebooks/`, `src/` and `data/processed/`.
