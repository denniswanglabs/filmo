# Walk Studio

**Walk Studio** is an AI agent that turns a URL + a goal into a finished, on-brand
promo video — planned, priced, paid for on Stripe, and produced end to end.
Built for the Hermes hackathon (NVIDIA x Stripe x Nous Research).

Positioning: *"Ploy, but for video."* Curation is the moat. The agent extracts a
brand from its URL, plans a VO-driven shot list, prices it cost-plus, takes payment
on Stripe, and renders designed motion-graphics that fill a small set of curated,
on-brand styles — anti-slop video, not generic AI b-roll.

## What it does

- **URL -> brand** (`brand_extract.py`): a URL becomes a `brand_theme.json`
  (palette, fonts, wordmark, copy, features). Never fabricates a tagline.
- **Plan** (`plan_job.py`, `planner-prompt.md`): goal + brand -> a quality-aware
  shot list. Standard plans only `title` + `motion-graphic` (Remotion);
  Premium may add cinematic scenes.
- **VO-driven timeline** (`align_vo.py` -> `build_timeline.py`): the picture is
  built *from* the voice. Script + beats -> word-level timestamps -> per-scene
  in/out frames. Free path = edge-tts + local whisper; Premium = ElevenLabs
  with-timestamps.
- **Style fill + render** (`style_fill.py`, `studio/` Remotion `<Timeline>`):
  brand theme + timeline + curated style -> `props.json` -> rendered video.
- **Pricing** (`pricing.json`, `pricing.py`): `model: cost_plus`.
  `price = max($5 floor, round_to_$0.50(plan_cogs_cents x 6))`. Single source of
  truth read by both producer and dashboard. Standard vs Premium = `selection.quality`.
- **Pay** (`stripe_earn.py`, `stripe_money.py`): Stripe Checkout at the pay-gate.
  Test-mode only — every live call refuses an `sk_live_`/`rk_live_` key.
- **Produce** (`orchestrator.py`, `producer.py`, `adapters.py`): a serial
  budget-gate + Stripe-authorize sequence; the brain can autonomously decline an
  over-budget spend (the "money-shot").
- **Customer dashboard** (`dashboard/`): a clean Claude/Jitter-style app —
  empty-state composer, past builds, curated lookbook. Operator economics live in
  a separate **Analytics tab** (`analytics.py`, `GET /api/analytics`).

## How to run

Prereqs: Python 3.11+, Node (for Remotion renders), and a `~/.hermes/.env` with
`STRIPE_SECRET_KEY` (test), `ELEVENLABS_API_KEY`, `NVIDIA_API_KEY`. The brain is
NVIDIA Nemotron Super-120B (free, build.nvidia.com).

```sh
# Customer dashboard (Safari -> http://localhost:3030)
python3 dashboard/serve.py
# or the durable launcher:  ~/Desktop/start-walk-studio.command

# Tests (free, no API spend)
./run_all_tests.sh --no-eval

# End-to-end orchestration, $0 mock generation, live Stripe test-mode
python3 orchestrator.py --plan sample-plan.json --mode mock --vo edge
```

## Layout

- `orchestrator.py`, `producer.py`, `adapters.py` — produce pipeline + budget gate
- `plan_job.py`, `plan_schema.py`, `planner-prompt.md` — quality-aware planner
- `align_vo.py`, `build_timeline.py`, `style_fill.py` — VO-driven timeline engine
- `pricing.py` / `pricing.json` — cost-plus pricing (single source of truth)
- `stripe_earn.py`, `stripe_money.py`, `stripe_webhook.py` — Stripe
- `analytics.py` — operator P&L aggregator
- `dashboard/` — customer app (`index.html`, `app.js`, `styles.css`, `serve.py`)
- `studio/src/` — Remotion `<Timeline>` composition + style archetypes
- `branding/` — Walk Studio logos (SVG)
- `tests/` — pytest suite; `run_all_tests.sh` — runner
- `docs/`, `research/`, `*.md`, `.handoff-*.md` — design notes and per-change context

See `HANDOFF.md` for the current state and the deeper `.handoff-*.md` trail.

---

Hermes hackathon entry. Private during development.
