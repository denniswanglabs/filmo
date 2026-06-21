# Stripe Issuing — Real-Time Authorization Decisioning in Test Mode

Researched 2026-06-20 against Stripe's official docs (docs.stripe.com, read-only). Where a
detail is NOT in the docs, it is flagged explicitly rather than guessed.

## TL;DR verdict

**Two separate problems are tangled together.** Real-time decisioning is enabled simply by
having a webhook endpoint subscribed to `issuing_authorization.request` (no special toggle).
But the reason every auth declines `insufficient_funds` is a *prerequisite* check that runs
**before** the webhook — and the `stripe listen` CLI listener does not register a persistent
subscribed endpoint, so `.request` never fires for you. To flip the reason to
`webhook_declined`, you must do BOTH: (a) **fund the test Issuing balance** via
`POST /v1/test_helpers/issuing/fund_balance` so the pre-webhook insufficient-funds gate
passes, and (b) **register a real (HTTPS, Dashboard-registered) webhook endpoint** subscribed
to `issuing_authorization.request`, OR drive it locally with `stripe listen` + a server that
returns the decision synchronously. Yes, it will then flip — but it's only worth it if a live
real-time-decisioning demo (not just the auth lifecycle) is the point of the Hermes entry.

---

## 1. How is real-time decisioning enabled?

**No explicit "real-time authorizations" on/off toggle is documented.** It activates by
configuring a webhook endpoint that receives `issuing_authorization.request`.

> "You can configure your webhook endpoint in your Issuing settings. When a purchase attempt
> occurs, Stripe creates an `issuing_authorization.request` event and sends it to your
> configured endpoint for your approval."
> — https://docs.stripe.com/issuing/controls/real-time-authorizations

