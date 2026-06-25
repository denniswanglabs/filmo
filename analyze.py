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
import time
import urllib.error

import brain as brain_mod
import validate_planner as vp

# Frozen contract — consumers (build_runner, the dashboard, the plan seeder) read
# these exact names. Order of dimensions is free; presence of all six is required.
DIMENSION_KEYS = ("promise", "outcome", "proof", "show", "specificity", "cta")
SCORE_MIN, SCORE_MAX = 0, 5

# --- HONEST ENGINE TAGGING ----------------------------------------------------
# The Conversion Read is our ONE real Nous-model usage; a Nous judge scores us, so
# the ledger/dashboard must say truthfully WHICH model produced each Read. We never
# claim Hermes ran when the Nemotron Ultra fallback did. `engine` is an EXTRA key on
# the Read dict — validate_read (the frozen contract) ignores extra keys, so this is
# additive and safe. Map each brain key to the human-facing engine label.
ENGINE_BY_BRAIN = {
    "hermes": "nous-hermes-3-405b",
    "hermes-405b": "nous-hermes-4-405b",
    "ultra-paid": "nemotron-ultra-fallback",
}


def _engine_for(brain):
    """Human-facing engine label for a (normalized) brain key. Unknown -> the slug
    so the tag is never a lie of omission."""
    b = brain_mod.normalize_brain(brain)
    return ENGINE_BY_BRAIN.get(b) or brain_mod.brain_def(b)["slug"]


# Default tiered order for the Conversion Read: Hermes is the honest primary (our
# only Nous-model usage); Nemotron Ultra is the RELIABILITY fallback when the free
# Hermes tier is throttled. minimal_read is the last-resort floor below both.
ANALYZE_BRAIN_CHAIN = ("hermes", "ultra-paid")

# 429 backoff for the free Hermes tier (Venice-hosted, intermittently rate-limited).
# Bounded so a build never hangs: a couple of short sleeps keep total Hermes wait
# well under ~30s before we hand off to the Ultra fallback.
RATELIMIT_BACKOFF_S = 6
RATELIMIT_MAX_RETRIES = 2


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


# --- TOLERANT PARSER (final fallback) -----------------------------------------
# The regex repairs above each target ONE known slip. Real super-free output
# varies: across 20 live stripe captures the regex chain still choked on a
# missing '}' before a ']' (an unclosed last array element) and a stray ':'
# after a value (`{"key": "rank": 2, ...}`). Rather than add another regex per
# shape, this guaranteed-terminating recursive-descent reader treats the whole
# family of "the value's boundaries are wrong" slips uniformly: single-quoted
# values, unescaped inner quotes, multiple quoted fragments where one value
# belongs, a missing closing bracket at EOF, and a stray ':' after a value. It
# builds Python objects directly. It is invoked ONLY after strict json.loads and
# every regex repair have already failed, so well-formed output never reaches it
# (the clean path stays byte-for-byte json.loads). Matched the json-repair lib's
# recovery rate (16/20) on the captures, stdlib-only. ANALYZE-path only.
_TP_DELIMS = ",}]:"     # structural delimiters that legitimately end a value
_TP_CLOSERS = "}]"
_TP_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f",
               "n": "\n", "r": "\r", "t": "\t"}


