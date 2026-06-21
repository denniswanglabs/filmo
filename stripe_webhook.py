#!/usr/bin/env python3
"""Real-time Issuing authorization webhook — the producer brain AS the money layer.

This is the design doc's §B Option 2 enforcement, and the cleanest, most credible
money-shot: every time the agent's Issuing card is charged, Stripe fires
`issuing_authorization.request` to THIS endpoint, and the producer brain replies
approve / DECLINE in real time from the live budget. A declined authorization is
then a REAL Stripe object whose reason is the brain's verdict (`webhook_declined`)
— not `insufficient_funds`, so it does not depend on funding the test balance
(which Stripe blocks for US test accounts).

Run it (Dennis, in the morning):
    1. brew install stripe && stripe login          # once
    2. python3 stripe_webhook.py                     # this server, port 4242
    3. stripe listen --forward-to localhost:4242/webhook \
         --events issuing_authorization.request
    4. enable real-time decisioning on the card (the listener does this implicitly
       once an endpoint for issuing_authorization.request exists).

Budget state is read from a JSON file the orchestrator writes (the bridge):
    runs/active_budget.json  ->  {"budget_cents": N, "spent_cents": M}
orchestrator.write_active_budget() writes this at budget-lock and refreshes it
right before every money.authorize(), so the webhook decides against the SAME
locked budget + running spend the brain uses (not {0,0}). Stdlib only.
"""

import argparse
import json
import os
import urllib.parse
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

import stripe_money

STATE_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs", "active_budget.json")
DECISION_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs", "webhook_decisions.jsonl")


def read_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"budget_cents": 0, "spent_cents": 0}


def stripe_post(path, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request("https://api.stripe.com" + path, data=data, method="POST",
                                 headers={"Authorization": "Bearer " + stripe_money._secret(),
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())


def decide(amount_cents, state):
    remaining = int(state.get("budget_cents", 0)) - int(state.get("spent_cents", 0))
    approved = amount_cents <= remaining
    return approved, remaining


class Handler(BaseHTTPRequestHandler):
    state_path = STATE_DEFAULT
    dry_run = False  # when True, decide + log but do NOT call the Stripe API

    def log_message(self, *a):
        pass  # quiet

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            event = json.loads(raw)
        except ValueError:
            self.send_response(400); self.end_headers(); return

        if event.get("type") != "issuing_authorization.request":
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"received":true}'); return

        auth = event["data"]["object"]
        auth_id = auth.get("id")
        amount = auth.get("pending_request", {}).get("amount") or auth.get("amount") or 0
        state = read_state(self.state_path)
        approved, remaining = decide(amount, state)

        # Respond to Stripe by approving/declining within the 2s window.
        if self.dry_run:
            ok = None  # decision computed + logged; no Stripe round-trip
        else:
            try:
                verb = "approve" if approved else "decline"
                stripe_post("/v1/issuing/authorizations/%s/%s" % (auth_id, verb), {})
                ok = True
            except (urllib.error.URLError, urllib.error.HTTPError):
                ok = False

        record = {"auth_id": auth_id, "amount_cents": amount, "remaining_cents": remaining,
                  "decision": "approve" if approved else "decline", "api_ok": ok}
        _append(DECISION_LOG, record)
        print("[webhook] %s %dc (remaining %dc) -> %s"
              % (auth_id, amount, remaining, "APPROVED" if approved else "DECLINED"))

        # Stripe's synchronous real-time-decisioning path requires a valid Stripe-Version
        # response header alongside the 200 + {"approved": bool}; without it the auth's
        # reason becomes webhook_error instead of webhook_declined. Echo the incoming
        # request's Stripe-Version if present, else fall back to a recent valid version.
        stripe_version = self.headers.get("Stripe-Version") or "2024-06-20"
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Stripe-Version", stripe_version); self.end_headers()
        self.wfile.write(json.dumps({"approved": approved}).encode())


def _append(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4242)
    ap.add_argument("--state", default=STATE_DEFAULT)
    ap.add_argument("--dry-run", action="store_true",
                    help="decide + log but never call the Stripe API (for local verification)")
    args = ap.parse_args()
    Handler.state_path = args.state
    Handler.dry_run = args.dry_run
    info = stripe_money.detect_key()
    if not info["present"] and not args.dry_run:
        raise SystemExit("No Stripe key in ~/.hermes/.env — the webhook needs it to approve/decline.")
    print("Issuing authorization webhook on :%d (key=%s, state=%s)"
          % (args.port, info["kind"], args.state))
    print("Forward Stripe to it:  stripe listen --forward-to localhost:%d/webhook "
          "--events issuing_authorization.request" % args.port)
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
