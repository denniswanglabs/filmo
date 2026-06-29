#!/usr/bin/env python3
"""Filmo HOST tool-server (M2 Phase A) — the 5 SANCTIONED tools Hermes will
conduct from inside the NemoClaw sandbox, each wired to the REAL curated pipeline
function (in-process on the host).

  conversion_read · plan · price · gate · produce_and_ship

Transport: PLAIN HTTP MCP at POST /mcp on 0.0.0.0:<port> (the proven M0 bridge
contract — sandbox reaches it at http://host.openshell.internal:<port>/mcp through
OpenShell's L7 proxy). Dependency-free: speaks MCP JSON-RPC 2.0 over a stdlib
http.server, so it needs NO `mcp`/uvicorn pip package. GET /mcp and /health are
liveness probes.

HOST-ONLY. This is a SEPARATE process/port from the live `filmo-claimer` systemd
service — it does NOT touch the claimer or curated-claimer.js. The heavy + trusted
execution (Nemotron Read+plan, screenshot capture, Remotion render) stays
host-resident; the pipeline is NOT ported into the sandbox.

Each tool wraps one real curated step (branch hosted-saas, dir /root/filmo-pipeline):
  conversion_read -> url_guard.assert_public_url + build_runner._maybe_conversion_read
                     + build_runner._brand_facts  (REAL design_brief via Nemotron)
  plan            -> plan_job.plan_job(... conversion_read=read)  (+ selection stamp)
  price           -> producer.cmd_estimate(plan)  (WS_PREMIUM_MENU=1 cost-plus)
  gate            -> pure logic: proceed iff price_cents <= budget_cents
  produce_and_ship-> url_guard + build_runner._capture_screenshots_for_run
                     + style_fill.run_pipeline(..., do_render=True) -> runs/<key>/video.mp4
                     + InsForge walk-videos upload -> final_url

Secrets come from the process env (the launcher sources /root/.orkey etc.) and are
never printed.
"""
import json
import os
import re
import sys
import time
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # make analyze/build_runner/plan_job/producer/style_fill importable

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "filmo-host"
SERVER_VERSION = "2.0.0"
PORT = int(os.environ.get("MCP_PORT", "8770"))

# InsForge upload helper (Node, reuses /root/filmo-worker/@insforge/sdk).
INSFORGE_UPLOADER = os.environ.get(
    "INSFORGE_UPLOADER", "/root/filmo-worker/insforge_upload.mjs")
WORKER_DIR = os.environ.get("WORKER_DIR", "/root/filmo-worker")
NODE_BIN = os.environ.get("NODE_BIN", "node")
INSFORGE_URL = os.environ.get("INSFORGE_URL", "https://jd3mdkqr.ap-southeast.insforge.app")

# Curated price uses the cost-plus menu (the dashboard's source-of-truth price).
os.environ.setdefault("WS_PREMIUM_MENU", "1")


def _log(msg):
    sys.stderr.write("[mcp_toolserver] %s\n" % msg)
    sys.stderr.flush()


def _safe_run_key(run_key):
    """sec-C2: sanitize a run_key before it is used as a path component.

    run_key flows verbatim into os.path.join(HERE, "runs", run_key); a crafted
    value (../../…, an absolute path, …) would escape the runs dir and write as
    root. Reduce to a safe slug: keep [A-Za-z0-9._-], map everything else to '-',
    strip leading dots/dashes, reject the pure-dot traversal tokens.
    """
    raw = str(run_key or "").strip()
    slug = re.sub(r"[^A-Za-z0-9._-]", "-", raw).lstrip(".-")
    if slug in ("", ".", ".."):
        slug = "run"
    return slug[:128]


def _runs_dir(run_key):
    d = os.path.join(HERE, "runs", _safe_run_key(run_key))
    os.makedirs(d, exist_ok=True)
    return d


