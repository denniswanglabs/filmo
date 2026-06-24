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
import re
import sys

import brain as brain_mod
import validate_planner as vp

# Frozen contract — consumers (build_runner, the dashboard, the plan seeder) read
# these exact names. Order of dimensions is free; presence of all six is required.
DIMENSION_KEYS = ("promise", "outcome", "proof", "show", "specificity", "cta")
SCORE_MIN, SCORE_MAX = 0, 5


# --- ANALYZE-LOCAL JSON REPAIR ------------------------------------------------
# The super-free Nemotron 120B reliably emits a handful of small malformations
# that break strict json.loads (and therefore vp.extract_json). The most common,
# and the one that DEGRADED the Read ~2/3 of runs, is packing multiple
# comma-separated quoted strings into ONE field value, e.g.
#     "evidence": "Financial infrastructure", "and", "Millions of companies",
# which strict JSON reads as an extra (key-less) value and rejects. We repair
# these locally, on the ANALYZE path ONLY -- the shared vp.extract_json /
# planner stay untouched to avoid planner regressions.

# Curly/smart quote -> straight quote. (Apostrophes inside words are handled by
# only swapping the double-quote variants; single curly quotes are left as text
# unless they sit at a value boundary, which json tolerates inside a string.)
_SMART_QUOTES = {
    "“": '"', "”": '"',  # “ ”
    "‘": "'", "’": "'",  # ‘ ’
}

# A run of >=2 comma-separated double-quoted fragments sitting where a single
# OBJECT VALUE belongs:   "key": "frag1", "frag2"[, "frag3"...]  followed by a
# value terminator (a comma+next-key, or a closing } / ]). The run MUST begin
# right after a ':' -- i.e. a value position -- so we never touch a genuine
# string array like ["a","b","c"] (whose elements follow '[' or ',', never ':').
_FRAGMENT_RUN = re.compile(
    r'(?P<lead>:\s*)'                         # object-value position: after ':'
    r'(?P<frags>"(?:[^"\\]|\\.)*"'            # first quoted fragment
    r'(?:\s*,\s*"(?:[^"\\]|\\.)*")+)'         # >=1 more comma-separated fragments
    r'(?P<tail>\s*[,}\]])'                    # terminator: , } or ]
)


def _collapse_fragment_run(m):
    """Join a run of comma-separated quoted fragments into ONE JSON string,
    space-separated, preserving each fragment's text."""
    pieces = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group("frags"))
    joined = " ".join(p.strip() for p in pieces if p.strip())
    return '%s"%s"%s' % (m.group("lead"), joined, m.group("tail"))


def _requote_single_quoted(t):
    """Convert SINGLE-quoted JSON keys/values to double-quoted, e.g.
        "finding": 'Primary CTAs are clear ("Get started", "Sign up") but ...'
    The super-free model reaches for single quotes precisely when a value already
    contains double quotes, which strict JSON rejects. We rewrite only single
    quotes that sit at a key/value DELIMITER position (after { [ : , or run start,
    ignoring whitespace) and run to a matching close (a ' followed by : , } ] or
    end). Inner double-quotes in the rewritten token are escaped; apostrophes
    inside legit double-quoted strings are never touched (we skip those spans).
    ANALYZE-path only."""
    out = []
    i, n = 0, len(t)
    while i < n:
        c = t[i]
        if c == '"':  # skip an entire double-quoted string verbatim
            out.append(c)
            i += 1
            while i < n:
                out.append(t[i])
                if t[i] == "\\" and i + 1 < n:
                    out.append(t[i + 1]); i += 2; continue
                if t[i] == '"':
                    i += 1; break
                i += 1
            continue
        if c == "'":
            # Is this a delimiter-position opening quote? Look back past spaces.
            j = len(out) - 1
            while j >= 0 and out[j] in " \t\r\n":
                j -= 1
            prev = out[j] if j >= 0 else "{"
            if prev in "{[:,":
                # consume to the closing ' that precedes : , } ] or end
                k = i + 1
                buf = []
                while k < n:
                    if t[k] == "\\" and k + 1 < n:
                        buf.append(t[k:k + 2]); k += 2; continue
                    if t[k] == "'":
                        m = k + 1
                        while m < n and t[m] in " \t\r\n":
                            m += 1
                        if m >= n or t[m] in ',}]:':  # real close
                            break
                        buf.append("'"); k += 1; continue  # apostrophe inside value
                    buf.append(t[k]); k += 1
                inner = "".join(buf).replace('"', '\\"')
                out.append('"%s"' % inner)
                i = k + 1
                continue
        out.append(c)
        i += 1
    return "".join(out)


