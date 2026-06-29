#!/usr/bin/env python3
"""Pre-conduct Stripe TEST payment gate for the Hermes claimer.

Mirrors build_runner._payment_gate's create+poll, exposed as a CLI the node claimer
(curated-claimer.js) drives as a subprocess. TEST-mode ONLY: it reuses
stripe_earn.create_checkout_session / get_session_status, whose _assert_test_key()
refuses any missing/live key (sk_live_/rk_live_) and whose livemode==true responses
raise LiveModeError. This shim NEVER prints the Stripe key (it only calls the earn
helpers, which read it internally and never echo it).

Subcommands:
  create --run-id <id> --amount-cents <n> [--currency usd] [--product-name <s>]
         [--success-url <u>] [--cancel-url <u>]
     -> prints JSON {session_id, checkout_url, price_cents, currency, livemode,
        payment_status, client_reference_id} on stdout (exit 0), or
        {error} on stderr (exit 2 = key/livemode refusal, exit 1 = http/other).
  status --session <cs_test_...>
     -> prints JSON {session_id, payment_status} (exit 0) or {error} (exit 2/1).

The amount is a positive-int guard (mirrors build_runner H3): a None/0/negative/
non-int price is refused rather than minting a $0 / bogus Checkout Session.
"""
import argparse
import json
import os
import sys

# stripe_earn lives in PIPELINE_DIR (the claimer passes it through). Default to the
# known install path so the shim also works when run by hand.
sys.path.insert(0, os.environ.get("PIPELINE_DIR", "/root/filmo-pipeline"))
import stripe_earn  # noqa: E402  (reuses _assert_test_key + create + status, test-only)


def _create(a):
    # SOURCE OF TRUTH: amount_cents must be a positive int (bool is not an int here).
    if isinstance(a.amount_cents, bool) or not isinstance(a.amount_cents, int) or a.amount_cents <= 0:
        print(json.dumps({"error": "invalid amount_cents=%r" % (a.amount_cents,)}), file=sys.stderr)
        return 2
    s = stripe_earn.create_checkout_session(
        a.run_id, a.amount_cents, currency=a.currency, product_name=a.product_name,
        success_url=a.success_url, cancel_url=a.cancel_url)
    # _assert_test_key already ran inside create_checkout_session; a live key would
    # have been refused and a livemode=true session would have raised. Re-assert here.
    if bool(s.get("livemode")):
        print(json.dumps({"error": "refusing livemode=true session"}), file=sys.stderr)
        return 2
    print(json.dumps({
        "session_id": s.get("session_id"),
        "checkout_url": s.get("url"),
        "price_cents": a.amount_cents,
        "currency": a.currency,
        "livemode": bool(s.get("livemode")),
        "payment_status": s.get("payment_status") or "unpaid",
        "client_reference_id": s.get("client_reference_id"),
    }))
    return 0


def _status(a):
    print(json.dumps({
        "session_id": a.session,
        "payment_status": stripe_earn.get_session_status(a.session),
    }))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Pre-conduct Stripe TEST payment gate (claimer subprocess).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--run-id", required=True)
    c.add_argument("--amount-cents", type=int, required=True)
    c.add_argument("--currency", default="usd")
    c.add_argument("--product-name", default="Filmo promo video")
    c.add_argument("--success-url", default=None)
    c.add_argument("--cancel-url", default=None)
    s = sub.add_parser("status")
    s.add_argument("--session", required=True)
    a = ap.parse_args()
    try:
        return _create(a) if a.cmd == "create" else _status(a)
    except (stripe_earn.LiveKeyRefused, stripe_earn.LiveModeError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001  (any other failure: surface JSON, exit 1)
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
