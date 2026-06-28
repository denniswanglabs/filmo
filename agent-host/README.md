# Filmo Agent Host — Hermes + NemoClaw

This directory holds everything that runs on the **Agent-Host VM** (Hetzner Ampere ARM,
Ubuntu 24.04) — the piece of Filmo that needs privileged Docker (which Railway/Vercel
can't give us). See `../HERMES-NEMOCLAW-PLAN.md` for the full plan.

## What runs here
- **NemoClaw sandbox** — the secure box (seccomp + egress-allowlist + fs boundary). The
  untrusted work (reading an arbitrary user URL with Chromium) happens *inside* it.
- **Hermes runtime** (brain = NVIDIA Nemotron 3 Ultra) — the orchestrator. On each job it
  runs the **`filmo-producer` skill**, which drives the pipeline tools in sequence and
  makes the call at the budget gate. Real agentic orchestration, not a shell script.
- **The MCP tools** (`mcp_studio_server.py`) — `conversion_read → plan_job → price_job →
  budget_gate → produce_and_ship`, each wrapping a real pipeline step and writing progress
  to InsForge `run_events` so the web UI shows the agent working.

## Run flow
```
web (Vercel) → InsForge jobs row → [VM] claimer → Hermes runs `filmo-producer`:
   1. conversion_read(url)   → Chromium reads the site INSIDE the NemoClaw sandbox
   2. plan_job(read, goal)   → Nemotron plans the cut
   3. price_job(plan)        → deterministic cost-plus / banded quote
   4. budget_gate(...)       → deterministic approve/downgrade/decline; Hermes respects it
   5. produce_and_ship(plan) → render (Remotion) + upload MP4 → runs.final_url
Fallback: if Hermes stalls/errors (watchdog) → deterministic build_runner.py finishes it.
```

## Architecture decision still open (resolved by Phase-0 spike 0c)
Two viable placements for Hermes:
- **A (proven pattern, lower risk):** Hermes + the pipeline run on the VM *host*; only the
  untrusted READ (`conversion_read`) executes *inside* the sandbox via `nemoclaw exec`.
  This is exactly how walk-ultra worked. Honest claim: "the agent reads your site inside
  an NVIDIA sandbox."
- **B (stronger isolation, stretch):** the whole Hermes agent runs *inside* the sandbox.
  Maximal "agent runs safely through NemoClaw" — but heavier (the sandbox's hardcoded
  `ulimit -u 512` + memory ceiling constrain it). Spike 0c measures whether this is viable.

The scaffolds here work for both; the spike picks the placement.

## Files
- `provision-vm.sh` — one-shot VM bootstrap: Docker + Node + NemoClaw + Hermes + the sandbox.
- `sandbox/Dockerfile` — the chrome-deps-baked sandbox image (from the NVIDIA ghcr base).
- `sandbox/provision-sandbox.sh` — onboard + policies + Chromium (adapted from walk-ultra).
- `sandbox/policies/` — `nim.yaml` (NIM endpoint) + `target.yaml.tmpl` (PER-RUN dynamic
  allowlist for the user's URL — Filmo reads arbitrary sites, so this is generated per job,
  not a static demo list).
- `skills/filmo-producer/SKILL.md` — the Hermes orchestration playbook.
- `mcp_studio_server.py` — the pipeline tools (ported + extended from hermes-video-agent).

## What I need from Dennis (the only non-code steps)
1. Provision the Hetzner **CAX21** (Ampere ARM, 4 vCPU / 8 GB) on **Ubuntu 24.04**.
2. Add an SSH key I can use from this Mac (or run `provision-vm.sh` yourself).
3. The `NVIDIA_API_KEY` (and OpenRouter key for paid Ultra) set on the VM — I'll show
   exactly where; I never handle the values.
