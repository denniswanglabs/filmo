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
import math
import subprocess
import threading
import urllib.request
import urllib.error
import urllib.parse
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


# --------------------------------------------------------------------------- #
# InsForge write resilience: a slow InsForge write must NOT drag each scene or hang
# the ship. Every urllib InsForge call below goes through _insforge_request, which:
#   - uses a SHORT per-attempt timeout (IF_HTTP_TIMEOUT, default 8s) instead of the
#     old 15s, so one slow write stalls a step by at most ~8s, not 15s+;
#   - retries IF_HTTP_ATTEMPTS times (default 3) with 0.4s/0.8s backoff on a timeout
#     or transient (5xx / network) error — a 4xx is NOT retried (it won't self-heal);
#   - is BEST-EFFORT: it NEVER raises (returns the response body on success, or None),
#     exactly like the callers already are, so a feed/phase/props write can never
#     fail a (paid, delivered) conduct. Tunable via env IF_HTTP_TIMEOUT / IF_HTTP_ATTEMPTS.
# --------------------------------------------------------------------------- #
IF_HTTP_TIMEOUT = float(os.environ.get("IF_HTTP_TIMEOUT", "8"))
IF_HTTP_ATTEMPTS = int(os.environ.get("IF_HTTP_ATTEMPTS", "3"))


