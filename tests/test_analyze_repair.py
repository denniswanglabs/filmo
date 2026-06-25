#!/usr/bin/env python3
"""$0, offline tests for analyze.py's JSON-repair on the ANALYZE path.

These pin the small-model (super-free Nemotron 120B) malformations that were
DEGRADING the Conversion Read ~2 of 3 runs: the model packs multiple
comma-separated quoted strings into a single field value (esp. `evidence`),
emits trailing commas, smart quotes, or unescaped inner quotes. The repair
must turn each into a VALID, non-degraded, 6-dimension Read -- without touching
the shared validate_planner.extract_json (planner regression guard).
"""
import os
import signal
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analyze


def _dims_json(evidence_field='"e"'):
    """Build the 6 dimension objects as a raw JSON fragment, injecting a
    possibly-malformed evidence value into the FIRST dimension."""
    parts = []
    for i, k in enumerate(analyze.DIMENSION_KEYS):
        ev = evidence_field if i == 0 else '"clean evidence"'
        parts.append(
            '{"key": "%s", "score": %d, "finding": "finding text", '
            '"evidence": %s, "fix": "fix text"}' % (k, (i % 6), ev)
        )
    return "[\n    " + ",\n    ".join(parts) + "\n  ]"


def _wrap(dims_fragment, trailing=""):
    return (
        "{\n"
        '  "url": "https://stripe.com",\n'
        '  "verdict": "feature-led hero, thin proof"%s\n'
        '  ,"dimensions": %s,\n'
        '  "priority_fixes": [{"rank": 1, "fix": "add a real proof beat", "maps_to": "proof"}],\n'
        '  "headline_fix": "Grow your revenue with one integration"%s\n'
        "}" % ("", dims_fragment, trailing)
    )


# The EXACT shape the 120B emitted: multiple comma-separated quoted strings as
# the evidence value -> breaks plain json.loads / vp.extract_json.
EXACT_MODEL_MALFORMATION = _wrap(
    _dims_json('"Financial infrastructure", "and", "Millions of companies of all sizes"')
)

# Trailing comma inside the dimensions array.
TRAILING_COMMA = _wrap(_dims_json('"clean"'), trailing="").replace(
    '"maps_to": "proof"}]', '"maps_to": "proof"},]'
)

# Smart/curly quotes around a value (model "prettified" the JSON).
SMART_QUOTES = _wrap(_dims_json('“We move money for millions”'))

# Comma-separated fragments AND a trailing comma together (compound slip).
COMPOUND = _wrap(
    _dims_json('"Payments", "Billing", "Connect"'),
).replace('"maps_to": "proof"}]', '"maps_to": "proof"},]')

# Unescaped inner double-quotes inside an evidence value (model forgot to escape).
INNER_QUOTES = _wrap(_dims_json('"they say "powerful" a lot"'))

# CAPTURED FROM THE LIVE FREE TIER: the model single-quotes a value precisely
# because that value already contains double quotes. This was an UNRECOVERED
# strict-parse failure before the single-quote repair pass (real /tmp/fail_11).
SINGLE_QUOTED_VALUE = (
    "{\n"
    '  "url": "https://stripe.com",\n'
    '  "verdict": "outcome-led but thin proof",\n'
    '  "dimensions": [\n'
    + ",\n".join(
        '    {"key": "%s", "score": %d, "finding": %s, "evidence": "ev", "fix": "fx"}'
        % (
            k,
            i,
            # the cta dimension is single-quoted AND holds double quotes inside
            ("'Primary CTAs are clear (\"Get started\", \"Sign up with Google\") "
             "but secondary actions distract.'") if k == "cta" else '"finding text"',
        )
        for i, k in enumerate(analyze.DIMENSION_KEYS)
    )
    + "\n  ],\n"
    '  "priority_fixes": [{"rank": 1, "fix": "add a real demo", "maps_to": "show"}],\n'
    '  "headline_fix": "Accept global payments and grow revenue faster"\n'
    "}"
)

# CAPTURED FROM THE LIVE FREE TIER (real /tmp/cr_raw/raw_08): the model forgot the
# closing '}' on the LAST dimension object, so it runs straight into the ']' that
# closes the dimensions array. The regex chain cannot recover a missing brace; the
# tolerant parser closes the object when it meets the array terminator.
MISSING_BRACE = _wrap(_dims_json('"clean"')).replace(
    '"fix text"}\n  ]', '"fix text"\n  ]'
)

# CAPTURED FROM THE LIVE FREE TIER (real /tmp/cr_raw/raw_10): a stray '"key":'
# leaves a double-colon (`"key": "rank": 2`) in a priority_fix. The tolerant parser
# drops the orphaned ': 2' and keeps the usable {fix, maps_to}.
STRAY_COLON = (
    "{\n"
    '  "url": "https://stripe.com",\n'
    '  "verdict": "feature-led hero, thin proof",\n'
    '  "dimensions": ' + _dims_json('"clean"') + ",\n"
    '  "priority_fixes": [{"key": "rank": 2, "fix": "add a real proof beat", '
    '"maps_to": "proof"}],\n'
    '  "headline_fix": "Grow your revenue with one integration"\n'
    "}"
)


