#!/usr/bin/env python3
"""Stripe money layer for the producer brain — EARN + per-scene budget gate.

Two enforcement surfaces (STRIPE-PRODUCER-DESIGN.md §A/§B):
  EARN  — create a test-mode Product + Price + Payment Link; production is gated
          on payment landing.
  SPEND — a Stripe Issuing virtual card with spending_controls. Before each paid
          scene the agent simulates a card authorization; Stripe replies
          approve / DECLINE in real time. A declined authorization is the
          autonomous money-shot.

This module is **safe by default**:
  * It detects a Stripe key by PRESENCE ONLY (length), never reading/printing it.
  * With no key (or live=False) every method SIMULATES — returning authorization
    objects that faithfully model what Stripe would return, so the dashboard
    money-shot renders identically with or without a key. The instant a real
    sk_test_/rk_test_ key exists and live=True, the same calls hit Stripe test
    mode and produce REAL `declined` authorization objects.

Stdlib only (urllib). Test mode == live API minus settlement; no real money.
"""

import json
import os
import urllib.parse
import urllib.request
import urllib.error

HERMES_ENV = os.path.expanduser("~/.hermes/.env")
STRIPE_API = "https://api.stripe.com"


def detect_key():
    """Return (present, source, kind) WITHOUT exposing the value.

    kind is 'test' | 'live' | 'unknown' inferred from the sk_test_/rk_test_/
    sk_live_ prefix only. We never store or print the secret itself.
    """
    val = None
    source = None
    for k in ("STRIPE_SECRET_KEY", "STRIPE_API_KEY"):
        env_val = _read_hermes_env().get(k) or os.environ.get(k)
        if env_val:
            val, source = env_val, ("~/.hermes/.env" if k in _read_hermes_env() else "env")
            break
    if not val:
        return {"present": False, "source": None, "kind": None, "length": 0}
    kind = "unknown"
    if val.startswith(("sk_test_", "rk_test_")):
        kind = "test"
    elif val.startswith(("sk_live_", "rk_live_")):
        kind = "live"
    return {"present": True, "source": source, "kind": kind, "length": len(val)}


