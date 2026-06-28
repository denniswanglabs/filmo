# Run Page — Duplicate Activity UI RCA

Read-only investigation. No files were edited.

Scope: `web/app/runs/[id]/page.tsx` and its components.

---

## 1. The TWO activity surfaces

Both render at the same time while a build is in progress. They read the **same**
`run_events` data and differ only in framing/trim.

### Surface A — "Live activity" (inside the build-progress card)
- **Name in UI:** `Live activity` (header text `BuildProgress.tsx:187`)
- **Component / file:line:** `web/app/components/BuildProgress.tsx`, the live-feed block at **`BuildProgress.tsx:184-214`** (the whole `BuildProgress` card is `:135-230`)
- **Rendered from page:** `web/app/runs/[id]/page.tsx:166` — `<BuildProgress run={run} events={events} />` (the non-terminal branch of the status switch).
- **Data source:** the `events` array (the `run_events` table). Passed down as a prop from the page poll. `BuildProgress` trims it to the **6 most-recent events, newest first** (`BuildProgress.tsx:141` — `[...events].sort((a,b)=>b.seq-a.seq).slice(0,6)`), and highlights the top (newest) line.
- **Also in this card:** an elapsed timer, a shimmer progress bar, and a **stage tracker** (`STAGES` checklist, `BuildProgress.tsx:19-27, 174-182`) derived from `run.phase` — a fixed 7-step checklist (Reading the site → Planning → Pricing → Producing → Voiceover → Stitching → Delivering). This stage checklist is the only piece NOT sourced from `run_events`; it reads `run.phase`.

### Surface B — "Activity" (the static section at the bottom of the page)
- **Name in UI:** `Activity` (header text `page.tsx:179-181`)
- **File:line:** `web/app/runs/[id]/page.tsx:177-204` — the `<section className="mt-8">…</section>` block.
- **Data source:** the SAME `events` array (`run_events` table), but rendered **in full, oldest-first** (no slice, no sort — uses the page's ascending-`seq` order from the poll at `page.tsx:43-48`).
- **Always renders** regardless of run status (it sits below the status switch and the P&L grid), so during a build it appears directly under the `BuildProgress` card — which is why the user sees the event list twice.

---

## 2. Why both render at once

They are not a real-time feed vs. a fixed checklist — that distinction lives *inside*
Surface A (the `STAGES` tracker is the checklist; the `Live activity` list is the
stream). Surfaces A and B are **two renderings of the identical `run_events` stream**:

| | Surface A (`Live activity`) | Surface B (`Activity` section) |
|---|---|---|
| Source | `events` prop (run_events) | `events` state (run_events) |
| Order | newest-first | oldest-first |
| Count | last 6 | all |
| Visible when | non-terminal only (`page.tsx:166`) | always (`page.tsx:177`) |
| Extra chrome | timer, shimmer, stage tracker, newest-line highlight | plain list |

The overlap exists because `BuildProgress` was introduced to make the build feel
alive (its header comment at `BuildProgress.tsx:5-15` says it "Replaces the old
static RunningPanel" and folds a "prominent live activity feed" inside), but the
original standalone `Activity` section at `page.tsx:177-204` was never removed. So
during a build the same events show up in both — once as the trimmed live feed,
once as the full static log.

---

## 3. Consolidation recommendation

**Keep Surface A's live feed (inside `BuildProgress`) as the in-build view, and
make Surface B (the static `Activity` section) the full log that only shows after
the build is terminal.** This removes the double-render during a build while
preserving the complete history for delivered/failed runs.

Concretely, the cleanest fix (no component merge needed — they already share the
`events` array and identical row markup / `ActorBadge`):

- **Gate the static `Activity` section so it does NOT render while a build is in
  progress.** In `web/app/runs/[id]/page.tsx`, the section at **`page.tsx:177-204`**
  currently renders unconditionally. Wrap it so it only renders for terminal runs,
  e.g. `{TERMINAL.has(run.status) && ( …section… )}` (the `TERMINAL` set already
  exists at `page.tsx:16`). During a build, only `BuildProgress`'s `Live activity`
  shows; after delivery/failure the full `Activity` log appears below the video.

- **No change needed to `BuildProgress`** — its `Live activity` block
  (`BuildProgress.tsx:184-214`) stays as the single in-build activity surface.

If instead the user wants exactly ONE activity UI everywhere (build AND
post-delivery), the alternative is to **delete the static section entirely**
(`page.tsx:177-204`) and let `BuildProgress`'s feed be the only one — but note
`BuildProgress` is only rendered in the non-terminal branch (`page.tsx:166`), so
after delivery there would be NO activity list at all. That loses the full
history, so the gated-section approach above is preferred.

Row markup is duplicated between the two surfaces (the `<li>` with `ActorBadge` +
`msg` + timestamp appears at both `page.tsx:186-201` and `BuildProgress.tsx:194-211`,
and `ActorBadge`/`ACTOR_STYLES` are defined twice — `page.tsx:237-252` and
`BuildProgress.tsx:118-133`). Optional cleanup: extract one shared `EventRow` +
`ActorBadge`. Not required to fix the duplicate-UI complaint.

---

## 4. SECONDARY — Stripe payment-link surfacing (payment gate)

**Finding: NO. The run page does not surface a clickable Stripe checkout/payment
link for a human to pay.**

- There is **no `checkout_url` / `payment_link` / `earn.*` / `pay_url` field on the
  `Run` type** at all (`lib/types.ts:7-36` — fields are id, brand, status, phase,
  price_cents, cogs_cents, margin, final_url, edited_url, etc.; no payment URL).
- A repo-wide grep for `checkout_url|payment_link|checkout.stripe|Pay now|paymentUrl|pay_url`
  across `app/` and `lib/` returns **no UI affordance** — the only `stripe` hits are
  the `'stripe'` actor badge style (`page.tsx:240`, `BuildProgress.tsx:121`), the
  Examples/featured-run mock data pointing at `https://stripe.com`, and the
  `awaiting_payment` phase string.
- The `awaiting_payment` phase is recognized only as a **stage-tracker label**
  (mapped into the `Pricing` stage at `BuildProgress.tsx:22`). When a run is in the
  payment gate, the page shows the `BuildProgress` card with "Pricing → Working" —
  but there is **no "Pay" button and no checkout URL rendered**. A human cannot
  click to pay from this page; payment must be happening out-of-band (agent-side /
  Stripe-link in events text at most, not as an actionable affordance).

Reported only, per instructions — not fixed.

---

## File reference index
- `web/app/runs/[id]/page.tsx:166` — renders `BuildProgress` (Surface A) for non-terminal runs
- `web/app/runs/[id]/page.tsx:177-204` — static `Activity` section (Surface B), always rendered
- `web/app/components/BuildProgress.tsx:184-214` — `Live activity` feed (Surface A)
- `web/app/components/BuildProgress.tsx:19-27,174-182` — `STAGES` stage tracker (phase-driven checklist)
- `web/lib/types.ts:7-36` — `Run` type (no payment-URL field)
