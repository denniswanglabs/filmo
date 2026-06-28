# Hermes Conducts the Real Filmo Pipeline — Design Spec

**Date:** 2026-06-28
**Status:** Design shape approved by Dennis; spec pending review.
**Related:** `agent-host/mcp_studio_server.py` (scaffold), `HERMES-NEMOCLAW-PLAN.md`, `VIDEO-OVERHAUL-SPEC.md`, `HERMES-STYLE-DECISION-RCA.md`, `2026-06-27-filmo-curated-pattern-library-design.md`.

## 1. Context & Goal

The Filmo agent-host path (Hermes-in-NemoClaw, proven end-to-end on the Hetzner VM) currently produces **generic** videos: it uses a toy planner (`/sandbox/tools/plan_job_rich.py`) + a bare `style_fill --render`, which **bypass the curated pipeline Filmo already ships in production** (the Pattern Library + Design-Fit Variety live on filmostudio.vercel.app).

Symptoms (from the first Hermes-produced Stripe video): no real logo, none of the 14 curated patterns, none of the design-fit variety, not the solidified look DNA.

**Goal:** make Hermes — the autonomous agent, running contained in the NemoClaw sandbox — **conduct the real Filmo pipeline**, so its videos inherit the shipped, brand-faithful, curated quality (real logos, the 14 patterns, design-fit variety, the text-left / glass-card-UI-right / brand-accent / blooms / device-as-hero look), while preserving (a) the agentic-orchestration story and (b) NemoClaw security containment.

**Staged delivery (Dennis: approach C):** a Stripe **hero** for the hackathon demo now (the production pipeline already nails Stripe), built on the general architecture below.

**This is not new architecture** — it is the original agent-host vision (`mcp_studio_server.py`: 5 tools), with the tools wired to the *real* pipeline instead of toy logic.

## 2. Architecture

Hermes (contained in NemoClaw) conducts via **5 sanctioned MCP tools** hosted on the VM host. Each tool runs a real pipeline step; the heavy + trusted execution (Nemotron planning, screenshot capture, Remotion render) stays on the **host**, where it is already proven. The pipeline is **not** ported into the sandbox.

```
Hermes (NemoClaw sandbox, contained)  ──conducts──▶  5 MCP tools (host-resident)
  · reasons between steps                              conversion_read · plan · price · gate · produce_and_ship
  · narrates each step → run_events                          │  each invokes a REAL pipeline step
  · can ONLY call these 5 tools                              ▼
                                       host pipeline: analyze→design_brief → plan_job (pattern-typed scenes)
                                       → brand_extract (real logo) → capture_screenshots → style_fill (14 patterns) → MP4
```

### 2.1 Components

