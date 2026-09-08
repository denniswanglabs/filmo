# Hermes skill — `filmo-producer`

`filmo-producer/SKILL.md` is the Hermes skill the conduct runs. It turns the
Hermes agent into a strict **conductor** of the 5 `filmo-host` MCP tools — it
never generates the plan or the video itself; the host tool-server does.

## How it's invoked

The host worker (`filmo-claimer`, in `CLAIMER_MODE=hermes`) runs the agent
inside the `filmo` NemoClaw sandbox:

```
nemoclaw filmo exec -- bash -c '
  export HOME=/sandbox
  set -a; . /sandbox/.orkey; set +a       # OpenRouter key (sandbox-local, gitignored)
  hermes chat -Q -s filmo-producer -q "<single-line conduct prompt>" 2>&1 | tail -60
'
```

The worker passes the entire inner script as a single base64 argv token to avoid
nested-quote mangling across the node→nemoclaw→openshell→bash layers, and wipes
the agent's mutable state (`/sandbox/.hermes/{sessions,memories,state.db,…}`)
before each conduct so one job cannot contaminate the next. It then parses the
agent's final `Shipped: <final_url> (N scenes).` line and marks the run delivered
with `producer=hetzner-hermes`. On any conduct failure/timeout it falls back to
the deterministic `build_runner` (`producer=hetzner-curated`), so a render never
fails.

## The five tools the skill conducts

Exposed by the host MCP tool-server (`mcp_toolserver.py` on `:8770`), each wraps
one real curated pipeline step:

| Tool | Wraps |
|---|---|
| `conversion_read` | `url_guard` + `build_runner` conversion read + brand facts (Nemotron) |
| `plan` | `plan_job.plan_job(...)` → caches the full plan, returns a `plan_id` handle |
| `price` | `producer.cmd_estimate(plan)` (cost-plus menu, capped at $10) |
| `gate` | pure logic: proceed iff `price_cents <= budget_cents` (always proceeds at the cap) |
| `produce_and_ship` | capture + `style_fill.run_pipeline(do_render=True)` → upload to `walk-videos` → `final_url` |

## Env the agent needs in the sandbox

See `deploy/.env.example` → `~/.hermes/.env` (the OpenRouter / NVIDIA / ElevenLabs
keys). On the live VM the OpenRouter key reaches the sandbox as `/sandbox/.orkey`
(a `KEY=VALUE` file, mode 600, never committed).
