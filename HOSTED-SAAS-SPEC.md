# Walk Studio — Hosted SaaS Spec (full cloud, local-as-fallback)

_Draft for Dennis's review — written 2026-06-23 while you were out. Nothing here is
built yet; this is the design to approve before I touch code. Hackathon: NVIDIA ×
Stripe × Nous (Hermes), due 2026-06-30._

## Decisions locked (from our chat)
- **Full cloud.** Frontend, backend, and the producer worker all hosted — not a Mac
  behind a tunnel.
- **Additive / local-as-fallback.** All new code lands on a branch in a new `web/`
  app + a worker wrapper around the **existing** `build_runner.py` (unchanged). At any
  moment `python3 dashboard/serve.py` + local builds work exactly as today. If the
  cloud stalls before the deadline, `git checkout main` → proven local demo, zero
  reconstruction.
- **Demo on Nemotron 550B, framed accurately.** Run the demo with `--brain ultra-paid`
  (`nvidia/nemotron-3-ultra-550b-a55b`). Claim: _"Nemotron 550B is the planning brain
  inside the Hermes producer agent; deterministic gates run the money; Stripe moves it."_

## Why not pure-Vercel
The pipeline spawns long, stateful, non-serverless work: Playwright+Chromium capture
(`.venv-capture`), multi-minute Remotion renders (Node+Chromium), the Higgsfield CLI,
edge-tts/ElevenLabs, ffmpeg, and the persistent **NemoClaw** broker. None fit Vercel
functions (even 300s Fluid Compute). So Vercel hosts the frontend + thin API; the heavy
pipeline lives on an always-on worker.

## Three tiers

### 1. Frontend + thin API — Vercel (Next.js App Router)
- The customer app: composer (goal + URL), Recents + search, delivered view + player,
  Standard/Premium, the **Agent activity** sidebar panel, Stripe checkout return.
- Reuse the current dashboard's HTML/CSS/SVG where it speeds us up; port `app.js`
  view-logic into React/route-handlers incrementally.
- Vercel route handlers (serverless, fine): create build (enqueue a job), list runs,
  fetch a run, fetch activity feed, Stripe **webhooks**. No heavy compute here.

### 2. Worker — a persistent cloud machine (CPU-heavy, GPU optional)
- Runs the **existing Python pipeline unchanged**: `build_runner.py` → capture → Nemotron
  plan → produce → Remotion render → ffmpeg stitch → upload. Plus **NemoClaw** (broker)
  and the **Nemotron 550B** OpenRouter calls.
- Pulls jobs from a queue (a Supabase `jobs` table polled, or Vercel Queues), writes
  progress to the `runs` row + `events` (so the live view + activity feed stream), and
  uploads `final.mp4` to Supabase Storage on deliver.
- **Host:** a long-running container/VM — Fly.io machine, Railway, Render, or a plain
  cloud VM. **GPU not required:** Remotion renders on Chromium (CPU), Higgsfield is a
  remote API, edge-tts/ffmpeg are CPU. A beefy multi-core CPU box (8–16 vCPU) suffices;
  add GPU only if we later move to local video models. (Recommend Fly.io for fast
  always-on + simple secrets; decide at build time.)

### 3. Data — Supabase
- **Postgres** replaces the file-based `runs/*/ledger.json` + `runs/index.json`:
  - `users` — Supabase Auth users (self-signup).
  - `runs` — one row per build: id, user_id, brand/url, goal, emphasis, quality, brain,
    mode, status, phase, price_cents, cogs_cents, margin, created_at, final_url,
    plan (jsonb), selection (jsonb: brain/tokens/finish_reason).
  - `run_events` — append-only `{run_id, seq, level, msg, actor}` (feeds live view +
    the Agent activity conversation).
  - `jobs` — the work queue: `{id, run_id, status: queued|claimed|done|failed,
    claimed_at, params}` (mirrors today's atomic-claim marker protocol).
- **Auth** — self-signup (email/OAuth). The custom domain is needed for OAuth callbacks.
- **Storage** — `final.mp4` + thumbnails (replaces serving from `runs/` with Range; the
  Storage CDN handles Range natively).
- **Realtime** — subscribe to `runs`/`run_events` for the live build view + the activity
  feed, replacing the current 2–4s polling of `/api/active` and `/api/activity`.

## API contract mapping (current → cloud)
| Today (`serve.py`) | Cloud |
|---|---|
| `POST /api/build` | Vercel route → insert `runs` + `jobs(queued)` → worker picks up |
| `GET /runs/index.json` | Vercel route → `select * from runs order by created_at desc` |
| `GET /api/active` | Supabase Realtime channel (or a `runs where status=running` query) |
| `GET /api/analytics` | Vercel route → SQL rollup over `runs` |
| `GET /api/activity` | Vercel route → build the Hermes↔Nemotron `turns` from `runs`+`run_events` (port `activity.py`) |
| `GET /runs/<id>/final.mp4` | Supabase Storage public/signed URL |
| `POST /api/editor/*` | Phase 2 — keep local-only at first |
| Stripe Payment Link/webhook | Stripe Checkout on Vercel + webhook route → mark `runs.paid` |

## Fallback strategy (the hard requirement)
- New code only: `web/` (Next.js), `worker/` (thin wrapper importing `build_runner`),
  `supabase/` (schema migrations). **Zero edits to** `build_runner.py`, `serve.py`,
  `dashboard/`, or the producer modules — they stay the working local path.
- Develop on a branch (`hosted-saas`). `main` always boots the local demo.
- CI gate at every milestone: `python3 dashboard/serve.py` + a local mock build must
  still deliver. If cloud work ever breaks that, it's a bug, not a tradeoff.

## Build order (7 days → 2026-06-30)
1. **(½ day) 550B framing** — demo runs `--brain ultra-paid`; accurate "Powered by"
   copy. (Cheap; gate the paid call.)
2. **(1 day) Supabase** — schema + Auth + Storage bucket; seed from a few local ledgers.
3. **(1–2 days) Worker** — `worker/run.py`: claim a `jobs` row → call existing
   `build_runner.py` → stream events to `run_events` → upload `final.mp4` → mark done.
   Stand it up on the chosen host with NemoClaw + the venvs + Higgsfield CLI + keys.
4. **(2 days) Vercel app** — Next.js frontend (port the composer, Recents+search,
   delivered view, Agent activity panel) + route handlers against Supabase + Stripe
   Checkout/webhooks.
5. **(1 day) Realtime + polish** — live build view + activity feed via Realtime; custom
   domain; end-to-end paid (test-mode) run on 550B; verify local fallback still green.
6. **(buffer) Hardening** — concurrency limits on the worker, error/timeouts, the
   editor (phase 2) if time.

## Risks / open questions (for Dennis)
- **Worker host choice** — Fly.io vs Railway vs a raw VM. (Recommend Fly.io.) Confirm.
- **Secrets in cloud** — OPENROUTER, Stripe, ElevenLabs, Higgsfield keys move from
  `~/.hermes/.env` to the host's secret store + NemoClaw on the worker. No keys in Vercel
  except Stripe's.
- **Custom domain** — needed for Auth OAuth callbacks + a clean demo URL. Which domain?
- **Cost** — 550B planning is ~sub-cent/build; worker host ~$5–20/mo; Supabase free tier
  likely fine for the demo. All negligible vs. the hackathon payoff.
- **Editor (`/api/editor/*`)** — defer to phase 2 (keep local) to protect the timeline.

## What I did NOT do (gated on you)
- No code written, no commits, no paid (550B / real-mode) builds, no infra provisioned.
- This spec + the activity-log rework are uncommitted, awaiting your word.
