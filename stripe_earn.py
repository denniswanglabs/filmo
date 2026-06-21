#!/usr/bin/env python3
"""EARN-side Stripe TEST-mode Checkout helper — the customer-pays-for-the-video gate.

This is the **EARN** primitive from STRIPE-PRODUCER-DESIGN.md §A: a per-job hosted
Checkout Session the customer pays to start production. It is the counterpart to (and
strictly NOT) the SPEND-side Issuing card in `stripe_money.py`.

Design (per the brief + §A):
  * A per-job `checkout.sessions.create` with mode=payment, a single inline line_item
    (price_data, no pre-created Product/Price), `client_reference_id = job_id`, and
    success/cancel URLs that point back at the dashboard.
  * Payment detection is **webhook-first** (`checkout.session.completed`) but the webhook
    isn't wired yet (blocked on Dennis's `stripe login`), so the backstop NOW is to POLL
    the session's `payment_status` via `get_session_status()` until it reads 'paid'.

Safety — same posture as `stripe_money.py`, and stricter on the key kind:
  * Reuses that module's key loader EXACTLY: presence/length detection, value never
    printed, read from `~/.hermes/.env` then process env.
  * **TEST KEY ONLY.** Every live call refuses if the key looks live (sk_live_/rk_live_),
    and asserts the API response's `livemode == false` — if a live session ever came back
    we raise rather than return it.
  * `--dry-run` builds the request params with NO network call (offline / $0 tests).

Stdlib only (urllib), mirroring `stripe_money.py`. Test mode == live API minus settlement.
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request
import urllib.error

# Reuse the proven, never-prints-the-key loader from the SPEND-side module verbatim.
import stripe_money

STRIPE_API = stripe_money.STRIPE_API  # "https://api.stripe.com"
DASHBOARD_BASE = "http://localhost:3030"


class LiveKeyRefused(RuntimeError):
    """Raised when a live-looking key is used — the earn helper is TEST-only."""


class LiveModeError(RuntimeError):
    """Raised if Stripe ever returns livemode=true — we refuse to surface it."""


def _assert_test_key():
    """Refuse to make any live call unless a TEST key is present.

    Mirrors stripe_money.detect_key() (presence + prefix kind only; never reads the
    value here). Returns the key_info dict on success.
    """
    info = stripe_money.detect_key()
    if not info["present"]:
        raise LiveKeyRefused(
            "No Stripe key in ~/.hermes/.env — earn helper needs a TEST key (sk_test_/rk_test_)."
        )
    if info["kind"] == "live":
        raise LiveKeyRefused(
            "Refusing to run: the configured Stripe key looks LIVE (sk_live_/rk_live_). "
            "The earn helper is TEST-mode only."
        )
    if info["kind"] != "test":
        raise LiveKeyRefused(
            "Refusing to run: Stripe key kind is %r, expected 'test' (sk_test_/rk_test_)." % info["kind"]
        )
    return info


def _post(path, params):
    """Form-encoded POST to the Stripe API, same approach as stripe_money._post."""
    data = urllib.parse.urlencode(stripe_money._flatten(params)).encode()
    req = urllib.request.Request(
        STRIPE_API + path, data=data, method="POST",
        headers={"Authorization": "Bearer " + stripe_money._secret(),
                 "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _get(path):
    """GET to the Stripe API (used to retrieve a session for polling)."""
    req = urllib.request.Request(
        STRIPE_API + path, method="GET",
        headers={"Authorization": "Bearer " + stripe_money._secret()})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def build_session_params(job_id, amount_cents, currency="usd",
                         product_name="Producer video",
                         success_url=None, cancel_url=None):
    """Build the flattened checkout.sessions.create params WITHOUT calling Stripe.

    This is the single source of truth for the request shape; both the dry-run path and
    the live create() use it, so a dry-run faithfully previews the real request.
    """
    # Point straight at the dashboard page (NOT the bare "/" — the static server
    # returns a directory listing for "/?paid=…" because its root-redirect only
    # matches a query-less "/"). Landing directly on /dashboard/index.html lets
    # app.js read the ?paid / ?cancelled param and resume the run's live view.
    if success_url is None:
        success_url = "%s/dashboard/index.html?paid=%s" % (DASHBOARD_BASE, urllib.parse.quote(str(job_id)))
    if cancel_url is None:
        cancel_url = "%s/dashboard/index.html?cancelled=%s" % (DASHBOARD_BASE, urllib.parse.quote(str(job_id)))
    return {
        "mode": "payment",
        "client_reference_id": str(job_id),
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items[0][quantity]": 1,
        "line_items[0][price_data][currency]": currency,
        "line_items[0][price_data][unit_amount]": int(amount_cents),
        "line_items[0][price_data][product_data][name]": product_name,
    }


def create_checkout_session(job_id, amount_cents, currency="usd",
                            product_name="Producer video",
                            success_url=None, cancel_url=None,
                            dry_run=False):
    """Create a per-job TEST-mode Checkout Session for the customer to pay.

    Returns:
      {session_id, url, payment_status, livemode, client_reference_id, amount_cents,
       currency}
    On dry_run: returns {dry_run: True, params: {...}} with NO network call.

    Raises LiveKeyRefused if the key is missing/live; LiveModeError if Stripe ever
    returns livemode=true (we refuse to hand back a live session).
    """
    params = build_session_params(job_id, amount_cents, currency, product_name,
                                  success_url, cancel_url)
    if dry_run:
        return {"dry_run": True, "params": params}

    _assert_test_key()
    session = _post("/v1/checkout/sessions", params)
    livemode = bool(session.get("livemode"))
    if livemode:
        # Hard stop — the earn helper must never operate against live mode.
        raise LiveModeError(
            "Stripe returned livemode=true for session %s — refusing (TEST-mode only)."
            % session.get("id"))
    return {
        "session_id": session.get("id"),
        "url": session.get("url"),
        "payment_status": session.get("payment_status"),
        "status": session.get("status"),
        "livemode": livemode,
        "client_reference_id": session.get("client_reference_id"),
        "amount_cents": amount_cents,
        "currency": currency,
    }


def get_session_status(session_id):
    """Retrieve a Checkout Session and return its payment_status.

    payment_status is one of: 'paid' | 'unpaid' | 'no_payment_required'. This is the
    polling backstop the dashboard pay-gate uses until the webhook is wired. Asserts the
    retrieved session is livemode=false.
    """
    _assert_test_key()
    session = _get("/v1/checkout/sessions/" + urllib.parse.quote(str(session_id)))
    if bool(session.get("livemode")):
        raise LiveModeError(
            "Session %s is livemode=true — refusing (TEST-mode only)." % session_id)
    return session.get("payment_status")


def get_session(session_id):
    """Retrieve the full session dict (for callers wanting status + payment_status)."""
    _assert_test_key()
    session = _get("/v1/checkout/sessions/" + urllib.parse.quote(str(session_id)))
    if bool(session.get("livemode")):
        raise LiveModeError(
            "Session %s is livemode=true — refusing (TEST-mode only)." % session_id)
    return {
        "session_id": session.get("id"),
        "payment_status": session.get("payment_status"),
        "status": session.get("status"),
        "url": session.get("url"),
        "livemode": bool(session.get("livemode")),
        "client_reference_id": session.get("client_reference_id"),
    }


def _cli():
    ap = argparse.ArgumentParser(description="EARN-side Stripe TEST-mode Checkout helper.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create", help="create a Checkout Session for a job")
    c.add_argument("--job", required=True, help="job_id -> client_reference_id")
    c.add_argument("--amount", required=True, type=int, help="amount in cents")
    c.add_argument("--currency", default="usd")
    c.add_argument("--name", default="Producer video", help="product_data name")
    c.add_argument("--success-url", default=None)
    c.add_argument("--cancel-url", default=None)
    c.add_argument("--dry-run", action="store_true",
                   help="print the request params with NO API call")

    s = sub.add_parser("status", help="poll a session's payment_status")
    s.add_argument("--session", required=True, help="cs_test_... session id")

    args = ap.parse_args()
    try:
        if args.cmd == "create":
            out = create_checkout_session(
                args.job, args.amount, currency=args.currency, product_name=args.name,
                success_url=args.success_url, cancel_url=args.cancel_url,
                dry_run=args.dry_run)
            print(json.dumps(out, indent=2))
        elif args.cmd == "status":
            print(json.dumps({"session_id": args.session,
                              "payment_status": get_session_status(args.session)},
                             indent=2))
    except (LiveKeyRefused, LiveModeError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 2
    except urllib.error.HTTPError as e:
        # Stripe error bodies never contain the secret; safe to surface for debugging.
        body = e.read().decode(errors="replace")
        print(json.dumps({"error": "HTTP %d" % e.code, "body": body}), file=sys.stderr)
        return 1
    except (urllib.error.URLError, KeyError, ValueError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