def _tolerant_parse(text):
    """Permissive JSON reader for the small-model slips above. Returns a Python
    object; never hangs (every loop is guaranteed to consume >=1 char) and never
    collapses a genuine string array (the fragment-join fires only in object-value
    position). Not a general JSON parser -- tuned to the flat Conversion Read shape;
    on exhausted input it returns what it parsed so far (validate_read then rejects
    an incomplete Read and analyze_read reprompts)."""
    s, n = text, len(text)
    pos = [0]

    def ws():
        while pos[0] < n and s[pos[0]] in " \t\r\n":
            pos[0] += 1

    def peek():
        return s[pos[0]] if pos[0] < n else ""

    def parse_value():
        ws()
        c = peek()
        if c == "{":
            return parse_object()
        if c == "[":
            return parse_array()
        if c == '"' or c == "'":
            return parse_string()
        return parse_scalar()

    def decode_escape(j):
        if j + 1 >= n:
            return "\\", j + 1
        e = s[j + 1]
        if e == "u" and j + 6 <= n:
            try:
                return chr(int(s[j + 2:j + 6], 16)), j + 6
            except ValueError:
                return e, j + 2
        return _TP_ESCAPES.get(e, e), j + 2

    def parse_string():
        quote = s[pos[0]]
        j = pos[0] + 1
        buf = []
        while j < n:
            c = s[j]
            if c == "\\":
                dec, j = decode_escape(j)
                buf.append(dec)
                continue
            if c == quote:
                # a real close only if the next non-ws char is a structural
                # delimiter / EOF; otherwise it's an inner quote -> keep literal
                k = j + 1
                while k < n and s[k] in " \t\r\n":
                    k += 1
                if k >= n or s[k] in _TP_DELIMS:
                    j += 1
                    break
                buf.append(c)
                j += 1
                continue
            if c == '"':  # a double quote inside a single-quoted value -> literal
                buf.append(c)
                j += 1
                continue
            buf.append(c)
            j += 1
        pos[0] = j
        return "".join(buf)

    def parse_scalar():
        start = pos[0]
        while pos[0] < n and s[pos[0]] not in _TP_DELIMS:
            pos[0] += 1
        tok = s[start:pos[0]].strip()
        low = tok.lower()
        if low == "true":
            return True
        if low == "false":
            return False
        if low in ("null", "none", ""):
            return None
        try:
            return int(tok)
        except ValueError:
            pass
        try:
            return float(tok)
        except ValueError:
            return tok

    def parse_array():
        pos[0] += 1  # consume [
        arr = []
        while pos[0] < n:
            guard = pos[0]
            ws()
            c = peek()
            if c == "" or c in _TP_CLOSERS:
                if c == "]":
                    pos[0] += 1
                break  # ']' closes; '}' is left for the parent object
            if c == ",":
                pos[0] += 1
                continue
            arr.append(parse_value())
            ws()
            if peek() == ",":
                pos[0] += 1
            if pos[0] == guard:  # progress guarantee -> always terminates
                pos[0] += 1
        return arr

    def parse_object():
        pos[0] += 1  # consume {
        obj = {}
        last_key = None
        while pos[0] < n:
            guard = pos[0]
            ws()
            c = peek()
            if c == "" or c in _TP_CLOSERS:
                if c == "}":
                    pos[0] += 1
                break  # '}' closes; ']' is left for the parent array
            if c == ",":
                pos[0] += 1
                continue
            if c == ":":
                # stray ':' after a value (`"key": "rank": 2`) -> skip to next sep
                pos[0] += 1
                while pos[0] < n and s[pos[0]] not in ",}]":
                    pos[0] += 1
                continue
            key = parse_string() if c in "\"'" else str(parse_scalar())
            ws()
            if peek() == ":":
                pos[0] += 1
                obj[key] = parse_value()
                last_key = key
            elif last_key is not None and isinstance(obj.get(last_key), str):
                # a "key" not followed by ':' is really a stray fragment of the
                # PREVIOUS value (the multi-quote-in-one-value bug) -> space-join
                obj[last_key] = (obj[last_key] + " " + key).strip()
            ws()
            if peek() == ",":
                pos[0] += 1
            if pos[0] == guard:  # progress guarantee -> always terminates
                pos[0] += 1
        return obj

    ws()
    if peek() not in "{[":  # skip any leading prose to the first container
        for k in range(pos[0], n):
            if s[k] in "{[":
                pos[0] = k
                break
    return parse_value()