# --------------------------------------------------------------------------- #
# Server-side PLAN CACHE (the plan_id HANDLE).
# The full plan is large and contains JSON-escaped unicode (em-dashes —,
# curly quotes, etc.). When the plan round-trips through Hermes's tokens between
# tools, the model corrupts those escapes (— -> literal "u2014"), which then
# bakes into on-screen text + VO. FIX: the `plan` tool caches the full plan
# server-side under runs/<plan_id>/plan.json and returns only a SHORT plan_id
# handle. price / produce_and_ship accept plan_id and resolve the plan from disk,
# so the plan NEVER passes through the model's tokens. This eliminates the
# corruption AND cuts token cost.
# --------------------------------------------------------------------------- #
def _plan_cache_path(plan_id):
    return os.path.join(_runs_dir(plan_id), "plan.json")


def _cache_plan(plan, plan_id):
    """Persist the full plan under runs/<plan_id>/plan.json (utf-8, real chars)."""
    path = _plan_cache_path(plan_id)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=2, ensure_ascii=False)
    return path


def _load_cached_plan(plan_id):
    """Return the cached plan dict for plan_id, or None if absent/invalid."""
    if not plan_id:
        return None
    path = _plan_cache_path(plan_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        _log("plan cache read failed for %s: %s" % (plan_id, e))
        return None


def _resolve_plan(args):
    """Resolve a plan from args, PREFERRING the plan_id handle (no corruption).
    Order: plan_id (cache) -> inline plan dict (legacy/fallback).
    Returns (plan_dict_or_None, plan_id_or_None, error_str_or_None)."""
    plan_id = (args.get("plan_id") or "").strip() or None
    if plan_id:
        plan = _load_cached_plan(plan_id)
        if isinstance(plan, dict) and plan:
            return plan, plan_id, None
        # plan_id given but cache miss — try inline as a fallback before erroring
        inline = args.get("plan")
        if isinstance(inline, dict) and inline:
            return inline, plan_id, None
        return None, plan_id, ("plan_id %r not found in cache (no runs/%s/plan.json) "
                               "and no inline plan provided" % (plan_id, plan_id))
    # No handle — accept an inline plan (legacy path / direct callers).
    inline = args.get("plan")
    if isinstance(inline, dict) and inline:
        return inline, None, None
    return None, None, "plan_id (preferred) or plan (dict) is required"


# --------------------------------------------------------------------------- #
# Tool 1 — conversion_read (REAL: Nemotron Read + design_brief + brand_facts)
# --------------------------------------------------------------------------- #
def tool_conversion_read(args):
    url = (args.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "url is required"}
    run_key = (args.get("run_key") or _slug(url) + "-mcp").strip()
    run_dir = _runs_dir(run_key)

    try:
        import url_guard
        import build_runner
    except Exception as e:
        return {"ok": False, "error": "import failed: %s" % e}

    # SSRF guard the untrusted URL first.
    try:
        url = url_guard.assert_public_url(url)
    except Exception as e:
        return {"ok": False, "error": "url rejected by guard: %s" % e}

    brain = (args.get("brain") or build_runner.ANALYZE_BRAIN).strip() or build_runner.ANALYZE_BRAIN
    have_key = bool(os.environ.get("OPENROUTER_API_KEY"))
    try:
        read = build_runner._maybe_conversion_read(url, run_dir, brain=brain)
    except Exception as e:
        return {"ok": False, "error": "_maybe_conversion_read failed: %s" % e}
    try:
        facts = build_runner._brand_facts(url, run_dir)
    except Exception as e:
        return {"ok": False, "error": "_brand_facts failed: %s" % e}

    design_brief = (read.get("design_brief") if isinstance(read, dict) else None) or {}
    story_shape = design_brief.get("story_shape") or {}
    brand_vibe = design_brief.get("brand_vibe") or {}
    return {
        "ok": True,
        "step": "conversion_read",
        "url": url,
        "run_key": run_key,
        "run_dir": run_dir,
        "openrouter_key_present": have_key,
        "engine": read.get("engine") if isinstance(read, dict) else None,
        "degraded": read.get("degraded") if isinstance(read, dict) else None,
        # the curated payload the runtime threads forward:
        "conversion_read": read,
        "design_brief": design_brief,
        "design_brief_nonempty": bool(story_shape) or bool(brand_vibe),
        "story_shape_keys": sorted(story_shape.keys()),
        "brand_vibe": brand_vibe,
        "brand_facts": facts,
    }


# --------------------------------------------------------------------------- #
# Tool 2 — plan (REAL: plan_job.plan_job threading the Read's design_brief)
# --------------------------------------------------------------------------- #
def tool_plan(args):
    url = (args.get("url") or "").strip()
    goal = (args.get("goal") or "").strip()
    if not url:
        return {"ok": False, "error": "url is required"}
    duration = int(args.get("duration") or 30)
    brand_facts = args.get("brand_facts") or None
    conversion_read = args.get("conversion_read") or None
    style = (args.get("style") or "standard").strip() or "standard"
    quality = (args.get("quality") or "standard").strip() or "standard"
    # M2 Phase B: default the planner brain to ultra-paid (Nemotron 550B) so
    # Hermes-conducted plans are LLM-planned (plan_source=llm), per locked architecture.
    brain = (args.get("brain") or "ultra-paid").strip() or "ultra-paid"
    emphasis = (args.get("emphasis") or "").strip() or None

    try:
        import plan_job
    except Exception as e:
        return {"ok": False, "error": "import plan_job failed: %s" % e}

    try:
        plan = plan_job.plan_job(
            url, goal, target_duration_s=duration, style=style, quality=quality,
            brain=brain, company_facts=brand_facts, emphasis=emphasis,
            conversion_read=conversion_read,
        )
    except Exception as e:
        return {"ok": False, "error": "plan_job failed: %s" % e}

    # Stamp plan["selection"] from plan["_planner"] (build_runner.py ~513-522).
    prov = plan.get("_planner") or {}
    plan["selection"] = {
        "quality": quality,
        "brain": brain,
        "plan_source": prov.get("plan_source", "llm"),
        "finish_reason": prov.get("finish_reason"),
        "planner_reason": prov.get("reason"),
        "planner_usage": prov.get("usage"),
    }

    scenes = plan.get("scenes", []) if isinstance(plan, dict) else []
    design_brief = plan.get("design_brief") or {}

    # Cache the full plan server-side and return only a SHORT plan_id handle.
    # The plan NEVER round-trips through Hermes's tokens (kills the u2014 bug).
    plan_id = (args.get("plan_id") or args.get("run_key") or "").strip() or (_slug(url) + "-mcp")
    plan["_plan_id"] = plan_id
    try:
        cache_path = _cache_plan(plan, plan_id)
    except Exception as e:
        return {"ok": False, "error": "plan cache write failed: %s" % e}

    # Lightweight, corruption-safe summary only. Do NOT return the full plan.
    return {
        "ok": True,
        "step": "plan",
        "plan_id": plan_id,
        "plan_cached_at": cache_path,
        "scene_count": len(scenes),
        "scene_types": [s.get("type") for s in scenes],
        "design_brief_present": "design_brief" in plan,
        "plan_source": plan["selection"]["plan_source"],
        "note": ("Plan cached server-side. Pass plan_id (NOT the full plan) to "
                 "price and produce_and_ship."),
    }


# --------------------------------------------------------------------------- #
# Tool 3 — price (REAL: producer.cmd_estimate, cost-plus menu)
# --------------------------------------------------------------------------- #
def tool_price(args):
    plan, plan_id, err = _resolve_plan(args)
    if err:
        return {"ok": False, "error": err}
    try:
        import producer
    except Exception as e:
        return {"ok": False, "error": "import producer failed: %s" % e}
    try:
        est = producer.cmd_estimate(plan)
    except Exception as e:
        return {"ok": False, "error": "cmd_estimate failed: %s" % e}
    return {
        "ok": True,
        "step": "price",
        "plan_id": plan_id,
        "price_cents": est.get("suggested_price_cents"),
        "cogs_cents": est.get("total_cogs_cents"),
        "margin": est.get("target_margin"),
        "currency": est.get("currency"),
        "pricing_mode": est.get("pricing_mode"),
        "menu": est.get("menu"),
        "estimate": est,
    }


# --------------------------------------------------------------------------- #
# Tool 4 — gate (pure logic: the agent's money decision)
# --------------------------------------------------------------------------- #
def tool_gate(args):
    try:
        price_cents = int(args.get("price_cents"))
        budget_cents = int(args.get("budget_cents"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "price_cents and budget_cents (ints) are required"}
    proceed = price_cents <= budget_cents
    if proceed:
        reason = ("price %d cents within budget %d cents — PROCEED"
                  % (price_cents, budget_cents))
    else:
        reason = ("price %d cents exceeds budget %d cents by %d — DECLINE"
                  % (price_cents, budget_cents, price_cents - budget_cents))
    return {
        "ok": True,
        "step": "gate",
        "proceed": proceed,
        "reason": reason,
        "price_cents": price_cents,
        "budget_cents": budget_cents,
    }


# --------------------------------------------------------------------------- #
# Tool 5 — produce_and_ship (REAL: capture + run_pipeline render + InsForge ship)
# --------------------------------------------------------------------------- #
def _slug(url):
    s = (url or "").lower()
    for pre in ("https://", "http://", "www."):
        if s.startswith(pre):
            s = s[len(pre):]
    out = "".join(c if c.isalnum() else "-" for c in s).strip("-")
    return (out or "site")[:48]


# Belt-and-suspenders: even with the plan_id handle, normalize any stray
# bare "uXXXX" (a corrupted JSON \uXXXX escape) back to the real character in
# all plan strings before render. Matches the literal lowercase 'u' followed by
# exactly 4 hex digits NOT preceded by a backslash. With the handle this should
# never fire, but it guarantees clean on-screen + VO text.
import re as _re
_BARE_U = _re.compile(r"(?<![\\\w])u([0-9a-fA-F]{4})")


def _denorm_bare_unicode(text):
    if not isinstance(text, str) or "u" not in text:
        return text
    def _sub(m):
        try:
            return chr(int(m.group(1), 16))
        except Exception:
            return m.group(0)
    return _BARE_U.sub(_sub, text)


def _scrub_plan_unicode(obj):
    """Recursively fix bare uXXXX artifacts in all strings of a plan structure."""
    if isinstance(obj, str):
        return _denorm_bare_unicode(obj)
    if isinstance(obj, list):
        return [_scrub_plan_unicode(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _scrub_plan_unicode(v) for k, v in obj.items()}
    return obj


def _upload_to_insforge(mp4_path, object_key):
    """Replicate curated-claimer.js uploadVideo via the Node @insforge/sdk helper.
    Returns (final_url_or_None, info_dict)."""
    if not os.path.exists(INSFORGE_UPLOADER):
        return None, {"error": "uploader missing: %s" % INSFORGE_UPLOADER}
    env = dict(os.environ)
    env.setdefault("INSFORGE_URL", INSFORGE_URL)
    if not env.get("INSFORGE_API_KEY"):
        return None, {"error": "INSFORGE_API_KEY not in env"}
    try:
        proc = subprocess.run(
            [NODE_BIN, INSFORGE_UPLOADER, os.path.abspath(mp4_path), object_key],
            cwd=WORKER_DIR, capture_output=True, text=True, timeout=300, env=env,
        )
    except subprocess.TimeoutExpired:
        return None, {"error": "upload timed out"}
    out = (proc.stdout or "").strip().splitlines()
    last = out[-1] if out else ""
    try:
        res = json.loads(last)
    except Exception:
        return None, {"error": "non-JSON upload output", "stderr": (proc.stderr or "")[-800:],
                       "stdout": (proc.stdout or "")[-800:]}
    if not res.get("ok"):
        return None, {"error": res.get("error"), "stderr": (proc.stderr or "")[-800:]}
    return res.get("url"), {"key": res.get("key"), "bucket": res.get("bucket")}


def tool_produce_and_ship(args):
    url = (args.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "url is required"}

    # Resolve the plan from the plan_id HANDLE (preferred) or inline plan (legacy).
    plan, plan_id, err = _resolve_plan(args)
    if err:
        return {"ok": False, "error": err}
    brand_theme = args.get("brand_theme")

    # Reuse the plan_id as the run_key so render + the cached plan.json share one
    # run dir (and the on-screen text uses the un-corrupted cached plan).
    run_key = (args.get("run_key") or "").strip() or plan_id or (_slug(url) + "-ship")

    try:
        import url_guard
        import build_runner
        import style_fill
    except Exception as e:
        return {"ok": False, "error": "import failed: %s" % e}

    try:
        url = url_guard.assert_public_url(url)
    except Exception as e:
        return {"ok": False, "error": "url rejected by guard: %s" % e}

    run_dir = _runs_dir(run_key)

    # 1) real website screenshots (idempotent, best-effort, $0)
    try:
        build_runner._capture_screenshots_for_run(url, run_dir)
    except Exception as e:
        _log("produce_and_ship: screenshot capture degraded: %s" % e)

    # 2) write plan.json + brand_theme.json into runs/<run_key>/
    #    Scrub any stray bare-uXXXX artifact (defensive; the plan_id handle should
    #    have prevented it) then write with ensure_ascii=False so real chars (—,
    #    curly quotes) land on disk and the render never re-introduces a u2014.
    plan = _scrub_plan_unicode(plan)
    plan_path = os.path.join(run_dir, "plan.json")
    with open(plan_path, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=2, ensure_ascii=False)

    # brand_theme: caller-provided OR resolve the curated fixture/extract fallback.
    if isinstance(brand_theme, dict) and brand_theme:
        brand_path = os.path.join(run_dir, "brand_theme.json")
        with open(brand_path, "w", encoding="utf-8") as fh:
            json.dump(brand_theme, fh, indent=2)
    else:
        try:
            brand_path = build_runner._resolve_brand_theme(url, run_dir)
        except Exception as e:
            return {"ok": False, "error": "brand theme resolve failed: %s" % e}

    # 3) the curated assembler + render -> runs/<run_key>/video.mp4
    #    (entityLogos + screenshots + page logo staged inside run_pipeline)
    try:
        res = style_fill.run_pipeline(
            plan_path, brand_path, build_runner.VO_ENGINE_STYLE, run_dir,
            fps=30, do_align=True, do_render=True,
        )
    except Exception as e:
        return {"ok": False, "error": "run_pipeline render failed: %s" % e}

    video_path = os.path.join(run_dir, "video.mp4")
    if not os.path.exists(video_path):
        # fall back to whatever run_pipeline reported, else fail honestly
        rp = (res or {}).get("video_path") if isinstance(res, dict) else None
        if rp and os.path.exists(rp):
            video_path = rp
        else:
            return {"ok": False, "error": "render produced no video.mp4 in %s" % run_dir,
                    "run_pipeline_result_keys": sorted((res or {}).keys()) if isinstance(res, dict) else None}

    video_bytes = os.path.getsize(video_path)

    # 4) upload to InsForge walk-videos -> final_url (idempotent remove+upload)
    object_key = "%s/video.mp4" % run_key
    final_url, up_info = _upload_to_insforge(video_path, object_key)

    return {
        "ok": True,
        "step": "produce_and_ship",
        "plan_id": plan_id,
        "run_key": run_key,
        "run_dir": run_dir,
        "video_path": video_path,
        "video_bytes": video_bytes,
        "final_url": final_url,
        "upload_info": up_info,
        "montage_path": (res or {}).get("montage_path") if isinstance(res, dict) else None,
    }


# --------------------------------------------------------------------------- #
# Tool registry
# --------------------------------------------------------------------------- #
TOOLS = {
    "conversion_read": {
        "handler": tool_conversion_read,
        "schema": {
            "name": "conversion_read",
            "description": (
                "Run the curated Conversion Read on a company URL (SSRF-guarded). "
                "Fetches the page, runs the 6-dimension Read on Nemotron, and returns "
                "the validated Read PLUS a real design_brief {story_shape, brand_vibe} "
                "and brand_facts {wordmark, tagline, features}. FIRST step — call before "
                "plan. Thread the returned conversion_read + brand_facts into plan."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Company/product URL to read."},
                    "run_key": {"type": "string", "description": "Optional run id (default derived from url)."},
                    "brain": {"type": "string", "description": "Model brain (default ultra-paid = Nemotron Ultra 550B)."},
                },
                "required": ["url"],
            },
        },
    },
    "plan": {
        "handler": tool_plan,
        "schema": {
            "name": "plan",
            "description": (
                "Decompose the brief into a schema-valid curated SCENE PLAN via the "
                "Nemotron planner. Pass the url, goal, and the brand_facts + "
                "conversion_read from conversion_read so the plan inherits the "
                "design_brief (pattern-typed scenes, content-fit seeding). The full plan "
                "is CACHED SERVER-SIDE and this tool returns a short plan_id HANDLE "
                "(plus a scene summary) — NOT the full plan. Pass that plan_id to price "
                "and produce_and_ship; never pass the full plan between tools."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "goal": {"type": "string"},
                    "duration": {"type": "integer", "description": "Target seconds (default 30)."},
                    "brand_facts": {"type": "object", "description": "From conversion_read.brand_facts."},
                    "conversion_read": {"type": "object", "description": "From conversion_read.conversion_read (carries design_brief)."},
                    "style": {"type": "string", "description": "snappy | standard | cinematic (default standard)."},
                    "quality": {"type": "string", "description": "standard | premium (default standard)."},
                    "brain": {"type": "string", "description": "Planner brain (default ultra-paid = Nemotron 550B)."},
                    "emphasis": {"type": "string"},
                },
                "required": ["url", "goal"],
            },
        },
    },
    "price": {
        "handler": tool_price,
        "schema": {
            "name": "price",
            "description": (
                "Deterministically price a scene plan via the cost-plus menu: returns "
                "price_cents (the customer price), cogs_cents, and margin. The model "
                "reads these numbers; it does not set them. Call after plan, before gate. "
                "Pass the plan_id handle returned by plan (the server resolves the cached "
                "plan)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string", "description": "The plan_id handle from the plan tool (preferred)."},
                    "plan": {"type": "object", "description": "Legacy: an inline plan dict (use plan_id instead)."},
                },
                "required": ["plan_id"],
            },
        },
    },
    "gate": {
        "handler": tool_gate,
        "schema": {
            "name": "gate",
            "description": (
                "The agent's money decision: proceed iff price_cents <= budget_cents. "
                "Returns {proceed, reason}. An over-budget job is DECLINED here — this is "
                "the autonomous money-shot. Call after price; only run produce_and_ship "
                "when proceed is true."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "price_cents": {"type": "integer", "description": "Customer price from price."},
                    "budget_cents": {"type": "integer", "description": "The job's budget ceiling."},
                },
                "required": ["price_cents", "budget_cents"],
            },
        },
    },
    "produce_and_ship": {
        "handler": tool_produce_and_ship,
        "schema": {
            "name": "produce_and_ship",
            "description": (
                "Produce the curated video and ship it. SSRF-guards the url, captures "
                "real website screenshots, writes plan.json + brand_theme.json, runs the "
                "curated assembler + Remotion render (14-pattern content-fit routing, "
                "entityLogos, real screenshots + page logo) -> runs/<run_key>/video.mp4, "
                "then uploads to the InsForge walk-videos bucket -> final_url. Call LAST, "
                "only after gate approves. Pass the url and the plan_id handle (the "
                "server resolves the cached plan). Returns {final_url, run_key, video_path}."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "plan_id": {"type": "string", "description": "The plan_id handle from the plan tool (preferred)."},
                    "plan": {"type": "object", "description": "Legacy: an inline plan dict (use plan_id instead)."},
                    "brand_theme": {"type": "object", "description": "Optional brand theme; else resolved from the url."},
                    "run_key": {"type": "string", "description": "Run id / object-key prefix (default = plan_id)."},
                },
                "required": ["url", "plan_id"],
            },
        },
    },
}


