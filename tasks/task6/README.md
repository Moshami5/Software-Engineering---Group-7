# Task 6 — Scaling (up) the system

**Due:** Fri 13 Nov 2026, 18:00 · **Points:** 3 · **Status:** not started

## What was asked

Turn the components into a distributed system with at least:

- an **interface server** that handles user requests, checks for errors and stores data —
  it must **not** call the AI component directly;
- one or more **AI servers** hosting the models;
- one or more **orchestrator** servers between them (e.g. a queue such as RabbitMQ, or a
  database).

The servers may run on one machine as separate logical servers, locally or in the cloud
(tell the lecturer if using the cloud). Preliminary report: 1 page.

## Rubric

| Criterion | Points | Full marks when |
|---|---:|---|
| Distribution | 1.5 | each component is hosted on a different server |
| Interfacing | 1.5 | components communicate through a central point, peer-to-peer, or APIs — not interface → AI directly |

## Files

The one-page report goes here when written.
