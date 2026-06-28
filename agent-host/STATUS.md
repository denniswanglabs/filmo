# Filmo — Agent-Host Status

**Repo:** `github.com/denniswanglabs/filmo` (PRIVATE)
**Updated:** 2026-06-28
**Scope of this file:** the Hermes-in-NemoClaw agent-host work and how it relates to the
deployed product. For the per-step plan see the spec/plan referenced under PLANNED.

---

## CURRENT — what is proven

The **Hermes-in-NemoClaw** pipeline is proven **end-to-end on the VM**
(`root@REDACTED-VM-HOST`, Hetzner Ampere ARM). The autonomous agent runs **contained inside
the NemoClaw sandbox** and conducts a full job:

> **read → plan → price → render → ship**

All of the hardened plumbing is verified (2026-06-28):

- **SSRF guard** — 35-vector URL guard runs before any fetch; blocks link-local /
  metadata-endpoint targets (`169.254.169.254`, etc.).
- **Dynamic per-job egress** — the sandbox egress allowlist is rewritten per job to the
  one target host the agent is allowed to read (`filmo-dynamic.yaml`), so the agent can
  read an arbitrary user URL without a static demo allowlist.
- **Real brand extraction** — `extract_brand_theme.py` turns any product URL into a
  render-shaped `brand_theme.json` (palette, fonts, features, CTA).
- **Producer / price tagging** — each delivered run is tagged with `producer=hermes`,
  a real `price_cents`, and ships its MP4 to InsForge storage (`final_url`).
- **First videos delivered** — for **stripe.com** and **vercel.com**, agent-produced and
  shipped through this path.

**Important caveat (why the agent videos still look generic):** the VM currently runs the
**`main` = OLD pipeline** (toy planner + bare `style_fill --render`). That path bypasses the
**curated** pipeline (design brief + 14-pattern catalog + design-fit variety) that is
already live in production on the deployed branches. So the architecture and containment
story are proven, but the *visual quality* of agent videos is not yet the shipped curated
look. Closing that gap is exactly the PLANNED work below (re-base the VM on `hosted-saas`).

---

## BRANCH MAP

| Branch | Role | Last commit |
| --- | --- | --- |
| `main` | **OLD** pre-curated pipeline (toy planner + bare render). This is what the VM currently runs. | 06-26 |
| `landing-polish` | **CURATED + DEPLOYED** pipeline — `design_brief` + pattern catalog (14 patterns) + design-fit variety. | 06-28 |
| `hosted-saas` | The **deployed Railway worker** branch — the curated pipeline running in production. | 06-28 |
| `agent-host` | The **new Hermes-in-NemoClaw architecture** work — scaffold (`mcp_studio_server.py`, `sandbox/`, `skills/filmo-producer/`), the captured VM artifacts (`vm/`), the spec + plan, and this STATUS. | 06-28 |

`landing-polish` and `hosted-saas` carry the same curated production pipeline;
`hosted-saas` is the branch deployed to the Railway worker. `agent-host` is the
forward-looking architecture and does **not** yet carry the curated pipeline onto the VM.

---

## PLANNED — Approach A: Hermes conducts the *real curated* pipeline

**Goal:** make Hermes (contained in NemoClaw) conduct the **real, curated** pipeline that
`hosted-saas` ships, so agent-produced videos inherit the shipped brand-faithful quality
(real logos, the 14 curated patterns, design-fit variety) — while keeping both the
agentic-orchestration story and NemoClaw containment.

**Mechanism (approach A):** Hermes, sealed in the sandbox, can call **only 5 sanctioned,
host-resident MCP tools** — each wrapping one real pipeline step:

1. `conversion_read(url)` — `analyze.py` (Nemotron Conversion Read) → page text +
   `design_brief` + `brand_facts` + logo. (Untrusted URL read; SSRF-guarded; the one step
   whose fetch runs through the sandbox.)
2. `plan(...)` — real `plan_job.plan_job()` → pattern-typed scenes + voiceover beats.
3. `price(...)` — real `producer.py` cost-plus quote.
4. `gate(price, budget)` — deterministic proceed / decline (the agentic money gate; the
   demo's auto-decline money-shot rides here).
5. `produce_and_ship(...)` — `capture_screenshots.py` + full `style_fill` (14 patterns +
   design-fit routing + real logos/screenshots) → MP4 → upload → `final_url`.

The heavy + trusted execution (Nemotron planning, screenshot capture, Remotion render)
stays **host-resident**; the pipeline is **not** ported into the sandbox. Pitch:
*"the agent that could go rogue is sealed in NVIDIA's sandbox and can only pull the five
levers we sanctioned."*

### Status of the planned work

- **Spec + plan committed on `agent-host`:**
  - Spec: `docs/superpowers/specs/2026-06-28-hermes-conducts-real-pipeline-design.md`
  - Plan: `docs/superpowers/plans/2026-06-28-hermes-conducts-real-pipeline.md`
- **M0 — sandbox→host MCP bridge spike: PASSED.** Hermes inside the sandbox can call a
  host-resident MCP tool over HTTP via `host.openshell.internal` (egress-allowed). The
  gating unknown is resolved; the InsForge step-queue fallback is not needed.
- **M1 — interface map: being redone against `hosted-saas`.** The earlier interface map
  was drafted against the old pipeline; it is being re-mapped to the curated
  `hosted-saas` entrypoints (`analyze` / `plan_job` / `producer` / `capture_screenshots`
  / `style_fill`) so the 5 tools wrap the curated steps with no guesswork.
- **Next:** re-base the VM on `hosted-saas` (so it runs the curated pipeline, not `main`),
  then build the 5 MCP tools per the plan (M2), wire the `filmo-producer` skill (M3), and
  run the Stripe hero end-to-end with a contact-sheet parity check vs. the production
  render (M4).

---

## Captured VM artifacts (`agent-host/vm/`)

Snapshot of the built Hermes system on the VM (`root@REDACTED-VM-HOST`), code/config only —
**no secrets** (all keys are read from env vars or keyfiles at runtime; verified clean):

- `vm/worker.js` — the hardened job worker (claim → SSRF guard → dynamic egress → invoke
  Hermes → ship to InsForge → producer/price tag).
- `vm/extract_brand_theme.py` — host-side brand-theme extractor (URL → render-shaped
  `brand_theme.json`).
- `vm/Dockerfile` — the NemoClaw sandbox image (NVIDIA `sandbox-base` + Hermes venv).
- `vm/filmo-dynamic.yaml` — **per-job** egress policy (rewritten to the target host per
  build; current snapshot pins vercel.com).
- `vm/filmo-targets.yaml` — test-target egress policy (stripe.com family).
- `vm/hermes-inference.yaml` — Hermes LLM egress policy (OpenRouter + NVIDIA NIM).
