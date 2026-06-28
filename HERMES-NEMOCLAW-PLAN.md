# Filmo — Hermes-orchestrated, NemoClaw-sandboxed architecture (plan)

**Vision (Dennis):** *Hermes runs safely through NemoClaw, quickly on Nemotron 3 Ultra,
and intelligently with its extensive agent skills.* This IS the submission — the agent
runtime is the deliverable, not a deterministic pipeline with a sandbox bolted on.

**Priority:** THE priority (polish slides). Deterministic path stays as the fallback.

---

## Target architecture — "Agent inside the box"

```
Vercel (Next.js web)
   └─ user pastes URL → createBuild → InsForge `jobs` row
InsForge (data / auth / storage / video bucket)            ── unchanged
   ▲                                                   claim_next_job
   │                                                        │
   └──────────────  AGENT-HOST VM  ◄───────────────────────┘  (privileged Docker; arm64)
                    │
                    ├─ NemoClaw sandbox  ── the SECURE BOX
                    │    └─ Hermes runtime (brain = Nemotron 3 Ultra) + its skills
                    │         on a job: activates the `filmo-producer` SKILL →
                    │         orchestrates: READ → PLAN → PRICE → GATE → (hand to render)
                    │    └─ Chromium reads the user URL IN-SANDBOX (egress-allowlisted)
                    │
                    └─ host (outside the sandbox): Remotion render + ffmpeg + upload
                         (our own props — not untrusted — so it runs with full headroom)
Stripe (payments, test mode)                               ── unchanged
Fallback: deterministic build_runner.py (watchdog) → every build still ships
```

**Why this split:** untrusted work (autonomous agent loop + reading arbitrary URLs)
runs *inside* NemoClaw's seccomp + egress guardrails. The render (our own data, heavy
Chromium) runs on the host where the sandbox's `ulimit -u 512` + memory ceiling don't
choke it. Hermes orchestrates the *job*; the render is a tool it calls.

**Sponsor truth after this:** Nous Hermes = the orchestrator (real), NVIDIA Nemotron
Ultra = the brain (real), NVIDIA NemoClaw = the secure runtime (real, live), Stripe =
payments (real, test). No framing stretch.

---

## Phase 0 — De-risk the unknowns FIRST (spikes; nothing big until these are green)

The whole plan rides on four things I will not assume:

