# Hermes Conducts the Real Filmo Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Hermes (in the NemoClaw sandbox) conduct the real Filmo pipeline via 5 host-resident MCP tools, so agent-produced videos inherit the shipped curated quality (real logos, 14 patterns, design-fit variety).

**Architecture:** Hermes (sandbox, contained) calls 5 MCP tools on the VM host; each tool runs a real pipeline step (`analyze → plan_job → producer → capture_screenshots → style_fill`). Pipeline stays host-resident. The agent is sealed to the 5 tools.

**Tech Stack:** Python (pipeline + MCP server), Node (`worker.js`, already hardened), NemoClaw (sandbox + egress), Hermes-agent (MCP client), InsForge (jobs/storage), Remotion (render).

**Spec:** `docs/superpowers/specs/2026-06-28-hermes-conducts-real-pipeline-design.md`

**VM:** `root@REDACTED-VM-HOST` (key `~/.ssh/id_ed25519`). Pipeline at `/root/filmo-pipeline`; sandbox `filmo`; worker `/root/filmo-worker/worker.js`. **Sandbox discipline:** never run two `nemoclaw exec` concurrently; never probe the sandbox while a run is in flight; clear orphans with `nemoclaw filmo exec -- bash -lc 'exec pkill -9 -f filmo-producer'`.

---

## File Structure

- **Create** `agent-host/sandbox/mcp_studio_server.py` — evolve the scaffold into the real 5-tool MCP server (host-resident). One responsibility: expose the 5 pipeline steps as MCP tools.
- **Create** `agent-host/INTERFACE-MAP.md` — output of Milestone 1 (the real pipeline step signatures). The source of truth the tools wrap.
- **Create** `agent-host/sandbox/filmo-producer/SKILL.md` — the Hermes skill (call the 5 tools in order).
- **Modify** `/root/filmo-worker/worker.js` — swap `hermesPlanWithRetry` (toy) for "invoke Hermes with the MCP-tools skill"; keep claim/SSRF/egress/ship/tag.
- **Reuse unchanged:** `analyze.py`, `plan_job.py`, `producer.py`, `capture_screenshots.py`, `style_fill.py`, `extract_brand_theme.py`, `url_guard.py`.

---

## Milestone 0 — SPIKE: sandbox→host MCP bridge (gating unknown)

**Goal:** Prove Hermes (sandbox) can call a tool that executes on the host. If this fails, switch to the InsForge-queue fallback (documented in step 5).

### Task 0.1: Trivial host MCP tool reachable from the sandbox

**Files:** Create `agent-host/sandbox/spike_mcp.py` (throwaway).

- [ ] **Step 1: Write a one-tool MCP server on the host.** A stdio/HTTP MCP server exposing `ping(msg)` → returns `{"pong": msg, "host": <hostname>}`. Use the same MCP lib `hermes-agent[mcp]` expects (confirm which: `mcp` python SDK vs a custom transport — check `hermes mcp add --help` on the VM first).

```bash
ssh -i ~/.ssh/id_ed25519 root@REDACTED-VM-HOST 'source /root/.nemoclaw-env; export PATH=$HOME/.local/bin:/usr/local/bin:$PATH; hermes mcp add --help 2>&1 | head -40'
```
Expected: shows how Hermes registers an MCP server (stdio command vs URL).

- [ ] **Step 2: Determine reachability.** Confirm whether the sandbox can reach the host: from inside the sandbox, attempt a TCP connect to `host.docker.internal` and to the docker bridge gateway.

```bash
ssh -i ~/.ssh/id_ed25519 root@REDACTED-VM-HOST "source /root/.nemoclaw-env; export PATH=\$HOME/.local/bin:/usr/local/bin:\$PATH; nemoclaw filmo exec --no-tty -- bash -lc 'exec /sandbox/hermes-venv/bin/python3 -c \"import socket; [print(h, socket.gethostbyname(h)) for h in [\\\"host.docker.internal\\\"]]\"'"
```
Expected: resolves to a reachable host IP, OR fails (→ the tool must run via stdio, not network — see step 4).

- [ ] **Step 3: Register the spike server with Hermes in the sandbox.** Two transports to try, in order: (a) **stdio** — `hermes mcp add` a command the sandbox runs locally that *itself* bridges to the host (rules out if no host access); (b) **HTTP/SSE** — point Hermes at `http://host.docker.internal:PORT` with that host added to the sandbox egress (`ensureEgress`-style policy-add).

- [ ] **Step 4: Round-trip a call.** Run `hermes chat -q "Call the ping tool with msg=hello and report the host field." -Q` inside the sandbox; confirm the response carries the host's hostname (proving the call executed on the host).

