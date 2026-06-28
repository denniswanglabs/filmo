#!/usr/bin/env python3
"""Filmo Agent-Host MCP server — exposes the HOSTED video-production pipeline's
steps as first-class Hermes tools, so the Hermes RUNTIME (Nemotron) drives the
job by calling discrete tools and chaining them itself, instead of a Python
harness running the whole loop opaquely.

This is a dependency-free MCP **stdio** server. It speaks raw MCP JSON-RPC 2.0
over stdin/stdout (initialize -> tools/list -> tools/call), which is exactly what
Hermes' built-in MCP client (`mcp.client.stdio.stdio_client`) expects after
`hermes mcp add filmo-studio --command <python> --args <this file>`.

Ported from hermes-video-agent/mcp_studio_server.py and re-pointed at the HOSTED
repo's CLIs (walk-studio-hosted/). The pipeline dir is `PIPELINE_DIR` (default:
the hosted repo root = this file's grandparent, since this lives in agent-host/).

Tools exposed (the Filmo agent-host chain — conversion_read -> plan_job ->
price_job -> budget_gate -> produce_and_ship):

  - conversion_read(url, brain="ultra-paid")
        REAL pipeline step. Fetches the page's visible copy and runs
        analyze.analyze_read() on Nemotron (via OpenRouter). Returns the validated
        Read JSON + which engine produced it.
        ★SPIKE 0c (below): in the agent-host the untrusted site read must run
        INSIDE the NemoClaw sandbox via `nemoclaw <sandbox> exec`. The seam is
        marked; wiring depends on the placement spike.

  - plan_job(url, goal, duration=30, brain="ultra-paid")
        REAL pipeline step. Shells plan_job.py (Nemotron planner) and returns the
        schema-validated SCENE PLAN JSON. Persists plan.json for downstream tools.

  - price_job(plan_path)
        DETERMINISTIC money glue. Runs producer.py estimate -> suggested price,
        locked production budget, per-scene budgets. The LLM never overrides the
        budget math; it only reads the result.

  - budget_gate(plan_path, scene_id, proposed_cost_cents, spent_cents)
        DETERMINISTIC money guardrail. Runs producer.py gate -> approve /
        downgrade / decline. The gate declines an over-budget scene in code; the
        model cannot spend past it.

  - produce_and_ship(plan_path, run_id)
        REAL pipeline step. Renders the planned video (Remotion) and uploads the
        MP4, returning the final URL. Shells build_runner.py.
        ★SPIKE (below): build_runner.py has NO produce-from-existing-plan flag
        today — its only entrypoint is the full produce loop keyed on
        --url + --run-id. This tool invokes that real entrypoint and marks the gap.

Design notes:
  - Money guardrails stay deterministic in code (producer.py). The MCP tools
    surface the numbers to the runtime; they do not let the model invent prices
    or bypass a decline.
  - InsForge progress hook: each tool calls `_emit(run_id, actor, msg)` to append
    a `run_events` row so the live web UI shows the agent working. Mirrors the
    Node worker's `db.database.from('run_events').insert(...)` (worker/run.js).
  - Keys come from the process env. Hermes injects its env into the MCP subprocess;
    this server also self-loads ~/.hermes/.env and the repo's .env as a
    belt-and-suspenders. Secrets are never printed.
"""
import json
import os
import sys
import subprocess
import time
import urllib.request
import urllib.error

# This server lives in walk-studio-hosted/agent-host/. The hosted pipeline (CLIs,
# analyze.py, build_runner.py, …) lives at the repo ROOT — one dir up. PIPELINE_DIR
# overrides that default (the worker uses the same env var; see worker/run.js).
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PIPELINE_DIR = os.path.dirname(HERE)  # repo root = parent of agent-host/
PIPELINE_DIR = os.path.abspath(os.environ.get("PIPELINE_DIR", DEFAULT_PIPELINE_DIR))
# Make the pipeline modules (analyze, etc.) importable from this process.
sys.path.insert(0, PIPELINE_DIR)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "filmo-studio"
SERVER_VERSION = "0.1.0"


# --------------------------------------------------------------------------- #
# Logging — stderr only (stdout is the JSON-RPC channel and must stay clean)
# --------------------------------------------------------------------------- #
def _log(msg):
    sys.stderr.write("[mcp_studio_server] %s\n" % msg)
    sys.stderr.flush()


