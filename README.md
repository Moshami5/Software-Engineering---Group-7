# Software-Engineering---Group-7

SE4CSAI course project, Tilburg University — **study-path advisor**.

A student describes an interest in their own words; the system returns a few coherent
study paths, each with concrete courses and the skills they lead to. The system narrows
and explains — it does not enrol or apply on anyone's behalf.

The part that needs intelligence: student interests and course descriptions are
inconsistent free text written for different purposes, and no fixed rule maps one onto
the other.

## Repository layout

```
data/                raw data as downloaded — read-only, never write here
data/processed/      cleaned data and the frozen train/dev/test split (generated, not committed)
src/                 library code: loading, preprocessing, splitting, models, pipeline
scripts/             one runnable stage each; every reported number comes from one of these
tests/               automated tests (pytest)
reports/             the per-task deliverables
```

Empty directories are held by `.gitkeep` files and fill up as each task lands.

## Working agreements

- **Raw data is read-only.** Cleaning writes to `data/processed/`, never back over the
  files in `data/`.
- **The split gets frozen.** Once the train/dev/test split is committed it does not
  change — a different split makes everyone's numbers incomparable. It is written with a
  fixed seed and a checksum manifest so a change fails loudly instead of silently.
- **Numbers must be regenerable.** Anything quoted in a report should come from a script
  in `scripts/` that can be re-run, so notebooks stay for exploration rather than being
  the only place a result exists.
- **Generated data is not committed** — see `.gitignore`; the scripts rebuild it.

## Status

| Task | Due | Status |
|---|---|---|
| 1 — Problem definition, goals, measurements | 11 Sep | done, in `reports/` |
| 2 — From data to AI | 25 Sep | in progress |
| 3 — Analysis (SRS) | 9 Oct | not started |
| 4 — Project management and implementation | 23 Oct | not started |
| 5 — Implementation and testing | 6 Nov | not started |
| 6 — Scaling up | 13 Nov | not started |
| 7 — Wrap up | 20 Nov | not started |

## Data

Four raw files in `data/`, ~47 MB total:

| File | Contents |
|---|---|
| `Online_Courses.csv` | scraped MOOC catalogue, 8,092 rows × 45 columns, four sites |
| `skills_en.csv` | ESCO skills pillar, 13,960 concepts |
| `ISCOGroups_en.csv` | ISCO-08 occupation hierarchy, 619 groups |
| `occupationSkillRelations_en.csv` | occupation ↔ skill links, 126,051 rows |

Only the Coursera rows in the catalogue carry a `Category` label, so the supervised
problem is defined on that subset.

Reuse of these datasets still needs to be cleared with the lecturer, as the brief requires.
