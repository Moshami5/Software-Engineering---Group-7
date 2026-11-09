# Task 5 — Implementation and testing

**Due:** Fri 6 Nov 2026, 18:00 · **Points:** 6 · **Status:** report submitted 6 Nov; tests demonstrated in class 9 Nov

## What was asked

- Keep implementing: pick tasks from the board's To Do list and add new ones.
- Define **at least 5 unit tests and at least 3 integration tests**, each with test case,
  test data and expected result. Tests must run automatically (pytest; ideally in CI).
- Update the repo regularly.
- Demonstrate the tests in class during the practical session after the deadline.
- Report (max 1 page): the test cases, test data, results, and why these tests were chosen.

## Rubric

| Criterion | Points | Full marks when |
|---|---:|---|
| Unit tests | 2 | all well defined (input and expected output) and at unit level, not integration |
| Integration tests | 2 | all well defined and at component level, not unit |
| Implementation progress | 2 | implementation clearly follows the board's tasks and grows at a steady pace |

## Test plan and status (6 Nov)

The same rows as Table 1 in the report. Change a row to "pass" in the pull request that
merges the test.

| ID | Level | What it checks | Owner | Status | File |
|---|---|---|---|---|---|
| U1 | Unit | interest validation (FR-1) | Musaed | pass | `tests/test_interest.py` |
| U2 | Unit | study context, "not given" (FR-2, NFR-3) | Melat | pass | `tests/test_study_context.py` |
| U3 | Unit | thresholds (FR-13, AIR-3) | Bilgin | pass | `tests/test_thresholds.py` |
| U4 | Unit | Model 1 classify (FR-14, AIR-1) | Musaed | pass | `tests/test_model_category.py` |
| U5 | Unit | Model 2 match (FR-15, AIR-2) | Mohamed | pass | `tests/test_model_skills.py` |
| I1 | Integration | Model 1 + thresholds | Bilgin | pass | `tests/test_category_threshold_integration.py` |
| I2 | Integration | Model 2 + thresholds | Alexia | pass | `tests/test_i2_skill_matching.py` |
| I3 | Integration | batch catalogue preparation, 10 courses that list skills | Raluca | pass | `tests/test_integration_i3_batch_catalogue.py` |

Extra integration tests already in main: `tests/test_model_category_integration.py`
(real Model 1) and `tests/test_model_skills_integration.py` (real Model 2).

**CI:** every push and pull request runs the whole suite in GitHub Actions
(`.github/workflows/tests.yml`). On 6 Nov main ran 171 tests, all passing, in 54 s.

## Files

| File | What it is |
|---|---|
| `Task5_presentation.pptx` | slides used for the in-class test demo on 9 Nov (speaker notes included) |
| `Task5_Group7_Report.pdf` | the submitted one-page report |

Tests live in `tests/`.