# --------------------------------------------------------------------------- #
# MCP JSON-RPC dispatch (shared by HTTP)
# --------------------------------------------------------------------------- #
def dispatch(req):
    """Return a JSON-RPC response dict, or None for notifications (no id)."""
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params") or {}

    if method == "notifications/initialized" or (req_id is None and method and method.startswith("notifications/")):
        return None

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }}

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id,
                "result": {"tools": [t["schema"] for t in TOOLS.values()]}}

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        entry = TOOLS.get(name)
        if not entry:
            return {"jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32601, "message": "unknown tool: %s" % name}}
        _log("TOOL CALL %s url=%s run_key=%s" % (name, args.get("url"), args.get("run_key")))
        t0 = time.time()
        try:
            out = entry["handler"](args)
        except Exception as e:
            out = {"ok": False, "error": "tool crashed: %s" % e}
        _log("TOOL DONE %s ok=%s %.1fs" % (
            name, (out.get("ok") if isinstance(out, dict) else "?"), time.time() - t0))
        is_error = isinstance(out, dict) and out.get("ok") is False
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "content": [{"type": "text", "text": json.dumps(out, indent=2)}],
            "isError": bool(is_error),
        }}

    if req_id is not None:
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": "method not found: %s" % method}}
    return None


# --------------------------------------------------------------------------- #
# HTTP server — MCP at /mcp (POST = JSON-RPC, GET = liveness)
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):  # quiet default access log -> stderr only
        _log("HTTP " + (fmt % a))

    def _send_json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/") in ("/health", "/mcp", ""):
            self._send_json(200, {"ok": True, "server": SERVER_NAME,
                                  "version": SERVER_VERSION, "tools": list(TOOLS)})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/mcp":
            self._send_json(404, {"error": "post to /mcp"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            req = json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._send_json(400, {"jsonrpc": "2.0", "id": None,
                                  "error": {"code": -32700, "message": "parse error: %s" % e}})
            return
        # Support a single request or a batch.
        if isinstance(req, list):
            resp = [r for r in (dispatch(x) for x in req) if r is not None]
            self._send_json(200, resp)
            return
        resp = dispatch(req)
        if resp is None:
            # notification -> 202 Accepted, no body
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._send_json(200, resp)


def main():
    _log("starting %s v%s on 0.0.0.0:%d /mcp; tools: %s"
         % (SERVER_NAME, SERVER_VERSION, PORT, ", ".join(TOOLS)))
    _log("WS_PREMIUM_MENU=%s OPENROUTER_API_KEY=%s INSFORGE_API_KEY=%s" % (
        os.environ.get("WS_PREMIUM_MENU"),
        "set" if os.environ.get("OPENROUTER_API_KEY") else "MISSING",
        "set" if os.environ.get("INSFORGE_API_KEY") else "MISSING"))
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.serve_forever()


if __name__ == "__main__":
    main()
