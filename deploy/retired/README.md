# `deploy/retired/` — kept for reference, not used by the Railway image

**Retired 2026-07-16.** Everything under this directory describes the June-2026
hackathon-era deployment: a Hetzner VM running the `filmo-claimer` daemon and a host
MCP tool-server, with the produce step conducted by a **Hermes** agent sealed inside an
**NVIDIA NemoClaw / OpenShell** sandbox.

That architecture is **gone**. Production is now:

- **Vercel** — the Next.js frontend at `https://filmo.dev`
- **InsForge** — Postgres, auth, the `jobs` queue, the `walk-videos` bucket
- **Railway** — the worker service `walk-studio-hosted` (2 replicas), whose image boots
  `agent-host/vm/curated-claimer.js` at `CLAIMER_MODE=curated` and runs the deterministic
  `build_runner.py` pipeline

See [`../../DEPLOY.md`](../../DEPLOY.md) for the live system and
[`../../RAILWAY-CUTOVER.md`](../../RAILWAY-CUTOVER.md) for the cutover runbook.

## Why these files are still here

They are the honest record of how the hackathon build ran, and the NemoClaw egress
policies in particular are a useful reference for anyone sandboxing an agent. Nothing in
the build or runtime path reads them: no `Dockerfile`, `railway.json`, `scripts/`,
`agent-host/`, `worker/`, or `web/` file references any path under `deploy/retired/`.

Every Hermes code path in `agent-host/vm/curated-claimer.js` is guarded by
`CLAIMER_MODE === 'hermes'`; the shipped image pins `CLAIMER_MODE=curated`, so none of it
is reachable in production.

## What is in here

| Path | What it was |
|---|---|
| `hermes/` | the `filmo-producer` / `filmo-plan` / `filmo-produce` Hermes skills the conduct ran, plus its `.env.example` |
| `nemoclaw/` | the `filmo` sandbox: `Dockerfile`, `sandboxes.json`, `onboard-session.json`, `openshell-gateway.json`, `policies/*.yaml` (the per-job egress allowlist), the egress-firewall + capability-hardening scripts |
| `systemd/` | the VM's units: `filmo-claimer.service` (+ `.d/` drop-ins), `mcp-toolserver.service`, `gateway-watchdog.service` + `.timer`, `filmo-egress-firewall.service` |
| `worker/` | the VM-only host scripts those units invoked: `start-mcp-toolserver.sh`, `prewarm-gateway.sh`, `gateway-watchdog.sh` |

> These files reference VM host paths (`/root/filmo-worker`, `/root/filmo-pipeline`,
> `/root/filmo-venv`) and secret `EnvironmentFile`s that no longer exist. Do not run them.
