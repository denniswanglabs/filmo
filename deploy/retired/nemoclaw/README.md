# NemoClaw sandbox — isolation + per-job egress model

This directory captures the `filmo` NemoClaw sandbox: the definition, its egress
policies, and the host-side firewall/hardening scripts. The sandbox is where the
Hermes agent runs **inside NVIDIA's NemoClaw containment**, on NVIDIA Nemotron.

## What the sandbox is for

The host worker (`filmo-claimer`) drives the produce step by running the Hermes
agent **inside the `filmo` sandbox**:

```
nemoclaw filmo exec -- bash -c '... hermes chat -Q -s filmo-producer -q "<prompt>" ...'
```

The agent only **conducts** — it calls the 5 `filmo-host` MCP tools
(conversion_read → plan → price → gate → produce_and_ship) on the host
tool-server. The heavy, trusted work (Nemotron read+plan, Playwright capture,
Remotion render, InsForge upload) stays on the HOST, never inside the sandbox.

## Files

| File | What it is |
|---|---|
| `Dockerfile` | sandbox image: NemoClaw base + a venv with `hermes-agent[cli]` |
| `sandboxes.json` | the `filmo` sandbox definition (`/root/.nemoclaw/sandboxes.json`, scrubbed) |
| `onboard-session.json` | onboarding state (`/root/.nemoclaw/`, scrubbed — already carried no secrets) |
| `openshell-gateway.json` | OpenShell L7 gateway config (`~/.config/openshell/`) |
| `policies/*.yaml` | the per-sandbox egress allowlist presets |
| `apply-egress-firewall.sh` | host nsenter iptables: drop raw agent (uid 998) egress |
| `harden-caps.sh` | drop container caps + no-new-privileges (faithful commit+recreate) |
| `RESTORE-hardening.sh` | one-command rollback of both hardening steps |

## Two-layer egress containment

**Layer 1 — OpenShell L7 allowlist (the cooperating path).** The sandbox can
reach only the hosts named in its policy presets, mediated by the OpenShell L7
gateway on `127.0.0.1:8080`:

- `hermes-inference` → `openrouter.ai`, `integrate.api.nvidia.com` (the LLM brain)
- `filmo-host` → `host.openshell.internal:8770` (the 5 MCP tools)
- `filmo-targets` → the Stripe hosts (checkout)
- `filmo-dynamic` → **rewritten per job** to the single SSRF-vetted customer URL.
  The host worker overwrites `filmo-dynamic.yaml` with the approved host and runs
  `nemoclaw filmo policy-add filmo-dynamic --from-file … --yes` before the conduct,
  so the sandbox can only reach the one site the current build was approved for.
- plus the package presets `npm` / `pypi` / `huggingface` / `brew`.

**Layer 2 — uid-998 host firewall (the hijack guard).** All legitimate egress is
made by the supervisor PID1 as root (uid 0). The Hermes agent runs as the
unprivileged `sandbox` user (uid 998). `apply-egress-firewall.sh` installs an
iptables `OUTPUT` rule (host-side, via `nsenter` into the container netns) that
routes only uid-998 traffic into a restrictive chain allowing **only** loopback,
DNS, and the L7 gateway — everything else (raw internet, host:22 pivot, direct
host:8770, C2) is dropped + logged. A hijacked agent therefore cannot open its
own socket to an arbitrary host; it can only use the cooperating, allowlisted L7
path. Driven by `filmo-egress-firewall.service`, which re-applies on every
container start (the rule is netns-scoped, so it must be re-applied after any
`nemoclaw recover` / restart).

**Capability hardening.** `harden-caps.sh` recreates the container with
`--security-opt no-new-privileges` (blocking setuid escalation) while preserving
the `SYS_ADMIN`/`NET_ADMIN` the OpenShell supervisor genuinely needs to build the
agent's inner netns + relay. The old container is renamed `-prehardened` for
instant rollback via `RESTORE-hardening.sh`.

## No secrets in the sandbox onboarding

The sandbox never stores LLM keys — `credentialEnv`, `hermesAuthMethod`, and
`routerCredentialHash` are all `null`. The OpenRouter/NVIDIA keys live in the
host MCP tool-server's process env (sourced from `/root/.orkey` etc. by
`start-mcp-toolserver.sh`); the sandbox reaches inference only through the
allowlisted `hermes-inference` egress policy.