```bash
# (exact invocation depends on step 3's transport; capture the trace)
```
Expected: Hermes reports `host=<vm hostname>` → bridge works.

- [ ] **Step 5: Decision + commit the finding.** If round-trip works → record the transport in `agent-host/INTERFACE-MAP.md` (§Bridge) and proceed to Milestone 1. **If it fails** → the fallback is the InsForge step-queue: Hermes's tools write `{step, args}` rows to an InsForge `agent_steps` table; the host worker polls, executes the real step, writes the result back, Hermes polls for it. Record which path was chosen.

```bash
git add agent-host/INTERFACE-MAP.md && git commit -m "spike: sandbox->host tool bridge — <transport> works"
```

---

## Milestone 1 — SPIKE: map the real pipeline step interfaces (read-only)

**Goal:** Produce `agent-host/INTERFACE-MAP.md` documenting the exact callable entrypoint + I/O for each of the 5 steps, so the tools wrap them with no guesswork. **No code changes** — exploration only.

### Task 1.1: Document each step's interface

**Files:** Create/extend `agent-host/INTERFACE-MAP.md`.

- [ ] **Step 1: `conversion_read` source = `analyze.py`.** Read `analyze.py` + `build_runner.py`'s call to it + `_parse_design_brief`. Record: the function/CLI to produce `{page_text/read, design_brief:{story_shape, brand_vibe}, brand_facts, logo}` from a URL, its inputs, its outputs (exact keys), and where the logo is captured. Note runtime (~34s, Nemotron-550B) + required env (OpenRouter/NVIDIA key).

- [ ] **Step 2: `plan` source = `plan_job.py`.** Read `plan_job.plan_job()` + `_plan_with_nemotron()` + the signature `build_runner` calls it with. Record: exact args (`company_facts`, `design_brief`, `goal`, `target_duration_s`, `quality`, `style`), the output plan shape, and how `design_brief` is threaded (it is a top-level plan key → must stay in `plan_schema.allowed_top`).

- [ ] **Step 3: `price` source = `producer.py`.** Read `producer.cmd_estimate` / the pricing entrypoint `build_runner` uses. Record args + the `{price_cents, cogs_cents, margin}` output.

- [ ] **Step 4: `produce_and_ship` sources = `capture_screenshots.py` + `style_fill.py`.** Read `build_runner._run_vo_engine` (the proven render driver) + `style_fill.run_pipeline(...)` + `_stage_audio` + how screenshots are captured and staged. Record: the exact render call, where `final.mp4`/`video.mp4` lands, and the asset-staging (entityLogos, screenshots) that gives the curated look.

- [ ] **Step 5: Commit the map.**

```bash
git add agent-host/INTERFACE-MAP.md && git commit -m "docs: real pipeline step interface map (5 steps)"
```

---

## Milestone 2 — The 5-tool MCP server (wraps the real steps)

**Goal:** `mcp_studio_server.py` exposes 5 tools, each calling the real step per `INTERFACE-MAP.md`. Each tool tested standalone on `stripe.com` before wiring. Build order = pipeline order so each tool's output feeds the next test.

**For EACH tool below, the task pattern is:** (1) write a failing standalone test that calls the tool handler with real inputs and asserts the real-shaped output; (2) run it, see it fail; (3) implement the handler by calling the real function from `INTERFACE-MAP.md`; (4) run, see it pass on `stripe.com`; (5) commit.

### Task 2.1: `conversion_read(url)` tool
**Files:** Create `agent-host/sandbox/mcp_studio_server.py` (this tool first). Test: `agent-host/tests/test_conversion_read.py`.
- [ ] Test: `conversion_read("https://stripe.com")` returns a dict with non-empty `design_brief.brand_vibe` in {enterprise, bold, consumer, calm, …}, non-empty `brand_facts`, and a `logo` field. Assert SSRF guard: `conversion_read("http://169.254.169.254/")` raises/returns blocked.
- [ ] Implement: handler calls the `analyze` entrypoint from INTERFACE-MAP §1; runs the SSRF guard (reuse `url_guard.assert_public_url`) BEFORE fetch.
- [ ] Verify on stripe.com → enterprise vibe; commit.

### Task 2.2: `plan(brand_facts, design_brief, goal, duration)` tool
**Files:** extend `mcp_studio_server.py`. Test: `test_plan.py`.
- [ ] Test: `plan(<stripe facts+brief>)` returns a plan with `scenes[]` (≥4, typed among the real archetypes), `voiceover.beats[]`, and `design_brief` preserved as a top-level key.
- [ ] Implement: handler calls `plan_job.plan_job(...)` per INTERFACE-MAP §2; ensure `design_brief` stays in `plan_schema.allowed_top`.
- [ ] Verify; commit.