def repair_json(text):
    """Best-effort repair of common small-model JSON slips, then parse.

    Repairs, in order: strip code fences / prose, normalize smart quotes,
    collapse comma-separated quoted fragments inside a value into one string,
    drop trailing commas before } or ], requote single-quoted values, escape
    stray inner double-quotes, and finally a guaranteed-terminating tolerant
    parser for the residual structural slips. Returns the parsed object or raises
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
    # An unescaped double-quote left inside a value.
    try:
        return json.loads(_escape_inner_quotes(requoted))
    except (ValueError, json.JSONDecodeError):
        pass
    # Final fallback: the tolerant parser handles the residual structural slips
    # the regex chain can't (missing '}' before ']', a stray ':' after a value).
    # Raise if it can't yield a JSON object so analyze_read reprompts.
    obj = _tolerant_parse(t)
    if not isinstance(obj, (dict, list)):
        raise ValueError("tolerant parse did not yield a JSON object")
    return obj


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
        "engine": "minimal",
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


def _is_retryable_upstream(e):
    """True for transient upstream errors worth a short backoff + retry on the SAME
    brain: an HTTP 429 (the free Hermes tier's rate limit) or a 5xx server error.
    These are the errors the prior code degraded on instead of waiting out — the
    429 in particular is transient (retry_after ~25s)."""
    if isinstance(e, urllib.error.HTTPError):
        return e.code == 429 or 500 <= e.code < 600
    # urllib.error.URLError (DNS/connection reset) is also transient.
    return isinstance(e, urllib.error.URLError)


def _analyze_read_one_brain(url, body_text, headline, brain):
    """Run the Conversion Read on ONE brain and return a validated Read dict, or
    None if this brain ultimately failed (network/parse/schema) so the caller can
    fall to the next brain in the chain. On a 429 / transient upstream error this
    RETRIES the same brain after a short bounded backoff (the 429 is transient)
    rather than giving up. Tags read["engine"] with this brain's engine label so the
    ledger/dashboard is honest about WHICH model produced the Read."""
    messages = _build_messages(url, body_text, headline=headline)
    ratelimit_retries = 0
    # Budget of 4 content attempts: each tries vp.extract_json then the analyze-local
    # repair before any reprompt, so the common small-model slips recover in-attempt.
    # 429/transient retries are counted SEPARATELY (and don't consume a content
    # attempt) so a throttled call still gets its full repair budget once it lands.
    attempt = 0
    while attempt < 4:
        try:
            raw = vp.call_model(messages, brain=brain)
        except Exception as e:  # network/HTTP
            if _is_retryable_upstream(e) and ratelimit_retries < RATELIMIT_MAX_RETRIES:
                ratelimit_retries += 1
                print("[analyze] %s transient upstream error (%s); backoff %ds then retry (%d/%d)"
                      % (brain, e, RATELIMIT_BACKOFF_S, ratelimit_retries, RATELIMIT_MAX_RETRIES),
                      file=sys.stderr)
                time.sleep(RATELIMIT_BACKOFF_S)
                continue  # same attempt index — retry without burning a content attempt
            print("[analyze] %s call_model error (attempt %d): %s" % (brain, attempt, e), file=sys.stderr)
            return None  # give up on THIS brain -> caller tries the next in the chain
        attempt += 1
        try:
            read = extract_read_json(raw)
        except (ValueError, json.JSONDecodeError):
            # malformed — repair-nudge once, then loop to a fresh attempt.
            messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "Your previous output did not parse. "
                 "Return ONLY the corrected JSON Conversion Read object."}]
            continue
        read["url"] = url  # the URL is ground truth, never the model's echo
        read.setdefault("degraded", False)
        problems = validate_read(read)
        if not problems:
            read["engine"] = _engine_for(brain)  # honest tag: this brain produced it
            return read
        print("[analyze] %s model Read failed validation: %s"
              % (brain, "; ".join(problems)), file=sys.stderr)
        # The residual degradations are SCHEMA slips (a dropped dimension, a missing
        # field) -- not parse errors. Name the exact problems so the retry fixes
        # THOSE; a targeted nudge converges far faster than a generic "try again".
        messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "That JSON did not match the schema. Fix "
             "exactly these problems and re-emit the FULL corrected Conversion Read "
             "(all 6 dimensions promise/outcome/proof/show/specificity/cta, each "
             "with int score 0-5 and finding/evidence/fix, plus a non-empty "
             "priority_fixes and headline_fix): " + "; ".join(problems)}]
    return None  # exhausted content attempts on this brain -> caller falls onward


def analyze_read(url, body_text, hero_path=None, headline=None, brain="hermes"):
    """Produce a validated Conversion Read for `url` from its `body_text`.

    Reuses validate_planner.call_model / extract_json (the planner's OpenRouter
    path). Hermes is the honest PRIMARY (our one real Nous-model usage); when the
    caller asks for the default `hermes` brain and it ultimately fails — even after
    429 backoff+retries — we DON'T drop straight to the bare minimal_read. We first
    retry the Read once on **Nemotron Ultra** (`ultra-paid`) as a RELIABILITY
    fallback. Only if Ultra ALSO fails do we fall to minimal_read(url, body_text)
    marked degraded -- so the caller ALWAYS gets a valid Read and the pipeline never
    blocks. read["engine"] records which model actually produced the Read so the
    ledger/dashboard is truthful. `hero_path` is accepted for parity/forward-compat
    (text-only model today). The PLANNER path is untouched (it never calls this)."""
    brain = brain_mod.normalize_brain(brain)
    if not brain_mod.brain_key():
        return minimal_read(url, body_text)
    # Build the tiered brain chain. If the caller asked for the default `hermes`
    # primary, append the Nemotron Ultra reliability fallback. If the caller asked
    # for a DIFFERENT brain explicitly, honor exactly that one (no surprise paid
    # fallback) -- keeps existing/test callers' behavior predictable.
    if brain == "hermes":
        chain = list(ANALYZE_BRAIN_CHAIN)
    else:
        chain = [brain]
    _restore = getattr(vp, "PLANNER_MAX_TOKENS", ANALYZE_MAX_TOKENS)
    _patch_token_cap()
    try:
        for b in chain:
            read = _analyze_read_one_brain(url, body_text, headline, b)
            if read is not None:
                return read
            if len(chain) > 1:
                print("[analyze] brain %r failed; falling to next in chain" % b, file=sys.stderr)
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
