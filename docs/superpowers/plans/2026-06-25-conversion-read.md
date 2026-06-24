# Conversion Read — implementation plan

> **For agentic workers:** this plan is built for the `superpowers:subagent-driven-development` workflow. Each task is a self-contained, 2-5 minute TDD loop (failing test → run-and-see-it-fail → minimal implementation → run-and-see-it-pass → commit). Dispatch one fresh-context subagent per task in order; the verifier gate is the test command's expected output. Do not batch, do not skip the "see it fail" step, do not change the contract names.

**Goal:** Add a feature-flagged Conversion Read stage that reads the target page's real copy, scores it on 6 conversion dimensions via Nemotron, shows the diagnosis as a first-class deliverable, and seeds the video plan so the produced video *is* that diagnosis fixed — without changing `main`'s default behavior.

**Architecture:** A new ANALYZE stage runs BEFORE PLAN inside `build_runner.run()`, gated on `PRODUCER_CONVERSION_READ=1`. It does a cheap text+hero `read_pass` (reusing `capture_screenshots`), calls `analyze.analyze_read()` (which reuses `validate_planner.call_model`/`extract_json` exactly as the planner does) to produce a validated Conversion Read JSON, persists it to `runs/<id>/conversion_read.json` + the ledger, and seeds the planner (COMPANY-FACTS + a deterministic backstop that maps `priority_fixes`→scenes and `headline_fix`→opening title). The dashboard renders an Analysis panel before the video. Every failure path degrades to a best-effort/minimal Read and still produces the video.

**Tech Stack:** Python 3 (stdlib only: `urllib`, `json`, `os`, `subprocess`); Nemotron via OpenRouter (`brain.py` registry, `super-free` default, $0); Playwright capture via `.venv-capture` (existing); vanilla JS dashboard (`dashboard/app.js`, `dashboard/serve.py` `http.server`); `unittest` test harness driven by `run_all_tests.sh`.

---

## File Structure

| File | New/Mod | Single responsibility |
|---|---|---|
| `analyze.py` | NEW | Assemble the analyzer prompt, call Nemotron (reusing `vp.call_model`/`vp.extract_json`), retry on malformed JSON, return a validated Conversion Read dict; `validate_read()` + `minimal_read()` live here. |
| `analyzer-prompt.md` | NEW | Frozen Conversion Read JSON contract + numbered rules + self-check, mirroring `planner-prompt.md`. The `analyze.SYSTEM_PROMPT` string is the source of truth; this doc restates it for humans. |
| `read_pass.py` | NEW | Cheap "text+hero only" capture: reuse `capture_screenshots.capture_url` for ONE hero shot + extract `body_text` (<=4000 chars); returns `{url, body_text, hero_screenshot_path, headline, degraded}`. Never raises. |
| `build_runner.py` | MOD | Insert the flag-gated ANALYZE stage (read_pass → analyze → persist → ledger `analyzing` event) BEFORE PLAN; thread the Read into `_brand_facts`/`plan_job`. Default off ⇒ byte-unchanged. |
| `plan_job.py` | MOD | Accept `conversion_read=` kwarg; extend the STANDARD deterministic backstop so top `priority_fixes` appear as beats and `headline_fix` becomes the opening title text. |
| `validate_planner.py` | MOD | Extend `company_facts_block` to append a "CONVERSION READ — PRESCRIPTIONS" block when a Read is supplied (additive; empty when absent). |
| `dashboard/app.js` | MOD | `analysisPanel(l)` renders the 6 scored dimensions + priority fixes + verdict; insert it before `deliveredHero` in `renderDetail`; add the `analyzing` phase to the stage map. |
| `dashboard/serve.py` | MOD | Thread `PRODUCER_CONVERSION_READ` into the build subprocess env when requested (top-level body flag), so the feature is togglable from the composer without editing the shell. |
| `dashboard/index.html` | MOD | Add the `.analysis-panel` CSS so the new panel matches the existing card system. |
| `tests/test_analyze.py` | NEW | Unit tests for `validate_read`, `minimal_read`, `analyze_read` (mock Nemotron), retry-then-minimal fallback. |
| `tests/test_read_pass.py` | NEW | Unit tests for `read_pass` success (injected capture) + degraded fallback (capture raises). |
| `tests/test_plan_seeding.py` | NEW | Mapping tests: low-`proof` Read → plan has a proof beat; `headline_fix` → opening title text. |
| `tests/test_conversion_read_e2e.py` | NEW | `$0` mock end-to-end: flag on, injected Nemotron+capture → run produces `conversion_read.json` + `analyzing` ledger event + delivered video; flag off → no Read, behavior unchanged. |
| `run_all_tests.sh` | MOD | Register the 4 new unittest modules in section 2b. |

**Frozen Conversion Read JSON contract** (consumers read these exact names — never rename/drop):

```json
{
  "url": "str",
  "verdict": "str",
  "dimensions": [
    {"key": "promise|outcome|proof|show|specificity|cta",
     "score": 0, "finding": "str", "evidence": "str", "fix": "str"}
  ],
  "priority_fixes": [{"rank": 1, "fix": "str", "maps_to": "str"}],
  "headline_fix": "str",
  "degraded": false
}
```

`DIMENSION_KEYS = ("promise", "outcome", "proof", "show", "specificity", "cta")` — all six present, in any order; `score` is an int 0-5.

---

## Bite-sized TDD tasks

> Run every test from the repo root: `cd /Users/dennis/Desktop/Projects/Hackathons/walk-studio-conversion-read`. All work is on branch `conversion-read`; commit after each task.

---

### Task 1 — `validate_read()` rejects bad Reads, normalizes good ones

- [ ] **Write failing test** — create `tests/test_analyze.py`:

```python
#!/usr/bin/env python3
"""$0, offline unit tests for analyze.py (no network, no Nemotron call)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analyze


def _good_read():
    dims = [{"key": k, "score": 3, "finding": "f", "evidence": "e", "fix": "x"}
            for k in analyze.DIMENSION_KEYS]
    return {
        "url": "https://acme.com",
        "verdict": "feature-led hero, thin proof",
        "dimensions": dims,
        "priority_fixes": [{"rank": 1, "fix": "add a proof beat", "maps_to": "proof"}],
        "headline_fix": "Ship 10x faster",
    }


class ValidateRead(unittest.TestCase):
    def test_good_read_has_no_problems(self):
        self.assertEqual(analyze.validate_read(_good_read()), [])

    def test_missing_dimension_is_flagged(self):
        r = _good_read()
        r["dimensions"] = r["dimensions"][:5]  # drop cta
        problems = analyze.validate_read(r)
        self.assertTrue(any("cta" in p for p in problems), problems)

    def test_score_out_of_range_is_flagged(self):
        r = _good_read()
        r["dimensions"][0]["score"] = 9
        self.assertTrue(analyze.validate_read(r))

    def test_missing_headline_fix_is_flagged(self):
        r = _good_read()
        del r["headline_fix"]
        self.assertTrue(analyze.validate_read(r))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Run it, expect FAIL** — `python3 -m unittest tests.test_analyze -v`
  Expected: `ModuleNotFoundError: No module named 'analyze'` (collection error, all tests error).

- [ ] **Minimal implementation** — create `analyze.py`:

```python
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
```

- [ ] **Run it, expect PASS** — `python3 -m unittest tests.test_analyze -v`
  Expected: `Ran 4 tests` ... `OK`.

- [ ] **Commit** — `git add analyze.py tests/test_analyze.py && git commit -m "analyze: validate_read for the frozen Conversion Read contract"`

---

### Task 2 — `minimal_read()` deterministic fallback (never crashes the pipeline)

- [ ] **Write failing test** — append to `tests/test_analyze.py` (new class):

```python
class MinimalRead(unittest.TestCase):
    def test_minimal_read_is_valid(self):
        r = analyze.minimal_read("https://acme.com", body_text="Acme builds widgets.")
        self.assertEqual(analyze.validate_read(r), [])

    def test_minimal_read_is_marked_degraded(self):
        r = analyze.minimal_read("https://acme.com", body_text="")
        self.assertTrue(r["degraded"])

    def test_minimal_read_carries_url(self):
        r = analyze.minimal_read("https://acme.com", body_text="x")
        self.assertEqual(r["url"], "https://acme.com")
