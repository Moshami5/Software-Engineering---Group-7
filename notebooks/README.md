# Notebooks

Run from the **repo root** with the `CSAI` env (`environment.yml`).
The frozen split must exist first: `python scripts/make_split.py`.

- `model1_classifier.ipynb` — supervised course→category classifier.
  Writes `model1_results.{json,md}`, `model1_confusion.png`,
  `model1_loss_curve.png` to `data/processed/`.
- `model2_esco_matcher.ipynb` — ESCO retrieval. **Set `ESCO_SOURCE` in cell 2**
  (`"full_filtered"` | `"clean"`) — a group decision, still open. Writes
  `model2_results_<ESCO_SOURCE>.json` and `model2_match_examples_<ESCO_SOURCE>.csv`.
  The embedding tier needs `sentence-transformers` (not in `environment.yml`); the
  exact-match and TF-IDF tiers run without it.

Numbers in the report come from `data/processed/`, never from a notebook cell.
