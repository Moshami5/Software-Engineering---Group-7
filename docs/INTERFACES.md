# Module interfaces (Sprint 1)

Agreed before coding starts so the Sprint 1 cards can be built in parallel. Each module
already exists as a stub with these signatures; the card owner replaces the
`NotImplementedError` with the real code and keeps the signature. If a signature has to
change, change it here and in `tests/test_interfaces.py` in the same pull request and tell
the team.

## Model 1: `src/model_category.py` (FR-14, AIR-1)

```python
course_text(title, intro) -> str              # "title. intro", exactly as in training (done)
classify(title, intro) -> (category, confidence)
```

- `category` is one of the 11 `CATEGORIES`; `confidence` is the top class probability, 0–1.
- Loads `MODEL1_PATH` (`data/processed/model1_tfidf-logreg.joblib`) once.
- Does **not** threshold. Returning "uncategorised" is `thresholds.py`'s job.

## Model 2: `src/model_skills.py` (FR-15, AIR-2)

```python
match(skill_text, k=5) -> list[SkillMatch]    # SkillMatch(esco_id, label, score)
```

- At most `k` results, sorted by `score` from high to low.
- Index: `ESCO_INDEX_CSV` = `data/skills_clean.csv` (2,154 skills), the index every
  reported Model 2 number uses. `esco_id` is the ESCO `conceptUri`.
- Does **not** threshold.

## Thresholds: `src/thresholds.py` + `config/thresholds.json` (FR-13, AIR-3)

```python
load_thresholds(path=THRESHOLDS_JSON) -> dict[str, float]
passes(score, kind, thresholds=None) -> bool  # score >= threshold
UNCATEGORISED = "uncategorised"; UNMATCHED = "unmatched"
```

- Four kinds: `category`, `occupation`, `retrieval`, `skill`. All are `null` until chosen
  on the **dev split only**; `load_thresholds` should refuse to run while any is `null`.

## Who uses what

| Card | Uses |
|---|---|
| Batch catalogue preparation | `classify`, `match`, `passes` |
| Integration tests I1 / I2 | `classify` + `passes`; `match` + `passes` |
| Input validation | none of these. It defines its own module (suggested `src/inputs.py`) |

All paths come from `src/data_contract.py`.
