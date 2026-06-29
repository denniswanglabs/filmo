# Filmo — Deploy & Infrastructure (the live system)

Filmo is an AI Product Launch Producer for the **Hermes × NVIDIA × Stripe**
hackathon: a URL goes in, and a launch video comes out — Conversion Read → plan →
price → pay → produce → ship. This document is the reproducible snapshot of the
**currently live** system. The app code is in this repo and matches the running
VM; `deploy/` is the infra that makes it RUN.

- **Hermes = the AI harness** (the agent runtime that conducts the pipeline).
- **NVIDIA Nemotron = the brain** (every LLM/reasoning call — Conversion Read and
  planning — on `nvidia/nemotron-3-ultra-550b-a55b`, the 550B flagship).
- **Stripe = payments** (a TEST-mode pre-produce checkout gate).

## Live components

| Component | Where it runs | What it is |
|---|---|---|
| **Web** (Next.js) | **Vercel** → `https://filmostudio.vercel.app` | the site: submit a URL, watch the live agent feed, edit + download the video |
| **InsForge** | hosted Postgres + storage `https://jd3mdkqr.ap-southeast.insforge.app` | the shared backend: `runs` / `jobs` / `run_events` / `developers` tables + the public **`walk-videos`** bucket |
| **Worker** (`filmo-claimer`) | **Hetzner VM** `REDACTED-VM-HOST` (`ubuntu-8gb-hel1-1`) | polls InsForge `jobs`, conducts the produce step, uploads the MP4, marks the run delivered |
| **Host MCP tool-server** | same Hetzner VM, `:8770` | the 5 sanctioned tools (`conversion_read`, `plan`, `price`, `gate`, `produce_and_ship`) the agent conducts |
| **NemoClaw sandbox** (`filmo`) | Docker on the same VM | NVIDIA's containment; runs the Hermes agent on Nemotron, behind a per-job egress allowlist |

> Historical note: an earlier worker ran on Railway (service `walk-studio-hosted`,
> deploy branch `hosted-saas`). The **current** produce worker is the Hetzner
> `filmo-claimer`; that is what this document and `deploy/` describe.

## How a job flows: URL → video

```
  Browser (Vercel)                 InsForge (Postgres + storage)            Hetzner VM
 ─────────────────                ───────────────────────────────        ─────────────────────────────
  submit URL  ───────────────────►  insert runs + jobs(queued)
                                          ▲                                 filmo-claimer polls jobs
  live feed  ◄──── run_events ◄──────────┼──────────────────────────────   claim_next_job (atomic)
                                          │                                    │ CLAIMER_MODE=hermes
                                          │                                    ▼
                                          │                       nemoclaw filmo exec → hermes -s filmo-producer
                                          │                                    │ conducts 5 MCP tools on :8770
                                          │                                    ▼
                                          │            conversion_read → plan → price → gate → produce_and_ship
                                          │            (Nemotron read+plan · Playwright capture · Remotion render)
  download  ◄──── runs.final_url ◄────────┴──────────── upload MP4 → walk-videos/<run_key>/final.mp4
```

1. The site (or a direct insert) creates a `runs` row + a `queued` `jobs` row.
2. `filmo-claimer` on the VM claims the oldest job (`claim_next_job`, atomic).
3. In `CLAIMER_MODE=hermes`, the claimer runs the Hermes agent **inside the
   `filmo` NemoClaw sandbox** (`nemoclaw filmo exec … hermes chat -s
   filmo-producer`). The agent is a strict **conductor**: it calls the 5
   `filmo-host` MCP tools once each, in order, passing a `plan_id` handle (not the
   full plan) between them, and threading the `run_id` into every call so each
   step emits a `run_events` row (the live "watch the agent work" feed).
4. The tools do the real work on the **host** (Nemotron Conversion Read + plan,
   Playwright screenshot capture, Remotion render). `produce_and_ship` uploads the
   finished video to the `walk-videos` bucket and returns `final_url`.
5. The claimer parses `Shipped: <final_url>`, stamps `runs.final_url` +
   `props.producer=hetzner-hermes`, and marks the job done. On any conduct
   failure/timeout it **falls back** to the deterministic `build_runner`
   (`producer=hetzner-curated`) so a render never fails.