1. **Host MCP server** — evolve `agent-host/mcp_studio_server.py`. Exposes 5 tools, each calling a real pipeline step:
   - `conversion_read(url)` → `analyze.py` (Nemotron-550B Conversion Read) → `{page_text, design_brief:{story_shape, brand_vibe}, brand_facts, logo}` (honesty-guarded; the production `_parse_design_brief`).
   - `plan(brand_facts, design_brief, goal, duration)` → real `plan_job.plan_job()` → the rich plan (scenes typed for the content-fit patterns + `voiceover.beats`).
   - `price(plan)` → real `producer.py` cost-plus → `{price_cents, cogs_cents, margin}`.
   - `gate(price, budget)` → budget decision (proceed / decline) — the agentic money gate (the demo's auto-decline money-shot rides here).
   - `produce_and_ship(plan, brand_theme)` → `capture_screenshots.py` + full `style_fill` (14 patterns + design-fit routing + real logos/screenshots) → MP4 → upload to `walk-videos` → `final_url`.

2. **Hermes config + `filmo-producer` skill** (sandbox) — the skill instructs Hermes to call the 5 tools in order, reasoning between them (re-read on a weak `design_brief`, gate on price, narrate to `run_events`). Brain = Nemotron Ultra 550B (Super-120B fallback for cost).

3. **Sandbox→host bridge** — Hermes (sandbox) reaches the host MCP server (`host.docker.internal:PORT`) via the egress allowlist + Hermes's MCP-client registration (`hermes mcp add`). **This is the one real unknown — see §5 Spike 1.**

4. **Worker** (host) — claims the InsForge job → invokes Hermes with the skill + the job URL → Hermes conducts → marks delivered. Reuses today's hardened worker shell (SSRF guard, dynamic egress, InsForge ship, producer tag).

### 2.2 Data flow

`URL → worker → Hermes:` `conversion_read(url)` → `plan(...)` → `price(...)` → `gate(...)` → `produce_and_ship(...)` → `final_url`. Hermes narrates each step into `run_events` (the "watch the agent work" demo surface).

### 2.3 Security model (the NemoClaw story)

The autonomous agent is **contained**: in the sandbox it can **only** call the 5 sanctioned tools — no arbitrary code execution, no exfiltration, egress-gated. The untrusted URL read is a sanctioned tool with the **verified SSRF guard** (35-vector). The deterministic, trusted pipeline runs on the host. The pitch: *"the agent that could go rogue is sealed in NVIDIA's sandbox and can only pull the five levers we sanctioned."*

### 2.4 What carries over / what's replaced

- **Carries over (done + verified 2026-06-28):** the worker shell, SSRF guard + dynamic per-job egress, InsForge ship, producer/price/quality tagging, `extract_brand_theme.py`.
- **Replaced:** toy `plan_job_rich.py` + bare `style_fill` → the real `analyze` + `plan_job` + full `style_fill` (14 patterns), exposed via the 5 MCP tools.

## 3. The Stripe Hero (staged)

Run this on `stripe.com` → the production-quality Stripe video the pipeline already nails (clean enterprise wordmark open, real logos in the mosaic, real stats, the solidified look), now **conducted by Hermes-in-NemoClaw and narrated step-by-step**. This is the demo's "watch the agent produce" centerpiece. Acceptance: visually indistinguishable from the production pipeline's Stripe video, but driven by the agent.

## 4. Verification / Testing

1. **Spike 1 (bridge) green** before building tools (§5).
2. Each of the 5 tools tested **standalone** against the real step on `stripe.com` (real outputs, not stubs).
3. **End-to-end:** a `stripe.com` job → Hermes conducts all 5 tools → a delivered MP4 with **real logo + curated patterns + the look DNA**, verified by **contact-sheet read** (judge the whole video, per house rule), not one frame.
4. **Parity:** compare the Hermes-conducted Stripe video to the production pipeline's Stripe output — quality should match.
5. **Generality:** repeat on a non-Stripe URL (e.g. `vercel.com`) to confirm design-fit variety fires (real brand vibe + logo).
6. Regression: the production Railway pipeline is untouched and still passes its suite.

## 5. Risks & Spikes (do first, in order)

1. **Sandbox→host MCP bridge** — can Hermes (sandbox) reach + use a host-resident MCP server (`host.docker.internal` + egress), and does Hermes's MCP client support a remote/stdio server across the boundary? **Spike:** stand up a trivial host MCP tool, `hermes mcp add` it, confirm a tool call round-trips from inside the sandbox. *If this fails,* fallback is an InsForge-mediated step queue (Hermes writes "ready for step N"; the host worker executes + returns) — less elegant, same outcome.
2. **Real pipeline step interfaces** — confirm the callable entrypoints (function vs CLI) + I/O for `analyze` / `plan_job` / `producer` / `capture_screenshots` / `style_fill`, so each tool wraps one cleanly. The scaffold's ★SPIKE markers already flagged gaps (e.g. `plan_job` had no `--from-plan` entrypoint; `conversion_read` NemoClaw routing). Resolve these into thin, testable wrappers.
3. **`design_brief` threading** — ensure the `design_brief` from `conversion_read` flows into `plan` and `style_fill.build_props` (the variety routing). The production path does this; confirm it survives the tool decomposition (it is a top-level plan key — must stay in `plan_schema.allowed_top`).

## 6. Out of scope (now)

- Hermes-only demo switch / Railway fallback wiring (separate, already specced).
- The "Produced by Hermes" web badge (deferred until Cursor is clear).
- Porting the pipeline *into* the sandbox (explicitly rejected — keep it host-resident).
- Real-time cost optimization (Ultra vs Super selection) beyond a simple default.

## 7. Open question for review

- Is the 5-tool decomposition the right granularity, or should `conversion_read` + `plan` collapse into one "understand + plan" tool (fewer round-trips across the bridge, slightly less granular narration)?