```

- [ ] **Run it, expect FAIL** — `python3 -m unittest tests.test_analyze.MinimalRead -v`
  Expected: `AttributeError: module 'analyze' has no attribute 'minimal_read'`.

- [ ] **Minimal implementation** — append to `analyze.py`:

```python
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
```

- [ ] **Run it, expect PASS** — `python3 -m unittest tests.test_analyze.MinimalRead -v`
  Expected: `Ran 3 tests` ... `OK`.

- [ ] **Commit** — `git add analyze.py tests/test_analyze.py && git commit -m "analyze: minimal_read deterministic fallback (always valid, never raises)"`

---

### Task 3 — `analyze_read()` calls Nemotron, retries malformed JSON, falls back to minimal

- [ ] **Write failing test** — append to `tests/test_analyze.py`:

```python
class AnalyzeRead(unittest.TestCase):
    def setUp(self):
        self._orig_call = analyze.vp.call_model
        self._orig_key = analyze.brain_mod.brain_key

    def tearDown(self):
        analyze.vp.call_model = self._orig_call
        analyze.brain_mod.brain_key = self._orig_key

    def _good_json(self):
        dims = [{"key": k, "score": 2, "finding": "f", "evidence": "e", "fix": "x"}
                for k in analyze.DIMENSION_KEYS]
        return analyze.json.dumps({
            "url": "https://acme.com", "verdict": "v", "dimensions": dims,
            "priority_fixes": [{"rank": 1, "fix": "add proof", "maps_to": "proof"}],
            "headline_fix": "Ship 10x faster"})

    def test_valid_model_output_is_returned(self):
        analyze.brain_mod.brain_key = lambda: "k"
        analyze.vp.call_model = lambda messages, brain=None, meta=None: self._good_json()
        r = analyze.analyze_read("https://acme.com", "Acme copy", hero_path=None)
        self.assertEqual(analyze.validate_read(r), [])
        self.assertFalse(r.get("degraded"))

    def test_malformed_then_minimal(self):
        analyze.brain_mod.brain_key = lambda: "k"
        analyze.vp.call_model = lambda messages, brain=None, meta=None: "I cannot help with that."
        r = analyze.analyze_read("https://acme.com", "Acme copy", hero_path=None)
        self.assertEqual(analyze.validate_read(r), [])  # still valid (minimal)
        self.assertTrue(r["degraded"])

    def test_no_key_returns_minimal(self):
        analyze.brain_mod.brain_key = lambda: None
        called = []
        analyze.vp.call_model = lambda *a, **k: called.append(1) or "{}"
        r = analyze.analyze_read("https://acme.com", "Acme copy", hero_path=None)
        self.assertTrue(r["degraded"])
        self.assertEqual(called, [])  # never hit the network without a key

    def test_url_is_forced_onto_read(self):
        analyze.brain_mod.brain_key = lambda: "k"
        analyze.vp.call_model = lambda messages, brain=None, meta=None: self._good_json()
        r = analyze.analyze_read("https://other.com", "copy", hero_path=None)
        self.assertEqual(r["url"], "https://other.com")  # model's url is overwritten
```

- [ ] **Run it, expect FAIL** — `python3 -m unittest tests.test_analyze.AnalyzeRead -v`
  Expected: `AttributeError: module 'analyze' has no attribute 'analyze_read'`.

- [ ] **Minimal implementation** — append to `analyze.py` (the prompt + call + retry):

```python
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
    _patch_token_cap()
    for attempt in range(2):
        try:
            raw = vp.call_model(messages, brain=brain)
        except Exception as e:  # network/HTTP — try once more, then minimal
            print("[analyze] call_model error (attempt %d): %s" % (attempt, e), file=sys.stderr)
            continue
        try:
            read = vp.extract_json(raw)
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
    return minimal_read(url, body_text)


def _patch_token_cap():
    """Tell the shared call_model to use the smaller analyze budget for this call.
    call_model reads vp.PLANNER_MAX_TOKENS; the Read is small, so cap it lower to
    keep the free tier snappy. Idempotent; safe across calls."""
    vp.PLANNER_MAX_TOKENS = min(getattr(vp, "PLANNER_MAX_TOKENS", ANALYZE_MAX_TOKENS), ANALYZE_MAX_TOKENS)
