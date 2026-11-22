# Task 7 — Wrapping up (final report)

**Due:** Mon 23 Nov 2026, 11:00 (moved by the lecturer from Fri 20 Nov) · **Points:** 2 · **Status:** final report in progress

Followed by the **project presentation** on 30 Nov (7 points; 10–15 minutes plus 5–7
minutes of questions; every member must attend, and each gets an individual question).

## What was asked

- **Code:** clean, documented, all tests passing, everything committed and merged to main.
- **Operation:** the software runs as designed; the SRS matches the final design.
- **AI:** the models work, the APIs are in place, the models are the latest version.
- **Report:** concatenate the reports of Tasks 1–6 (revised so they tell one coherent
  story), plus:
  - teamwork, max half a page: each member's roles and tasks, how the team worked
    together, the main challenges and how they were overcome;
  - value sensitive design and environmental impact, max half a page together: would design,
    development and testing have been done differently under VSD? What is the carbon
    footprint of the AI component and of the non-AI part?

## Rubric

| Criterion | Points | Full marks when |
|---|---:|---|
| Submitted on time | 1 | on time |
| Teamwork | 2 | half a page that clearly identifies each member's role |
| VSD | 3 | reflects on all three aspects (design, development, testing) |
| Environmental considerations | 3 | reflects on both the AI and the non-AI parts |

## Inputs to collect along the way

- Revised reports: `tasks/task1/Task1_Group7_revised.*`, Task 2 with the 1 Oct feedback
  applied, `tasks/task3/Task3_Group7_SRS_v2.*`.
- Training and inference times for the carbon-footprint section.
- Each sprint's scrum master and who owned which board cards, for the teamwork section.

## Done for Task 7 (Sprint 4, 16–22 Nov)

| What | Requirement | PR |
|---|---|---|
| Real orchestrator after the Task 6 feedback | Task 6 | #42 |
| Re-evaluate when inputs change | FR-12 | #43 |
| SRS v3: every requirement compared with the built system | Task 7 "Operation" | #44 |
| Model 2 evaluation re-run with the alt-label fix | FR-15, AIR-2 | #45 |
| Explain every study path | FR-8 – FR-11, NFR-6, AIR-5 | #46, #47 |
| Bias evaluation with paired inputs | AIR-6, NFR-7 | #48 |
| Documentation for the whole project | Task 7 "Code" | `docs/HOW_IT_WORKS.md` |

## Files

The final report (`Task7_Group7_Final_Report.pdf`) goes here when submitted.