class RepairsToValidRead(unittest.TestCase):
    """Each malformation must repair into a Read that PASSES validate_read with
    all 6 dimensions -- i.e. NOT the degraded minimal fallback."""

    def _assert_repairs(self, raw):
        read = analyze.extract_read_json(raw)
        problems = analyze.validate_read(read)
        self.assertEqual(problems, [], "repaired read invalid: %s" % problems)
        keys = sorted(d["key"] for d in read["dimensions"])
        self.assertEqual(keys, sorted(analyze.DIMENSION_KEYS))
        return read

    def test_exact_model_evidence_fragments(self):
        read = self._assert_repairs(EXACT_MODEL_MALFORMATION)
        # The fragments must collapse into ONE string carrying the evidence.
        ev = read["dimensions"][0]["evidence"]
        self.assertIsInstance(ev, str)
        self.assertIn("Financial infrastructure", ev)
        self.assertIn("Millions of companies", ev)

    def test_trailing_comma(self):
        self._assert_repairs(TRAILING_COMMA)

    def test_smart_quotes(self):
        self._assert_repairs(SMART_QUOTES)

    def test_compound_fragments_and_trailing_comma(self):
        self._assert_repairs(COMPOUND)

    def test_unescaped_inner_quotes(self):
        read = self._assert_repairs(INNER_QUOTES)
        self.assertIn("powerful", read["dimensions"][0]["evidence"])

    def test_single_quoted_value_with_inner_double_quotes(self):
        read = self._assert_repairs(SINGLE_QUOTED_VALUE)
        cta = next(d for d in read["dimensions"] if d["key"] == "cta")
        self.assertIn("Get started", cta["finding"])
        self.assertIn("Sign up with Google", cta["finding"])

    def test_missing_closing_brace_on_last_dimension(self):
        # raw_08 family: the tolerant fallback closes the unclosed object at the ']'.
        self._assert_repairs(MISSING_BRACE)

    def test_stray_colon_in_priority_fix(self):
        # raw_10 family: `"key": "rank": 2` must still yield a usable priority_fix.
        read = self._assert_repairs(STRAY_COLON)
        self.assertEqual(read["priority_fixes"][0]["fix"], "add a real proof beat")


class RepairPreservesValidJson(unittest.TestCase):
    """Well-formed JSON must pass straight through the repair path unchanged."""

    def test_clean_json_untouched(self):
        clean = _wrap(_dims_json('"a clean, single quoted string"'))
        read = analyze.extract_read_json(clean)
        self.assertEqual(analyze.validate_read(read), [])

    def test_repair_does_not_collapse_real_string_arrays(self):
        # A genuine JSON array of strings (elements after '[' or ',', never ':')
        # must survive repair_json untouched -- the collapse only fires in an
        # object-VALUE position.
        raw = '{"verdict":"v","tags":["a","b","c"],"headline_fix":"h"}'
        out = analyze.repair_json(raw)
        self.assertEqual(out["tags"], ["a", "b", "c"])


class AnalyzeReadRecoversInsteadOfDegrading(unittest.TestCase):
    """End to end: a model that emits the EXACT malformation must yield a real,
    non-degraded Read (not minimal_read)."""

    def setUp(self):
        self._orig_call = analyze.vp.call_model
        self._orig_key = analyze.brain_mod.brain_key

    def tearDown(self):
        analyze.vp.call_model = self._orig_call
        analyze.brain_mod.brain_key = self._orig_key

    def test_malformed_evidence_recovers_non_degraded(self):
        analyze.brain_mod.brain_key = lambda: "k"
        analyze.vp.call_model = (
            lambda messages, brain=None, meta=None: EXACT_MODEL_MALFORMATION
        )
        r = analyze.analyze_read("https://stripe.com", "Stripe copy", hero_path=None)
        self.assertEqual(analyze.validate_read(r), [])
        self.assertFalse(r.get("degraded"), "recovered Read should not be degraded")
        self.assertEqual(len(r["dimensions"]), 6)


class TolerantParserTerminates(unittest.TestCase):
    """The tolerant fallback builds objects from arbitrary bytes; a non-advancing
    branch would hang the entire pipeline (not just degrade it). Every loop has a
    progress guarantee -- pin it so a future edit that drops the guard fails loudly
    here instead of hanging a live Read."""

    ADVERSARIAL = [
        "",                        # empty
        "{",                       # lone open brace
        "}{][",                    # closers first
        '{"k":',                   # value missing at EOF
        '{"a": "b" "c" "d"}',      # missing commas / stray fragments
        '{"a": "b", "c": "d"',     # unterminated object
        "[" * 80,                  # unbalanced nesting (shallow enough to not recurse-error)
        '{"k": ' * 80,             # repeated value-missing
        '"' * 400,                 # only quotes
        "::::,,,,}}}]]]",          # only delimiters
    ]

    def test_never_hangs_on_adversarial_input(self):
        if not hasattr(signal, "SIGALRM"):
            self.skipTest("SIGALRM unavailable on this platform")
        old = signal.signal(signal.SIGALRM,
                            lambda *_: (_ for _ in ()).throw(TimeoutError("parser hung")))
        try:
            for bad in self.ADVERSARIAL:
                signal.alarm(5)
                try:
                    analyze._tolerant_parse(bad)  # must RETURN; value is irrelevant
                finally:
                    signal.alarm(0)
        finally:
            signal.signal(signal.SIGALRM, old)


if __name__ == "__main__":
    unittest.main()