- **0a · Provision the Agent-Host VM** *(Dennis's step — billing/account).* NemoClaw needs
  privileged Docker + is arm64-locked → best match is a **Hetzner Ampere ARM** box
  (~€6/mo, proven in walk-ultra notes) or a **Fly Machine** / **Vercel Sandbox** micro-VM.
  I prep the exact provisioning + setup commands; Dennis runs the account/billing steps.
- **0b · NemoClaw-on-VM spike.** Install NemoClaw, onboard a sandbox from a baked
  Dockerfile, reproduce the `provision.sh` recipe, and confirm Chromium captures a real
  URL — with the known flags baked in (see Landmines). Confirms NemoClaw runs on the VM.
- **0c · Hermes-in-sandbox spike (the keystone).** Install the Hermes runtime + skills
  INSIDE the NemoClaw sandbox; confirm Hermes runs on Nemotron Ultra and can execute a
  skill that calls a tool — within the sandbox's seccomp/egress/`ulimit` constraints.
  This is the make-or-break: does the agent loop survive inside the box?
- **0d · Ultra-latency spike (honesty gate).** Measure Nemotron-3-Ultra *in the agent
  loop* end-to-end. ⚠️ In the Walk Agent work, Ultra-550B was slow under agent loops
  (≈176s for 53 tokens; 25-min runs) and the team flipped to a faster model for the live
  demo. We keep Ultra per your call; if the loop is too slow, the fallback covers demo
  speed and we can run the loop on a faster Nemotron while reserving Ultra for the key
  reasoning steps. Measure, don't guess.

## Phase 1 — The `filmo-producer` Hermes skill + tools
- Author `SKILL.md` for `filmo-producer`: on a URL+goal, it orchestrates read → plan →
  price → budget-gate → produce → ship, deciding at the gate. Register it with Hermes.
- Expose each pipeline step as a tool the skill calls (port + extend `mcp_studio_server.py`:
  add `produce_and_ship`). **Money math stays deterministic in `producer.py`** — the agent
  decides *when* to call price/gate and reacts to the result; it can't invent a price.
- Each tool writes to InsForge `run_events` → the live UI shows the agent's real tool
  calls = proof-of-execution for judges.

## Phase 2 — Wire the hosted flow onto the VM
- The Agent-Host VM runs a small claimer (same `claim_next_job` contract) that, per job,
  invokes Hermes-in-NemoClaw with the URL → Hermes runs `filmo-producer`.
- Keep `build_runner.py` as the **watchdog'd deterministic fallback**: if the agent stalls
  or errors, the deterministic path finishes the build so nothing strands.

## Phase 3 — In-sandbox capture + safety
- The READ step runs Chromium inside NemoClaw (all Landmine flags), egress-allowlisted to
  the target's registrable domain (`STAY_ON_DOMAIN`) + the SSRF guard. The `/inside` view
  shows the **live** sandbox capture (not the baked fixture).

## Phase 4 — Verify + the demo
- One end-to-end gen where Hermes-in-NemoClaw orchestrates on Ultra and ships a real video,
  with `run_events` showing the agent's tool calls + the live capture.
- Kill Hermes mid-run → confirm the deterministic fallback delivers.
- A "watch Hermes work" view for judges (the agent's live tool-call stream).

---

## NemoClaw landmines (pre-paid by the Walk Agent research — bake in from day one)
- **Chromium in-sandbox:** `--enable-features=NetworkServiceInProcess --disable-features=NetworkService` (seccomp blocks AF_NETLINK); `--ignore-certificate-errors` + `ignoreHTTPSErrors:true` (proxy MITM CA); spawn chrome + `connectOverCDP` (NOT `chromium.launch`); `--remote-debugging-address=127.0.0.1`; unique `--user-data-dir`; pass `FONTCONFIG_PATH/FILE`, `XDG_DATA_DIRS`; pass the proxy explicitly.
- **LLM/NIM calls:** `node:https`, NOT `fetch` (undici bypasses the injected proxy); hard wall-clock deadline (dead tunnels read "active" for ~1hr); `max_tokens ≥ 1500` for reasoning models; retry/backoff on 5xx/429.
- **Egress policy:** authorized per (host, binary-path) — `node` allowed, `curl` blocked (test egress with `node -e fetch`); every preset needs `binaries: - { path: "/**" }`; per-run allowlist reset; the host-allowlist is load-bearing for *navigation quality* (`STAY_ON_DOMAIN`), not just security.
- **Credentials:** the `nvidia-prod` gateway credential goes stale on ANY key rotation → `nemoclaw credentials reset nvidia-prod --yes` + re-onboard; export `NVIDIA_API_KEY` in the exec payload (sandbox doesn't inherit host env).
- **Lifecycle:** `ulimit -u 512` is HARDCODED in the openshell binary (caps parallelism → ~1 capture/run); only `recover` preserves state (never `rebuild`/`destroy` casually); codify the recreate as `provision.sh`; `nemoclaw exec` rejects multi-line / >1MB payloads (use script files + base64 piping); exec is the real liveness test (healthcheck lies).
- **Ops:** nothing survives a host reboot without a LaunchAgent/systemd unit; long ops need care (locally, Claude Code's Bash sandbox kills them — `dangerouslyDisableSandbox`).

## Safety invariants (held throughout)
Money path stays deterministic (price/gate/Stripe); the auth + SSRF hardening from the
prior pass stays; the deterministic fallback guarantees delivery; the agent runs *inside*
the sandbox so a hostile URL is contained.

## Account / billing boundary
Dennis provisions the VM + enters all secret values (NVIDIA key, etc.); I write all code
+ prepare exact commands. (Per the standing rule: I never handle his keys/passwords.)

## Open risks (honest)
1. **Ultra latency under the agent loop** (measured in 0d). 2. **Hermes-inside-NemoClaw
feasibility** — the keystone (0c). 3. **VM ops surface** — NemoClaw is hand-tended
(reboot recovery, credential resets, `ulimit` ceiling). 4. **Time** — this is a multi-day
build; the deterministic app stays live the whole time as the safety net.