### Task 2.3: `price(plan)` tool
**Files:** extend `mcp_studio_server.py`. Test: `test_price.py`.
- [ ] Test: `price(<stripe plan>)` returns `{price_cents>0, cogs_cents>=0, margin in [0,1)}`.
- [ ] Implement via `producer` entrypoint (INTERFACE-MAP §3); commit.

### Task 2.4: `gate(price, budget)` tool
**Files:** extend `mcp_studio_server.py`. Test: `test_gate.py`.
- [ ] Test: `gate({price_cents:1000}, {budget_cents:5000})` → `{proceed:true}`; `gate({price_cents:9000}, {budget_cents:5000})` → `{proceed:false, reason:"over budget"}` (the money-shot decision).
- [ ] Implement: pure budget comparison (the agentic decision Hermes acts on). Commit.

### Task 2.5: `produce_and_ship(plan, brand_theme, run_key)` tool
**Files:** extend `mcp_studio_server.py`. Test: `test_produce.py` (slow — render).
- [ ] Test: given a real stripe plan + theme, produces `runs/<run_key>/video.mp4` (ffprobe: 1920×1080 h264 + aac) and returns `{final_url}` (HTTP 200 MP4). Run detached + poll (multi-minute).
- [ ] Implement: handler runs `capture_screenshots` then `style_fill.run_pipeline(... do_render=True)` per INTERFACE-MAP §4, then the existing `uploadVideo` path (reuse worker's idempotent upload, or call InsForge SDK).
- [ ] Verify the MP4 has a real logo + a curated pattern via a contact-sheet read; commit.

---

## Milestone 3 — Hermes filmo-producer skill + MCP registration

### Task 3.1: The conductor skill
**Files:** Create `agent-host/sandbox/filmo-producer/SKILL.md`; register the MCP server with Hermes (transport from Milestone 0).
- [ ] Write SKILL.md: instruct Hermes to call, in order, `conversion_read(url)` → `plan(...)` → `price(...)` → `gate(price, budget)` → if `proceed`, `produce_and_ship(...)`; narrate each step in one line; on `gate.proceed=false`, stop and report the decline (the money-shot). One tool call each; do not fabricate data.
- [ ] Deploy the skill + `hermes mcp add` the studio server in the sandbox.
- [ ] Test: `hermes chat -q "Produce a launch video for https://stripe.com" -Q -s filmo-producer` → Hermes calls all 5 tools, narrates, returns a `final_url`. (Sole sandbox user; don't probe during the run.)
- [ ] Commit.

---

## Milestone 4 — Stripe hero end-to-end + worker swap

### Task 4.1: Swap the worker's planner for the conductor
**Files:** Modify `/root/filmo-worker/worker.js` — replace `hermesPlanWithRetry` + the local render with "invoke Hermes (filmo-producer skill) which conducts produce_and_ship itself"; keep claim/SSRF/egress/ship-bookkeeping/producer-tag.
- [ ] Test: `node worker.js --url https://stripe.com` → delivered MP4 via the conductor path; run row `producer=hermes`, real `price_cents`, `final_url` 200.
- [ ] Commit.

### Task 4.2: Hero verification
- [ ] Download the Stripe MP4, contact-sheet read: confirm real Stripe logo, a curated pattern (mosaic/metric-row/kinetic), the look DNA. Compare to a production-pipeline Stripe render for parity.
- [ ] Repeat `--url https://vercel.com` → confirm design-fit variety (different vibe + real logo).
- [ ] Deliver the hero to `~/Desktop/filmo-videos/` named; commit the plan-completion note.

---

## Self-Review

- **Spec coverage:** §2 components → M2 (tools) + M3 (skill) + worker (M4); §2.3 security → SSRF in 2.1 + sealed-to-5-tools by design; §3 hero → M4; §4 verification → M2 standalone + M4 contact-sheet/parity; §5 spikes → M0 (bridge) + M1 (interfaces) + design_brief thread in 2.2; §6 out-of-scope respected. Covered.
- **Placeholder scan:** the tool-internal code intentionally references real functions resolved in M1's INTERFACE-MAP (not "TBD" — existing functions). M0/M1 are fully concrete. The spike-gated detail is by design, not omission.
- **Type consistency:** tool names + I/O keys (`design_brief`, `price_cents`, `final_url`, `proceed`) used consistently across tasks.

---

## Execution Handoff

Milestones 0–1 are spikes (do first; they ground 2–5). Recommended execution: **subagent-driven** — a fresh subagent per task, sole-sandbox-user discipline enforced, review between tasks. The interface details from M1 flow into M2 naturally because each subagent re-reads INTERFACE-MAP.md.
