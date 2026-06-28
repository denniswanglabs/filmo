# Filmo

**Filmo** is an AI Product Launch Producer. Paste a URL and a goal; Filmo reads your
real product, diagnoses how the page converts, plans a video, prices the job, takes
payment on Stripe, and produces a finished 1080p launch video — end to end.

Built for the **Hermes Hackathon** (Nous Research × NVIDIA × Stripe).
Live: **https://filmostudio.vercel.app**

> **Curation is the moat.** Instead of letting a model improvise every layout (which
> yields "AI slop"), Filmo picks from a hand-curated library of designer-quality
> motion-graphic patterns and fills each with the brand's **real** data — never
> fabricated. Anti-slop video, grounded in your actual product.

## Pipeline

URL → **Conversion Read** → plan → price → pay → produce → ship.

1. **Read the product** — `brand_extract.py` pulls the brand (palette, fonts, wordmark,
   real copy) from the URL; `analyze.py` runs a **Conversion Read** (Nemotron): a
   scored diagnosis of why the page converts or doesn't, plus the headline that should
   open the video. Honesty-guarded — never fabricates a stat or a quote.
2. **Plan** — `plan_job.py` turns the goal + Conversion Read into a quality-aware,
   VO-driven shot list, choosing curated patterns that fit the brand's real material.
3. **Price** — `pricing.py`: a dynamic **banded** quote derived from the storyboard
   (scene count, cinematic count, duration) plus the planner's token cost, clamped to
   the quality tier — **Standard $5–$10**, **Premium $15–$25**.
4. **Pay** — `stripe_earn.py`: a Stripe Checkout session at the pay-gate. The autonomous
   over-budget **Stripe Issuing decline** (`stripe_money.py`) is surfaced in the
   developer view. Stripe runs in **test mode**.
5. **Produce** — `align_vo.py` + `build_timeline.py` build the picture *from* the voice
   (word-level VO timing); `style_fill.py` + the `studio/` **Remotion** composition
   render the final MP4, which is uploaded back to the run.

## Architecture (hosted SaaS)

| Layer | Tech |
|---|---|
| **Web** | Next.js 15 (App Router) · React 19 · Tailwind · `@remotion/player` in-browser editor → **Vercel** |
| **Worker** | Node poller (`worker/run.js`) + Python pipeline (`build_runner.py`) in one Docker image → **Railway** |
| **Data / auth / storage** | **InsForge** — `runs` / `jobs` / `run_events` tables (row-level security), auth, and the video storage bucket |
| **Brain** | **NVIDIA Nemotron** — every reasoning call. Super-120B (free) and Ultra-550B (`ultra-paid`); the Conversion Read defaults to Ultra-550B for fidelity |
| **Agent framework** | **Hermes** (Nous Research) — the hackathon's agent framework; here the build loop is a deterministic Python harness (`build_runner.py` → `orchestrator.py`) with Nemotron as its reasoning brain |
| **Payments** | **Stripe** — Checkout (earn) + Issuing (autonomous decline), **test mode only** (every live call refuses an `sk_live_`/`rk_live_` key) |
| **Video** | **Remotion** (render) · **Playwright** (site capture) · **edge-tts** (VO; **ElevenLabs** on the premium path) · **whisper.cpp** (word timing) · **ffmpeg** (stitch) |

The web app creates a build by inserting a `runs` + `jobs` row into InsForge; the
Railway worker claims the job (`claim_next_job`), runs the pipeline, and uploads the
finished MP4 back to `runs.final_url`.

## Run it

**Hosted:** deploy `web/` to Vercel and the worker (`Dockerfile`) to Railway, both
pointed at an InsForge project. Required env: `INSFORGE_*`, `OPENROUTER_API_KEY` (or
`NVIDIA_API_KEY`), `STRIPE_SECRET_KEY` (test), `ELEVENLABS_API_KEY`.

**Local pipeline (debug):**
```sh
set -a; source ~/.hermes/.env; set +a
python3 build_runner.py --url https://stripe.com --run-id dev1 --mode mock --brain ultra-paid
# → renders runs/dev1/final.mp4   (mock = real Remotion cards, $0 production)
```

**Verify:**
```sh
cd web && npm run build           # web: typecheck + production build
python3 -m unittest test_url_guard tests.test_build_runner_failure   # sample suites
```

## Layout

- `web/` — Next.js app (Vercel)
- `worker/` — Node job poller (Railway)
- `build_runner.py`, `orchestrator.py`, `producer.py`, `adapters.py` — produce loop + budget gate
- `brand_extract.py`, `analyze.py`, `plan_job.py`, `plan_schema.py` — read → Conversion Read → plan
- `align_vo.py`, `build_timeline.py`, `style_fill.py` — VO-driven timeline engine
- `url_guard.py` — SSRF guard for the user-supplied URL
- `pricing.py` — cost-plus pricing
- `stripe_earn.py`, `stripe_money.py`, `stripe_webhook.py` — Stripe (test mode)
- `studio/` — Remotion `<Timeline>` composition + the curated pattern library
- `tests/` — pipeline test suite

## Honesty notes

- **Stripe is test mode** — real API calls, real objects, no real settlement (one key
  swap plus a registered entity away from live).
- Filmo only renders stats/entities from the model's **verified knowledge** of a brand;
  unknown brands degrade to honest, data-poor layouts rather than fabricated numbers.

---

Hermes Hackathon entry (Nous Research × NVIDIA × Stripe). Private during development.
