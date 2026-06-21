# Stripe setup — money layer (EARN + the auto-decline money-shot)

Everything here is **Stripe TEST mode** — byte-for-byte the live API minus settlement.
No real money moves. The honest framing for the demo is in `STRIPE-PRODUCER-DESIGN.md` §E.

## Status (validated 2026-06-19, $0)
- A **test secret key** is present in `~/.hermes/.env` as `STRIPE_SECRET_KEY` (detected by
  presence/length only — never printed). `python3 stripe_money.py` confirms it: `kind=test`.
- The key works: `GET /v1/balance` → 200, `livemode=false`.
- **Issuing is enabled** in test mode (`GET /v1/issuing/cards` → 200).
- A real Issuing **virtual card with a spending limit** was created, and real **declined
  authorization objects** were produced — the integration is proven end to end.

## How the code uses it
- `stripe_money.py` — `detect_key()` (presence only), `earn()` (test Payment Link or DEV
  MODE), `provision_card()` (real Issuing card with `spending_limit == budget`),
  `authorize()` (real test-mode authorization, or a faithful simulation when not live).
- `orchestrator.py --stripe-live` switches `earn`/`card`/`authorize` from simulated to the
  real test API. Without the flag (the default / the whole test suite), Stripe is
  **simulated** — the authorization mirrors the producer brain's own budget verdict, which
  is the real decision-maker. The dashboard renders both identically.

## The one open item for the CLEAN money-shot (a ~5-minute morning step)
A US test account **cannot fund the Issuing balance via API** (`fund_balance` →
"not supported for US"), so an over-limit authorization declines as `insufficient_funds`
rather than the on-message `spending_controls`. The credible, funding-independent fix is
**real-time authorization decisioning**, where the producer brain itself replies
approve/DECLINE — the decline reason becomes the brain's verdict (`webhook_declined`).
That server is already written (`stripe_webhook.py`). To light it up:

```bash
brew install stripe && stripe login            # one time, test mode
python3 stripe_webhook.py                       # the brain-as-money-layer, port 4242
stripe listen --forward-to localhost:4242/webhook --events issuing_authorization.request
```
Then a `--stripe-live` run's over-budget scene produces a **real Stripe `declined`
authorization whose reason is the agent's budget decision** — the on-camera money-shot,
no human in the loop. (`stripe_webhook.py` reads the locked budget the orchestrator
writes, so it decides against the same number the brain used.)

## If you ever need to (re)add the key
1. dashboard.stripe.com → Test mode ON → Developers → API keys → copy the `sk_test_…`.
2. (money-shot) Enable Issuing: dashboard.stripe.com/test/issuing/overview → Get started.
3. `open -e ~/.hermes/.env` → add a line `STRIPE_SECRET_KEY=sk_test_…` → save.
4. Verify: `python3 stripe_money.py` → `{"present": true, "kind": "test", ...}` (never prints the value).
