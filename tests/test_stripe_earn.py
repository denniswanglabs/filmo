#!/usr/bin/env python3
"""Offline ($0, no network) tests for the EARN-side Checkout helper.

Verifies the request-param shape (dry-run) and the TEST-only safety posture WITHOUT
hitting the Stripe API. The real-session create + status poll is exercised separately
via the CLI (needs the test key; that's the verify step, not a unit test).

Run: python3 tests/test_stripe_earn.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# DASHBOARD_BASE is bound at import time; drop any ambient override so the
# default-URL check below asserts the committed default, not this shell's env.
os.environ.pop("FILMO_PUBLIC_BASE", None)

import stripe_earn  # noqa: E402

_checks = 0
_fails = 0


def ok(cond, label):
    global _checks, _fails
    _checks += 1
    if cond:
        print("  PASS  " + label)
    else:
        _fails += 1
        print("  FAIL  " + label)


def test_dryrun_params_wellformed():
    out = stripe_earn.create_checkout_session(
        "test-001", 102, currency="usd", product_name="Stripe promo", dry_run=True)
    ok(out.get("dry_run") is True, "dry_run returns dry_run=True")
    p = out["params"]
    ok(p["mode"] == "payment", "mode == payment")
    ok(p["client_reference_id"] == "test-001", "client_reference_id == job_id")
    ok(p["line_items[0][price_data][unit_amount]"] == 102, "unit_amount == amount_cents")
    ok(p["line_items[0][price_data][currency]"] == "usd", "currency in price_data")
    ok(p["line_items[0][quantity]"] == 1, "quantity == 1")
    ok(p["line_items[0][price_data][product_data][name]"] == "Stripe promo", "product name set")
    ok("test-001" in p["success_url"] and p["success_url"].startswith("https://filmostudio.vercel.app"),
       "success_url points back at dashboard with job_id")
    ok("test-001" in p["cancel_url"], "cancel_url carries job_id")
    # No API call happened => no network keys leaked, no spend.
    ok("session_id" not in out, "dry_run does NOT create a real session")


def test_custom_urls_respected():
    out = stripe_earn.create_checkout_session(
        "job-9", 500, success_url="https://x/ok", cancel_url="https://x/no", dry_run=True)
    p = out["params"]
    ok(p["success_url"] == "https://x/ok", "custom success_url respected")
    ok(p["cancel_url"] == "https://x/no", "custom cancel_url respected")


def test_amount_coerced_int():
    out = stripe_earn.create_checkout_session("j", "750", dry_run=True)
    ok(out["params"]["line_items[0][price_data][unit_amount]"] == 750,
       "string amount coerced to int cents")


def _check_live_key_refused(kind_result):
    """With a live-looking key, every live entrypoint must refuse before any network call."""
    orig = stripe_earn.stripe_money.detect_key
    stripe_earn.stripe_money.detect_key = lambda: kind_result
    try:
        try:
            stripe_earn._assert_test_key()
            ok(False, "live key should raise in _assert_test_key")
        except stripe_earn.LiveKeyRefused:
            ok(True, "_assert_test_key refuses a live key")
    finally:
        stripe_earn.stripe_money.detect_key = orig


def test_live_key_refused():
    """A live-looking key AND a missing key must both refuse. (No-arg so pytest
    collects it as a plain test; the parameterized cases are driven internally
    instead of via a fixture named 'monkeypatched_kind'.)"""
    _check_live_key_refused({"present": True, "source": "x", "kind": "live", "length": 30})
    _check_live_key_refused({"present": False, "source": None, "kind": None, "length": 0})


def main():
    test_dryrun_params_wellformed()
    test_custom_urls_respected()
    test_amount_coerced_int()
    test_live_key_refused()
    print("\n%d checks, %d failures" % (_checks, _fails))
    return 1 if _fails else 0


if __name__ == "__main__":
    sys.exit(main())
