#!/usr/bin/env python3
"""Conversion Read — the diagnosis brain.

Reads a page's real copy and scores how well it converts on 6 dimensions, then
emits the frozen Conversion Read JSON. Mirrors plan_job's strict-JSON discipline:
JSON-only prompt, frozen contract restated verbatim, retry-then-deterministic
fallback so the pipeline NEVER crashes on a small model's malformed output.

Reuses validate_planner.call_model / extract_json (the exact OpenRouter path the
planner uses) so the analyze call inherits the planner's reasoning-off + token
accounting + brain-registry behavior. Default brain = super-free ($0).
"""
import json
import sys

import brain as brain_mod
import validate_planner as vp

# Frozen contract — consumers (build_runner, the dashboard, the plan seeder) read
# these exact names. Order of dimensions is free; presence of all six is required.
DIMENSION_KEYS = ("promise", "outcome", "proof", "show", "specificity", "cta")
SCORE_MIN, SCORE_MAX = 0, 5


def validate_read(read):
    """Return a list of human-readable problems with a Conversion Read dict (empty
    list = valid). Checks the frozen contract: url/verdict/headline_fix strings,
    all six dimensions present with an int score in [0,5] + finding/evidence/fix
    strings, and priority_fixes a list of {rank,fix,maps_to}. Never raises."""
    problems = []
    if not isinstance(read, dict):
        return ["read is not a dict"]
    for key in ("url", "verdict", "headline_fix"):
        if not isinstance(read.get(key), str) or not read.get(key).strip():
            problems.append("missing or empty string field: %s" % key)
    dims = read.get("dimensions")
    if not isinstance(dims, list):
        problems.append("dimensions is not a list")
        dims = []
    seen = {}
    for d in dims:
        if not isinstance(d, dict):
            problems.append("dimension is not a dict")
            continue
        k = d.get("key")
        seen[k] = seen.get(k, 0) + 1
        s = d.get("score")
        if not isinstance(s, int) or isinstance(s, bool) or not (SCORE_MIN <= s <= SCORE_MAX):
            problems.append("dimension %r score out of range: %r" % (k, s))
        for sub in ("finding", "evidence", "fix"):
            if not isinstance(d.get(sub), str):
                problems.append("dimension %r missing string %s" % (k, sub))
    for k in DIMENSION_KEYS:
        if seen.get(k, 0) != 1:
            problems.append("dimension %r must appear exactly once (got %d)" % (k, seen.get(k, 0)))
    pf = read.get("priority_fixes")
    if not isinstance(pf, list) or not pf:
        problems.append("priority_fixes must be a non-empty list")
    else:
        for fix in pf:
            if not isinstance(fix, dict) or not isinstance(fix.get("fix"), str) or not fix.get("fix").strip():
                problems.append("priority_fix missing a non-empty 'fix' string")
    return problems


def minimal_read(url, body_text=""):
    """Deterministic, always-valid Conversion Read used when the live model is
    unavailable / unparseable, or the page could not be read. Marked degraded=True
    so the dashboard can flag it as a best-effort diagnosis. NEVER raises — this is
    the floor that guarantees the pipeline always has a Read object to seed/render."""
    snippet = (body_text or "").strip().replace("\n", " ")[:120]
    evidence = snippet or "(page copy unavailable)"
    dims = [
        {"key": k, "score": 2,
         "finding": "Not assessed in detail — using a best-effort baseline read.",
         "evidence": evidence,
         "fix": "Lead with the buyer's outcome and add one concrete proof point."}
        for k in DIMENSION_KEYS
    ]
    return {
        "url": url,
        "verdict": "Best-effort read: lead with the outcome and show one real proof point.",
        "dimensions": dims,
        "priority_fixes": [
            {"rank": 1, "fix": "Open on the buyer's outcome, not a feature list.", "maps_to": "outcome"},
            {"rank": 2, "fix": "Show one real, specific proof point (number, demo, or logo).", "maps_to": "proof"},
        ],
        "headline_fix": "The outcome your customer gets — in one clear line.",
        "degraded": True,
    }