> "If you don't have a real-time authorization webhook configured, and we don't have a reason
> to decline the authorization request, we'll approve it."
> — https://docs.stripe.com/issuing/purchases/authorizations
> (#scenarios-without-a-real-time-authorization-request)

So: **endpoint configured + subscribed to `issuing_authorization.request` ⇒ decisioning is
live.** Dashboard path referenced by the docs:

- **Issuing settings:** Dashboard → Settings → Issuing
  (https://dashboard.stripe.com/account/issuing) — referenced as where the webhook endpoint /
  timeout settings live.
- **Webhook endpoint registration (persistent):** Dashboard → Developers → Webhooks → Add
  endpoint → subscribe to event `issuing_authorization.request`. (This is the standard
  Stripe webhooks UI; the Issuing docs point you to configure "your webhook endpoint" but the
  generic webhook-registration UI is Developers → Webhooks.)

> NOT IN DOCS: I could not find a doc stating there is a distinct UI checkbox literally labeled
> "Enable real-time authorizations." Treat enablement as "a subscribed endpoint exists," not a
> toggle.

**Timeout fallback (important for the 2s window):**

> "If Stripe doesn't receive your approve or decline response within 2 seconds, the
> Authorization is automatically approved or declined based on your timeout settings, or
> Autopilot settings, if configured."
> — https://docs.stripe.com/issuing/controls/real-time-authorizations

You respond **directly to the webhook event** (HTTP 200 with `{"approved": true|false}` and a
`Stripe-Version` header) — there is no separate approve/decline call required in the synchronous
path. (Async approve/decline endpoints do exist:
https://docs.stripe.com/api/issuing/authorizations/approve)

---

## 2. Does `stripe listen` satisfy the requirement, or must a Dashboard endpoint be registered?

This is the crux of why `.request` didn't fire for you.

- The docs present `stripe listen` strictly as a **local testing** mechanism, not as the
  production/registered endpoint:
  > "To test webhooks locally, you can use Stripe CLI ... `stripe listen --forward-to
  > localhost:4242/webhook`."
  > — https://docs.stripe.com/issuing/controls/real-time-authorizations
- And separately, the quickstart shows triggering events with:
  > "In another terminal, you can then manually trigger `issuing_authorization.request` events
  > from the CLI ... `stripe trigger issuing_authorization.request`"
  > — https://docs.stripe.com/issuing/controls/real-time-authorizations/quickstart

**What this means for you:** `stripe listen` only *forwards* events that Stripe already decided
to emit; it does **not** register a subscribed endpoint that makes Stripe treat your account as
having real-time decisioning. For a real `test_helpers` authorization to emit
`issuing_authorization.request`, Stripe needs (a) the pre-checks to pass and (b) a configured
endpoint subscribed to that event. `stripe listen` by itself does not create that subscription
relationship — which matches your symptom (CLI listener alone, no `.request`).

**Two working paths:**
- **Path A (most reliable):** Register a persistent endpoint in **Developers → Webhooks**
  subscribed to `issuing_authorization.request`, pointed at a publicly reachable HTTPS URL that
  responds within 2s.
- **Path B (local dev):** Use `stripe listen --forward-to localhost:PORT/webhook --events
  issuing_authorization.request` AND have a local server that returns the synchronous decision
  (`200` + `{"approved": ...}`). The CLI's forwarded request is the event; your server's HTTP
  response is the decision. Note the signing secret printed by `stripe listen` is what your
  local server must verify against. (If `.request` still doesn't arrive in this mode, it's the
  balance gate in §3 biting first, not the listener.)

> NOT IN DOCS: Stripe does not publish an explicit sentence "the CLI listener does not count as
> a registered endpoint for enabling real-time decisioning." The above is the consistent reading
> of the docs + your observed behavior; if it must be airtight, register a Dashboard endpoint
> (Path A) and the ambiguity disappears.

---

## 3. Do `test_helpers/issuing/authorizations` honor real-time decisioning? And why insufficient_funds?

**Yes — test-helper authorizations DO go through real-time decisioning, once it's configured.**
Stripe's testing doc states the test-mode simulated authorization fires the request event:

> "You can simulate the creation of an authorization in test mode with the Authorization test
> helpers API. After you configure real-time authorizations, Stripe sends the
> `issuing_authorization.request` webhook event."
> — https://docs.stripe.com/issuing/testing (with-code variant)

So `POST /v1/test_helpers/issuing/authorizations` is the correct way to test a
real-time-decisioned auth. The reason you saw only `issuing_authorization.created` and
`insufficient_funds` is the **pre-webhook gate**:

> "Stripe receives an authorization request ... and approves or declines it without sending you
> an `issuing_authorization.request` event:
> - If Stripe decides that the authorization request can't be approved (for example, because the
>   card is inactive or your spending controls don't allow it), we'll decline it.
> ...
> When this occurs, Stripe still sends an `issuing_authorization.created` event."
> — https://docs.stripe.com/issuing/purchases/authorizations

The decisioning page also confirms balance is checked up front:

> "Stripe checks that the balance used for Issuing has sufficient funds, that the card is active,
> and that your spending controls allow the authorization. Sometimes, Stripe immediately approves
> or declines the authorization request at this stage."
> — https://docs.stripe.com/issuing/purchases/authorizations

**Conclusion:** a $0 balance is one of these "decline before the webhook" conditions. With $0,
the auth never reaches your webhook, so it can't become `webhook_declined` — it's
`insufficient_funds`, decided pre-webhook, and only `.created` fires. **The fix is to fund the
test Issuing balance**, which the docs support via a dedicated test helper:

> `POST https://api.stripe.com/v1/test_helpers/issuing/fund_balance` with `amount` (smallest
> currency unit) and `currency`. — https://docs.stripe.com/issuing/funding/balance

> NOT IN DOCS (timing nuance): The docs explicitly name "card inactive" and "spending controls"
> as pre-webhook decline reasons, and separately list `insufficient_funds` as an authorization
> outcome and state that balance is checked "at this stage." They do not contain one sentence
> that literally says "insufficient funds declines *before* the webhook." The strong inference
> (balance is part of the same up-front check that runs before the request event) matches your
> observed behavior. Funding the balance is the way to confirm and resolve it.

---

## 4. With decisioning active, does the declined reason become `webhook_declined`?

**Yes.** The authorizations page lists `request_history[].reason` values that include both, as
distinct outcomes:

`webhook_approved`, `webhook_declined`, `webhook_error`, `webhook_timeout`,
`spending_controls`, `insufficient_funds`, `verification_failed`, `card_active`,
`card_inactive`, `card_expired`, `card_canceled`, `cardholder_inactive`, `cardholder_blocked`,
`cardholder_verification_required`, `account_disabled`, `suspected_fraud`,
`insecure_authorization_method`, `pin_blocked`, `not_allowed`, `network_fallback`.
— https://docs.stripe.com/issuing/purchases/authorizations

So once the pre-webhook gate passes and your webhook returns `{"approved": false}`, a declined
auth's reason is **`webhook_declined`** (not `insufficient_funds`, not `verification_failed`).
If your endpoint times out / returns a bad `Stripe-Version`, you instead get `webhook_timeout`
or `webhook_error` respectively (per the real-time-authorizations doc).

---

## Step-by-step Dennis can follow (test mode / sandbox)

Terminal (`STRIPE_SECRET_KEY` = test key, `sk_test_...`):

1. **Fund the test Issuing balance** (kills the `insufficient_funds` pre-gate). Use the card's
   currency; example USD-style call (docs show eur/gbp — use your card's currency):
   ```bash
   curl https://api.stripe.com/v1/test_helpers/issuing/fund_balance \
     -u "$STRIPE_SECRET_KEY:" \
     -d amount=100000 \
     -d currency=usd
   ```
   Verify: Dashboard → Balance overview (#issuing-summary), or GET /v1/balance.
   (Ref: https://docs.stripe.com/issuing/funding/balance)

2. **Register a persistent webhook endpoint** (Path A — recommended):
   Dashboard → Developers → Webhooks → Add endpoint → URL = your reachable HTTPS handler →
   subscribe to event **`issuing_authorization.request`** (add `issuing_authorization.created`
   too for visibility). Confirm Issuing settings has no conflicting timeout default you don't
   want (Dashboard → Settings → Issuing → https://dashboard.stripe.com/account/issuing).

   *OR* Path B (local): in one terminal
   ```bash
   stripe listen --forward-to localhost:4242/webhook --events issuing_authorization.request,issuing_authorization.created
   ```
   and run a local server that, on `issuing_authorization.request`, returns **HTTP 200** with
   header `Stripe-Version: <your API version>` and body `{"approved": false}` (or `true`)
   within 2 seconds.

3. **Webhook handler must respond synchronously** to `issuing_authorization.request`:
   - HTTP 200, header `Stripe-Version` set to your account/API version,
   - body `{"approved": false}` to force a decline (or `true` to approve).
   (Ref: https://docs.stripe.com/issuing/controls/real-time-authorizations)

4. **Create the test authorization** (this now passes the balance gate and hits your webhook):
   ```bash
   curl https://api.stripe.com/v1/test_helpers/issuing/authorizations \
     -u "$STRIPE_SECRET_KEY:" \
     -d card="$ISSUINGCARD_ID" \
     -d amount=1000 \
     -d authorization_method=chip \
     -d "merchant_data[category]=taxicabs_limousines" \
     -d "merchant_data[city]=San Francisco" \
     -d "merchant_data[country]=US" \
     -d "merchant_data[name]=Rocket Rides" \
     -d "merchant_data[network_id]=1234567890" \
     -d "merchant_data[postal_code]=94107" \
     -d "merchant_data[state]=CA"
   ```
   (Ref: https://docs.stripe.com/api/issuing/authorizations/test_mode_create,
   https://docs.stripe.com/issuing/testing)

   Optional quick smoke test of the wiring (no auth object created, just fires the event):
   ```bash
   stripe trigger issuing_authorization.request
   ```

5. **Verify the flip:** retrieve the authorization; `approved` should be `false` and
   `request_history[].reason` should be **`webhook_declined`** (not `insufficient_funds`).
   If it's `webhook_timeout` → your handler was too slow (>2s) or unreachable;
   if `webhook_error` → bad/missing `Stripe-Version` header or unparseable body;
   if still `insufficient_funds` → step 1 didn't fund the right currency/card.

## Worth-it verdict

Worth it only if a *live real-time decision* is the demo's point: it will genuinely flip the
reason to `webhook_declined` once you (1) fund the test balance and (2) use a real subscribed
endpoint (Dashboard endpoint, or `stripe listen` + a synchronous 200-responding server) — the
`stripe listen` listener alone was never going to trigger `.request`, and at $0 balance no
webhook path could ever override the pre-gate decline.
