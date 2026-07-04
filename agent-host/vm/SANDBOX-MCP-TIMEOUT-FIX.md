# Sandbox MCP timeout fix (2026-07-04) — duplicate-produce root cause

## Symptom
Heavy sites (stripe.com, insforge.dev) produced the video TWICE (2x render + 2x
ElevenLabs COGS), the agent never echoed the `Shipped:` line, the conduct burned
its full 1200s budget, and delivery came ~15-20 min late via the claimer's
recovery net (`recoverShippedVideo`). apple.com (produce 184.9s) was always
clean. Evidence: `/root/mcp-toolserver.log` shows overlapping
`TOOL CALL produce_and_ship` pairs ~300s apart (`ok=True 421.2s` + `586.4s` for
run 2c877c63); run_events shows two full capture->render->upload passes.

## Root cause — a two-layer 300s client-side cut
`produce_and_ship` takes 400-600s on heavy sites. TWO independent client-side
timeouts in the sandbox Hermes agent both default to 300s and kill the call
mid-work; Nemotron then sees a "failed" tool call and retries (the skill says
"call EXACTLY ONCE" — but a timed-out call looks like it never happened):

1. **Per-server tool timeout** — `tools/mcp_tool.py`:
   `config.get("timeout", _DEFAULT_TOOL_TIMEOUT)` with default 300. The
   `filmo-host` entry in `/sandbox/.hermes/config.yaml` had no `timeout` key.
2. **Transport read timeout** — hardcoded `httpx.Timeout(..., read=300.0)` in
   the streamable-HTTP client construction (2 occurrences: main path + factory
   fallback). A produce that streams nothing for 5 min dies at the transport
   even if (1) is raised.

## Fix (LIVE since 2026-07-04 ~15:32 UTC, zero downtime)
Each conduct spawns a fresh `hermes chat` process that re-reads both files, so
no restart was needed.

- `/sandbox/.hermes/config.yaml` (in container `openshell-filmo-*`):
  ```yaml
  filmo-host:
    url: http://host.openshell.internal:8770/mcp
    timeout: 900        # <- added
    enabled: true
  ```
- `/sandbox/hermes-venv/lib/python3.13/site-packages/tools/mcp_tool.py`:
  both `read=300.0` -> `read=900.0` (py_compile verified).
- Backups in place: `config.yaml.bak-20260704`, `mcp_tool.py.bak-20260704`.

Why 900: worst observed single produce = 586s; 900 clears it with margin while
staying inside the 1200s conduct budget, and the recovery net remains as the
backstop for anything longer.

## After a sandbox REBUILD
The container filesystem is the only place these live. Rerun:
```bash
/root/filmo-sandbox/apply-mcp-timeout-fix.sh
```
(idempotent; sits next to apply-egress-firewall.sh).

## Deliberately NOT deployed yet (proposed hardening)
- **Idempotency / in-flight guard in `produce_and_ship`** (host
  mcp_toolserver.py): per-run_id lock — a duplicate call while one is in flight
  should await and return the first call's result instead of starting a second
  full production; an already-shipped run should return its cached final_url
  instantly. Defense-in-depth against ANY future retry source. Needs a guarded
  mcp-toolserver restart + verification on a real run before going live.
- **Claimer fast-path delivery**: finalize the run as soon as the video object
  lands in storage (the "Video uploaded" event) instead of waiting for the
  conduct to end — would have delivered the stripe run at ~96s post-payment.
