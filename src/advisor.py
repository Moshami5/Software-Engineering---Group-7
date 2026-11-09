"""The whole advisor chain FR-1 -> FR-7 behind one call: ``advise(request) -> response``.

validate interest (FR-1) and study context (FR-2)
-> required skills from matching occupations (FR-3)
-> candidate courses (FR-4) -> feasible courses (FR-5) -> ranked study paths (FR-6, FR-7).

Request and response are plain dicts of JSON types, so the Task 6 AI server can take a
request off the orchestrator queue, call ``advise`` and put the response back unchanged.
The interface server never imports this module; it only sends requests to the queue.

Every step can be swapped for a fake (keyword arguments), so the unit tests run without
the sentence-transformers models or the catalogue files.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.interest import validate_interest  # noqa: E402
from src.study_context import validate_study_context  # noqa: E402

CONTEXT_FIELDS = ("language", "hours_per_week", "weeks_available", "completed_courses")


def _error(message: str) -> dict:
    return {"ok": False, "error": message}


def _course(candidate) -> dict:
    return {
        "course_key": str(candidate.course_key),
        "title": str(candidate.title),
        "category": candidate.category,
        "skills": [label for _, label in candidate.matched_skills],
    }


def _path(path, required_labels: dict[str, str]) -> dict:
    return {
        "fit": round(float(path.fit), 3),
        "weeks": round(float(path.weeks), 1),
        "courses": [_course(c) for c in path.courses],
        "covered_skills": sorted(required_labels[i] for i in path.covered if i in required_labels),
    }


def advise(request: dict, *, derive=None, retrieve=None, facts=None, durations=None) -> dict:
    """Run FR-1 -> FR-7 for one request and return a JSON-safe response.

    ``request``: {"interest": str, "language": str, "hours_per_week": number,
    "weeks_available": number, "completed_courses": [str]}; only "interest" is required.

    Response on bad input: {"ok": False, "error": <user-facing message>}.
    Otherwise {"ok": True, "context", "occupations", "required_skills", "paths",
    "removed", "left_out_no_duration", "message"}; ``message`` is None when 3-5 paths
    were found, else it says why there are fewer (no occupation, no courses, few paths).
    """
    if not isinstance(request, dict):
        return _error("Request must be a JSON object")

    interest = validate_interest(request.get("interest"))
    if not interest.ok:
        return _error(interest.error)
    context_result = validate_study_context(**{f: request.get(f) for f in CONTEXT_FIELDS})
    if not context_result.ok:
        return _error(context_result.error)
    context = context_result.value

    # Real steps are imported here so that importing this module stays cheap.
    if derive is None:
        from src.occupations import derive_required_skills as derive
    if retrieve is None:
        from src.retrieval import retrieve_for as retrieve
    if facts is None:
        from src.feasibility import load_facts
        facts = load_facts()
    if durations is None:
        from src.paths import load_durations
        durations = load_durations()
    from src.feasibility import assess
    from src.paths import build_paths

    required = derive(interest.value)                       # FR-3
    candidates = retrieve(interest.value, required.skills)  # FR-4 (falls back to the interest)
    feasibility = assess(candidates.courses, context, facts)  # FR-5
    # Paths are scored against FR-3's required skills. When no occupation matched,
    # retrieval fell back to skills close to the interest; those are the skills the
    # candidates were matched on, so score against them instead.
    scored = list(required.skills) or list(
        {i: label for c in candidates.courses for i, label in c.matched_skills}.items())
    paths = build_paths([k.course for k in feasibility.kept], scored, context, durations)  # FR-6, FR-7

    message = candidates.message or paths.message or required.message
    return {
        "ok": True,
        "interest": interest.value,
        "context": context.display(),
        "occupations": [{"label": o.label, "score": round(float(o.score), 3)}
                        for o in required.occupations],
        "required_skills": [label for _, label in required.skills],
        "paths": [_path(p, dict(scored)) for p in paths.paths],
        "removed": [{"title": str(r.course.title), "reason": r.reason} for r in feasibility.removed],
        "left_out_no_duration": paths.left_out_no_duration,
        "message": message,
    }