```

> Note for the implementer: `_patch_token_cap` mutates the shared `vp.PLANNER_MAX_TOKENS` down. Because the planner is the LAST thing to run after analyze, and analyze runs once per build BEFORE plan, this only ever shrinks the cap; if you want belt-and-suspenders, capture/restore it around the call. For v1 the smaller cap is harmless to the planner (16000→4000 is still ample for a scene plan once reasoning is off), but if `tests.test_analyze` and the planner are ever run in the same process, restore it in a `finally`. The e2e test (Task 11) injects `call_model` so it never observes this.

- [ ] **Run it, expect PASS** — `python3 -m unittest tests.test_analyze.AnalyzeRead -v`
  Expected: `Ran 4 tests` ... `OK`.

- [ ] **Commit** — `git add analyze.py tests/test_analyze.py && git commit -m "analyze: analyze_read with retry + minimal fallback (reuses vp.call_model)"`

---

### Task 4 — `analyzer-prompt.md` (frozen contract doc, mirrors planner-prompt.md)

- [ ] **Write failing test** — append to `tests/test_analyze.py`:

```python
class AnalyzerPromptDoc(unittest.TestCase):
    def test_doc_exists_and_lists_all_dimensions(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(here, "analyzer-prompt.md")
        self.assertTrue(os.path.exists(path), "analyzer-prompt.md missing")
        with open(path) as f:
            doc = f.read()
        for k in analyze.DIMENSION_KEYS:
            self.assertIn(k, doc, "dimension %r not documented" % k)
        for field in ("headline_fix", "priority_fixes", "verdict"):
            self.assertIn(field, doc)
```

- [ ] **Run it, expect FAIL** — `python3 -m unittest tests.test_analyze.AnalyzerPromptDoc -v`
  Expected: `AssertionError: analyzer-prompt.md missing`.

- [ ] **Minimal implementation** — create `analyzer-prompt.md`:

```markdown
# Hermes Conversion-Read Prompt

This file documents the exact prompt the ANALYZE step (`analyze.py`) sends to Nemotron.
It turns a page's real copy into a **strict Conversion Read JSON** that is (a) shown to
the user as a first-class diagnosis and (b) seeds the video plan. The string source of
truth is `analyze.SYSTEM_PROMPT`; this doc restates it for humans and freezes the contract.

## Output contract (FIXED — consumers read these exact names)

```json
{
  "url": "str",
  "verdict": "str",
  "dimensions": [
    {"key": "promise|outcome|proof|show|specificity|cta",
     "score": 0, "finding": "str", "evidence": "str", "fix": "str"}
  ],
  "priority_fixes": [{"rank": 1, "fix": "str", "maps_to": "str"}],
  "headline_fix": "str"
}
```

## The 6 dimensions (score 0 worst — 5 best)

| key | question | 0 | 5 |
|---|---|---|---|
| `promise` | first 5s say what it is + who it's for? | makes you work | instantly clear |
| `outcome` | sells the buyer's result vs features? | feature list | outcome-led |
| `proof` | credible evidence (numbers/demo/logos)? | none | strong, specific |
| `show` | shows the product working vs abstract talk? | all tell | real demo |
| `specificity` | concrete vs vague? | "powerful" | "10x faster" |
| `cta` | one clear next step? | none/many | single obvious |

`proof` and `show` are the highest-leverage dimensions (Ploy: "zero social proof is the
biggest lever"); `priority_fixes` weights toward them.

## Rules (numbered, as sent)

1. Ground every finding/evidence in the page's actual words (quote them).
2. proof + show are highest-leverage; weight `priority_fixes` toward them.
3. `priority_fixes` = top 1-3 fixes, rank 1 first; `maps_to` is a short scene hint.
4. `headline_fix` = one outcome-led sentence (never a feature, never the bare brand name).
5. Never invent a different product than the one in the copy.
6. Self-check before emitting: 6 keys present once, int scores 0-5, JSON parses, `{`…`}`.

## Failure handling

`analyze.analyze_read` does up to 2 attempts with a JSON-repair nudge; on no-key,
network error, unparseable output, or a Read that fails `validate_read`, it returns
`analyze.minimal_read(url, body_text)` (deterministic, valid, `degraded=true`). The
pipeline is NEVER blocked by the analyzer.
```

- [ ] **Run it, expect PASS** — `python3 -m unittest tests.test_analyze.AnalyzerPromptDoc -v`
  Expected: `Ran 1 test` ... `OK`.

- [ ] **Commit** — `git add analyzer-prompt.md tests/test_analyze.py && git commit -m "analyzer-prompt.md: frozen Conversion Read contract doc"`

---

### Task 5 — `read_pass()` cheap text+hero capture (success path)

- [ ] **Write failing test** — create `tests/test_read_pass.py`:

```python
#!/usr/bin/env python3
"""$0, offline unit tests for read_pass.py (capture is injected; no Playwright)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import read_pass


class ReadPassSuccess(unittest.TestCase):
    def test_returns_body_text_and_hero(self):
        def fake_capture(url, out_dir, max_shots=1):
            return {"ok": True, "url": url,
                    "shots": [{"file": "shot-00.png",
                               "path": os.path.join(out_dir, "shot-00.png"),
                               "title": "Acme — ship faster",
                               "body_text": "Acme helps teams ship faster. Powerful."}]}
        r = read_pass.read_pass("https://acme.com", "/tmp/acme-run",
                                capture_fn=fake_capture)
        self.assertEqual(r["url"], "https://acme.com")
        self.assertTrue(r["body_text"].startswith("Acme helps"))
        self.assertTrue(r["hero_screenshot_path"].endswith("shot-00.png"))
        self.assertEqual(r["headline"], "Acme — ship faster")
        self.assertFalse(r["degraded"])

    def test_body_text_is_capped_at_4000_chars(self):
        big = "x" * 9000
        def fake_capture(url, out_dir, max_shots=1):
            return {"ok": True, "url": url,
                    "shots": [{"file": "shot-00.png", "path": "/tmp/s.png",
                               "title": "t", "body_text": big}]}
        r = read_pass.read_pass("https://acme.com", "/tmp/x", capture_fn=fake_capture)
        self.assertLessEqual(len(r["body_text"]), 4000)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Run it, expect FAIL** — `python3 -m unittest tests.test_read_pass -v`
  Expected: `ModuleNotFoundError: No module named 'read_pass'`.

- [ ] **Minimal implementation** — create `read_pass.py`:

```python
#!/usr/bin/env python3
"""Cheap 'text + hero only' read pass over the real page, for the Conversion Read.

REUSES capture_screenshots.capture_url (max_shots=1) for ONE hero screenshot, and
pulls the page's visible copy from the shot's body_text. This deliberately does NOT
fire the full walkthrough / smart-nav / multi-shot flow -- that stays at produce
time. Best-effort: any failure returns a degraded result so the pipeline proceeds.

Returns: {"url", "body_text" (<=4000 chars), "hero_screenshot_path" or None,
          "headline" or "", "degraded" bool}.
"""
import os
import sys

BODY_TEXT_CAP = 4000


def _default_capture(url, out_dir, max_shots=1):
    import capture_screenshots
    return capture_screenshots.capture_url(url, out_dir, max_shots=max_shots)


def read_pass(url, run_dir, capture_fn=None):
    """Run the cheap read pass. `capture_fn(url, out_dir, max_shots)` is injectable
    for tests; defaults to capture_screenshots.capture_url. Never raises."""
    capture_fn = capture_fn or _default_capture
    shots_dir = os.path.join(run_dir, "screenshots")
    result = {"url": url, "body_text": "", "hero_screenshot_path": None,
              "headline": "", "degraded": False}
    try:
        manifest = capture_fn(url, shots_dir, max_shots=1)
    except Exception as e:
        print("[read_pass] capture failed: %s" % e, file=sys.stderr)
        result["degraded"] = True
        return result
    shots = (manifest or {}).get("shots") or []
    if not shots:
        result["degraded"] = True
        return result
    hero = shots[0]
    result["hero_screenshot_path"] = hero.get("path")
    result["headline"] = (hero.get("title") or "").strip()
    result["body_text"] = (hero.get("body_text") or "")[:BODY_TEXT_CAP]
    if not result["body_text"]:
        # we got a shot but no readable copy -- degraded (the Read will lean on
        # world-knowledge / minimal), but we still have a hero for the panel.
        result["degraded"] = True
    return result
```

> Note for the implementer: the existing capture manifest (`capture_screenshots.py:1820`) does NOT include `body_text` per shot today. Task 6 adds it to the capture manifest so `read_pass` can read it. Until Task 6 lands, `read_pass` returns `body_text=""` + `degraded=True` from a real capture (still valid — `analyze_read` then leans on the URL/world-knowledge or minimal). The injected test above proves the parsing contract independent of that.

- [ ] **Run it, expect PASS** — `python3 -m unittest tests.test_read_pass -v`
  Expected: `Ran 2 tests` ... `OK`.

- [ ] **Commit** — `git add read_pass.py tests/test_read_pass.py && git commit -m "read_pass: cheap text+hero capture (injectable, never raises)"`

---

### Task 6 — capture manifest carries per-shot `body_text` (so read_pass gets real copy)

- [ ] **Write failing test** — append to `tests/test_read_pass.py`:

```python
class CaptureExposesBodyText(unittest.TestCase):
    def test_screenshot_record_helper_includes_body_text(self):
        # The capture module exposes a pure helper that maps a (title, body) pair
        # onto the shot record's body_text field, capped. We test the helper, not
        # Playwright, so this stays $0/offline.
        import capture_screenshots as cs
        rec = {"index": 0, "file": "shot-00.png"}
        cs._attach_read_text(rec, title="Acme", body_text="y" * 5000)
        self.assertIn("body_text", rec)
        self.assertLessEqual(len(rec["body_text"]), 4000)
        self.assertEqual(rec["body_text"], "y" * 4000)
```

- [ ] **Run it, expect FAIL** — `python3 -m unittest tests.test_read_pass.CaptureExposesBodyText -v`
  Expected: `AttributeError: module 'capture_screenshots' has no attribute '_attach_read_text'`.

- [ ] **Minimal implementation** — in `capture_screenshots.py`, add a pure helper near the top-level helpers (e.g. just above `def capture_url`, ~line 1828), and call it inside `_screenshot_pg` so the FIRST (hero) shot carries body text. Add the helper:

```python
def _attach_read_text(rec, title="", body_text=""):
    """Attach the read-pass fields (title already on rec; body_text capped at 4000)
    to a shot record. Pure + idempotent; used by the hero shot so read_pass.read_pass
    can pull the page copy from the manifest without a second navigation."""
    if title and not rec.get("title"):
        rec["title"] = title
    rec["body_text"] = (body_text or "")[:4000]
    return rec
```

Then inside `_screenshot_pg` (after the `rec = {...}` dict is built, ~line 1495, before the `focus = _compute_focus(pg)` line), capture the body text once for the hero and attach it:

```python
            # READ-PASS copy: pull the visible body text ONCE for the hero shot so
            # the Conversion Read's read_pass can diagnose the real page copy without
            # a second navigation. Best-effort; an unreadable body just leaves "".
            try:
                _btext = (pg.inner_text("body") or "")
            except Exception:
                _btext = ""
            _attach_read_text(rec, title=title, body_text=_btext)
```

- [ ] **Run it, expect PASS** — `python3 -m unittest tests.test_read_pass.CaptureExposesBodyText -v`
  Expected: `Ran 1 test` ... `OK`.

- [ ] **Regression check** — `python3 -m unittest tests.test_capture_variety -v`
  Expected: `OK` (manifest is additive — body_text is a new key, no existing key changed).

- [ ] **Commit** — `git add capture_screenshots.py tests/test_read_pass.py && git commit -m "capture: hero shot carries body_text for the read pass (additive)"`

---

### Task 7 — `company_facts_block` appends the Read's prescriptions

- [ ] **Write failing test** — create `tests/test_plan_seeding.py`:

```python
#!/usr/bin/env python3
"""$0, offline tests for Read->plan seeding (facts block + STANDARD backstop)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import validate_planner as vp


def _read():
    return {
        "url": "https://acme.com", "verdict": "feature-led, no proof",
        "dimensions": [
            {"key": "promise", "score": 3, "finding": "", "evidence": "", "fix": ""},
            {"key": "outcome", "score": 2, "finding": "", "evidence": "", "fix": "lead with outcome"},
            {"key": "proof", "score": 1, "finding": "no numbers", "evidence": "", "fix": "add a proof beat"},
            {"key": "show", "score": 2, "finding": "", "evidence": "", "fix": ""},
            {"key": "specificity", "score": 2, "finding": "", "evidence": "", "fix": ""},
            {"key": "cta", "score": 2, "finding": "", "evidence": "", "fix": "single CTA"},
        ],
        "priority_fixes": [
            {"rank": 1, "fix": "Add a proof beat with a real number", "maps_to": "proof"},
            {"rank": 2, "fix": "One clear closing CTA", "maps_to": "cta"},
        ],
        "headline_fix": "Ship 10x faster with Acme.",
    }


class FactsBlockWithRead(unittest.TestCase):
    def test_read_block_appends_prescriptions(self):
        facts = {"wordmark": "Acme", "tagline": "", "features": ["a", "b", "c"]}
        block = vp.company_facts_block(facts, company_url="https://acme.com",
                                       conversion_read=_read())
        self.assertIn("CONVERSION READ", block)
        self.assertIn("Add a proof beat with a real number", block)
        self.assertIn("Ship 10x faster with Acme.", block)

    def test_absent_read_is_byte_identical_to_before(self):
        facts = {"wordmark": "Acme", "tagline": "", "features": ["a", "b", "c"]}
        with_none = vp.company_facts_block(facts, company_url="https://acme.com",
                                           conversion_read=None)
        without = vp.company_facts_block(facts, company_url="https://acme.com")
        self.assertEqual(with_none, without)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Run it, expect FAIL** — `python3 -m unittest tests.test_plan_seeding.FactsBlockWithRead -v`
  Expected: `TypeError: company_facts_block() got an unexpected keyword argument 'conversion_read'`.

- [ ] **Minimal implementation** — in `validate_planner.py`, change the `company_facts_block` signature (line 257) to accept the Read, and append a prescriptions block just before the final `return "\n".join(lines) + "\n"` (line 365):

```python
def company_facts_block(facts, company_url=None, genre=None, conversion_read=None):
```

Then, immediately before the final `return` of that function, insert:

```python
    # CONVERSION READ prescriptions (additive; only when a Read is supplied). These
    # are the diagnosed fixes the produced video must EMBODY: the headline_fix opens
    # the video, and each priority_fix becomes a directed beat. None/absent => no
    # block, so the prompt is byte-identical to before (behavior unchanged when the
    # PRODUCER_CONVERSION_READ flag is off).
    if isinstance(conversion_read, dict):
        cr_lines = ["", "CONVERSION READ — PRESCRIPTIONS (diagnosed fixes the video MUST embody):"]
        hf = (conversion_read.get("headline_fix") or "").strip()
        if hf:
            cr_lines.append("- OPEN the video with this outcome-led hero line (the opening "
                            "title's voiceover beat): \"%s\"" % hf)
        pfs = [f for f in (conversion_read.get("priority_fixes") or []) if isinstance(f, dict)]
        if pfs:
            cr_lines.append("- The video MUST address each of these prioritized fixes, in a beat:")
            for f in pfs:
                fix = (f.get("fix") or "").strip()
                mt = (f.get("maps_to") or "").strip()
                if fix:
                    cr_lines.append("    * %s%s" % (fix, (" [%s]" % mt if mt else "")))
        cr_lines.append("Treat these prescriptions as REQUIRED -- the produced video is the "
                        "diagnosis, fixed. Do not contradict them.")
        lines += cr_lines
```

> Place this block AFTER the existing `lines.append(... "Do NOT invent a DIFFERENT product ...")` and BEFORE `return "\n".join(lines) + "\n"`. If `facts`/`company_url` were empty so the function returned `""` early (line 293), a Read alone does not re-trigger the block — acceptable for v1: the Read still seeds via the backstop (Task 8) and `build_runner` always passes resolved facts. (Risk noted in the closing summary.)

- [ ] **Run it, expect PASS** — `python3 -m unittest tests.test_plan_seeding.FactsBlockWithRead -v`
  Expected: `Ran 2 tests` ... `OK`.

- [ ] **Commit** — `git add validate_planner.py tests/test_plan_seeding.py && git commit -m "validate_planner: company_facts_block appends Conversion Read prescriptions (additive)"`

---

### Task 8 — STANDARD backstop maps top fixes→beats + headline_fix→opening title

- [ ] **Write failing test** — append to `tests/test_plan_seeding.py`:

```python
import plan_job


def _std_plan():
    return {
        "job": {"company_url": "https://acme.com", "goal": "promo",
                "target_duration_s": 30, "_wordmark": "Acme"},
        "scenes": [
            {"id": "00_open", "type": "title", "brief": "", "model": None, "duration_s": 4, "input_image": None},
            {"id": "shot", "type": "screenshot", "brief": "", "model": None, "duration_s": 8, "input_image": None},
            {"id": "walk", "type": "walkthrough", "brief": "", "model": None, "duration_s": 10, "input_image": None},
            {"id": "99_close", "type": "title", "brief": "", "model": None, "duration_s": 4, "input_image": None},
        ],
        "voiceover": {"voice": "adam", "beats": [
            {"scene_id": "00_open", "text": "Acme."},
            {"scene_id": "shot", "text": "A screenshot."},
            {"scene_id": "walk", "text": "A walkthrough."},
            {"scene_id": "99_close", "text": "Try Acme."},
        ]},
    }


class StandardBackstopSeeding(unittest.TestCase):
    def test_headline_fix_becomes_opening_title_beat(self):
        plan = plan_job.seed_plan_with_read(_std_plan(), _read())
        beats = {b["scene_id"]: b["text"] for b in plan["voiceover"]["beats"]}
        self.assertEqual(beats["00_open"], "Ship 10x faster with Acme.")

    def test_top_proof_fix_lands_as_a_beat_brief(self):
        plan = plan_job.seed_plan_with_read(_std_plan(), _read())
        # the rank-1 fix text must appear somewhere in a scene brief OR a vo beat
        briefs = " ".join(s.get("brief", "") for s in plan["scenes"])
        beats = " ".join(b["text"] for b in plan["voiceover"]["beats"])
        self.assertIn("proof beat", (briefs + " " + beats).lower())

    def test_no_read_is_a_noop(self):
        before = _std_plan()
        after = plan_job.seed_plan_with_read(_std_plan(), None)
        self.assertEqual(after["voiceover"]["beats"][0]["text"], before["voiceover"]["beats"][0]["text"])
```

- [ ] **Run it, expect FAIL** — `python3 -m unittest tests.test_plan_seeding.StandardBackstopSeeding -v`
  Expected: `AttributeError: module 'plan_job' has no attribute 'seed_plan_with_read'`.

- [ ] **Minimal implementation** — in `plan_job.py`, add `seed_plan_with_read` (place it near `_enforce_standard_structure`, ~line 343):

```python
def seed_plan_with_read(plan, conversion_read):
    """Deterministic backstop that GUARANTEES the Conversion Read's top prescriptions
    appear in the plan, even when the LLM silently dropped them:
      - headline_fix -> the OPENING title scene's voiceover beat text (the outcome-led
        hero line the Read prescribes).
      - the top priority_fixes -> directed into the content scenes' briefs (and a
        marker in the matching beat) so each diagnosed fix maps to a beat the producer
        will shoot. Mapping is by `maps_to`: a 'proof'/'show' fix targets the
        screenshot/walkthrough beats (the real-capture pillars that BEAT AI-film
        rivals); a 'cta' fix targets the CLOSING title.

    Mutates + returns `plan`. No-op when conversion_read is falsy. Never raises."""
    if not isinstance(conversion_read, dict):
        return plan
    scenes = [s for s in (plan.get("scenes") or []) if isinstance(s, dict)]
    vo = plan.get("voiceover") or {}
    beats = vo.get("beats")
    if not isinstance(beats, list):
        beats = []
        vo["beats"] = beats
        plan["voiceover"] = vo
    beat_by_id = {b.get("scene_id"): b for b in beats if isinstance(b, dict)}

    titles = [s for s in scenes if s.get("type") == "title"]
    opening = titles[0] if titles else (scenes[0] if scenes else None)
    closing = titles[-1] if len(titles) >= 2 else None
    content = [s for s in scenes if s.get("type") in ("screenshot", "walkthrough")]

    # 1) headline_fix -> opening title beat text (the diagnosis's outcome-led open).
    hf = (conversion_read.get("headline_fix") or "").strip()
    if hf and opening is not None:
        sid = opening.get("id")
        b = beat_by_id.get(sid)
        if b is None:
            b = {"scene_id": sid, "text": hf}
            beats.insert(0, b)
            beat_by_id[sid] = b
        else:
            b["text"] = hf

    # 2) priority_fixes -> directed beats. Append the fix to the target scene's brief
    # and mark its beat so the prescription is shot. Targeting by maps_to keyword.
    def _target_for(maps_to):
        mt = (maps_to or "").lower()
        if "cta" in mt and closing is not None:
            return closing
        if ("proof" in mt or "show" in mt) and content:
            # prefer the walkthrough (the strongest 'show' surface), else a screenshot
            walk = [s for s in content if s.get("type") == "walkthrough"]
            return (walk or content)[0]
        return content[0] if content else (opening if opening is not None else None)

    for f in (conversion_read.get("priority_fixes") or []):
        if not isinstance(f, dict):
            continue
        fix = (f.get("fix") or "").strip()
        if not fix:
            continue
        tgt = _target_for(f.get("maps_to"))
        if tgt is None:
            continue
        prior = (tgt.get("brief") or "").strip()
        tgt["brief"] = (prior + " " if prior else "") + ("CONVERSION FIX: %s" % fix)
        sid = tgt.get("id")
        tb = beat_by_id.get(sid)
        if tb is not None and "CONVERSION FIX" not in (tb.get("text") or "") \
                and tgt is not opening:
            # surface the prescription in the spoken beat too (skip the opening,
            # which is already the headline_fix line).
            tb["text"] = (tb.get("text") or "").strip()
            if tb["text"] and not tb["text"].endswith("."):
                tb["text"] += "."
            tb["text"] = (tb["text"] + " " if tb["text"] else "") + fix
    return plan
```

- [ ] **Run it, expect PASS** — `python3 -m unittest tests.test_plan_seeding.StandardBackstopSeeding -v`
  Expected: `Ran 3 tests` ... `OK`.

- [ ] **Commit** — `git add plan_job.py tests/test_plan_seeding.py && git commit -m "plan_job: seed_plan_with_read maps top fixes->beats + headline_fix->open title"`

---

### Task 9 — `plan_job.plan_job` threads the Read through (facts block + backstop)

- [ ] **Write failing test** — append to `tests/test_plan_seeding.py`:

```python
class PlanJobThreadsRead(unittest.TestCase):
    def setUp(self):
        self._orig = plan_job.brain_mod.brain_key
        plan_job.brain_mod.brain_key = lambda: None  # force the template path ($0)

    def tearDown(self):
        plan_job.brain_mod.brain_key = self._orig

    def test_read_headline_lands_on_template_plan_open(self):
        plan = plan_job.plan_job(
            "https://acme.com", "promo", 30, style="standard", quality="standard",
            company_facts={"wordmark": "Acme", "tagline": "", "features": ["a", "b", "c"]},
            conversion_read=_read())
        beats = {b["scene_id"]: b["text"] for b in plan["voiceover"]["beats"]}
        opener = plan["scenes"][0]["id"]
        self.assertEqual(beats[opener], "Ship 10x faster with Acme.")
```

- [ ] **Run it, expect FAIL** — `python3 -m unittest tests.test_plan_seeding.PlanJobThreadsRead -v`
  Expected: `TypeError: plan_job() got an unexpected keyword argument 'conversion_read'`.

- [ ] **Minimal implementation** — in `plan_job.py`:

  (a) Add `conversion_read=None` to the `plan_job` signature (line 131-133):
  ```python
  def plan_job(company_url, goal, target_duration_s=30, target_margin=0.6,
               currency="usd", style="standard", quality="standard",
               brain="super-free", company_facts=None, emphasis=None,
               conversion_read=None):
  ```

  (b) Pass it into the Nemotron planner so the facts block carries the prescriptions. Change the `_plan_with_nemotron(...)` call (line 159-160) to thread it, and add `conversion_read=None` to `_plan_with_nemotron`'s signature (line 501-503) + pass it to `vp.company_facts_block` (line 541-542):
  ```python
  # call site (line ~159):
  plan = _plan_with_nemotron(company_url, goal, target_duration_s, style, quality,
                             brain, company_facts, meta=planner_meta,
                             conversion_read=conversion_read)
  # signature (line ~501):
  def _plan_with_nemotron(company_url, goal, target_duration_s, style="standard",
                          quality="standard", brain="super-free", company_facts=None,
                          meta=None, conversion_read=None):
  # facts block (line ~541):
  facts_block = vp.company_facts_block(company_facts or {}, company_url=company_url,
                                       genre=genre, conversion_read=conversion_read)
  ```

  (c) Apply the deterministic backstop AFTER the existing grounding backstops and BEFORE the `_wordmark` pop + `validate_plan` (insert just before line 234 `(plan.get("job") or {}).pop("_wordmark", None)`):
  ```python
      # CONVERSION READ seeding backstop: guarantee the diagnosed top fixes appear as
      # beats and the headline_fix opens the video, even if the LLM/template dropped
      # them. No-op when conversion_read is None (flag off) -> behavior unchanged.
      plan = seed_plan_with_read(plan, conversion_read)
  ```

- [ ] **Run it, expect PASS** — `python3 -m unittest tests.test_plan_seeding.PlanJobThreadsRead -v`
  Expected: `Ran 1 test` ... `OK`.

- [ ] **Regression check** — `python3 -m unittest tests.test_plan_seeding -v`
  Expected: all tests in the module `OK` (none of the existing facts-block defaults changed).

- [ ] **Commit** — `git add plan_job.py tests/test_plan_seeding.py && git commit -m "plan_job: thread conversion_read into facts block + seeding backstop"`

---

### Task 10 — wire the ANALYZE stage into `build_runner.run` (flag-gated, persisted, ledger event)

- [ ] **Write failing test** — create `tests/test_conversion_read_e2e.py`:

```python
#!/usr/bin/env python3
"""$0 mock end-to-end-ish tests for the ANALYZE stage in build_runner.

Capture + Nemotron + payment gate are all INJECTED/simulated, so no network, no
Higgsfield, no real Stripe settlement, no Playwright. Proves: with the flag ON a
run writes conversion_read.json + an 'analyzing' ledger event; with the flag OFF
the run does NOT analyze (current behavior unchanged)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build_runner


class AnalyzeStage(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev_runs = build_runner.RUNS
        build_runner.RUNS = self._tmp.name
        os.environ.pop("PRODUCER_CONVERSION_READ", None)

    def tearDown(self):
        build_runner.RUNS = self._prev_runs
        os.environ.pop("PRODUCER_CONVERSION_READ", None)
        self._tmp.cleanup()

    def _fake_read(self):
        import analyze
        dims = [{"key": k, "score": 2, "finding": "f", "evidence": "e", "fix": "x"}
                for k in analyze.DIMENSION_KEYS]
        return {"url": "https://acme.com", "verdict": "v", "dimensions": dims,
                "priority_fixes": [{"rank": 1, "fix": "add proof", "maps_to": "proof"}],
                "headline_fix": "Ship 10x faster.", "degraded": False}

    def test_flag_on_runs_analyze_and_persists(self):
        os.environ["PRODUCER_CONVERSION_READ"] = "1"
        run_dir = os.path.join(build_runner.RUNS, "build-acme-test")
        os.makedirs(run_dir, exist_ok=True)
        cr = build_runner._maybe_conversion_read(
            "https://acme.com", run_dir, brain="super-free",
            read_pass_fn=lambda url, rd: {"url": url, "body_text": "Acme copy",
                                          "hero_screenshot_path": None, "headline": "Acme",
                                          "degraded": False},
            analyze_fn=lambda url, body, hero_path=None, headline=None, brain="super-free": self._fake_read())
        self.assertIsNotNone(cr)
        self.assertEqual(cr["headline_fix"], "Ship 10x faster.")
        self.assertTrue(os.path.exists(os.path.join(run_dir, "conversion_read.json")))
        with open(os.path.join(run_dir, "conversion_read.json")) as f:
            self.assertEqual(json.load(f)["url"], "https://acme.com")

    def test_flag_off_skips_analyze(self):
        run_dir = os.path.join(build_runner.RUNS, "build-acme-off")
        os.makedirs(run_dir, exist_ok=True)
        cr = build_runner._maybe_conversion_read(
            "https://acme.com", run_dir, brain="super-free",
            read_pass_fn=lambda *a, **k: 1 / 0,   # must NOT be called
            analyze_fn=lambda *a, **k: 1 / 0)
        self.assertIsNone(cr)
        self.assertFalse(os.path.exists(os.path.join(run_dir, "conversion_read.json")))

    def test_read_pass_failure_degrades_not_crashes(self):
        os.environ["PRODUCER_CONVERSION_READ"] = "1"
        run_dir = os.path.join(build_runner.RUNS, "build-acme-degraded")
        os.makedirs(run_dir, exist_ok=True)
        cr = build_runner._maybe_conversion_read(
            "https://acme.com", run_dir, brain="super-free",
            read_pass_fn=lambda url, rd: (_ for _ in ()).throw(RuntimeError("unreachable")),
            analyze_fn=lambda *a, **k: 1 / 0)
        # read pass blew up -> a degraded minimal Read, video still proceeds
        self.assertIsNotNone(cr)
        self.assertTrue(cr["degraded"])
        self.assertTrue(os.path.exists(os.path.join(run_dir, "conversion_read.json")))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Run it, expect FAIL** — `python3 -m unittest tests.test_conversion_read_e2e.AnalyzeStage -v`
  Expected: `AttributeError: module 'build_runner' has no attribute '_maybe_conversion_read'`.

- [ ] **Minimal implementation** — in `build_runner.py`:

  (a) Add the flag constant near the other env flags (after `VO_ENGINE_STYLE`, ~line 62):
  ```python
  # CONVERSION READ feature flag. When PRODUCER_CONVERSION_READ=1, build_runner runs
  # the ANALYZE stage (read_pass -> analyze -> persist) BEFORE planning and seeds the
  # planner with the Read. Default OFF -> main's behavior is byte-unchanged.
  CONVERSION_READ_ENV = "PRODUCER_CONVERSION_READ"

  def conversion_read_enabled():
      return (os.environ.get(CONVERSION_READ_ENV) or "").strip().lower() in ("1", "true", "yes", "on")
  ```

  (b) Add the staged helper (place after `_brand_facts`, ~line 225):
  ```python
  def _maybe_conversion_read(url, run_dir, brain="super-free",
                             read_pass_fn=None, analyze_fn=None):
      """Run the ANALYZE stage and return the Conversion Read dict, or None when the
      flag is OFF. Persists runs/<id>/conversion_read.json on success. Best-effort:
      a read-pass failure degrades to a minimal Read (video still proceeds); the Read
      is NEVER allowed to block the build. read_pass_fn/analyze_fn are injectable for
      tests; they default to the real read_pass.read_pass / analyze.analyze_read."""
      if not conversion_read_enabled():
          return None
      import analyze
      read_pass_fn = read_pass_fn or (lambda u, rd: __import__("read_pass").read_pass(u, rd))
      analyze_fn = analyze_fn or analyze.analyze_read
      try:
          rp = read_pass_fn(url, run_dir)
      except Exception as e:
          print("[build_runner] read_pass crashed: %s" % e, file=sys.stderr)
          rp = {"url": url, "body_text": "", "hero_screenshot_path": None,
                "headline": "", "degraded": True}
      try:
          read = analyze_fn(url, rp.get("body_text", ""),
                            hero_path=rp.get("hero_screenshot_path"),
                            headline=rp.get("headline"), brain=brain)
      except Exception as e:
          print("[build_runner] analyze crashed: %s" % e, file=sys.stderr)
          read = analyze.minimal_read(url, rp.get("body_text", ""))
      if rp.get("degraded"):
          read["degraded"] = True
      read["hero_screenshot_path"] = rp.get("hero_screenshot_path")
      try:
          with open(os.path.join(run_dir, "conversion_read.json"), "w") as f:
              json.dump(read, f, indent=2)
      except OSError as e:
          print("[build_runner] could not persist conversion_read.json: %s" % e, file=sys.stderr)
      return read
  ```

  (c) Call it in `run()` BEFORE the `company_facts = _brand_facts(...)` line (~line 368) and emit the `analyzing` ledger event + thread the Read into the planner. Insert just inside the `try:` (before `company_facts = ...`):
  ```python
          # -- ANALYZE (Conversion Read) -- runs BEFORE planning, behind the flag.
          conversion_read = None
          if conversion_read_enabled():
              led.set_phase("analyzing")
              led.data["stage"] = "analyzing"
              led.event("info", "analyzing %s — reading the page and diagnosing how it "
                        "converts before planning the video" % url)
              led.write(led_path)
              conversion_read = _maybe_conversion_read(url, run_dir, brain=brain)
              if conversion_read is not None:
                  led.data["conversion_read"] = conversion_read
                  scored = ", ".join("%s %d" % (d.get("key"), d.get("score", 0))
                                     for d in conversion_read.get("dimensions", []))
                  led.event("info", "conversion read: %s — scores [%s]%s"
                            % (conversion_read.get("verdict", ""), scored,
                               " (degraded)" if conversion_read.get("degraded") else ""))
                  led.set_phase("planning")
                  led.data["stage"] = None
                  led.write(led_path)
  ```

  And thread the Read into the planner call (line 380-382):
  ```python
          plan = plan_job.plan_job(url, goal, target_duration, style=style,
                                   quality=quality, brain=brain,
                                   company_facts=company_facts, emphasis=emphasis,
                                   conversion_read=conversion_read)
  ```

- [ ] **Run it, expect PASS** — `python3 -m unittest tests.test_conversion_read_e2e.AnalyzeStage -v`
  Expected: `Ran 3 tests` ... `OK`.

- [ ] **Regression check** — `python3 -m unittest tests.test_build_runner_failure -v`
  Expected: `OK` (the new path is flag-gated; the failure handler is untouched).

- [ ] **Commit** — `git add build_runner.py tests/test_conversion_read_e2e.py && git commit -m "build_runner: flag-gated ANALYZE stage (read->analyze->persist->ledger), seeds the planner"`

---

### Task 11 — `$0` mock full-run smoke (flag on/off through `run()`, simulated paid, no network)

- [ ] **Write failing test** — append to `tests/test_conversion_read_e2e.py`:

```python
class FullRunSmoke(unittest.TestCase):
    """Drive build_runner.run() end-to-end at $0: every external boundary is stubbed
    (plan = template via no key, payment = simulated, production = stubbed). Proves
    the analyzing ledger event + conversion_read.json are present on a real run() with
    the flag ON, and absent with it OFF -- the demo's $0 parity."""
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev_runs = build_runner.RUNS
        build_runner.RUNS = self._tmp.name
        self._saved = {}
        # No OpenRouter key -> planner uses the deterministic template ($0).
        import plan_job, analyze
        self._saved["pk"] = plan_job.brain_mod.brain_key
        self._saved["ak"] = analyze.brain_mod.brain_key
        plan_job.brain_mod.brain_key = lambda: None
        analyze.brain_mod.brain_key = lambda: None
        # Stub the heavy boundaries: pricing, payment gate, orchestrate, VO engine.
        self._saved["price"] = build_runner._price_plan
        self._saved["quote"] = build_runner._build_quote
        self._saved["gate"] = build_runner._payment_gate
        self._saved["orch"] = build_runner.orchestrator.orchestrate
        self._saved["vo"] = build_runner.vo_engine_enabled
        self._saved["facts"] = build_runner._brand_facts
        self._saved["read"] = build_runner._maybe_conversion_read
        build_runner._price_plan = lambda plan, run_dir: (500, "usd", {"menu": None})
        build_runner._build_quote = lambda est, currency="usd": None
        build_runner._payment_gate = lambda *a, **k: {"status": "paid", "price_cents": 500,
                                                      "currency": "usd"}
        build_runner.orchestrator.orchestrate = lambda plan, run_id, **k: ({"status": "delivered"}, None)
        build_runner.vo_engine_enabled = lambda: False
        build_runner._brand_facts = lambda url, rd: {"wordmark": "Acme", "tagline": "", "features": ["a", "b", "c"]}
        # Keep analyze offline/deterministic in the staged helper.
        def _fake_maybe(url, run_dir, brain="super-free", read_pass_fn=None, analyze_fn=None):
            if not build_runner.conversion_read_enabled():
                return None
            import analyze as _a
            read = _a.minimal_read(url, "Acme copy")
            with open(os.path.join(run_dir, "conversion_read.json"), "w") as f:
                json.dump(read, f, indent=2)
            return read
        build_runner._maybe_conversion_read = _fake_maybe

    def tearDown(self):
        build_runner.RUNS = self._prev_runs
        import plan_job, analyze
        plan_job.brain_mod.brain_key = self._saved["pk"]
        analyze.brain_mod.brain_key = self._saved["ak"]
        build_runner._price_plan = self._saved["price"]
        build_runner._build_quote = self._saved["quote"]
        build_runner._payment_gate = self._saved["gate"]
        build_runner.orchestrator.orchestrate = self._saved["orch"]
        build_runner.vo_engine_enabled = self._saved["vo"]
        build_runner._brand_facts = self._saved["facts"]
        build_runner._maybe_conversion_read = self._saved["read"]
        os.environ.pop("PRODUCER_CONVERSION_READ", None)
        self._tmp.cleanup()

    def test_flag_on_run_has_analyzing_event_and_read_file(self):
        os.environ["PRODUCER_CONVERSION_READ"] = "1"
        build_runner.run("https://acme.com", "promo", "build-acme-on", mode="mock",
                         target_duration=30)
        run_dir = os.path.join(build_runner.RUNS, "build-acme-on")
        self.assertTrue(os.path.exists(os.path.join(run_dir, "conversion_read.json")))
        import ledger as ledger_mod
        led = ledger_mod.Ledger.load(os.path.join(run_dir, "ledger.json"))
        msgs = " ".join(e.get("msg", "") for e in led.data["events"])
        self.assertIn("analyzing", msgs.lower())
        self.assertIsInstance(led.data.get("conversion_read"), dict)

    def test_flag_off_run_has_no_read(self):
        build_runner.run("https://acme.com", "promo", "build-acme-off2", mode="mock",
                         target_duration=30)
        run_dir = os.path.join(build_runner.RUNS, "build-acme-off2")
        self.assertFalse(os.path.exists(os.path.join(run_dir, "conversion_read.json")))
        import ledger as ledger_mod
        led = ledger_mod.Ledger.load(os.path.join(run_dir, "ledger.json"))
        self.assertIsNone(led.data.get("conversion_read"))
```

- [ ] **Run it, expect FAIL first** — `python3 -m unittest tests.test_conversion_read_e2e.FullRunSmoke -v`
  Expected initially: if Task 10's `run()` wiring places the `analyzing` event correctly, the flag-on test passes; if not, the `assertIn("analyzing", ...)` fails — fix the event placement in `run()` (Task 10 step c) until it passes. (This task adds no new production code; it is the integration gate that proves Task 10's wiring.)

- [ ] **Run it, expect PASS** — `python3 -m unittest tests.test_conversion_read_e2e.FullRunSmoke -v`
  Expected: `Ran 2 tests` ... `OK`.

- [ ] **Commit** — `git add tests/test_conversion_read_e2e.py && git commit -m "test: $0 mock full-run smoke for the ANALYZE stage (flag on/off parity)"`

---

### Task 12 — dashboard: `serve.py` threads the flag into the build subprocess env

- [ ] **Write failing test** — create `tests/test_serve_conversion_flag.py`:

```python
#!/usr/bin/env python3
"""$0 test: the build subprocess inherits PRODUCER_CONVERSION_READ when requested.

We test the pure env-builder helper, not the HTTP server, so no socket is opened."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "dashboard"))

import serve


class ConversionFlagEnv(unittest.TestCase):
    def test_flag_set_when_body_requests_it(self):
        env = serve._build_child_env({"conversion_read": True}, mode="mock")
        self.assertEqual(env.get("PRODUCER_CONVERSION_READ"), "1")

    def test_flag_absent_when_not_requested(self):
        env = serve._build_child_env({}, mode="mock")
        self.assertNotIn("PRODUCER_CONVERSION_READ", env)

    def test_mock_still_simulates_paid(self):
        env = serve._build_child_env({}, mode="mock")
        self.assertEqual(env.get("PRODUCER_SIMULATE_PAID"), "1")
```

- [ ] **Run it, expect FAIL** — `python3 -m unittest tests.test_serve_conversion_flag -v`
  Expected: `AttributeError: module 'serve' has no attribute '_build_child_env'`.

- [ ] **Minimal implementation** — in `dashboard/serve.py`, extract the env-building into a pure helper and call it from `_api_build`. Add near the top-level helpers:

```python
def _build_child_env(body, mode):
    """Build the build_runner subprocess env. MOCK auto-simulates the test payment;
    a truthy body['conversion_read'] turns on the ANALYZE stage feature flag. Pure +
    testable (no socket)."""
    env = os.environ.copy()
    if mode == "mock":
        env["PRODUCER_SIMULATE_PAID"] = "1"
    if body.get("conversion_read"):
        env["PRODUCER_CONVERSION_READ"] = "1"
    return env
```

Then in `_api_build`, replace the inline env block (lines 400-402) with:
```python
        child_env = _build_child_env(body, mode)
```

- [ ] **Run it, expect PASS** — `python3 -m unittest tests.test_serve_conversion_flag -v`
  Expected: `Ran 3 tests` ... `OK`.

- [ ] **Commit** — `git add dashboard/serve.py tests/test_serve_conversion_flag.py && git commit -m "serve: thread PRODUCER_CONVERSION_READ flag into the build subprocess env"`

---

### Task 13 — dashboard: Analysis panel renders the Read before the video (`app.js` + `index.html`)

> JS has no unittest harness here; the test is a deterministic DOM-string assertion run through Node (already required for Remotion). If Node is unavailable in the runner, this task's "test" is a manual checklist — but the assertion script below runs under plain `node`.

- [ ] **Write failing test** — create `tests/test_analysis_panel.js`:

```javascript
// $0 DOM-string test for analysisPanel(). Loads app.js's analysisPanel via a tiny
// shim (the function is pure: ledger in -> HTML string out). Run: node tests/test_analysis_panel.js
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const src = fs.readFileSync(path.join(__dirname, "..", "dashboard", "app.js"), "utf8");
// Pull just the analysisPanel function body by evaluating app.js in a sandbox that
// stubs the browser globals it references at module load.
const sandbox = { window: {}, document: { getElementById: () => null,
  querySelectorAll: () => [], addEventListener: () => {} },
  console, setInterval: () => 0, clearInterval: () => {}, fetch: () => {} };
vm.createContext(sandbox);
try { vm.runInContext(src, sandbox); } catch (e) { /* top-level init may noop */ }

const fn = sandbox.analysisPanel;
if (typeof fn !== "function") { console.error("FAIL: analysisPanel is not defined"); process.exit(1); }

const led = { conversion_read: {
  url: "https://acme.com", verdict: "feature-led hero, zero proof, weak CTA",
  dimensions: [
    { key: "promise", score: 3, finding: "", evidence: "", fix: "" },
    { key: "outcome", score: 2, finding: "", evidence: "", fix: "" },
    { key: "proof", score: 1, finding: "no numbers", evidence: "", fix: "add proof" },
    { key: "show", score: 2, finding: "", evidence: "", fix: "" },
    { key: "specificity", score: 2, finding: "", evidence: "", fix: "" },
    { key: "cta", score: 2, finding: "", evidence: "", fix: "" } ],
  priority_fixes: [{ rank: 1, fix: "Add a proof beat", maps_to: "proof" }],
  headline_fix: "Ship 10x faster.", degraded: false } };

const html = fn(led);
const need = ["Conversion Read", "promise", "outcome", "proof", "show",
  "specificity", "cta", "Add a proof beat", "feature-led hero"];
let ok = true;
for (const s of need) { if (!html.includes(s)) { console.error("FAIL: missing " + s); ok = false; } }
// empty read -> empty string (panel hidden when no Read)
if (fn({}) !== "") { console.error("FAIL: panel should be empty without a Read"); ok = false; }
console.log(ok ? "PASS: analysisPanel renders all 6 dimensions + fixes" : "FAILED");
process.exit(ok ? 0 : 1);
```

- [ ] **Run it, expect FAIL** — `node tests/test_analysis_panel.js`
  Expected: `FAIL: analysisPanel is not defined`.

- [ ] **Minimal implementation** — in `dashboard/app.js`, add the pure renderer (place near `deliveredHero`, before `renderDetail` at line 767):

```javascript
function analysisPanel(l) {
  const cr = l && l.conversion_read;
  if (!cr || !cr.dimensions) return "";
  const KEYS = ["promise", "outcome", "proof", "show", "specificity", "cta"];
  const byKey = {};
  (cr.dimensions || []).forEach((d) => { byKey[d.key] = d; });
  const rows = KEYS.map((k) => {
    const d = byKey[k] || { score: 0, finding: "", fix: "" };
    const score = Math.max(0, Math.min(5, parseInt(d.score, 10) || 0));
    const pips = Array.from({ length: 5 }, (_, i) =>
      '<span class="ap-pip ' + (i < score ? "on" : "") + '"></span>').join("");
    const tone = score <= 1 ? "bad" : score <= 2 ? "weak" : score >= 4 ? "good" : "ok";
    return '<div class="ap-row ap-' + tone + '">' +
      '<span class="ap-key">' + esc(k) + "</span>" +
      '<span class="ap-pips">' + pips + "</span>" +
      '<span class="ap-score">' + score + "/5</span>" +
      '<span class="ap-finding">' + esc(d.finding || "") + "</span>" +
    "</div>";
  }).join("");
  const fixes = (cr.priority_fixes || []).map((f) =>
    '<li class="ap-fix"><span class="ap-rank">' + esc(String(f.rank || "")) + "</span>" +
    esc(f.fix || "") + (f.maps_to ? ' <span class="ap-map">→ ' + esc(f.maps_to) + "</span>" : "") +
    "</li>").join("");
  const deg = cr.degraded ? '<span class="ap-degraded">best-effort read</span>' : "";
  return '<section class="analysis-panel">' +
    '<div class="ap-head"><span class="ap-title">Conversion Read</span>' + deg + "</div>" +
    '<div class="ap-verdict">' + esc(cr.verdict || "") + "</div>" +
    '<div class="ap-grid">' + rows + "</div>" +
    (fixes ? '<div class="ap-fixes-h">What the video fixes</div><ol class="ap-fixes">' + fixes + "</ol>" : "") +
    (cr.headline_fix ? '<div class="ap-headline">Opens with: <em>' + esc(cr.headline_fix) + "</em></div>" : "") +
  "</section>";
}
```

Then insert it BEFORE the video in `renderDetail`'s delivered branch (line 794) and in the live producing branch. Change line 794 from:
```javascript
    root.innerHTML = deliveredHero(l, runId) +
```
to:
```javascript
    root.innerHTML = analysisPanel(l) + deliveredHero(l, runId) +
```
And in `renderLive` (app.js ~line 1755), insert `analysisPanel(l)` after `liveStatusPanel(l)` so the Read shows during production too:
```javascript
  root.innerHTML = liveHeader(l, runId) +
    liveStatusPanel(l) +
    analysisPanel(l) +
    storyboardLead(done, scenes.length) + ...
```

Then add the `analyzing` phase to the stage map. In `app.js`, find the `BUILD_STAGES` array / `currentStageIndex` (around line 1410-1450 per the exploration) and add `"analyzing"` as the first content stage (before `"planning"`), e.g.:
```javascript
// BUILD_STAGES (chip labels) — insert analyzing before planning:
const BUILD_STAGES = ["analyzing", "planning", "pricing", "payment", "producing", "render", "delivered"];
// currentStageIndex(): map phase "analyzing" -> 0 so the chip lights up.
```

Add the CSS to `dashboard/index.html` (in the `<style>` block, near the other card styles):
```html
    .analysis-panel{border:1px solid var(--line,#2a2a2a);border-radius:14px;padding:16px 18px;margin:0 0 18px;background:var(--panel,#141414)}
    .ap-head{display:flex;align-items:center;gap:10px;margin-bottom:6px}
    .ap-title{font-weight:650;letter-spacing:.2px}
    .ap-degraded{font-size:11px;opacity:.6;border:1px solid var(--line,#333);border-radius:999px;padding:1px 8px}
    .ap-verdict{opacity:.85;margin-bottom:12px}
    .ap-grid{display:flex;flex-direction:column;gap:6px;margin-bottom:12px}
    .ap-row{display:grid;grid-template-columns:88px auto 34px 1fr;align-items:center;gap:10px;font-size:13px}
    .ap-key{text-transform:capitalize;opacity:.9}
    .ap-pips{display:flex;gap:3px}
    .ap-pip{width:10px;height:10px;border-radius:3px;background:var(--line,#333)}
    .ap-pip.on{background:var(--accent,#9bd62f)}
    .ap-row.ap-bad .ap-pip.on{background:#e5534b}
    .ap-row.ap-weak .ap-pip.on{background:#e0a030}
    .ap-score{opacity:.7;font-variant-numeric:tabular-nums}
    .ap-finding{opacity:.7}
    .ap-fixes-h{font-weight:600;margin:4px 0 6px}
    .ap-fixes{margin:0;padding-left:0;list-style:none;display:flex;flex-direction:column;gap:5px}
    .ap-fix{display:flex;align-items:baseline;gap:8px}
    .ap-rank{width:18px;height:18px;border-radius:50%;background:var(--accent,#9bd62f);color:#000;font-size:11px;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto}
    .ap-map{opacity:.6}
    .ap-headline{margin-top:12px;opacity:.85}
```

- [ ] **Run it, expect PASS** — `node tests/test_analysis_panel.js`
  Expected: `PASS: analysisPanel renders all 6 dimensions + fixes`.

- [ ] **Commit** — `git add dashboard/app.js dashboard/index.html tests/test_analysis_panel.js && git commit -m "dashboard: Analysis panel renders the Conversion Read before the video + analyzing stage chip"`

---

### Task 14 — register the new suites in `run_all_tests.sh`

- [ ] **Write failing test** — run the suite and confirm the new modules are NOT yet wired:
  `./run_all_tests.sh --no-eval 2>&1 | grep -c "test_analyze\|test_read_pass\|test_plan_seeding\|test_conversion_read_e2e\|test_serve_conversion_flag"`
  Expected: `0` (none registered yet).

- [ ] **Minimal implementation** — in `run_all_tests.sh`, add to section 2b (after line 46, the `test_analytics` line):

```bash
python3 -m unittest tests.test_analyze -v                    || fail=1
python3 -m unittest tests.test_read_pass -v                  || fail=1
python3 -m unittest tests.test_plan_seeding -v               || fail=1
python3 -m unittest tests.test_conversion_read_e2e -v        || fail=1
python3 -m unittest tests.test_serve_conversion_flag -v      || fail=1
```

And add a JS panel check after the Python block (so the panel renderer is gated too); add a small section before section 2c:

```bash
echo
echo "================================================================"
echo " 2b-js. CONVERSION READ — Analysis panel renderer (node, \$0)"
echo "================================================================"
if command -v node >/dev/null 2>&1; then
  node tests/test_analysis_panel.js || fail=1
else
  echo "  SKIPPED — node not on PATH."
fi
```

- [ ] **Run it, expect PASS** — `./run_all_tests.sh --no-eval`
  Expected: every new module prints `OK`, the node panel test prints `PASS`, and the final line is `ALL TESTS PASSED — $0 spent.`

- [ ] **Commit** — `git add run_all_tests.sh && git commit -m "run_all_tests: register the 4 Conversion Read suites + the panel renderer check"`

---

### Task 15 — final flag-off regression gate (prove `main` behavior is untouched)

- [ ] **Run the full suite with the flag explicitly OFF** —
  `unset PRODUCER_CONVERSION_READ; ./run_all_tests.sh --no-eval`
  Expected: `ALL TESTS PASSED — $0 spent.` — every pre-existing suite (`test_producer`, `test_orchestrator`, `test_build_runner_failure`, `test_brand_extract`, `test_style_fill`, …) still passes, proving the additive flag-gated work changed no default behavior.

- [ ] **Spot-check the byte-identical facts block** —
  `python3 -c "import validate_planner as vp; f={'wordmark':'Acme','tagline':'','features':['a','b','c']}; assert vp.company_facts_block(f, company_url='https://acme.com') == vp.company_facts_block(f, company_url='https://acme.com', conversion_read=None); print('FACTS BLOCK UNCHANGED WHEN NO READ')"`
  Expected: `FACTS BLOCK UNCHANGED WHEN NO READ`.

- [ ] **Commit (docs/changelog only, if any)** — no code change expected; if all green, the branch is ready. `git log --oneline | head -16` to confirm the 14 task commits.

---

## Self-review (spec-coverage · placeholder scan · type/name consistency)

**Spec-coverage — every spec section maps to a task:**

| Spec section | Task(s) |
|---|---|
| §3.1 `read_pass` (text+hero, no full walkthrough) | 5, 6 |
| §3.2 `analyze.py` + `analyzer-prompt.md` (reuse brain.py via vp.call_model) | 3, 4 |
| §3.3 Conversion Read JSON contract + validator (6 dims, 0-5, priority_fixes, headline_fix) | 1, 2 |
| §3.4 Read→plan seeding (COMPANY-FACTS + backstop: fixes→scenes, headline_fix→open title) | 7, 8, 9 |
| §3.5 Dashboard Analysis panel (6 scored dims + fixes before the video) + Analyzing stage | 13 |
| §3.6 Persistence (`conversion_read.json` + ledger event) | 10 |
| §5 Guardrails — feature flag `PRODUCER_CONVERSION_READ=1`, default off | 10, 12, 15 |
| §5 Never blocks the video — read fail → degraded; malformed JSON → retry → minimal | 2, 3, 5, 10 |
| §5 $0 mock parity | 11, 14 |
| §8 Testing (unit / mapping / fallbacks / $0 e2e via run_all_tests.sh) | 1-3, 8-11, 14 |
| §2 ledger `analyzing` stage before `planning` | 10, 13 |

All IN-scope items covered. OUT-of-scope items (toggleable fixes, separately-priced Read, next-steps/publish, premium Read, InsForge cloud row) are intentionally NOT planned — matches §6/§9.3.

**Placeholder scan:** No "TBD"/"add error handling"/"…" placeholders. Every code step is complete: full function bodies, exact insertion points (with the surrounding line the implementer matches on), and exact test commands with expected output. Error handling is concrete (degraded fallbacks, `try/except` with the actual except bodies).

**Type/name consistency across tasks (fixed identifiers, used identically everywhere):**
- `analyze.DIMENSION_KEYS = ("promise","outcome","proof","show","specificity","cta")` — Tasks 1,3,4,10,13 all reference these six, in this spelling.
- Read dict keys `url / verdict / dimensions / priority_fixes / headline_fix / degraded` and dimension keys `key / score / finding / evidence / fix` — identical in `validate_read` (T1), `minimal_read` (T2), the prompt (T3/T4), the facts block (T7), the seeder (T8), persistence (T10), the panel (T13).
- `conversion_read` is the kwarg name on `plan_job.plan_job`, `_plan_with_nemotron`, `vp.company_facts_block`, `seed_plan_with_read`, AND the ledger field `led.data["conversion_read"]` AND the JS field `l.conversion_read` — one name end to end.
- `PRODUCER_CONVERSION_READ` flag — same string in `build_runner.CONVERSION_READ_ENV`, `serve._build_child_env`, and the tests.
- `read_pass(url, run_dir, capture_fn=None)` return keys `url / body_text / hero_screenshot_path / headline / degraded` — produced in T5, consumed in `_maybe_conversion_read` (T10).
- `conversion_read.json` filename — written in T10, asserted in T10/T11.
- Score range `0-5` — `validate_read` (T1), prompt (T3), minimal (T2 score=2), panel clamp (T13) all agree.

No inconsistencies found. Plan is internally consistent and spec-complete for the "Read drives the video" scope.