def _insforge_request(req, label):
    """Perform a bounded, retried urllib InsForge request. Returns the response body
    bytes on success or None. Best-effort: never raises. A 4xx HTTPError is treated
    as terminal (no retry, no self-heal); timeouts and 5xx/network errors retry."""
    last = None
    for i in range(IF_HTTP_ATTEMPTS):
        try:
            with urllib.request.urlopen(req, timeout=IF_HTTP_TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                detail = ""
            # 4xx = a real rejection (bad row / not-found); retrying won't help.
            if 400 <= e.code < 500:
                _log("%s HTTPError %s (terminal): %s" % (label, e.code, detail))
                return None
            last = "HTTP %s: %s" % (e.code, detail)
        except Exception as e:
            last = str(e)
        if i < IF_HTTP_ATTEMPTS - 1:
            time.sleep(0.4 * (2 ** i))  # 0.4s, 0.8s
    _log("%s failed after %d attempts: %s" % (label, IF_HTTP_ATTEMPTS, last))
    return None


# --------------------------------------------------------------------------- #
# Customer-price cap (Phase-C money policy): EVERY video is capped at $10 so the
# demo never quotes a surprise price and the gate never declines. The cost-plus
# menu's premium band can quote up to $25; we clamp the customer-facing price to
# this ceiling in the `price` tool. The deterministic pricing.py is untouched
# (fallback intact) — this clamp lives only on the Hermes-conducted path.
# --------------------------------------------------------------------------- #
PRICE_CAP_CENTS = int(os.environ.get("HERMES_PRICE_CAP_CENTS", "1000"))


# --------------------------------------------------------------------------- #
# run_events emitter — the LIVE "watch the agent work" feed.
# Each MCP tool emits one (or more) run_events row(s) to InsForge as it runs, so a
# Hermes-conducted run shows the SAME rich per-step narration the deterministic
# claimer streams from the ledger. Events are SPONSOR-TAGGED via the `actor` column
# (nemotron = the NVIDIA brain; stripe = payments; hermes = the agent harness).
#
# Writes directly to InsForge PostgREST-style table endpoint
#   POST /api/database/records/run_events   (Authorization: Bearer INSFORGE_API_KEY)
# with the SAME row shape the curated-claimer.js emit() inserts:
#   {run_id, seq, actor, level, msg}   (id + created_at are server-assigned).
#
# Best-effort + NEVER raises: a feed write must NOT fail a (paid, delivered) conduct.
# When run_id is absent (a direct/legacy caller without the conductor's run_id) the
# emit is a quiet no-op — exactly like curated-claimer.js emit().
# --------------------------------------------------------------------------- #
def _emit_event(run_id, msg, actor="hermes", level="info"):
    """Insert one run_events row for the live feed. Best-effort; never raises."""
    if not run_id:
        return
    api_key = os.environ.get("INSFORGE_API_KEY")
    if not api_key:
        _log("emit skipped: INSFORGE_API_KEY missing")
        return
    # seq mirrors curated-claimer.js (Date.now() % 1e9) so ordering is monotonic
    # across the deterministic + Hermes paths and never collides within a run.
    seq = int(time.time() * 1000) % 1000000000
    row = {"run_id": run_id, "seq": seq, "actor": actor, "level": level, "msg": msg}
    body = json.dumps([row]).encode("utf-8")
    url = INSFORGE_URL.rstrip("/") + "/api/database/records/run_events"
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer %s" % api_key})
    _insforge_request(req, "emit(run %s)" % run_id)


# --------------------------------------------------------------------------- #
# runs.phase setter — drives the web run-page PROGRESS STEPPER.
#
# The deterministic build_runner.py advances the stepper via led.set_phase(...).
# The Hermes-conducted path runs the tools in THIS server, which previously never
# touched runs.phase — so the stepper stuck on its index-0 fallback ("Reading the
# site") for the whole conduct. This helper writes runs.phase from the relevant
# tools using the SAME InsForge PATCH mechanism _merge_run_props uses (PATCH the
# runs row by id). The phase strings are byte-exact to what BuildProgress.tsx maps:
#   planning -> Planning; pricing/awaiting_payment -> Pricing; producing -> Producing.
#
# Best-effort + NEVER raises (exactly like _emit_event): a stepper write must not
# fail a (paid, delivered) conduct. No-op when run_id is absent / not a UUID.
# --------------------------------------------------------------------------- #
def _set_phase(run_id, phase):
    """PATCH runs.phase for run_id so the web progress stepper advances. Best-effort."""
    if not run_id or not _UUID_RE.match(str(run_id)):
        return
    api_key = os.environ.get("INSFORGE_API_KEY")
    if not api_key:
        return
    try:
        body = json.dumps({"phase": phase}).encode("utf-8")
        url = INSFORGE_URL.rstrip("/") + "/api/database/records/runs?id=eq.%s" % run_id
        req = urllib.request.Request(
            url, data=body, method="PATCH",
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer %s" % api_key})
        _insforge_request(req, "phase PATCH(run %s)" % run_id)
    except Exception as e:
        _log("phase PATCH failed for run %s: %s" % (run_id, e))


# --------------------------------------------------------------------------- #
# FILMSTRIP feed — live scene-production thumbnails (demo showpiece).
#
# run_events has NO structured JSON column (only {run_id,seq,actor,level,msg}),
# so the machine-readable filmstrip payload rides INSIDE `msg` after a fixed
# sentinel. The front-end splits on the sentinel: the head is human-readable log
# text; the tail is a JSON object it parses to drive the filmstrip cards. The
# event KIND is also placed on the `level` column ("storyboard" / "scene_done")
# so the front-end can cheaply filter filmstrip rows without parsing every msg.
#
# Belt-and-suspenders: the SAME data is mirrored into runs.props (scenes[] +
# scene_thumbs{}) — a real JSON column — so the front-end has a durable, no-parse
# source for the initial render even if it misses live events.
# --------------------------------------------------------------------------- #
FILMSTRIP_MARK = " ::FILMSTRIP:: "


def _emit_filmstrip_event(run_id, human_msg, payload, level, actor="hermes"):
    """Emit one filmstrip run_event: human text + sentinel + compact JSON tail.

    `level` is the discriminator ("storyboard" | "scene_done"). Best-effort.
    """
    try:
        tail = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except Exception as e:
        _log("filmstrip payload not serializable: %s" % e)
        return
    _emit_event(run_id, human_msg + FILMSTRIP_MARK + tail, actor=actor, level=level)


_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _insforge_get(path):
    """GET an InsForge PostgREST endpoint, return parsed JSON or None. Best-effort."""
    api_key = os.environ.get("INSFORGE_API_KEY")
    if not api_key:
        return None
    url = INSFORGE_URL.rstrip("/") + path
    req = urllib.request.Request(
        url, method="GET",
        headers={"Authorization": "Bearer %s" % api_key})
    body = _insforge_request(req, "GET %s" % path)
    if body is None:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except Exception as e:
        _log("insforge GET parse failed (%s): %s" % (path, e))
        return None


def _merge_run_props(run_id, patch):
    """Merge `patch` into runs.props for run_id (read-modify-write). Best-effort.

    runs.props is a free-form JSON column already carrying
    {conducted_by, produced_on, producer}. We GET the current props, shallow-merge
    the new keys (scenes / scene_thumbs), and PATCH the row back. Never raises — a
    props write must not fail a (paid, delivered) conduct. The run_events feed is
    the live driver; this column is the durable, no-parse fallback for the UI.
    """
    if not run_id or not _UUID_RE.match(str(run_id)):
        return
    api_key = os.environ.get("INSFORGE_API_KEY")
    if not api_key:
        return
    try:
        cur_rows = _insforge_get(
            "/api/database/records/runs?id=eq.%s&limit=1" % run_id)
        cur = {}
        if isinstance(cur_rows, list) and cur_rows:
            cur = cur_rows[0].get("props") or {}
        if not isinstance(cur, dict):
            cur = {}
        # deep-merge one level for dict values (e.g. scene_thumbs index map) so a
        # later scene_thumbs patch does not clobber earlier indices.
        merged = dict(cur)
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                m = dict(merged[k])
                m.update(v)
                merged[k] = m
            else:
                merged[k] = v
        body = json.dumps({"props": merged}).encode("utf-8")
        url = INSFORGE_URL.rstrip("/") + "/api/database/records/runs?id=eq.%s" % run_id
        req = urllib.request.Request(
            url, data=body, method="PATCH",
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer %s" % api_key})
        _insforge_request(req, "props PATCH(run %s)" % run_id)
    except Exception as e:
        _log("props PATCH failed for run %s: %s" % (run_id, e))


def _resolve_run_id(args):
    """Return the REAL InsForge runs.id (UUID) the feed events attach to.

    Robust against the conductor agent (Hermes) failing to thread the run_id or
    hallucinating a non-UUID slug (observed: it passed a human-readable string that
    InsForge rejected as `invalid input syntax for type uuid`). Resolution order:

      1. A passed `run_id` that is a valid UUID -> use it verbatim.
      2. The cached plan's `_run_id` (set by the plan tool) if a valid UUID.
      3. DETERMINISTIC FALLBACK: look up the most recent `runs` row for this
         company_url whose status is an in-flight conduct (running / planning /
         hermes_conducting), and use its UUID. This is the bulletproof path — it
         does not depend on the agent passing anything correct, only on the url
         (which the tools always receive).

    Returns a UUID string or None (then _emit_event is a quiet no-op).
    """
    rid = (args.get("run_id") or "").strip()
    if rid and _UUID_RE.match(rid):
        return rid
    # try the cached plan handle's run_id
    plan, _pid, _err = _resolve_plan(args)
    if isinstance(plan, dict):
        prid = (plan.get("_run_id") or "").strip()
        if prid and _UUID_RE.match(prid):
            return prid
    # deterministic fallback by company_url (when we have one)
    url = (args.get("url") or "").strip()
    if not url and isinstance(plan, dict):
        url = ((plan.get("job") or {}).get("company_url") or "").strip()
    if url:
        # query the IN-FLIGHT run for this url (authoritative: a new conduct flips
        # any prior run to delivered, so only the current conduct matches these
        # statuses). No caching: one cheap GET per tool always hits the live run.
        import urllib.parse as _up
        q = ("/api/database/records/runs?company_url=eq.%s"
             "&status=in.(running,planning,hermes_conducting)"
             "&order=created_at.desc&limit=1" % _up.quote(url, safe=""))
        rows = _insforge_get(q)
        if isinstance(rows, list) and rows:
            rid = rows[0].get("id")
            if rid and _UUID_RE.match(str(rid)):
                return rid
    # FINAL fallback (for the `gate` tool, which receives neither url nor plan_id):
    # the live claimer processes ONE job at a time, so there is at most ONE in-flight
    # conduct. Resolve to the single most-recent run still in an in-flight status,
    # regardless of url. Safe because conducts are serialized by the daemon.
    rows2 = _insforge_get(
        "/api/database/records/runs?status=in.(running,planning,hermes_conducting)"
        "&order=created_at.desc&limit=1")
    if isinstance(rows2, list) and rows2:
        rid = rows2[0].get("id")
        if rid and _UUID_RE.match(str(rid)):
            return rid
    return None


def _run_id_of(args):
    """Back-compat shim: resolve the real run_id (see _resolve_run_id)."""
    return _resolve_run_id(args)


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
    run_id = _run_id_of(args)
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

    # LIVE FEED: the Conversion Read is the NVIDIA Nemotron brain scoring the page.
    # Tag actor=nemotron (fixes the old mis-tag where the Read read as hermes).
    dims = read.get("dimensions", []) if isinstance(read, dict) else []
    scored = sum(1 for d in dims if isinstance(d, dict) and d.get("score") is not None)
    verdict = (read.get("verdict") if isinstance(read, dict) else "") or ""
    verdict_short = verdict if len(verdict) <= 240 else (verdict[:237] + "…")
    _emit_event(
        run_id,
        "Reading the page on NVIDIA Nemotron — scored %d dimensions "
        "(promise/outcome/proof/show/specificity/cta): %s"
        % (scored or len(dims), verdict_short or "(read complete)"),
        actor="nemotron")

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

    # PROGRESS STEPPER: advance the web run page to "Planning" at the START of this
    # tool (byte-exact "planning" — BuildProgress.tsx maps it to the Planning stage).
    run_id = _run_id_of(args)
    _set_phase(run_id, "planning")

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
    scene_types = [s.get("type") for s in scenes]

    # Cache the full plan server-side and return only a SHORT plan_id handle.
    # The plan NEVER round-trips through Hermes's tokens (kills the u2014 bug).
    plan_id = (args.get("plan_id") or args.get("run_key") or "").strip() or (_slug(url) + "-mcp")
    plan["_plan_id"] = plan_id
    # Persist the run_id on the cached plan so price/produce_and_ship can emit feed
    # events without the conductor having to re-thread it into every tool call.
    # (run_id already resolved at the top of this tool for the phase update.)
    if run_id:
        plan["_run_id"] = run_id
    try:
        cache_path = _cache_plan(plan, plan_id)
    except Exception as e:
        return {"ok": False, "error": "plan cache write failed: %s" % e}

    # LIVE FEED: NVIDIA Nemotron returned the storyboard plan. actor=nemotron.
    _emit_event(
        run_id,
        "NVIDIA Nemotron planned the storyboard — %d scenes (%s)"
        % (len(scenes), ", ".join(t for t in scene_types if t) or "—"),
        actor="nemotron")

    # FILMSTRIP: storyboard event — list the PLANNED scenes so the run page can
    # render every filmstrip card up front as "pending" before any render finishes.
    # level="storyboard"; structured tail = {event, count, scenes:[{index,type,label,headline}]}.
    # Mirrored into runs.props.scenes as the durable, no-parse source.
    try:
        storyboard = _storyboard_from_plan(plan)
        _emit_filmstrip_event(
            run_id,
            "Storyboard ready — %d scenes" % len(storyboard),
            {"event": "storyboard", "count": len(storyboard), "scenes": storyboard},
            level="storyboard", actor="hermes")
        _merge_run_props(run_id, {"scenes": storyboard})
    except Exception as e:
        _log("storyboard filmstrip emit skipped: %s" % e)

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
def _elevenlabs_cogs_cents(plan):
    """ElevenLabs char cost for the plan's VO script (rate from producer.py).
    The render uses ElevenLabs as the default VO, so this is a real COGS line."""
    try:
        import producer
        vo = plan.get("voiceover") or {}
        cents, _note = producer.estimate_voiceover_cents(vo)
        return int(cents or 0)
    except Exception:
        return 0


def _real_token_cogs_cents(plan):
    """REAL per-run LLM (Nemotron via OpenRouter) COGS in cents.

    The planner records the EXACT OpenRouter spend at plan["selection"]
    ["planner_usage"]["cost"] (USD; e.g. 0.0027683). That is the real cost of the
    PLAN call. The Conversion Read + design_brief calls run earlier and do NOT
    persist their usage.cost, so we add a small token-rate estimate for them from
    their recorded token counts when available, else a flat conservative estimate.
    Returns (cents, breakdown_dict). Best-effort; never raises.
    """
    sel = (plan.get("selection") or {}) if isinstance(plan, dict) else {}
    usage = sel.get("planner_usage") or {}
    plan_cost_usd = 0.0
    try:
        plan_cost_usd = float(usage.get("cost") or 0.0)
    except (TypeError, ValueError):
        plan_cost_usd = 0.0
    plan_cost_cents = plan_cost_usd * 100.0

    # Conversion Read + design_brief: usage.cost is not persisted by analyze.py, so
    # ESTIMATE from a token-rate. The Read+brief are smaller than the plan call; a
    # conservative estimate is ~60% of the plan-call cost (two Nemotron calls of
    # similar prompt size, shorter completions). If there is no real plan cost
    # (template fallback / super-free), fall back to a flat 0.20c floor so a run
    # that DID hit Nemotron never reports COGS = 0.
    read_est_cents = round(plan_cost_cents * 0.6, 4) if plan_cost_cents > 0 else 0.0

    token_cents = plan_cost_cents + read_est_cents
    return token_cents, {
        "plan_call_usd": round(plan_cost_usd, 6),
        "plan_call_cents": round(plan_cost_cents, 4),
        "read_brief_estimate_cents": round(read_est_cents, 4),
        "method": ("real plan usage.cost + ~0.6x estimate for the Conversion Read "
                   "+ design_brief calls (their usage.cost is not persisted)"),
    }


def tool_price(args):
    plan, plan_id, err = _resolve_plan(args)
    if err:
        return {"ok": False, "error": err}
    run_id = _run_id_of(args) or (plan.get("_run_id") if isinstance(plan, dict) else None)
    # PROGRESS STEPPER: advance the web run page to "Pricing" (byte-exact "pricing").
    _set_phase(run_id, "pricing")
    try:
        import producer
    except Exception as e:
        return {"ok": False, "error": "import producer failed: %s" % e}
    try:
        est = producer.cmd_estimate(plan)
    except Exception as e:
        return {"ok": False, "error": "cmd_estimate failed: %s" % e}

    # FIX #4 — REAL per-run COGS: actual Nemotron/OpenRouter token spend
    # (planner usage.cost + a Read/brief estimate) + the real ElevenLabs char cost.
    # The producer estimate's total_cogs_cents is a token-RATE estimate; replace it
    # with the real spend so the owner-COGS + analytics show true profit.
    token_cents, cogs_breakdown = _real_token_cogs_cents(plan)
    vo_cents = _elevenlabs_cogs_cents(plan)
    real_cogs_cents = int(math.ceil(token_cents + vo_cents))
    cogs_breakdown["elevenlabs_cents"] = vo_cents
    cogs_breakdown["total_real_cogs_cents"] = real_cogs_cents

    # FIX #5 — cap the customer price at $10 (PRICE_CAP_CENTS). The cost-plus menu
    # can quote up to the premium band ($25); clamp so every video is <= $10. Price
    # still covers COGS (cap >> a few cents of token+VO spend) → always profitable.
    raw_price = est.get("suggested_price_cents")
    try:
        capped_price = min(int(raw_price), PRICE_CAP_CENTS) if raw_price is not None else PRICE_CAP_CENTS
    except (TypeError, ValueError):
        capped_price = PRICE_CAP_CENTS
    # Profit floor: never let the capped price dip below COGS (it never should —
    # COGS is cents, the cap is $10 — but assert the invariant defensively).
    if capped_price < real_cogs_cents:
        capped_price = min(PRICE_CAP_CENTS, max(real_cogs_cents, capped_price))

    profit_cents = capped_price - real_cogs_cents

    # LIVE FEED: the priced decision. Tag actor=stripe (the money rail).
    _emit_event(
        run_id,
        "Priced at $%.2f (capped at $%.2f)."
        % (capped_price / 100.0, PRICE_CAP_CENTS / 100.0),
        actor="stripe")

    return {
        "ok": True,
        "step": "price",
        "plan_id": plan_id,
        "price_cents": capped_price,
        "price_cents_uncapped": raw_price,
        "price_cap_cents": PRICE_CAP_CENTS,
        "cogs_cents": real_cogs_cents,
        "cogs_breakdown": cogs_breakdown,
        "profit_cents": profit_cents,
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
    except (TypeError, ValueError):
        return {"ok": False, "error": "price_cents (int) is required"}
    # budget is optional now (always-proceed policy). Default to the price cap so
    # the effective budget is >= every possible (capped) price.
    try:
        budget_cents = int(args.get("budget_cents"))
    except (TypeError, ValueError):
        budget_cents = PRICE_CAP_CENTS
    run_id = _run_id_of(args)

    # FIX #5 — the agent NEVER declines. With every price capped at $10 (price tool)
    # and the budget effectively >= $10, the budget check always passes. We treat the
    # budget as max(budget, price_cap) so the gate ALWAYS proceeds — no decline path.
    effective_budget = max(budget_cents, PRICE_CAP_CENTS)
    proceed = True  # always proceed: price <= cap <= effective budget by construction
    reason = ("Budget check — price $%.2f within budget $%.2f — PROCEED"
              % (price_cents / 100.0, effective_budget / 100.0))

    # LIVE FEED: the agent's money decision. actor=hermes (the harness decides).
    _emit_event(run_id, "Budget check — proceeding (price $%.2f, budget $%.2f)"
                % (price_cents / 100.0, effective_budget / 100.0), actor="hermes")

    return {
        "ok": True,
        "step": "gate",
        "proceed": proceed,
        "reason": reason,
        "price_cents": price_cents,
        "budget_cents": effective_budget,
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


# --------------------------------------------------------------------------- #
# FILMSTRIP scene summaries — the per-card descriptor the front-end shows.
# Two call sites, two scene shapes:
#   * tool_plan      -> plan["scenes"]  (id, type, brief)            -> storyboard
#   * produce_and_ship -> props["scenes"] (id, archetype, data{...}) -> scene_done
# Both reduce to {index, type, label, headline}. Index is 0-based and stable
# across the two passes (plan scenes map 1:1 to props scenes by position/id).
# --------------------------------------------------------------------------- #
_TYPE_LABELS = {
    "title": "Title", "screenshot": "Screenshot", "motion_graphic": "Motion graphic",
    "walkthrough": "Walkthrough", "hero-title": "Title", "apple-screenshot": "Screenshot",
    "explainer-card": "Feature", "split-stat": "Stat", "split-mosaic": "Mosaic",
    "icon-stat": "Stat", "icon-headline": "Headline", "logo-wall": "Logo wall",
    "walkthrough-player": "Walkthrough",
}


def _clip(s, n=72):
    s = (s or "").strip()
    return s if len(s) <= n else (s[: n - 1].rstrip() + "…")


def _label_for_type(t):
    if not t:
        return "Scene"
    return _TYPE_LABELS.get(t, t.replace("_", " ").replace("-", " ").title())

# Plan scene `type`/`role` -> render `archetype`, mirroring style_fill.py's
# Style.role_map. The STORYBOARD (planned cards) is built from plan `type`
# (e.g. "motion_graphic"); the per-scene RENDER pass labels from the rendered
# `archetype` (e.g. "explainer-card"). Without this the SAME scene showed
# "Motion graphic" in the storyboard and "Feature" once rendered. Resolving the
# plan type to its archetype here makes BOTH passes label a scene identically.
# (Kept in sync with style_fill role_map; the dominant feature beats —
# motion_graphic/feature/cinematic/explainer — all render as explainer-card.)
_TYPE_TO_ARCHETYPE = {
    "open": "hero-title", "hero": "hero-title", "title": "hero-title",
    "intro": "hero-title", "close": "hero-title", "cta": "hero-title",
    "outro": "hero-title",
    "feature": "explainer-card", "motion_graphic": "explainer-card",
    "motion-graphic": "explainer-card", "cinematic": "explainer-card",
    "explainer": "explainer-card",
    "capability": "card-ui", "capabilities": "card-ui",
    "cards": "card-ui", "grid": "card-ui",
    "walkthrough": "walkthrough-player", "demo": "walkthrough-player",
    "screenshot": "apple-screenshot", "site": "apple-screenshot",
}


def _archetype_for_plan_type(t):
    """Resolve a plan scene type/role to the render archetype it becomes, so the
    storyboard label matches the per-scene scene_done label. Unknown types pass
    through unchanged (labeled via the same title-case fallback as before)."""
    if not t:
        return ""
    return _TYPE_TO_ARCHETYPE.get(t, t)


def _storyboard_from_plan(plan):
    """[{index, type, label, headline}] from the plan's scenes (pending cards).

    The plan carries a coarse `type` (e.g. "motion_graphic"); the render labels
    from the resolved `archetype` (e.g. "explainer-card"). We resolve the plan
    type to that archetype HERE so a scene shows ONE consistent label across the
    storyboard and the per-scene scene_done event (no "Motion graphic" -> "Feature"
    flip mid-run)."""
    out = []
    for i, s in enumerate(_safe_scenes(plan)):
        t = s.get("type") or s.get("role") or ""
        arch = _archetype_for_plan_type(t)
        head = (s.get("headline") or s.get("title") or s.get("label")
                or s.get("brief") or "")
        out.append({
            "index": i,
            "type": arch,
            "label": _label_for_type(arch),
            "headline": _clip(head),
        })
    return out


def _scene_descriptor_from_props(scene, index):
    """{index, type, label, headline} from a rendered props scene (done card)."""
    d = scene.get("data") or {}
    arch = scene.get("archetype") or ""
    head = (d.get("headline") or d.get("title") or d.get("punchWord")
            or d.get("kicker") or scene.get("id") or "")
    return {
        "index": index,
        "type": arch,
        "label": _label_for_type(arch),
        "headline": _clip(head),
    }


def _safe_scenes(obj):
    if isinstance(obj, dict):
        sc = obj.get("scenes")
        if isinstance(sc, list):
            return [s for s in sc if isinstance(s, dict)]
    return []


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
    Returns (final_url_or_None, info_dict).

    BOUNDED + RETRIED: the upload subprocess is per-attempt timeout-capped (the node
    uploader's own remove+upload is idempotent, so a retry is safe) and retried up to
    UPLOAD_ATTEMPTS times with backoff on a timeout / non-ok result. The rendered
    video.mp4 stays on disk regardless, so an ultimate upload failure does NOT lose
    the video — produce_and_ship returns final_url=None and the caller can re-ship."""
    if not os.path.exists(INSFORGE_UPLOADER):
        return None, {"error": "uploader missing: %s" % INSFORGE_UPLOADER}
    # SIZE CAP (corrected 2026-07-02): the @insforge/sdk .upload() PRESIGNS and sends the
    # bytes DIRECT to AWS S3 — verified by tracing a real upload: the InsForge gateway only
    # handles the small strategy/confirm calls, it does NOT proxy the body (so there is no
    # gateway 413; the old "20-30MB gateway limit" note was wrong). The real ceiling is the
    # instance's storage max_file_size, checked at strategy time: empirically ~50MB on this
    # instance (a 40MB upload succeeds; 90MB is rejected 400 BEFORE any bytes move). Cap at
    # 45MB (safe margin under ~50MB) so an over-limit file is skipped here — kept on disk,
    # produce_and_ship returns final_url=None, re-shippable — instead of a doomed attempt.
    upload_max = int(os.environ.get("UPLOAD_MAX_BYTES", str(45 * 1024 * 1024)))
    try:
        sz = os.path.getsize(mp4_path)
    except OSError as e:
        return None, {"error": "stat failed: %s" % e}
    if sz > upload_max:
        _log("upload %s SKIPPED: %.1fMB > %dMB cap (over instance storage max_file_size); file kept at %s"
             % (object_key, sz / 1048576.0, upload_max // 1048576, mp4_path))
        return None, {"error": "file too large (%.1fMB > %dMB storage cap); kept on disk for re-ship"
                      % (sz / 1048576.0, upload_max // 1048576), "too_large": True}
    env = dict(os.environ)
    env.setdefault("INSFORGE_URL", INSFORGE_URL)
    if not env.get("INSFORGE_API_KEY"):
        return None, {"error": "INSFORGE_API_KEY not in env"}
    # RETRY (hardened, 2026-07-02): the video is ALREADY rendered on disk, so retrying
    # loops ONLY the ~7s upload — never a re-render. Default 6 attempts with EXPONENTIAL
    # backoff (2,4,8,16,32s) absorbs a transient InsForge 408 REQUEST_TIMEOUT blip so
    # produce_and_ship returns a real final_url on the FIRST call and the Hermes agent
    # never re-calls it (a re-call re-runs capture+render — the ~15min loop we saw on
    # insforge.dev). A total wall-time budget bounds the worst case if InsForge is truly
    # down (retrying can't help then; fail cleanly instead of stalling the conduct).
    attempts = int(os.environ.get("UPLOAD_ATTEMPTS", "6"))
    per_attempt_timeout = int(os.environ.get("UPLOAD_TIMEOUT", "180"))
    backoff_base = float(os.environ.get("UPLOAD_BACKOFF_BASE", "2.0"))
    backoff_cap = float(os.environ.get("UPLOAD_BACKOFF_CAP", "32"))
    total_budget = float(os.environ.get("UPLOAD_TOTAL_BUDGET_S", "150"))
    _t_start = time.time()
    last_info = {"error": "upload not attempted"}

    def _retry_ok(i):
        # Sleep before the next attempt, unless we're out of attempts OR over the
        # wall-time budget. Returns True to `continue` (retry), False to stop.
        if i >= attempts - 1:
            return False
        if (time.time() - _t_start) >= total_budget:
            _log("upload %s: retry budget %.0fs exhausted after %d attempts"
                 % (object_key, total_budget, i + 1))
            return False
        time.sleep(min(backoff_base * (2 ** i), backoff_cap))
        return True

    for i in range(attempts):
        try:
            proc = subprocess.run(
                [NODE_BIN, INSFORGE_UPLOADER, os.path.abspath(mp4_path), object_key],
                cwd=WORKER_DIR, capture_output=True, text=True,
                timeout=per_attempt_timeout, env=env,
            )
        except subprocess.TimeoutExpired:
            last_info = {"error": "upload timed out (attempt %d/%d)" % (i + 1, attempts)}
            _log("upload %s: %s" % (object_key, last_info["error"]))
            if _retry_ok(i):
                continue
            break
        out = (proc.stdout or "").strip().splitlines()
        last = out[-1] if out else ""
        try:
            res = json.loads(last)
        except Exception:
            last_info = {"error": "non-JSON upload output", "stderr": (proc.stderr or "")[-800:],
                         "stdout": (proc.stdout or "")[-800:]}
            if _retry_ok(i):
                continue
            break
        if not res.get("ok"):
            last_info = {"error": res.get("error"), "stderr": (proc.stderr or "")[-800:]}
            _log("upload %s failed (attempt %d/%d): %s" % (object_key, i + 1, attempts, res.get("error")))
            if _retry_ok(i):
                continue
            break
        return res.get("url"), {"key": res.get("key"), "bucket": res.get("bucket")}
    return None, last_info


# Per-scene editor assets (logo / screenshots / VO mp3s / music) that style_fill
# stages into studio/public/ with run-scoped names (<...>-<slug_run_key>...). The
# editor (web/app/runs/[id]/edit/page.tsx) resolves BARE asset filenames against
#   ${INSFORGE_URL}/api/storage/buckets/walk-videos/objects/${runs.run_key}/<name>
# i.e. namespaced by the *database* runs.run_key (e.g. web-1782749600146-zsurh),
# NOT the slug run_key (ycombinator-com-mcp) used as the on-disk run dir / video
# object prefix. The deterministic worker/run.js path uploads these via
# uploadRunAssets(runKey) -> putObject(`${runKey}/${name}`); produce_and_ship
# previously shipped ONLY video.mp4 + scene thumbnails, so the editor's <Img>/
# <Audio> URLs 404'd while scrubbing a Hermes-conducted run. This mirrors
# uploadRunAssets so future Hermes videos load in the editor.
def _studio_public_dir():
    """studio/public/ — where style_fill stages run-scoped editor assets."""
    return os.path.join(HERE, "studio", "public")


def _db_run_key(run_id):
    """The DB runs.run_key (UUID-keyed) the editor namespaces asset URLs under.

    Returns None when run_id is not a UUID or the lookup fails — the caller then
    skips the per-scene asset upload (best-effort; never fails a paid conduct)."""
    if not run_id or not _UUID_RE.match(str(run_id)):
        return None
    rows = _insforge_get(
        "/api/database/records/runs?id=eq.%s&select=run_key&limit=1" % run_id)
    if isinstance(rows, list) and rows:
        rk = rows[0].get("run_key")
        if isinstance(rk, str) and rk.strip():
            return rk.strip()
    return None


def _upload_run_assets_to_insforge(run_id, slug_run_key):
    """Upload every studio/public/* asset whose name contains slug_run_key to the
    walk-videos bucket under the DB runs.run_key namespace (so the editor's bare
    asset URLs resolve). Mirrors worker/run.js stagedAssetNames + uploadRunAssets.

    Best-effort + isolated: a missing dir, a failed DB lookup, or any single
    upload failure is logged and skipped; never raises. Returns
    {db_run_key, uploaded:[names], failed:[names]} (or {} when skipped)."""
    db_run_key = _db_run_key(run_id)
    if not db_run_key:
        _log("per-scene asset upload skipped: no DB run_key for run %s" % run_id)
        return {}
    pub = _studio_public_dir()
    if not os.path.isdir(pub):
        _log("per-scene asset upload skipped: studio/public missing (%s)" % pub)
        return {"db_run_key": db_run_key, "uploaded": [], "failed": []}
    try:
        names = [f for f in os.listdir(pub)
                 if slug_run_key in f and os.path.isfile(os.path.join(pub, f))]
    except Exception as e:
        _log("per-scene asset upload: listdir failed: %s" % e)
        return {"db_run_key": db_run_key, "uploaded": [], "failed": []}
    uploaded, failed = [], []
    for name in names:
        src = os.path.join(pub, name)
        object_key = "%s/%s" % (db_run_key, name)
        url, _info = _upload_to_insforge(src, object_key)
        if url:
            uploaded.append(name)
        else:
            failed.append(name)
            _log("per-scene asset upload failed: %s -> %s (%s)"
                 % (name, object_key, _info.get("error") if isinstance(_info, dict) else _info))
    _log("per-scene editor assets: %d/%d uploaded to %s/ (run %s)"
         % (len(uploaded), len(names), db_run_key, run_id))
    return {"db_run_key": db_run_key, "uploaded": uploaded, "failed": failed}


# --------------------------------------------------------------------------- #
# VERIFY-AND-HEAL — the permanent guarantee that every editor asset resolves.
#
# The generic upload above (_upload_run_assets_to_insforge) covers the happy path,
# but two failure modes can still ship a video with editor assets that 404 while
# scrubbing: (a) _db_run_key returns None (non-UUID run_id / DB blip) so the upload
# is skipped entirely; (b) the worker's recoverShippedVideo fallback ships a video
# WITHOUT re-running the per-scene upload. This bug ("logo + screenshot blank in the
# editor") has recurred across #50/#106/#111 because the upload was best-effort and
# nothing verified it AFTER the fact.
#
# This pass makes the upload SELF-CORRECTING and runs at the END of EVERY produce so
# it cannot be skipped. It is fully DATA-DRIVEN: it walks the FINAL props for every
# asset-ish string (so a NEW scene type / field is covered automatically — no
# hardcoded list), and for each:
#   - skips inline data: URIs and already-full http(s) URLs (those always resolve);
#   - resolves a bare/relative name against the DB run_key namespace (exactly what
#     the editor's makeResolveAsset builds), then HEAD/GETs it;
#   - on miss (404/non-200) RE-UPLOADS the staged file from studio/public/ and
#     REWRITES the props field to the FULL https URL (prefix-independent: it then
#     resolves regardless of run_key, and Remotion renders full URLs fine), then
#     re-checks;
#   - if it STILL can't resolve after healing, logs a LOUD error AND records a
#     run_event (actor=system, level=error) so the failure is VISIBLE, never silent.
# Returns a summary {checked, healed:[...], unresolved:[...]} and the (possibly
# rewritten) props are persisted by the caller's rich-props merge.
# --------------------------------------------------------------------------- #

# Fields whose string values are asset references. Used only to DECIDE which leaf
# strings to check while walking props generically; the walk itself is structural
# (recurses every dict/list) so a new scene archetype is covered without edits here.
_ASSET_FIELD_HINTS = (
    "logoSrc", "imageSrc", "videoSrc", "audioSrc", "src", "music",
    "audio_path", "music_path", "cornerMark", "posterSrc", "bgSrc",
)
# File extensions that mark a bare/relative string as a real asset to verify.
_ASSET_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif",
               ".mp3", ".wav", ".m4a", ".aac", ".mp4", ".webm", ".mov")


def _looks_like_asset_value(key, val):
    """True iff `val` is a bare/relative asset filename we should verify+heal.

    Skips inline data: URIs and full http(s) URLs (always resolvable). Catches a
    value either because its KEY is a known asset field OR because the string ends
    in a known asset extension — so an unknown new field still gets verified."""
    if not isinstance(val, str) or not val.strip():
        return False
    low = val.strip().lower()
    if low.startswith("data:") or low.startswith("http://") or low.startswith("https://"):
        return False
    if val.startswith("/"):  # absolute public path — render-only, not bucketed
        return False
    key_hit = isinstance(key, str) and (key in _ASSET_FIELD_HINTS)
    ext_hit = low.endswith(_ASSET_EXTS)
    return key_hit or ext_hit


def _walk_asset_refs(node, key=None):
    """Yield (container, container_key_or_index, value) for every asset-ish leaf
    string in `node`, recursing all dicts/lists. The container+key let the caller
    REWRITE the value in place (props mutated -> persisted by the rich-props merge)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if _looks_like_asset_value(k, v):
                yield (node, k, v)
            elif isinstance(v, (dict, list)):
                yield from _walk_asset_refs(v, k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if _looks_like_asset_value(key, v):
                yield (node, i, v)
            elif isinstance(v, (dict, list)):
                yield from _walk_asset_refs(v, key)


def _object_url_resolves(object_key):
    """HEAD/GET walk-videos/objects/<object_key>; True iff it ultimately 200s.

    Mirrors what the editor + a browser do: the storage endpoint 302-redirects to
    the object, so we follow redirects and accept only a final 200. Bounded; any
    error (network/timeout) is treated as 'does not resolve' so we heal it."""
    base = INSFORGE_URL.rstrip("/") + "/api/storage/buckets/walk-videos/objects/"
    url = base + urllib.parse.quote(object_key, safe="")
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=20) as resp:
            return 200 <= getattr(resp, "status", resp.getcode()) < 300
    except Exception:
        return False


def _verify_and_heal_assets(run_id, props, run_dir):
    """Walk FINAL props; ensure every asset reference resolves in storage. Heal any
    that don't (re-upload from studio/public/ or the run dir, rewrite props to the
    full URL), and LOUDLY report anything still unresolved. Best-effort; never
    raises. Mutates `props` in place. Returns a summary dict."""
    summary = {"checked": 0, "ok": 0, "healed": [], "unresolved": [], "skipped_no_run_key": False}
    if not isinstance(props, dict):
        return summary
    db_run_key = _db_run_key(run_id)
    if not db_run_key:
        # Without the DB run_key we cannot build the editor's namespace. This is the
        # exact silent-skip hole — make it LOUD instead of returning quietly.
        summary["skipped_no_run_key"] = True
        _log("ASSET-CHECK: no DB run_key for run %s — cannot verify editor assets" % run_id)
        _emit_event(run_id,
                    "asset_check: no DB run_key, editor assets unverifiable for run %s" % run_id,
                    actor="system", level="error")
        return summary
    pub = _studio_public_dir()
    base_url = (INSFORGE_URL.rstrip("/")
                + "/api/storage/buckets/walk-videos/objects/")
    seen = {}  # filename -> resolved full url (so we check/heal each object once)
    for container, ckey, val in list(_walk_asset_refs(props)):
        name = val.strip().lstrip("/")
        summary["checked"] += 1
        object_key = "%s/%s" % (db_run_key, name)
        full_url = base_url + urllib.parse.quote(object_key, safe="")
        # Resolve once per unique filename.
        if name in seen:
            container[ckey] = seen[name]
            continue
        if _object_url_resolves(object_key):
            summary["ok"] += 1
            container[ckey] = full_url        # rewrite to prefix-independent URL
            seen[name] = full_url
            continue
        # MISS -> heal: find the staged source (studio/public first, then run dir).
        src = None
        for cand in (os.path.join(pub, name), os.path.join(run_dir or "", name)):
            if cand and os.path.isfile(cand):
                src = cand
                break
        if not src:
            _log("ASSET-CHECK: %s 404 and no local source to heal (run %s)" % (name, run_id))
            _emit_event(run_id, "asset_check: %s unresolved (no local source)" % name,
                        actor="system", level="error")
            summary["unresolved"].append(name)
            continue
        url, _info = _upload_to_insforge(src, object_key)
        if url and _object_url_resolves(object_key):
            container[ckey] = full_url
            seen[name] = full_url
            summary["healed"].append(name)
            _log("ASSET-CHECK: healed %s -> %s (run %s)" % (name, object_key, run_id))
        else:
            _log("ASSET-CHECK: %s STILL unresolved after heal (run %s): %s"
                 % (name, run_id, _info.get("error") if isinstance(_info, dict) else _info))
            _emit_event(run_id, "asset_check: %s unresolved after re-upload" % name,
                        actor="system", level="error")
            summary["unresolved"].append(name)
    _log("ASSET-CHECK run %s: checked=%d ok=%d healed=%d unresolved=%d"
         % (run_id, summary["checked"], summary["ok"],
            len(summary["healed"]), len(summary["unresolved"])))
    if summary["unresolved"]:
        _emit_event(run_id,
                    "asset_check: %d editor asset(s) unresolved: %s"
                    % (len(summary["unresolved"]), ", ".join(summary["unresolved"])),
                    actor="system", level="error")
    return summary


def _scene_thumb_time_s(scene, fps, total_frames):
    """Pick a representative timestamp (seconds) inside a scene to grab a frame.

    Uses the scene's MIDPOINT between in_frame/out_frame (so we miss the
    cross-scene transition wipes that bookend each clip and land on the held
    composition). Clamped to [0, (total_frames-1)/fps]. Robust to missing fields.
    """
    fps = fps or 30
    try:
        a = int(scene.get("in_frame") or 0)
    except Exception:
        a = 0
    try:
        b = int(scene.get("out_frame") or (a + fps))
    except Exception:
        b = a + fps
    if b <= a:
        b = a + fps
    mid = a + int((b - a) * 0.55)  # slightly past center: clears the entrance anim
    if total_frames:
        mid = min(mid, max(0, int(total_frames) - 1))
    return max(0.0, mid / float(fps))


def _emit_scene_thumbnails(run_id, props, video_path, run_key):
    """FILMSTRIP per-scene pass: one frame -> PNG -> bucket -> scene_done event.

    For each rendered scene (props["scenes"]) extract a frame from the final
    video.mp4 at the scene midpoint (ffmpeg), upload it to the SAME walk-videos
    bucket under <run_key>/thumbs/scene-NN.png, and emit a `scene_done` run_event
    carrying {index, type, label, headline, thumbnail_url, status:"done"}. Also
    mirrors index->url into runs.props.scene_thumbs.

    Best-effort + isolated per scene: a single ffmpeg/upload failure emits a
    scene_done with thumbnail_url=null (the card still flips to done) and never
    aborts the conduct. Returns {index: url} for the scenes that uploaded.
    """
    thumbs = {}
    scenes = _safe_scenes(props)
    fps = props.get("fps") or 30
    total = props.get("total_frames")
    n = len(scenes)
    if not scenes or not os.path.exists(video_path):
        return thumbs
    thumb_dir = os.path.join(os.path.dirname(os.path.abspath(video_path)), "thumbs")
    try:
        os.makedirs(thumb_dir, exist_ok=True)
    except Exception:
        pass
    for i, scene in enumerate(scenes):
        desc = _scene_descriptor_from_props(scene, i)
        thumb_url = None
        try:
            t = _scene_thumb_time_s(scene, fps, total)
            png_path = os.path.join(thumb_dir, "scene-%02d.png" % i)
            # one frame at t, downscale to a card-sized 480px-wide preview.
            r = subprocess.run(
                ["ffmpeg", "-y", "-ss", "%.3f" % t, "-i", os.path.abspath(video_path),
                 "-frames:v", "1", "-vf", "scale=480:-1", png_path],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode == 0 and os.path.exists(png_path) and os.path.getsize(png_path) > 0:
                object_key = "%s/thumbs/scene-%02d.png" % (run_key, i)
                thumb_url, _info = _upload_to_insforge(png_path, object_key)
                if thumb_url:
                    thumbs[str(i)] = thumb_url
            else:
                _log("scene %d thumb ffmpeg rc=%s: %s"
                     % (i, r.returncode, (r.stderr or "")[-200:]))
        except Exception as e:
            _log("scene %d thumbnail failed: %s" % (i, e))
        payload = dict(desc)
        payload.update({"event": "scene_done", "status": "done",
                        "thumbnail_url": thumb_url, "scene_count": n})
        human = "Scene %d/%d done — %s%s" % (
            i + 1, n, desc["label"],
            (": %s" % desc["headline"]) if desc["headline"] else "")
        _emit_filmstrip_event(run_id, human, payload,
                              level="scene_done", actor="render")
    # durable mirror: index->url map on runs.props.scene_thumbs
    if thumbs:
        try:
            _merge_run_props(run_id, {"scene_thumbs": thumbs})
        except Exception as e:
            _log("scene_thumbs props merge skipped: %s" % e)
    return thumbs


def tool_produce_and_ship(args):
    url = (args.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "url is required"}

    # Resolve the plan from the plan_id HANDLE (preferred) or inline plan (legacy).
    plan, plan_id, err = _resolve_plan(args)
    if err:
        return {"ok": False, "error": err}
    brand_theme = args.get("brand_theme")
    run_id = _run_id_of(args) or (plan.get("_run_id") if isinstance(plan, dict) else None)
    # PROGRESS STEPPER: advance the web run page to "Producing scenes" (byte-exact
    # "producing") at the START of the produce+ship step.
    _set_phase(run_id, "producing")

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

    # 1) real website screenshots (best-effort, $0).
    #    The run_key is derived from the url slug, so EVERY conduct of the same site
    #    reuses one run dir (e.g. stripe-com-mcp). _capture_screenshots_for_run is
    #    IDEMPOTENT — it SKIPS capture if screenshots/manifest.json already exists.
    #    That meant a fresh conduct REUSED a stale capture from a PRIOR run that may
    #    pre-date the English-by-default geo override (observed: stale German Stripe
    #    shots persisting across conducts). FIX: clear any stale screenshots/ manifest
    #    so the capture re-runs fresh and the /gb (English) override is applied.
    try:
        import shutil as _shutil
        stale_shots = os.path.join(run_dir, "screenshots")
        if os.path.isdir(stale_shots):
            _shutil.rmtree(stale_shots, ignore_errors=True)
        # also drop the read-pass dir so the Conversion-Read hero is fresh too.
        stale_read = os.path.join(run_dir, "screenshots-read")
        if os.path.isdir(stale_read):
            _shutil.rmtree(stale_read, ignore_errors=True)
    except Exception as e:
        _log("produce_and_ship: could not clear stale screenshots: %s" % e)
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
    #    FRESHNESS GUARD (critical): the run dir is keyed by the URL SLUG
    #    (e.g. stripe-com-mcp), so a STALE video.mp4 from a PRIOR conduct can be
    #    sitting here. style_fill logs "render FAILED" but does NOT raise, so if
    #    this render fails, os.path.exists(video_path) is STILL True for the old
    #    file -> we must not treat that as success and ship a days-old video (this
    #    silently re-shipped one Jun-30 stripe render for ~1.3 days). Require the
    #    file to have been WRITTEN by THIS render (mtime >= our start time).
    _render_t0 = time.time()
    try:
        res = style_fill.run_pipeline(
            plan_path, brand_path, build_runner.VO_ENGINE_STYLE, run_dir,
            fps=30, do_align=True, do_render=True,
        )
    except Exception as e:
        return {"ok": False, "error": "run_pipeline render failed: %s" % e}

    def _is_fresh(p):
        try:
            return bool(p) and os.path.exists(p) and os.path.getmtime(p) >= _render_t0 - 2
        except OSError:
            return False

    video_path = os.path.join(run_dir, "video.mp4")
    if not _is_fresh(video_path):
        # this render did not write a FRESH video.mp4. Try run_pipeline's reported
        # path; else FAIL HONESTLY (never pass off a stale slug-dir artifact as a
        # successful render — the caller/claimer then fails loudly / re-renders
        # instead of delivering an old video).
        rp = (res or {}).get("video_path") if isinstance(res, dict) else None
        if _is_fresh(rp):
            video_path = rp
        else:
            stale = os.path.exists(video_path)
            return {"ok": False,
                    "error": ("render FAILED — no fresh video.mp4 in %s (stale artifact "
                              "present=%s)" % (run_dir, stale)),
                    "run_pipeline_result_keys": sorted((res or {}).keys()) if isinstance(res, dict) else None}

    video_bytes = os.path.getsize(video_path)

    # 4) upload to InsForge walk-videos -> final_url (idempotent remove+upload)
    #    G2 FIX: namespace the BUCKET object by the DB run UUID (run_id), NOT the
    #    url-slug run_key. Two conducts of the SAME site share one slug run_key
    #    (e.g. stripe-com-mcp) and the upload is remove-then-upload, so a slug key
    #    let every same-url job overwrite the previous job's delivered video
    #    (27 delivered runs all pointed at stripe-com-mcp/video.mp4). The DB run
    #    UUID is unique per run, so conducts of the same site never collide. The
    #    LOCAL render dir (run_dir / run_key) is unchanged -- only the bucket key
    #    moves. Fall back to the slug key only if run_id is not a valid UUID (the
    #    claimer recover lists run_id first, then the slug, so both schemes agree).
    if run_id and _UUID_RE.match(str(run_id)):
        object_key = "%s/video.mp4" % run_id
    else:
        object_key = "%s/video.mp4" % run_key
    final_url, up_info = _upload_to_insforge(video_path, object_key)

    # 4b) per-scene EDITOR assets: upload the staged logo / screenshot(s) / VO mp3s
    #     / music to walk-videos under the DB runs.run_key namespace (matching the
    #     editor's bare-filename URL resolution + worker/run.js uploadRunAssets).
    #     Without this the editor's <Img>/<Audio> 404 while scrubbing a Hermes run.
    #     Best-effort + AFTER the video upload so it never delays/fails delivery.
    run_assets = {}
    try:
        run_assets = _upload_run_assets_to_insforge(run_id, run_key)
    except Exception as e:
        _log("per-scene editor asset upload skipped: %s" % e)

    # FILMSTRIP: per-scene previews. The video is ONE Remotion render (not per-scene
    # renders), so we grab a real frame PER SCENE from the finished video.mp4 at each
    # scene's midpoint, upload each PNG to walk-videos, and emit a `scene_done` event
    # per scene carrying its thumbnail_url. Runs AFTER the final upload so it never
    # delays delivery; best-effort so it never fails a (paid) conduct. Uses the
    # RENDERED props (res["props"]) — the authoritative scene boundaries + archetypes.
    scene_thumbs = {}
    try:
        rendered_props = (res or {}).get("props") if isinstance(res, dict) else None
        if not isinstance(rendered_props, dict):
            # fall back to the props.json written by run_pipeline
            pj = os.path.join(run_dir, "props.json")
            if os.path.exists(pj):
                with open(pj, "r", encoding="utf-8") as fh:
                    rendered_props = json.load(fh)
        if isinstance(rendered_props, dict):
            scene_thumbs = _emit_scene_thumbnails(
                run_id, rendered_props, video_path, run_key)
    except Exception as e:
        _log("filmstrip scene-thumbnail pass skipped: %s" % e)

    # LIVE FEED: the produce+ship step done by the Hermes harness. actor=hermes.
    # Emitted AFTER the per-scene scene_done events above so its seq (wall-clock
    # derived, monotonic) sorts LAST: the live log reads price -> budget ->
    # Scene 1/N..N/N done -> "shipped to InsForge", never "shipped" before scenes.
    scene_count = len(plan.get("scenes", [])) if isinstance(plan, dict) else 0
    _emit_event(
        run_id,
        "Captured the page + logo, rendered %d curated scenes, ElevenLabs "
        "voiceover — shipped to InsForge" % scene_count,
        actor="hermes")

    # DURABLE RICH RENDER PROPS: persist the SAME rich props build_runner writes so
    # the editor can load a Hermes-conducted run. The `plan` step only wrote a THIN
    # storyboard ({type,index,label,headline}) to runs.props.scenes — missing the
    # top-level fps/theme/total_frames and the rich per-scene shape
    # ({id,archetype,data,audio,cues,in_frame,out_frame}) the editor's load gates
    # require (Editor total_frames; Timeline archetype/in_frame/out_frame). We merge
    # the rendered props back here, OVERWRITING the thin scenes with the rich scenes.
    # _merge_run_props read-modify-writes, so producer/conducted_by/produced_on/
    # scene_thumbs are preserved (they're not in this patch). Best-effort: a props
    # write must never fail a (paid, delivered) conduct.
    asset_check = {}
    try:
        if not isinstance(rendered_props, dict):
            pj = os.path.join(run_dir, "props.json")
            if os.path.exists(pj):
                with open(pj, "r", encoding="utf-8") as fh:
                    rendered_props = json.load(fh)
        if isinstance(rendered_props, dict):
            # VERIFY-AND-HEAL (intrinsic to produce; runs on EVERY conduct): walk the
            # FINAL props, ensure every editor asset (logo / screenshot / VO / music /
            # scene_thumbs / any new asset field) resolves in storage, re-upload +
            # rewrite-to-full-URL any that 404, and LOUDLY flag anything still broken.
            # Mutates rendered_props IN PLACE so the rewritten full URLs are what the
            # rich-props merge below persists to runs.props.
            try:
                asset_check = _verify_and_heal_assets(run_id, rendered_props, run_dir)
            except Exception as e:
                _log("asset verify-and-heal skipped: %s" % e)
            rich_patch = {}
            # scene_thumbs is a top-level asset map healed above; persist it too so the
            # editor's durable (no-event) source carries verified URLs.
            for k in ("fps", "theme", "total_frames", "audio_path", "lang",
                      "scenes", "scene_thumbs"):
                if k in rendered_props:
                    rich_patch[k] = rendered_props[k]
            if rich_patch:
                _merge_run_props(run_id, rich_patch)
                _log("rich render props merged to runs.props for run %s "
                     "(keys=%s)" % (run_id, ",".join(sorted(rich_patch))))
    except Exception as e:
        _log("rich render props merge skipped: %s" % e)

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
        "scene_thumbs": scene_thumbs,
        "run_assets": run_assets,
        "asset_check": asset_check,
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
                    "run_id": {"type": "string", "description": "The InsForge run id for the LIVE activity feed. Pass the run_id given in the prompt through EVERY tool so the watch-the-agent feed shows each step."},
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
                    "run_id": {"type": "string", "description": "The InsForge run id for the LIVE activity feed (pass through from the prompt)."},
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
                    "run_id": {"type": "string", "description": "The InsForge run id for the LIVE activity feed (pass through from the prompt; also read from the cached plan)."},
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
                "The agent's money decision. With every price capped at $10 and the "
                "budget effectively >= $10, this ALWAYS proceeds (the agent never "
                "refuses a job). Returns {proceed:true, reason}. Call after price, then "
                "run produce_and_ship."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "price_cents": {"type": "integer", "description": "Customer price from price."},
                    "budget_cents": {"type": "integer", "description": "Optional budget ceiling (defaults to the $10 cap)."},
                    "run_id": {"type": "string", "description": "The InsForge run id for the LIVE activity feed (pass through from the prompt)."},
                },
                "required": ["price_cents"],
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
                    "run_id": {"type": "string", "description": "The InsForge run id for the LIVE activity feed (pass through from the prompt; also read from the cached plan)."},
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


# --------------------------------------------------------------------------- #
# CLI REPAIR — heal a RECOVERED run (curated-claimer recoverShippedVideo path).
#
# When a Hermes produce conduct ships the video to the bucket but never echoes its
# "Shipped:" line, the worker delivers via recoverShippedVideo + deliverHermesRun,
# which reads props from the JOB run_key dir — but the render ran under run_key=
# <plan_id> (the brand-derived MCP run dir), so the rich props.json the editor needs
# is at runs/<plan_id>/props.json and the JOB dir does not exist. The delivered run
# then carries THIN props -> the editor shows 0 scenes + blank logo/screenshot/VO.
#
# This entrypoint reruns the produce tail (steps 4+5 of tool_produce_and_ship) for an
# ALREADY-shipped video: load runs/<plan_id>/props.json, verify-and-heal every editor
# asset under the DB run_key namespace (so each HEAD-200s), then merge the rich keys
# onto runs.props. Idempotent + best-effort; the running MCP server is untouched (this
# is a separate short-lived process). Returns 0 on success, 2 on a hard precondition
# failure. Usage: python3 mcp_toolserver.py --heal-recovered <run_id_uuid> <plan_run_key>
# --------------------------------------------------------------------------- #
def _heal_recovered_run(run_id, plan_run_key):
    run_dir = _runs_dir(plan_run_key)
    props_path = os.path.join(run_dir, "props.json")
    if not os.path.isfile(props_path):
        print(json.dumps({"ok": False, "error": "no props.json at %s" % props_path}))
        return 2
    try:
        with open(props_path, "r", encoding="utf-8") as fh:
            props = json.load(fh)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "props.json parse failed: %s" % e}))
        return 2
    if not isinstance(props, dict) or not _safe_scenes(props):
        print(json.dumps({"ok": False, "error": "props has no scenes[] to recover"}))
        return 2
    # (4) verify-and-heal: upload every referenced editor asset under the DB run_key
    #     namespace + rewrite refs to full URLs (mutates props in place). Identical to
    #     the pass tool_produce_and_ship runs at the end of EVERY successful conduct.
    asset_check = {}
    try:
        asset_check = _verify_and_heal_assets(run_id, props, run_dir)
    except Exception as e:
        _log("heal-recovered: verify-and-heal failed: %s" % e)
        asset_check = {"error": str(e)}
    # (5) rich-props merge: the editor's durable load source (scenes/theme/total_frames).
    rich_patch = {}
    for k in ("fps", "theme", "total_frames", "audio_path", "lang", "scenes", "scene_thumbs"):
        if k in props:
            rich_patch[k] = props[k]
    merged_keys = []
    if rich_patch:
        try:
            _merge_run_props(run_id, rich_patch)
            merged_keys = sorted(rich_patch)
            _log("heal-recovered: rich props merged to runs.props for run %s (keys=%s)"
                 % (run_id, ",".join(merged_keys)))
        except Exception as e:
            _log("heal-recovered: rich props merge failed: %s" % e)
    print(json.dumps({"ok": True, "run_id": run_id, "plan_run_key": plan_run_key,
                      "merged_keys": merged_keys, "asset_check": asset_check}))
    return 0


def main():
    # #89-M1 SECURITY: bind loopback + the docker-bridge gateway the sandbox reaches
    # us on (172.18.0.1) instead of 0.0.0.0, so the tool-server is NOT exposed on
    # the public interface. Override with MCP_BIND_HOSTS (comma-separated) if needed.
    hosts = [h.strip() for h in
             os.environ.get("MCP_BIND_HOSTS", "127.0.0.1,172.18.0.1").split(",")
             if h.strip()]
    _log("starting %s v%s on %s:%d /mcp; tools: %s"
         % (SERVER_NAME, SERVER_VERSION, ",".join(hosts), PORT, ", ".join(TOOLS)))
    _log("WS_PREMIUM_MENU=%s OPENROUTER_API_KEY=%s INSFORGE_API_KEY=%s" % (
        os.environ.get("WS_PREMIUM_MENU"),
        "set" if os.environ.get("OPENROUTER_API_KEY") else "MISSING",
        "set" if os.environ.get("INSFORGE_API_KEY") else "MISSING"))
    import threading
    servers = []
    for h in hosts:
        try:
            srv = ThreadingHTTPServer((h, PORT), Handler)
        except OSError as e:
            _log("WARN: could not bind %s:%d (%s) — skipping that host" % (h, PORT, e))
            continue
        servers.append(srv)
    if not servers:
        raise SystemExit("FATAL: no MCP bind host available (%s:%d)" % (",".join(hosts), PORT))
    # Serve all but the last in background threads; block on the last.
    for srv in servers[:-1]:
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
    servers[-1].serve_forever()


if __name__ == "__main__":
    # CLI repair entrypoint (does NOT start the MCP server). See _heal_recovered_run.
    if len(sys.argv) >= 2 and sys.argv[1] == "--heal-recovered":
        if len(sys.argv) < 4:
            print(json.dumps({"ok": False, "error": "usage: --heal-recovered <run_id> <plan_run_key>"}))
            raise SystemExit(2)
        raise SystemExit(_heal_recovered_run(sys.argv[2], sys.argv[3]))
    main()
