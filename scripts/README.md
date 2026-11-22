# `scripts/`: things you run from the command line

Run every script **from the repo root** in the CSAI environment, e.g.
`python scripts/run_servers.py --check`. Each one writes its output to `data/processed/`
(or `runtime/` for the servers), so every number in a report can be regenerated.

| Script | Task | What it does | Output | Run it when |
|---|---|---|---|---|
| `run_servers.py` | 6 | starts the orchestrator and the interface (the orchestrator starts the AI server); `--check` sends real requests end to end and stops | `runtime/logs/*.log` | you want to see or demo the whole system |
| `prepare_catalogue.py` | 5 | runs Model 1 and Model 2 over every course once (Phase 1, ~105 s) | `catalogue_enriched.csv`, `skill_matches.csv` | the catalogue or a model changed |
| `update_pipeline.py` | 7 | FR-16 / AIR-7: takes a new catalogue (and optionally a new ESCO file), retrains Model 1, re-runs the batch preparation in `data/staging/`, runs 11 acceptance checks (`config/acceptance_criteria.json`) and only then replaces the live files, with a backup; `--dry-run` checks without replacing | `version_record.json` per run in `data/releases/` | a new catalogue or ESCO release arrives |
| `bias_eval.py` | 7 | AIR-6 bias check: 48 paired inputs that differ only in gender, age or origin; `--strict` exits 1 if any pair differs | `bias_eval.json`, `bias_eval.md` | before adopting a new model version |
| `make_split.py` | 2 | builds the frozen train/dev/test split (seed 42) | `train.csv`, `dev.csv`, `test.csv`, `split_manifest.json` | **never casually**: every reported number depends on the committed split |
| `profile_data.py` | 2 | profiles the raw data; reproduces the "exact match finds ~4%" finding | `profile_report.md`, `profile_stats.json` | to re-check the data numbers |
| `data_resources.py` | 2 | measures data volume, load and query speed, veracity checks (Task 2 feedback) | `data_resources.json` | to re-check the 4 V's numbers |

## Typical commands

```bash
python scripts/run_servers.py --check      # prints "ok ..." per step and PASSED (exit code 0)
python scripts/run_servers.py              # leave the servers running; Ctrl+C stops all of them
python scripts/prepare_catalogue.py        # rebuild the Phase 1 results
python scripts/bias_eval.py                # re-run the bias check (~1 min)
python scripts/update_pipeline.py --catalogue new.csv --catalogue-version 2026-12 --dry-run
                                           # check a new catalogue without replacing anything (~1.5 min)
```

`run_servers.py` needs ports 8000, 8001 and 8002 to be free; it tells you if one is not.