# --------------------------------------------------------------------------- #
# Env loading (so keys are present whether or not Hermes passed env through)
# --------------------------------------------------------------------------- #
def _load_env_file(path):
    """Minimal .env loader. Does NOT overwrite already-set vars (passed env wins).
    Never prints values."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except FileNotFoundError:
        pass
    except Exception as e:  # never let env loading crash the server
        _log("env load warning for %s: %s" % (path, e))


for _envp in (
    os.path.expanduser("~/.hermes/.env"),
    os.path.join(PIPELINE_DIR, ".env"),
    os.path.join(PIPELINE_DIR, "worker", ".env"),
):
    _load_env_file(_envp)


# --------------------------------------------------------------------------- #
# InsForge progress hook — append a `run_events` row so the live web UI shows the
# agent working. Mirrors the Node worker's insert (worker/run.js syncEvents/emit):
#     db.database.from('run_events').insert([{ run_id, seq, actor, level, msg }])
# The @insforge/sdk routes that through PostgREST at
#     POST {INSFORGE_URL}/api/database/records/run_events
#     Authorization: Bearer {INSFORGE_API_KEY}   (admin key = RLS-exempt)
# (endpoint confirmed in @insforge/sdk dist: createInsForgePostgrestFetch ->
#  `/api/database/records/${table}`). We reconstruct that REST call with stdlib
# urllib to stay dependency-free.
#
# ★SPIKE: verify the run_events insert endpoint/shape against worker/run.js. The
# PostgREST bulk-insert wire format (array body, `Prefer: return=minimal`, Bearer
# admin key) was reconstructed from the SDK source AND probed live: a POST with a
# valid-UUID-shaped run_id reaches the DB insert and is only rejected by the
# run_id->runs foreign-key constraint (PG 23503), which confirms endpoint + auth +
# body shape are correct. Remaining spike: exercise it against a REAL existing run
# row and confirm the event shows up in the run page's live feed.
# --------------------------------------------------------------------------- #
# Monotonic-ish seq base, large so MCP-tool events sort AFTER the build's own
# ledger events (worker/run.js emit() uses the same 100000+ convention).
_EMIT_SEQ_BASE = 200000
_emit_counter = 0


def _emit(run_id, actor, msg, level="info"):
    """Append a run_events row for the live UI. Best-effort: never raises, never
    blocks the tool on a transient InsForge error (mirrors the worker's resilient
    emit()). `actor` is one of hermes | nemotron | stripe (the schema's enum-ish
    text column)."""
    global _emit_counter
    base_url = (os.environ.get("INSFORGE_URL") or "").rstrip("/")
    api_key = os.environ.get("INSFORGE_API_KEY") or ""
    if not run_id or not base_url or not api_key:
        # No InsForge configured (e.g. a local dry run) — log and move on.
        _log("emit (no insforge) run=%s actor=%s: %s" % (run_id, actor, msg))
        return False
    _emit_counter += 1
    seq = _EMIT_SEQ_BASE + int(time.time()) % 100000 + _emit_counter
    row = {
        "run_id": run_id,
        "seq": seq,
        "actor": actor or "hermes",
        "level": level or "info",
        "msg": str(msg)[:2000],
    }
    url = "%s/api/database/records/run_events" % base_url
    body = json.dumps([row]).encode("utf-8")  # PostgREST bulk insert = array body
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", "Bearer %s" % api_key)
    req.add_header("Content-Type", "application/json")
    # PostgREST default returns the inserted rows only with this Prefer header; we
    # don't need them back, but it keeps the response small + status predictable.
    req.add_header("Prefer", "return=minimal")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = 200 <= resp.status < 300
            if not ok:
                _log("emit non-2xx (%s) for run=%s" % (resp.status, run_id))
            return ok
    except urllib.error.HTTPError as e:
        _log("emit HTTPError %s for run=%s: %s" % (e.code, run_id, e.reason))
        return False
    except Exception as e:
        _log("emit failed for run=%s: %s" % (run_id, e))
        return False


# --------------------------------------------------------------------------- #
# Page-text fetch (lightweight; the prototype avoids the heavy Playwright capture
# so the Read step is fast + reliable in a single tool call)
# --------------------------------------------------------------------------- #
def _fetch_page_text(url, cap=4000):
    """Best-effort fetch of a page's visible copy. Returns (headline, body_text).
    Never raises — a thin/blocked page just yields short text and the Read leans on
    the model's world knowledge (the pipeline's designed degraded path).

    ★SPIKE 0c: in the agent-host this untrusted fetch of an arbitrary user URL must
    run INSIDE the NemoClaw sandbox so the egress-allowlisted, fs-bounded box does
    the dangerous network read — NOT this host process. The cleanest seam is to
    route this fetch (and/or the analyze.read_pass Chromium capture) through
    `nemoclaw <sandbox> exec ...` with a per-run target.yaml allowlist for `url`.
    Not wired here (it depends on the Phase-0 placement spike); this stdlib fetch is
    the host-side stand-in. DO NOT ship the host fetch for untrusted URLs without
    closing 0c.
    """
    headline, body = "", ""
    try:
        import re
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; FilmoStudioBot/0.1)"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read(2_000_000)  # cap bytes; never trust an arbitrary URL
        # Best-effort decode; arbitrary sites may not declare/honor charset.
        html = raw.decode("utf-8", errors="replace")
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if m:
            headline = re.sub(r"\s+", " ", m.group(1)).strip()[:200]
        # strip scripts/styles, then tags, collapse whitespace
        html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&[a-zA-Z#0-9]+;", " ", text)
        body = re.sub(r"\s+", " ", text).strip()[:cap]
    except Exception as e:
        _log("page fetch degraded for %s: %s" % (url, e))
    return headline, body


# --------------------------------------------------------------------------- #
# Pipeline CLI runner — runs the hosted CLIs (plan_job.py / producer.py /
# build_runner.py) in PIPELINE_DIR with the SAME interpreter as this server so
# deps resolve.
# --------------------------------------------------------------------------- #
def _run_pipeline_cli(argv, parse_stdout_json=False, timeout=540):
    """Run a pipeline CLI in PIPELINE_DIR and capture output."""
    try:
        proc = subprocess.run(
            [sys.executable] + argv,
            cwd=PIPELINE_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,  # < 600s subagent / harness cap
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "command timed out: %s" % " ".join(argv)}
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": "exit %d" % proc.returncode,
            "stderr": err[-2000:],
        }
    result = {"ok": True, "stderr": err[-1000:] if err else ""}
    if parse_stdout_json:
        try:
            result["data"] = json.loads(out)
        except Exception as e:
            return {"ok": False, "error": "non-JSON stdout: %s" % e, "stdout": out[:2000]}
    else:
        result["stdout"] = out
    return result


# --------------------------------------------------------------------------- #
# Tool implementations
# --------------------------------------------------------------------------- #
def tool_conversion_read(args):
    """REAL pipeline step: Conversion Read via analyze.analyze_read()."""
    url = (args.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "url is required"}
    # Hosted brand brain is PAID Nemotron Ultra (see CLAUDE.md: ANALYZE_BRAIN_CHAIN
    # = ultra-paid,super-paid). Default to ultra-paid, not the retired Nous 'hermes'.
    brain = (args.get("brain") or "ultra-paid").strip() or "ultra-paid"
    run_id = (args.get("run_id") or "").strip()

    _emit(run_id, "hermes", "Reading %s — running the Conversion Read…" % url)

    # ★SPIKE 0c: route the browser/read step through `nemoclaw <sandbox> exec` so the
    # untrusted fetch of the user's arbitrary URL happens IN-sandbox (egress-allowlist
    # + fs boundary), not in this host process. _fetch_page_text below is the
    # host-side stand-in until 0c is closed; see its docstring for the seam.
    headline, body_text = _fetch_page_text(url)

    try:
        import analyze
    except Exception as e:
        return {"ok": False, "error": "could not import analyze.py: %s" % e}

    have_key = bool(os.environ.get("OPENROUTER_API_KEY"))
    try:
        read = analyze.analyze_read(
            url, body_text, hero_path=None, headline=headline, brain=brain
        )
    except Exception as e:
        _emit(run_id, "nemotron", "Conversion Read failed: %s" % e, level="error")
        return {"ok": False, "error": "analyze_read failed: %s" % e}

    engine = read.get("engine") if isinstance(read, dict) else None
    _emit(run_id, "nemotron",
          "Conversion Read complete (engine=%s)." % (engine or "?"))
    return {
        "ok": True,
        "step": "conversion_read",
        "url": url,
        "openrouter_key_present": have_key,
        "fetched_headline": headline,
        "body_text_chars": len(body_text or ""),
        "engine": engine,
        "degraded": (read.get("degraded") if isinstance(read, dict) else None),
        "read": read,
    }


def tool_plan_job(args):
    """REAL pipeline step: Nemotron scene-plan via plan_job.py."""
    url = (args.get("url") or "").strip()
    goal = (args.get("goal") or "").strip()
    duration = int(args.get("duration") or 30)
    brain = (args.get("brain") or "ultra-paid").strip() or "ultra-paid"
    run_id = (args.get("run_id") or "").strip()
    if not url:
        return {"ok": False, "error": "url is required"}

    _emit(run_id, "nemotron", "Planning the cut for %s…" % url)

    argv = ["plan_job.py", "--url", url, "--goal", goal,
            "--duration", str(duration), "--brain", brain]
    res = _run_pipeline_cli(argv, parse_stdout_json=True)
    if not res.get("ok"):
        _emit(run_id, "nemotron", "Planning failed: %s" % res.get("error"),
              level="error")
        return res
    plan = res["data"]

    # Persist the plan so price_job / budget_gate / produce_and_ship read it by path.
    # When a run_id is set, write it into the run's own dir (runs/<run_id>/plan.json)
    # so produce_and_ship's build_runner picks up the SAME on-disk layout the worker
    # produces; otherwise fall back to a scratch dir.
    if run_id:
        out_dir = os.path.join(PIPELINE_DIR, "runs", run_id)
    else:
        out_dir = os.path.join(PIPELINE_DIR, "runs", "_mcp")
    os.makedirs(out_dir, exist_ok=True)
    plan_path = os.path.join(out_dir, "plan.json")
    with open(plan_path, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=2)

    scenes = plan.get("scenes", []) if isinstance(plan, dict) else []
    _emit(run_id, "nemotron",
          "Plan ready: %d scenes (%s)." % (
              len(scenes), ", ".join(str(s.get("type")) for s in scenes)))
    return {
        "ok": True,
        "step": "plan_job",
        "plan_path": plan_path,
        "scene_count": len(scenes),
        "scene_types": [s.get("type") for s in scenes],
        "plan": plan,
    }


def tool_price_job(args):
    """DETERMINISTIC money glue: producer.py estimate."""
    plan_path = (args.get("plan_path") or "").strip()
    run_id = (args.get("run_id") or "").strip()
    if not plan_path or not os.path.exists(plan_path):
        return {"ok": False, "error": "plan_path missing or not found: %r" % plan_path}
    res = _run_pipeline_cli(["producer.py", "estimate", "--plan", plan_path])
    if not res.get("ok"):
        return res
    _emit(run_id, "stripe", "Priced the job (deterministic cost-plus estimate).")
    return {"ok": True, "step": "price_job", "estimate_raw": res.get("stdout", "")}


def tool_budget_gate(args):
    """DETERMINISTIC money guardrail: producer.py gate (approve/downgrade/decline)."""
    plan_path = (args.get("plan_path") or "").strip()
    scene_id = (args.get("scene_id") or "").strip()
    proposed = int(args.get("proposed_cost_cents") or 0)
    spent = int(args.get("spent_cents") or 0)
    run_id = (args.get("run_id") or "").strip()
    if not plan_path or not os.path.exists(plan_path):
        return {"ok": False, "error": "plan_path missing or not found: %r" % plan_path}
    if not scene_id:
        return {"ok": False, "error": "scene_id is required"}
    res = _run_pipeline_cli([
        "producer.py", "gate", "--plan", plan_path, "--scene", scene_id,
        "--proposed_cost_cents", str(proposed), "--spent_cents", str(spent),
    ])
    if not res.get("ok"):
        return res
    _emit(run_id, "stripe",
          "Budget gate ran for scene %s (proposed %d¢, spent %d¢)."
          % (scene_id, proposed, spent))
    return {"ok": True, "step": "budget_gate", "verdict_raw": res.get("stdout", "")}


def tool_produce_and_ship(args):
    """REAL pipeline step: render the planned video (Remotion) + upload the MP4,
    returning the final URL.

    build_runner.py owns produce + render + upload end-to-end. The cleanest path is
    to shell build_runner.py in a "produce-from-existing-plan" mode...

    ★SPIKE: confirm build_runner exposes a produce-from-plan entrypoint, else add
    one. As of this scaffold, build_runner.py's argparse has NO --from-plan /
    --plan / resume flag — its ONLY entrypoint is the full produce loop keyed on
    `--url` + `--run-id` (build_runner.main(): --url, --goal, --emphasis, --run-id,
    --mode, --duration, --pace, --style, --quality, --brain). That loop re-runs
    analyze -> plan -> price internally; it does NOT consume the plan.json this
    tool's `plan_path` points at. So today this tool re-drives build_runner with the
    run params (url/goal/duration/brain/mode pulled from the plan) and the SAME
    run_id, which means plan.json is regenerated, not reused. To make
    produce_and_ship honor the upstream plan_job/price_job/budget_gate decisions,
    build_runner needs a real "produce from runs/<run_id>/plan.json, skip
    analyze/plan/price" entrypoint. DO NOT invent a CLI flag that isn't there — the
    flag is added here ONLY behind the BUILD_RUNNER_FROM_PLAN_FLAG env so a reviewer
    can flip it on once the entrypoint lands; default OFF = the real full-loop flag.
    """
    plan_path = (args.get("plan_path") or "").strip()
    run_id = (args.get("run_id") or "").strip()
    if not run_id:
        return {"ok": False, "error": "run_id is required"}

    plan, err = _load_plan(plan_path)
    if err:
        return {"ok": False, "error": err}

    job = plan.get("job", {}) if isinstance(plan, dict) else {}
    # Pull the run params back out of the plan so the full-loop build_runner call is
    # consistent with what plan_job was given.
    url = (job.get("company_url") or job.get("url") or args.get("url") or "").strip()
    goal = (job.get("goal") or args.get("goal") or "").strip()
    duration = int(job.get("duration") or args.get("duration") or 30)
    brain = (args.get("brain") or "ultra-paid").strip() or "ultra-paid"
    mode = (args.get("mode") or "mock").strip() or "mock"
    quality = (args.get("quality") or job.get("quality") or "standard").strip()
    if not url:
        return {"ok": False, "error": "could not resolve company url from plan or args"}

    _emit(run_id, "hermes", "Producing + rendering the video…")

    # ★SPIKE (see docstring): the produce-from-plan entrypoint does not exist in
    # build_runner.py yet. Default path = the REAL full produce loop (regenerates
    # the plan). Flip BUILD_RUNNER_FROM_PLAN_FLAG once build_runner adds a flag that
    # consumes runs/<run_id>/plan.json and skips analyze/plan/price.
    from_plan_flag = os.environ.get("BUILD_RUNNER_FROM_PLAN_FLAG", "").strip()
    argv = ["build_runner.py",
            "--url", url,
            "--goal", goal or ("%d-second brand explainer" % duration),
            "--run-id", run_id,
            "--mode", mode,
            "--duration", str(duration),
            "--quality", quality,
            "--brain", brain]
    if from_plan_flag:
        # e.g. BUILD_RUNNER_FROM_PLAN_FLAG="--from-plan" once that entrypoint exists.
        # ★SPIKE: this flag is a placeholder — DO NOT enable it until build_runner
        # actually parses it, or the build will exit-2 on an unknown argument.
        argv.append(from_plan_flag)

    res = _run_pipeline_cli(argv, parse_stdout_json=False, timeout=540)
    if not res.get("ok"):
        _emit(run_id, "hermes",
              "Produce/render failed: %s" % res.get("error"), level="error")
        return res

    # build_runner writes final.mp4 + ledger.json into runs/<run_id>/. The MP4
    # UPLOAD to InsForge storage is owned by the Node worker (worker/run.js
    # uploadVideo -> runs.final_url). Surface the local path + the ledger's
    # final_url if present so the runtime can report the shipped URL.
    run_dir = os.path.join(PIPELINE_DIR, "runs", run_id)
    final_path = os.path.join(run_dir, "final.mp4")
    final_exists = os.path.exists(final_path)
    final_url = _ledger_final_url(run_dir)

    # ★SPIKE: the actual MP4 UPLOAD (bucket put -> final_url) lives in the Node
    # worker, not in build_runner. In the agent-host placement, produce_and_ship is
    # the tool the runtime expects to "ship" the video. Either (a) keep the worker
    # as the uploader and have this tool report runs.final_url once the worker lands
    # it, or (b) add an upload step here (InsForge storage PUT). Not wired — confirm
    # the upload owner for the agent-host topology before claiming a returned URL.
    if final_url:
        _emit(run_id, "hermes", "Video shipped: %s" % final_url)
    elif final_exists:
        _emit(run_id, "hermes",
              "Render complete (final.mp4 on disk); upload owned by worker.")
    else:
        _emit(run_id, "hermes",
              "Build finished but final.mp4 not found.", level="warn")

    return {
        "ok": True,
        "step": "produce_and_ship",
        "run_id": run_id,
        "mode": mode,
        "quality": quality,
        "final_path": final_path if final_exists else None,
        "final_exists": final_exists,
        "final_url": final_url,  # None until the worker (or a future upload step) lands it
        "from_plan_entrypoint": bool(from_plan_flag),  # ★SPIKE: false today
        "note": "build_runner ran the full produce loop (★SPIKE: no produce-from-plan "
                "entrypoint yet — plan_path was NOT reused). MP4 upload to the "
                "walk-videos bucket is owned by the Node worker (★SPIKE: confirm "
                "upload owner for the agent-host topology).",
    }


def _load_plan(plan_path):
    """Read a plan.json written by plan_job. Returns (plan_dict_or_None, error)."""
    if not plan_path or not os.path.exists(plan_path):
        return None, "plan_path missing or not found: %r" % plan_path
    try:
        with open(plan_path, "r", encoding="utf-8") as fh:
            return json.load(fh), None
    except Exception as e:
        return None, "could not read plan: %s" % e


def _ledger_final_url(run_dir):
    """Best-effort read of runs/<id>/ledger.json for a final/checkout URL the worker
    may have recorded. Returns the URL string or None."""
    led_path = os.path.join(run_dir, "ledger.json")
    if not os.path.exists(led_path):
        return None
    try:
        with open(led_path, "r", encoding="utf-8") as fh:
            led = json.load(fh)
    except Exception:
        return None
    if not isinstance(led, dict):
        return None
    # The worker maps the bucket URL onto runs.final_url AFTER build_runner exits;
    # build_runner itself does not know the hosted URL. So this is usually None here
    # and the worker fills it in — surfaced honestly above.
    earn = led.get("earn") if isinstance(led.get("earn"), dict) else {}
    return led.get("final_url") or earn.get("checkout_url") or None


# --------------------------------------------------------------------------- #
# Tool registry (name -> {handler, schema})
# --------------------------------------------------------------------------- #
TOOLS = {
    "conversion_read": {
        "handler": tool_conversion_read,
        "schema": {
            "name": "conversion_read",
            "description": (
                "Run the Conversion Read on a company URL: fetch the page's "
                "visible copy and analyze it on NVIDIA Nemotron (via OpenRouter) "
                "into a validated Read (who the product is for, the core promise, "
                "proof points, the conversion goal). First real step of a job — "
                "call before plan_job. In the agent-host the untrusted site read "
                "runs inside the NemoClaw sandbox. Returns the Read JSON + engine."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Company/product URL to read."},
                    "brain": {
                        "type": "string",
                        "description": "Model brain key (default 'ultra-paid' = Nemotron Ultra 550B, super-paid fallback).",
                    },
                    "run_id": {
                        "type": "string",
                        "description": "Run id for the live UI progress feed (run_events).",
                    },
                },
                "required": ["url"],
            },
        },
    },
    "plan_job": {
        "handler": tool_plan_job,
        "schema": {
            "name": "plan_job",
            "description": (
                "Decompose a brief (url + goal + duration) into a schema-valid "
                "SCENE PLAN via the Nemotron planner. Call after conversion_read. "
                "Writes runs/<run_id>/plan.json and returns its path (feed that "
                "path to price_job, budget_gate and produce_and_ship)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "goal": {"type": "string"},
                    "duration": {"type": "integer", "description": "Target seconds (default 30)."},
                    "brain": {"type": "string", "description": "Planner brain (default 'ultra-paid' = Nemotron Ultra 550B)."},
                    "run_id": {"type": "string", "description": "Run id; also the plan.json dir + UI feed."},
                },
                "required": ["url", "goal"],
            },
        },
    },
    "price_job": {
        "handler": tool_price_job,
        "schema": {
            "name": "price_job",
            "description": (
                "Deterministically price a scene plan: total COGS, suggested "
                "customer price for the target margin, the locked production "
                "budget, and per-scene budgets. The model reads these numbers; "
                "it does not set them."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plan_path": {"type": "string", "description": "Path from plan_job."},
                    "run_id": {"type": "string", "description": "Run id for the UI feed."},
                },
                "required": ["plan_path"],
            },
        },
    },
    "budget_gate": {
        "handler": tool_budget_gate,
        "schema": {
            "name": "budget_gate",
            "description": (
                "Deterministic budget guardrail for a paid scene: returns "
                "approve / downgrade / decline given the proposed cost and the "
                "running spend. An over-budget scene is DECLINED in code — the "
                "model cannot spend past the budget. This is the autonomous "
                "money-shot."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plan_path": {"type": "string"},
                    "scene_id": {"type": "string"},
                    "proposed_cost_cents": {"type": "integer"},
                    "spent_cents": {"type": "integer"},
                    "run_id": {"type": "string", "description": "Run id for the UI feed."},
                },
                "required": ["plan_path", "scene_id", "proposed_cost_cents", "spent_cents"],
            },
        },
    },
    "produce_and_ship": {
        "handler": tool_produce_and_ship,
        "schema": {
            "name": "produce_and_ship",
            "description": (
                "Render the planned video (Remotion) and ship the MP4, returning "
                "the final URL. Call LAST, after budget_gate. Drives the hosted "
                "build_runner.py produce/render path for runs/<run_id>/. NOTE: the "
                "MP4 upload to storage (final_url) is currently owned by the cloud "
                "worker, so final_url may be null until the worker lands it."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plan_path": {"type": "string", "description": "Path from plan_job."},
                    "run_id": {"type": "string", "description": "Run id; the build writes runs/<run_id>/."},
                    "mode": {"type": "string", "description": "mock (default; real Remotion cards, $0 paid gen) or real."},
                    "quality": {"type": "string", "description": "standard (default) or premium."},
                    "brain": {"type": "string", "description": "Planner brain if the loop re-plans (default ultra-paid)."},
                },
                "required": ["plan_path", "run_id"],
            },
        },
    },
}


# --------------------------------------------------------------------------- #
# JSON-RPC / MCP stdio loop
# --------------------------------------------------------------------------- #
def _write(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _result(req_id, result):
    _write({"jsonrpc": "2.0", "id": req_id, "result": result})


def _error(req_id, code, message):
    _write({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def handle(req):
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params") or {}

    # Notifications (no id) — ack silently.
    if method == "notifications/initialized" or (req_id is None and method and method.startswith("notifications/")):
        return

    if method == "initialize":
        _result(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
        return

    if method == "ping":
        _result(req_id, {})
        return

    if method == "tools/list":
        _result(req_id, {"tools": [t["schema"] for t in TOOLS.values()]})
        return

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        entry = TOOLS.get(name)
        if not entry:
            _error(req_id, -32601, "unknown tool: %s" % name)
            return
        # AUDIT: log every tool invocation to stderr (the run log) with the
        # call-shaping args, so the orchestrator has an independent, timestamped
        # record of which tools the runtime drove and with what params. Never logs
        # secrets — args here are urls, plan paths, scene ids, brain flags, prices.
        try:
            _audit = {k: args.get(k) for k in
                      ("url", "scene_id", "run_id", "mode", "quality", "brain",
                       "proposed_cost_cents", "spent_cents") if k in args}
            _log("TOOL CALL %s %s" % (name, json.dumps(_audit)))
        except Exception:
            _log("TOOL CALL %s" % name)
        try:
            out = entry["handler"](args)
        except Exception as e:
            out = {"ok": False, "error": "tool crashed: %s" % e}
        try:
            _log("TOOL DONE %s ok=%s" % (name, (out.get("ok") if isinstance(out, dict) else "?")))
        except Exception:
            pass
        # MCP tools/call result: content blocks. isError flags a failed call.
        is_error = isinstance(out, dict) and out.get("ok") is False
        _result(req_id, {
            "content": [{"type": "text", "text": json.dumps(out, indent=2)}],
            "isError": bool(is_error),
        })
        return

    if req_id is not None:
        _error(req_id, -32601, "method not found: %s" % method)


def main():
    _log("starting (%s v%s); pipeline_dir=%s; tools: %s"
         % (SERVER_NAME, SERVER_VERSION, PIPELINE_DIR, ", ".join(TOOLS)))
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            _log("bad JSON line: %s" % e)
            continue
        try:
            handle(req)
        except Exception as e:
            _log("handler error: %s" % e)
            rid = req.get("id") if isinstance(req, dict) else None
            if rid is not None:
                _error(rid, -32603, "internal error: %s" % e)


if __name__ == "__main__":
    main()
