# Railway cutover runbook (Hetzner → Railway, curated mode)

> **STATUS: COMPLETED 2026-07-16.** The cutover ran and stuck. Production is the Railway
> service `walk-studio-hosted` (2 replicas), curated mode. **Hetzner is decommissioned** —
> the VM, its `filmo-claimer` / `mcp-toolserver` units, the Hermes agent harness, and the
> NemoClaw/OpenShell sandbox are all out of the production path and are no longer available
> as a rollback. Steps 5–7 below (the "keep Hetzner warm" verification) are therefore
> HISTORICAL; the deploy steps (1–4) and the env list are still the live runbook. The
> retired VM/Hermes/NemoClaw configuration is kept for reference under `deploy/retired/`.
> Current architecture: `DEPLOY.md`.


Goal: production worker moves to Railway; Hetzner claimer retires. Hermes/NemoClaw
are already out of the hot path (CLAIMER_MODE=curated on Hetzner since 2026-07-16).

## Pre-flight (done 2026-07-16)
- [x] VM pipeline vs repo working tree: 12/12 core files hash-identical (zero drift).
- [x] Dockerfile boots `agent-host/vm/curated-claimer.js` (curated), root node_modules
      symlink for `@insforge/sdk`, PRODUCER=railway-curated.
- [x] Hetzner flipped to curated + e2e verified (run `e2e-curated-*`).

## Blocked on Dennis
- [x] `railway login` — done 2026-07-16.
- [x] `gh auth login` — done 2026-07-16; commits pushed.

## Deploy (run from repo root, after railway login)
1. `cd ~/Desktop/Projects/Hackathons/walk-studio-hosted && railway status` — confirm
   the link (project walk-studio / service `walk-studio-hosted`, env production).
   NOTE: deploy FROM ~/filmo working tree: `cd ~/filmo && railway link` the same
   service first (the ~/filmo clone has no .railway config yet).
2. Push env vars (values read from the VM key files + web/.env.local — never echo):
   `bash scripts/railway-push-env.sh` (see below; creates nothing on failure).
   Required: INSFORGE_URL, INSFORGE_API_KEY, OPENROUTER_API_KEY, NVIDIA_API_KEY,
   ELEVENLABS_API_KEY, AGENTMAIL_API_KEY, FILMO_PUBLIC_BASE=https://filmo.dev,
   WALK_BUCKET=walk-videos, PAYMENTS_REQUIRED=true (gate only fires on payMode=human),
   PAYMENT_TIMEOUT_MS=900000. CLAIMER_MODE/PRODUCER/PYTHON_BIN bake into the image.
3. `railway up --service walk-studio-hosted` — builds the Dockerfile from the
   working tree (uncommitted PaaS-brand-fix files included; they hash-match the VM).
4. Watch build: `railway logs --build | head`, then runtime logs for
   `mode: curated (deterministic build_runner)`.

## Verify (Railway proves itself while Hetzner still runs)
5. Stop Hetzner claiming temporarily: `ssh root@<decommissioned-vm-ip> systemctl stop filmo-claimer`
   (claim is atomic, but stopping removes any race for the test).
6. Enqueue an e2e run (owner account, run_key `e2e-railway-<ts>`, brain super-free,
   mode mock — mirror the 2026-07-16 curated e2e insert) and watch it deliver with
   `producer=railway-curated`. Check the video URL 200s and a contact sheet looks sane.
7. If Railway fails: `systemctl start filmo-claimer` on Hetzner (instant rollback) and
   debug Railway offline.

## Cutover
8. Railway green → leave Hetzner's filmo-claimer STOPPED + DISABLED
   (`systemctl disable --now filmo-claimer mcp-toolserver`). Keep the VM around for
   a week as rollback, then Dennis cancels the server himself.
9. Update memory + CLAUDE.md: worker = Railway service `walk-studio-hosted`
   (curated claimer image); Hetzner retired.

## Notes
- The old `worker/run.js` stays in the repo (dormant) — the image no longer boots it.
- ElevenLabs VO comes from ELEVENLABS_API_KEY at runtime; edge-tts remains in the
  image as the fallback path build_runner already knows.
- Railway MCP tools historically stay Unauthorized even after CLI login — use the CLI.