def _read_hermes_env():
    out = {}
    if not os.path.exists(HERMES_ENV):
        return out
    try:
        with open(HERMES_ENV) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def _secret():
    env = _read_hermes_env()
    return (env.get("STRIPE_SECRET_KEY") or env.get("STRIPE_API_KEY")
            or os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY"))


class StripeMoney:
    def __init__(self, live=False):
        """live=True only takes effect when a key is actually present."""
        self.key_info = detect_key()
        self.live = bool(live and self.key_info["present"])

    # -- low-level test-mode API call (only used when self.live) ------------
    def _post(self, path, params):
        data = urllib.parse.urlencode(_flatten(params)).encode()
        req = urllib.request.Request(STRIPE_API + path, data=data, method="POST",
                                     headers={"Authorization": "Bearer " + _secret(),
                                              "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    # -- EARN ---------------------------------------------------------------
    def earn(self, price_cents, currency, job_goal):
        """Create a test Payment Link for the priced job, or DEV MODE if no key."""
        if not self.live:
            return {
                "enabled": False, "provider": "dev",
                "status": "dev_mode",
                "price_cents": price_cents, "currency": currency,
                "payment_link": None,
                "note": "No Stripe key configured — DEV MODE, payment gate skipped.",
                "key": self.key_info,
            }
        try:
            product = self._post("/v1/products", {"name": "Video: " + job_goal[:120]})
            price = self._post("/v1/prices", {
                "product": product["id"], "unit_amount": price_cents, "currency": currency})
            link = self._post("/v1/payment_links", {
                "line_items[0][price]": price["id"], "line_items[0][quantity]": 1})
            return {
                "enabled": True, "provider": "stripe", "status": "awaiting_payment",
                "price_cents": price_cents, "currency": currency,
                "payment_link": link.get("url"), "payment_link_id": link.get("id"),
                "product_id": product["id"], "price_id": price["id"],
                "key": self.key_info,
            }
        except (urllib.error.URLError, KeyError, ValueError) as e:
            return {"enabled": True, "provider": "stripe", "status": "error",
                    "error": str(e), "price_cents": price_cents, "key": self.key_info}

    # -- PROVISION the Issuing card ----------------------------------------
    def provision_card(self, budget_cents, currency="usd", terms_ts=None):
        """Create a test-mode Issuing virtual card with spending_limit == budget.

        The cardholder params below are the exact set Stripe test mode requires to
        ACTIVATE a card (validated 2026-06-19): an individual needs first_name +
        last_name AND a card_issuing user_terms_acceptance (date + ip), else the
        card 400s with "outstanding requirements". terms_ts is a unix timestamp
        the caller supplies (the orchestrator avoids wall-clock for reproducibility).
        """
        if not self.live:
            return {"enabled": False, "provider": "simulated",
                    "spending_limit_cents": budget_cents,
                    "card_id": "ic_sim_budget", "note": "Simulated Issuing card."}
        try:
            ts = int(terms_ts) if terms_ts else 1750000000
            cardholder = self._post("/v1/issuing/cardholders", {
                "name": "Hermes Producer Brain", "type": "individual",
                "email": "denniswanglabs@gmail.com", "phone_number": "+15555550123",
                "individual[first_name]": "Hermes", "individual[last_name]": "Producer",
                "individual[card_issuing][user_terms_acceptance][date]": ts,
                "individual[card_issuing][user_terms_acceptance][ip]": "8.8.8.8",
                "billing[address][line1]": "1 Test St", "billing[address][city]": "San Francisco",
                "billing[address][state]": "CA", "billing[address][postal_code]": "94103",
                "billing[address][country]": "US"})
            # Static card limit defaults to the budget → Stripe declines an over-budget
            # charge via spending_controls (reason `authorization_controls`), with no
            # dependency on the webhook. Set PRODUCER_CARD_LIMIT_CENTS to a high ceiling so
            # the over-budget charge PASSES static controls and reaches the real-time webhook
            # (stripe_webhook.py), which declines it on the LIVE budget → reason
            # `webhook_declined` — the brain's own verdict, the stronger autonomous artifact.
            card_limit_cents = int(os.environ.get("PRODUCER_CARD_LIMIT_CENTS") or budget_cents)
            card = self._post("/v1/issuing/cards", {
                "cardholder": cardholder["id"], "currency": currency, "type": "virtual",
                "status": "active",
                "spending_controls[spending_limits][0][amount]": card_limit_cents,
                "spending_controls[spending_limits][0][interval]": "all_time"})
            return {"enabled": True, "provider": "stripe",
                    "spending_limit_cents": card_limit_cents,
                    "card_id": card.get("id"), "cardholder_id": cardholder.get("id"),
                    "last4": card.get("last4")}
        except (urllib.error.URLError, KeyError, ValueError) as e:
            return {"enabled": True, "provider": "stripe", "status": "error", "error": str(e)}

    # -- per-scene authorization (the budget gate's physical enforcement) ----
    def authorize(self, amount_cents, remaining_cents, brain_decision, card_id=None):
        """Decide approve/decline for a scene's spend.

        Simulated mode mirrors the producer brain's verdict into a Stripe-shaped
        authorization object (approved bool + a decline reason on over-budget).
        Live mode creates a real test_helpers Issuing authorization; Stripe's own
        spending_controls decide, so an over-budget charge yields a REAL declined
        authorization object visible in the test dashboard.
        """
        approved = brain_decision == "approve"
        if not self.live:
            return {
                "id": "iauth_sim_%d" % (abs(hash((amount_cents, remaining_cents))) % 10**8),
                "object": "issuing.authorization",
                "simulated": True,
                "amount_cents": amount_cents,
                "approved": approved,
                "decline_reason": None if approved else "spending_controls",
                "remaining_budget_cents": remaining_cents,
            }
        try:
            auth = self._post("/v1/test_helpers/issuing/authorizations", {
                "card": card_id or "ic_sim_budget",
                "amount": amount_cents, "currency": "usd"})
            return {
                "id": auth.get("id"), "object": "issuing.authorization",
                "simulated": False,
                "amount_cents": amount_cents,
                "approved": bool(auth.get("approved")),
                "decline_reason": None if auth.get("approved") else (
                    (auth.get("request_history") or [{}])[0].get("reason", "spending_controls")),
                "remaining_budget_cents": remaining_cents,
            }
        except (urllib.error.URLError, KeyError, ValueError) as e:
            return {"id": None, "simulated": True, "error": str(e),
                    "amount_cents": amount_cents, "approved": approved,
                    "decline_reason": None if approved else "error_fallback",
                    "remaining_budget_cents": remaining_cents}


def _flatten(params):
    """Stripe wants form-encoded nested keys; our callers already pre-flatten,
    so this just stringifies values."""
    return {k: ("true" if v is True else "false" if v is False else str(v))
            for k, v in params.items()}


if __name__ == "__main__":
    import sys
    info = detect_key()
    print(json.dumps({"stripe_key": info}, indent=2))
    sys.exit(0)