6. The site shows the delivered video; the editor re-renders edits to `edited_url`.

For a `pay_mode=human` job with `PAYMENTS_REQUIRED=true`, the claimer first opens a
real Stripe **TEST** checkout (`gate.py`, card `4242…`) and waits for payment
before conducting. `gate.py` refuses any live/missing key.

## Sandbox isolation + egress (security posture)

The agent runs in NVIDIA's NemoClaw sandbox behind **two** egress layers:

1. **OpenShell L7 allowlist** — the sandbox can only reach the hosts named in its
   policy presets (OpenRouter + NVIDIA for inference, the host `:8770` tool-server,
   Stripe, and — rewritten **per job** — the one SSRF-vetted customer URL).
2. **uid-998 host firewall** — an iptables rule (applied host-side via `nsenter`)
   drops any raw socket the agent (uid 998) opens itself, so a hijacked agent
   cannot exfiltrate or pivot; it can only use the cooperating L7 path.

Plus capability hardening (`no-new-privileges`, dropped ptrace/syslog). Full
detail in `deploy/nemoclaw/README.md`.

## `deploy/` map

| Path | Captures |
|---|---|
| `deploy/systemd/` | the VM's systemd units: `filmo-claimer.service` (+ `.d/` drop-ins: home, prewarm, payments, hermes-mode), `mcp-toolserver.service`, `gateway-watchdog.service` + `.timer`, `filmo-egress-firewall.service` |
| `deploy/nemoclaw/` | the `filmo` sandbox: `Dockerfile`, `sandboxes.json`, `onboard-session.json`, `openshell-gateway.json`, `policies/*.yaml` (the egress allowlist), the egress-firewall + hardening scripts, and a `README.md` |
| `deploy/hermes/` | the `filmo-producer` Hermes skill (`SKILL.md`) the conduct runs + a `README.md` |
| `deploy/insforge/schema.md` | the DB schema (`runs`/`jobs`/`run_events`/`developers`) + the `walk-videos` bucket |
| `deploy/worker/` | host scripts the units reference (`start-mcp-toolserver.sh`, `prewarm-gateway.sh`, `gateway-watchdog.sh`, `gate.py`) + `.env.example` |
| `deploy/*/.env.example` | every env the system needs — names + placeholders, no real values |

## Deploy steps (brief)

**Web (Vercel):**
```
cd web && vercel --prod --yes
vercel alias set <new-deploy-url> filmostudio.vercel.app   # apex alias does NOT auto-follow
```
Env: `web/.env.local` (see `deploy/web/.env.example`).

**Worker (Hetzner VM):** the units are installed under `/etc/systemd/system/` and
reference host paths (`/root/filmo-worker`, `/root/filmo-pipeline`,
`/root/filmo-venv`) and secret `EnvironmentFile`s (`/root/.insforge-key`,
`/root/.orkey`, `/root/.el-key`, mode 600). To (re)install from this snapshot:
```
# copy the units + drop-ins
cp deploy/systemd/*.service deploy/systemd/*.timer        /etc/systemd/system/
cp -r deploy/systemd/filmo-claimer.service.d             /etc/systemd/system/
# copy the host scripts (chmod +x) and the sandbox/nemoclaw config
cp deploy/worker/*.sh deploy/worker/gate.py              /root/filmo-worker/   # (start-mcp-toolserver.sh -> /root/)
cp deploy/nemoclaw/policies/*.yaml deploy/nemoclaw/*.sh  /root/filmo-sandbox/
# create the secret KEY=VALUE files (mode 600) from deploy/worker/.env.example
systemctl daemon-reload
systemctl enable --now filmo-claimer mcp-toolserver gateway-watchdog.timer filmo-egress-firewall
```
The NemoClaw sandbox is built from `deploy/nemoclaw/Dockerfile` and onboarded with
the `filmo` policies (`nemoclaw … policy-add`), per `deploy/nemoclaw/README.md`.

**Backend (InsForge):** the `runs`/`jobs`/`run_events`/`developers` tables and the
public `walk-videos` bucket already exist on the shared project; schema in
`deploy/insforge/schema.md`. Do NOT rename the bucket (`walk-videos`) — renaming
breaks the live deploy.
