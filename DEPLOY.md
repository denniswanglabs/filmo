# Filmo — Deploy & Infrastructure (the live system)

Filmo is an AI Product Launch Producer: a URL goes in, and a launch video comes out —
Conversion Read → plan → price → gate → produce → ship. This document is the
reproducible snapshot of the **currently live** system.

Production is three managed services and nothing else:

- **Vercel** — the Next.js frontend at `https://filmo.dev`.
- **InsForge** — Postgres, auth, the `jobs` queue, and the `walk-videos` storage bucket.
- **Railway** — the async worker service `walk-studio-hosted` that produces the videos.

There is **no VM**. The June-2026 Hetzner worker, the Hermes agent harness, and the
NemoClaw/OpenShell sandbox were retired on **2026-07-16** (see
[`RAILWAY-CUTOVER.md`](RAILWAY-CUTOVER.md)); their configuration is kept for reference
under [`deploy/retired/`](deploy/retired/) and is **not** used by the Railway image.

## Live components

| Component | Where it runs | What it is |
|---|---|---|
| **Web** (Next.js 15 / React 19) | **Vercel** → `https://filmo.dev` | the site: submit a URL, watch the live run feed, edit + download the video. `web/middleware.ts` redirects the legacy `filmostudio.vercel.app` and `www.filmo.dev` to the canonical origin |
| **InsForge** | hosted Postgres + storage, project `jd3mdkqr.ap-southeast.insforge.app` | the shared backend: `runs` / `jobs` / `run_events` / `agent_events` / `credit_ledger` / `developers` tables, auth, and the public **`walk-videos`** bucket |
| **Worker** (`walk-studio-hosted`) | **Railway**, 2 replicas (`railway.json`) | polls InsForge `jobs`, runs the deterministic `build_runner.py` pipeline, uploads the MP4, marks the run delivered |

The worker image is built from the repo `Dockerfile`: it bundles the Python pipeline,
Playwright/Chromium, Remotion + its browser, ffmpeg, `edge-tts`, and a locally-built
`whisper.cpp`, then boots `agent-host/vm/curated-claimer.js` with
`CLAIMER_MODE=curated`, `PRODUCER=railway-curated`.

## How a job flows: URL → video

```
  Browser (Vercel)               InsForge (Postgres + storage)          Railway worker
 ─────────────────              ───────────────────────────────      ─────────────────────────────
  submit URL  ─────────────────►  insert runs + jobs(queued)
                                        ▲                              curated-claimer polls jobs
  live feed  ◄──── run_events ◄────────┼───────────────────────────   claim_next_job (atomic RPC)
                                        │                                  │ CLAIMER_MODE=curated
                                        │                                  ▼
                                        │                     build_runner.py (deterministic)
                                        │        Conversion Read → plan → price → gate → produce
                                        │        (Nemotron read+plan · Playwright capture ·
                                        │         align_vo + style_fill · Remotion render · ffmpeg)
  download  ◄──── runs.final_url ◄──────┴──────── upload MP4 → walk-videos/<run_key>/final.mp4
```

1. The site (or a direct insert) creates a `runs` row + a `queued` `jobs` row, and charges
   the film to the user's `credit_ledger` (`web/app/actions.ts`).
2. A worker replica claims the oldest job via the atomic `claim_next_job` RPC and
   SSRF-guards the target URL (`assertPublicUrl` — private/loopback/link-local and cloud
   metadata addresses are refused before any egress).
3. `build_runner.py` runs the pipeline: Conversion Read (`read_pass` → `analyze`) → plan
   (`plan_job`) → price (`producer`) → payment gate → produce (`orchestrator`) → picture
   (Playwright capture → `align_vo` → `build_timeline` → `style_fill` → Remotion render).
   Every ledger step is streamed into `run_events` as the live "watch it work" feed.
4. The claimer uploads `final.mp4` plus per-scene stills to the `walk-videos` bucket,
   stamps `runs.final_url` + `props.producer`, and marks the job done. A failed build
   **refunds** the credit row, so a failed attempt never consumes the allowance.
5. The site shows the delivered video; the editor and the chat director re-render edits
   (`rerender` / `director` job types on the same worker).

For a `pay_mode=human` job with `PAYMENTS_REQUIRED=true`, the claimer first opens a real
Stripe **TEST** checkout (`gate.py`, card `4242…`) and waits for payment before producing.
`gate.py` refuses any live/missing key. This path is opt-in; the default gate is credits.

## `deploy/` map

| Path | Captures |
|---|---|
| `deploy/insforge/schema.md` | the DB schema (`runs`/`jobs`/`run_events`/`developers`) + the `walk-videos` bucket |
| `deploy/web/.env.example` | the frontend env — names + placeholders, no real values |
| `deploy/worker/` | `gate.py` (the Stripe TEST checkout gate the claimer spawns) + `.env.example` for the worker |
| `deploy/retired/` | **RETIRED 2026-07-16, reference only** — the Hetzner systemd units + VM host scripts, the Hermes skills, and the NemoClaw sandbox/egress config. Nothing in the build or runtime path reads these; see `deploy/retired/README.md` |

## Deploy steps

**Web (Vercel):**
```
cd web && vercel --prod --yes
vercel alias set <new-deploy-url> filmo.dev    # the alias does NOT auto-follow — always re-alias
```
Env: `web/.env.local` (see `deploy/web/.env.example`).

**Worker (Railway):** deploy from the repo working tree — the image is built from the
root `Dockerfile`.
```
railway link                                    # project walk-studio / service walk-studio-hosted / env production
railway up --service walk-studio-hosted         # build + deploy from the working tree
railway logs --service walk-studio-hosted       # expect: "mode: curated (deterministic build_runner)"
```

> **Heads-up on `scripts/railway-push-env.sh`.** It still fetches `OPENROUTER_API_KEY`,
> `ELEVENLABS_API_KEY`, and `AGENTMAIL_API_KEY` over SSH from the decommissioned Hetzner
> VM, so it cannot run as written. Set those three variables from a local source (or
> `railway variables --set …` by hand) until the script is repointed; the rest of it —
> the name list and the "never echo a value" discipline — is still correct.

Required variables: `INSFORGE_URL`, `INSFORGE_API_KEY`, `OPENROUTER_API_KEY` (the brain —
every Nemotron call goes through OpenRouter), `ELEVENLABS_API_KEY` (optional; the image
falls back to `edge-tts` + `whisper.cpp`), `FILMO_PUBLIC_BASE=https://filmo.dev`,
`WALK_BUCKET=walk-videos`, `PAYMENTS_REQUIRED`, `PAYMENT_TIMEOUT_MS`. `CLAIMER_MODE` /
`PRODUCER` / `PYTHON_BIN` are baked into the image. Full runbook:
[`RAILWAY-CUTOVER.md`](RAILWAY-CUTOVER.md).

**Backend (InsForge):** the tables and the public `walk-videos` bucket already exist on the
shared project; schema in `deploy/insforge/schema.md`, migrations in `migrations/`. Auth
redirect hosts live in `insforge.toml`. Do NOT rename the bucket (`walk-videos`) — renaming
breaks the live deploy.