def _escape_inner_quotes(t):
    """Escape stray (unescaped) double-quotes INSIDE string values, e.g.
        "evidence": "they say "powerful" a lot"
    A value's real closing quote is a `"` immediately followed by `\\s*[,}\\]]`
    (or `:` for a key). Any other `"` while we're inside a string is an inner
    quote the small model forgot to escape -- so we escape it. Bounded to the
    flat scalar/object shape the Conversion Read uses; never invoked unless a
    cheaper repair already failed to parse."""
    out = []
    in_str = False
    i, n = 0, len(t)
    while i < n:
        c = t[i]
        if not in_str:
            out.append(c)
            if c == '"':
                in_str = True
            i += 1
            continue
        # inside a string
        if c == "\\":  # keep escape pairs intact
            out.append(t[i:i + 2])
            i += 2
            continue
        if c == '"':
            j = i + 1
            while j < n and t[j] in " \t\r\n":
                j += 1
            if j >= n or t[j] in ',}]:':  # legit closing quote
                out.append('"')
                in_str = False
            else:                          # stray inner quote -> escape it
                out.append('\\"')
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def repair_json(text):
    """Best-effort repair of common small-model JSON slips, then parse.

    Repairs, in order: strip code fences / prose, normalize smart quotes,
    collapse comma-separated quoted fragments inside a value into one string,
    drop trailing commas before } or ], and (only if still unparseable) escape
    stray inner double-quotes. Returns the parsed object or raises
    ValueError/JSONDecodeError if it still can't parse. ANALYZE-path only."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in model output")
    t = t[start : end + 1]
    for bad, good in _SMART_QUOTES.items():
        t = t.replace(bad, good)
    # Collapse fragment runs repeatedly (a terminator consumed by one match can
    # be the lead-in for the next, so iterate until stable).
    for _ in range(8):
        new = _FRAGMENT_RUN.sub(_collapse_fragment_run, t)
        if new == t:
            break
        t = new
    # Drop trailing commas: , followed by optional ws then } or ].
    t = re.sub(r",(\s*[}\]])", r"\1", t)
    try:
        return json.loads(t)
    except (ValueError, json.JSONDecodeError):
        pass
    # The model single-quoted a value (usually because it held double quotes).
    requoted = _requote_single_quoted(t)
    try:
        return json.loads(requoted)
    except (ValueError, json.JSONDecodeError):
        pass
    # Last resort: an unescaped double-quote left inside a value.
    return json.loads(_escape_inner_quotes(requoted))


def extract_read_json(text):
    """Parse a Conversion Read from raw model output. Tries the planner's strict
    extractor first (so well-formed output is byte-for-byte identical to before),
    then falls back to the analyze-local repair_json. ANALYZE-path only; never
    mutates vp.extract_json. Raises if neither succeeds."""
    try:
        return vp.extract_json(text)
    except (ValueError, json.JSONDecodeError):
        return repair_json(text)


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


SYSTEM_PROMPT = (
    "You are the CONVERSION READ analyst for an autonomous video-production studio. "
    "You read a real product page's copy and diagnose how well it converts, then "
    "output a STRICT JSON object ONLY -- no markdown, no code fences, no prose before "
    "or after. The first character of your reply MUST be { and the last MUST be }.\n\n"
    "OUTPUT SCHEMA (these keys and field names are FIXED -- never rename, add, or omit):\n"
    "{\n"
    '  "url": str,\n'
    '  "verdict": str,            // one line: the overall read\n'
    '  "dimensions": [            // EXACTLY these 6, one each:\n'
    '    {"key": "promise|outcome|proof|show|specificity|cta",\n'
    '     "score": int 0-5, "finding": str, "evidence": str, "fix": str}\n'
    "  ],\n"
    '  "priority_fixes": [{"rank": int, "fix": str, "maps_to": str}],\n'
    '  "headline_fix": str        // the outcome-led hero line to OPEN the video with\n'
    "}\n\n"
    "THE 6 DIMENSIONS (score 0 = worst, 5 = best):\n"
    "- promise:     does the first 5s say what it is + who it's for? (0 makes you work, 5 instant)\n"
    "- outcome:     sells the buyer's RESULT vs listing features? (0 feature list, 5 outcome-led)\n"
    "- proof:       credible evidence -- numbers, demo, logos? (0 none, 5 strong specific)\n"
    "- show:        shows the product WORKING vs abstract talk? (0 all tell, 5 real demo)\n"
    "- specificity: concrete vs vague adjectives? (0 'powerful', 5 '10x faster')\n"
    "- cta:         one clear next step? (0 none/many, 5 single obvious CTA)\n\n"
    "RULES:\n"
    "1. Ground EVERY finding and evidence in the page's ACTUAL words (quote them in 'evidence').\n"
    "2. proof and show are the highest-leverage dimensions -- weight priority_fixes toward them.\n"
    "3. priority_fixes lists the top 1-3 fixes, rank 1 first; each 'maps_to' is a short scene hint.\n"
    "4. headline_fix is a single outcome-led sentence (NOT a feature, NOT the bare brand name).\n"
    "5. Do NOT invent a DIFFERENT product than the one in the copy. Describe what the PRODUCT does.\n"
    "6. Self-check before emitting: all 6 dimension keys present once, every score an int 0-5, "
    "JSON parses, first char { and last char }.\n"
    "7. EACH field value is ONE JSON string. Never split a value into multiple comma-"
    "separated quoted pieces. If you must quote several phrases from the page, join them "
    "INSIDE one pair of quotes.\n"
    '   CORRECT:   "evidence": "Financial infrastructure; Millions of companies of all sizes"\n'
    '   MALFORMED (never do this): "evidence": "Financial infrastructure", "and", '
    '"Millions of companies"\n'
    "   No trailing commas, no smart/curly quotes -- use straight \" only.\n"
)

# Hidden-reasoning budget is generous; the Read is small but the model may reason.
ANALYZE_MAX_TOKENS = 4000


def _build_messages(url, body_text, headline=None):
    body = (body_text or "")[:4000]
    user = "Diagnose this product page's conversion. Output JSON only.\n\n" \
           "url: %s\n" % url
    if headline:
        user += "captured_headline: %s\n" % headline
    user += "\nPAGE COPY (verbatim, may be truncated):\n%s\n" % body
    user += ("\nThe copy above is COMPLETE for this task. Do NOT ask for more "
             "information, do NOT apologize, do NOT explain. Respond with ONLY the "
             "JSON Conversion Read object and nothing else.\n")
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user}]


def analyze_read(url, body_text, hero_path=None, headline=None, brain="super-free"):
    """Produce a validated Conversion Read for `url` from its `body_text`.

    Reuses validate_planner.call_model / extract_json (the planner's OpenRouter
    path). On no-key, network/HTTP error, malformed JSON after one repair retry, or
    a Read that fails validate_read, returns minimal_read(url, body_text) marked
    degraded -- so the caller ALWAYS gets a valid Read and the pipeline never blocks.
    `hero_path` is accepted for parity/forward-compat (text-only model today)."""
    brain = brain_mod.normalize_brain(brain)
    if not brain_mod.brain_key():
        return minimal_read(url, body_text)
    messages = _build_messages(url, body_text, headline=headline)
    _restore = getattr(vp, "PLANNER_MAX_TOKENS", ANALYZE_MAX_TOKENS)
    _patch_token_cap()
    try:
        # Budget of 4 attempts: each tries vp.extract_json then the analyze-local
        # repair before any reprompt, so the common small-model slips recover
        # in-attempt instead of degrading to minimal_read.
        for attempt in range(4):
            try:
                raw = vp.call_model(messages, brain=brain)
            except Exception as e:  # network/HTTP — try once more, then minimal
                print("[analyze] call_model error (attempt %d): %s" % (attempt, e), file=sys.stderr)
                continue
            try:
                read = extract_read_json(raw)
            except (ValueError, json.JSONDecodeError):
                # malformed — repair-nudge once, then loop to a fresh attempt / minimal
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": "Your previous output did not parse. "
                     "Return ONLY the corrected JSON Conversion Read object."}]
                continue
            read["url"] = url  # the URL is ground truth, never the model's echo
            read.setdefault("degraded", False)
            if not validate_read(read):
                return read
            print("[analyze] model Read failed validation: %s"
                  % "; ".join(validate_read(read)), file=sys.stderr)
            messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "That JSON did not match the schema. Emit a "
                 "corrected Conversion Read with all 6 dimensions and int scores 0-5."}]
    finally:
        # Restore the shared cap so the planner (which runs after analyze) is not
        # permanently shrunk by this call -- belt-and-suspenders per the plan note.
        vp.PLANNER_MAX_TOKENS = _restore
    return minimal_read(url, body_text)


def _patch_token_cap():
    """Tell the shared call_model to use the smaller analyze budget for this call.
    call_model reads vp.PLANNER_MAX_TOKENS; the Read is small, so cap it lower to
    keep the free tier snappy. Idempotent; safe across calls."""
    vp.PLANNER_MAX_TOKENS = min(getattr(vp, "PLANNER_MAX_TOKENS", ANALYZE_MAX_TOKENS), ANALYZE_MAX_TOKENS)
