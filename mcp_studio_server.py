#!/usr/bin/env python3
"""Walk Studio MCP server — exposes the video-production pipeline's steps as
first-class Hermes tools, so the Hermes RUNTIME (Nemotron) drives the job by
calling discrete tools and chaining them itself, instead of a Python harness
running the whole loop opaquely.

This is a dependency-free MCP **stdio** server. It speaks raw MCP JSON-RPC
2.0 over stdin/stdout (initialize -> tools/list -> tools/call), which is exactly
what Hermes' built-in MCP client (`mcp.client.stdio.stdio_client`) expects after
`hermes mcp add walk-studio --command <python> --args <this file>`.

Tools exposed (this prototype ships the first REAL one + the deterministic glue
ones so the chain is legible to the runtime):

  - conversion_read(url, brain="hermes")
        REAL pipeline step. Fetches the page's visible copy and runs
        analyze.analyze_read() -- the genuine Conversion Read on a Nous/Nemotron
        model via OpenRouter. Returns the validated Read JSON + which engine
        produced it. This is the load-bearing "the runtime called a real
        pipeline step" proof.

  - plan_job(url, goal, duration=30, brain="super-free")
        REAL pipeline step. Shells the existing plan_job.py (Nemotron planner)
        and returns the schema-validated SCENE PLAN JSON.

  - price_job(plan_path)
        DETERMINISTIC money glue. Runs producer.py estimate -> suggested price,
        locked production budget, per-scene budgets. The LLM never overrides the
        budget math; it only reads the result.

  - budget_gate(plan_path, scene_id, proposed_cost_cents, spent_cents)
        DETERMINISTIC money guardrail. Runs producer.py gate -> approve /
        downgrade / decline verdict. This is the autonomous money-shot: the gate
        declines an over-budget scene in code; the model cannot spend past it.

Design notes:
  - Money guardrails stay deterministic in code (producer.py). The MCP tools
    surface the numbers to the runtime; they do not let the model invent prices
    or bypass a decline.
  - Keys come from the process env. Hermes injects ~/.hermes/.env into the MCP
    subprocess env via the `--env` flags / its own env passthrough; this server
    also self-loads ~/.hermes/.env and the repo's .env as a belt-and-suspenders
    so a manual `hermes mcp add` without --env still works. Secrets are never
    printed.
"""
import json
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "walk-studio"
SERVER_VERSION = "0.1.0"


# --------------------------------------------------------------------------- #
# Env loading (so keys are present whether or not Hermes passed --env)
# --------------------------------------------------------------------------- #
def _load_env_file(path):
    """Minimal .env loader. Does NOT overwrite already-set vars (Hermes-passed
    env wins). Never prints values."""
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


def _log(msg):
    """Log to stderr only — stdout is the JSON-RPC channel and must stay clean."""
    sys.stderr.write("[mcp_studio_server] %s\n" % msg)
    sys.stderr.flush()


for _envp in (os.path.expanduser("~/.hermes/.env"), os.path.join(HERE, ".env")):
    _load_env_file(_envp)


# --------------------------------------------------------------------------- #
# Page-text fetch (lightweight; the prototype avoids the heavy Playwright
# capture so the Read step is fast + reliable in a single tool call)
# --------------------------------------------------------------------------- #
def _fetch_page_text(url, cap=4000):
    """Best-effort fetch of a page's visible copy. Returns (headline, body_text).
    Never raises — a thin/blocked page just yields short text and the Read leans
    on the model's world knowledge (the pipeline's designed degraded path)."""
    headline, body = "", ""
    try:
        import requests
        import re
        resp = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (compatible; WalkStudioBot/0.1)"},
        )
        html = resp.text or ""
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
# Tool implementations
# --------------------------------------------------------------------------- #
def tool_conversion_read(args):
    """REAL pipeline step: Conversion Read via analyze.analyze_read()."""
    url = (args.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "url is required"}
    brain = (args.get("brain") or "hermes").strip() or "hermes"

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
        return {"ok": False, "error": "analyze_read failed: %s" % e}

    return {
        "ok": True,
        "step": "conversion_read",
        "url": url,
        "openrouter_key_present": have_key,
        "fetched_headline": headline,
        "body_text_chars": len(body_text or ""),
        "engine": read.get("engine") if isinstance(read, dict) else None,
        "degraded": (read.get("degraded") if isinstance(read, dict) else None),
        "read": read,
    }


def _run_pipeline_cli(argv, parse_stdout_json=False):
    """Run a pipeline CLI (plan_job.py / producer.py) in the repo dir and capture
    output. Uses the SAME interpreter as this server so deps resolve."""
    try:
        proc = subprocess.run(
            [sys.executable] + argv,
            cwd=HERE,
            capture_output=True,
            text=True,
            timeout=540,  # < 600s subagent cap
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


def tool_plan_job(args):
    """REAL pipeline step: Nemotron scene-plan via plan_job.py."""
    url = (args.get("url") or "").strip()
    goal = (args.get("goal") or "").strip()
    duration = int(args.get("duration") or 30)
    brain = (args.get("brain") or "super-free").strip() or "super-free"
    if not url:
        return {"ok": False, "error": "url is required"}
    argv = ["plan_job.py", "--url", url, "--goal", goal,
            "--duration", str(duration), "--brain", brain]
    res = _run_pipeline_cli(argv, parse_stdout_json=True)
    if not res.get("ok"):
        return res
    plan = res["data"]
    # Persist the plan so price_job / budget_gate can read it by path.
    out_dir = os.path.join(HERE, "runs", "_mcp")
    os.makedirs(out_dir, exist_ok=True)
    plan_path = os.path.join(out_dir, "plan.json")
    with open(plan_path, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=2)
    scenes = plan.get("scenes", []) if isinstance(plan, dict) else []
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
    if not plan_path or not os.path.exists(plan_path):
        return {"ok": False, "error": "plan_path missing or not found: %r" % plan_path}
    res = _run_pipeline_cli(["producer.py", "estimate", "--plan", plan_path])
    if not res.get("ok"):
        return res
    return {"ok": True, "step": "price_job", "estimate_raw": res.get("stdout", "")}


def tool_budget_gate(args):
    """DETERMINISTIC money guardrail: producer.py gate (approve/downgrade/decline)."""
    plan_path = (args.get("plan_path") or "").strip()
    scene_id = (args.get("scene_id") or "").strip()
    proposed = int(args.get("proposed_cost_cents") or 0)
    spent = int(args.get("spent_cents") or 0)
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
    return {"ok": True, "step": "budget_gate", "verdict_raw": res.get("stdout", "")}


# --------------------------------------------------------------------------- #
# PRODUCE-TIME tools — each WRAPS an existing pipeline function (import + call).
# These do NOT modify the underlying pipeline source. They run in SIMULATE / dry
# mode by default (PRODUCER_SIMULATE_PAID): mode="mock" produce = a real but light
# ffmpeg color-card clip (adapters.synth_clip), VO = free edge-tts, stitch = ffmpeg
# concat. NO Remotion render is kicked from these tools. The Stripe earn path is
# TEST MODE ONLY and refuses a live key.
# --------------------------------------------------------------------------- #
def _simulate_paid():
    """True when the demo/SIMULATE affordance is on (PRODUCER_SIMULATE_PAID=1).
    The MCP server defaults it ON so the produce tools never fire a paid call
    unless the caller has explicitly cleared it for a genuine production run."""
    return os.environ.get("PRODUCER_SIMULATE_PAID", "1") == "1"


def _load_plan(plan_path):
    """Read a plan.json written by plan_job. Returns (plan_dict_or_None, error)."""
    if not plan_path or not os.path.exists(plan_path):
        return None, "plan_path missing or not found: %r" % plan_path
    try:
        with open(plan_path, "r", encoding="utf-8") as fh:
            return json.load(fh), None
    except Exception as e:
        return None, "could not read plan: %s" % e


def _run_dir_for(plan_path):
    """A per-job produce working dir next to the plan (defaults to runs/_mcp)."""
    base = os.path.dirname(os.path.abspath(plan_path)) if plan_path else os.path.join(HERE, "runs", "_mcp")
    out = os.path.join(base, "produce")
    os.makedirs(os.path.join(out, "clips"), exist_ok=True)
    return out


# --------------------------------------------------------------------------- #
# REAL / POLISHED render path (additive — keeps the SIMULATE proof intact).
#
# When a tool is called with `real:true` (or `mode:"real"`), produce/stitch drive
# the SAME polished studio render that build_runner._run_vo_engine uses: the
# VO-driven <Timeline> Remotion render with real kinetic-light overlays + real
# website screenshots + (with WS_VO_PROVIDER=elevenlabs) ElevenLabs VO. Higgsfield
# stays OFF the whole time (PRODUCER_SIMULATE_PAID=1 simulates the paid *cinematic*
# generators; the overlays + screenshots are genuinely rendered). This is NOT a
# per-scene synth card — the Timeline engine renders the whole picture in one pass,
# so we build the props ONCE (produce_scene) and render ONCE (stitch_final).
# --------------------------------------------------------------------------- #
def _real_requested(args):
    """True when the caller asked for the REAL polished render (real:true / mode:real).
    Default false => the existing SIMULATE proof (mock color cards) is unchanged."""
    if args.get("real") is True:
        return True
    return (str(args.get("mode") or "")).strip().lower() == "real"


def _real_run_dir(plan_path):
    """The run dir for the REAL render = the directory that holds plan.json.

    build_runner's engine writes brand_theme.json, screenshots/, props.json and
    final.mp4 directly into the run dir (not a produce/ subdir), so the real path
    operates in the plan's own directory — the same on-disk layout a dashboard run
    produces. Returns the absolute run dir."""
    return os.path.dirname(os.path.abspath(plan_path)) if plan_path \
        else os.path.join(HERE, "runs", "_mcp")


def _build_real_props(plan_path, plan):
    """Build the polished Timeline props ONCE for this job (idempotent).

    Mirrors build_runner._run_vo_engine's pre-render steps WITHOUT re-implementing
    them: resolve the brand theme, capture the real website screenshots, then run
    style_fill.run_pipeline (align_vo -> build_timeline -> build_props + stage audio)
    with do_render=False. ElevenLabs VO is selected by WS_VO_PROVIDER=elevenlabs in
    the env (read inside align_vo.synth_full_script). Returns (props_path, info)."""
    import build_runner
    import style_fill

    run_dir = _real_run_dir(plan_path)
    job = plan.get("job", {}) if isinstance(plan, dict) else {}
    url = job.get("company_url") or ""

    props_path = os.path.join(run_dir, "props.json")
    # Idempotent: if props already exist for this run, reuse them (per-scene
    # produce_scene calls must not re-render the whole timeline N times).
    if os.path.exists(props_path):
        return props_path, {"reused": True, "run_dir": run_dir}

    # 1) brand theme (curated fixture preferred, brand_extract fallback)
    brand_path = build_runner._resolve_brand_theme(url, run_dir)
    # 2) real website screenshots (idempotent, $0)
    try:
        build_runner._capture_screenshots_for_run(url, run_dir)
    except Exception as e:
        _log("real produce: screenshot capture degraded: %s" % e)
    # 3) align_vo -> build_timeline -> build_props (+ stage audio) => props.json.
    #    do_render=False: stitch_final does the single Remotion render below.
    res = style_fill.run_pipeline(plan_path, brand_path,
                                  build_runner.VO_ENGINE_STYLE, run_dir,
                                  fps=30, do_align=True, do_render=False)
    return res["props_path"], {"reused": False, "run_dir": run_dir,
                               "brand_path": brand_path}


def _render_real_final(plan_path):
    """Render the polished <Timeline> picture to final.mp4 in the run dir.

    Drives the SAME Remotion render build_runner._run_vo_engine uses (Timeline comp,
    h264, concurrency 8, --props=props.json). Returns (final_path_or_None, log)."""
    import style_fill

    run_dir = _real_run_dir(plan_path)
    props_path = os.path.join(run_dir, "props.json")
    if not os.path.exists(props_path):
        return None, "props.json missing — run produce_scene(real) first"

    final = os.path.join(run_dir, "final.mp4")
    studio = style_fill.STUDIO_DIR
    abs_props = os.path.abspath(props_path)
    env = dict(os.environ, PATH=os.path.join(studio, "node_modules", ".bin")
               + os.pathsep + os.environ.get("PATH", ""))
    cmd = ["remotion", "render", "src/index.ts", "Timeline", os.path.abspath(final),
           "--codec=h264", "--concurrency=8", "--props=%s" % abs_props]
    proc = subprocess.run(cmd, cwd=studio, env=env,
                          capture_output=True, text=True, timeout=540)
    if proc.returncode != 0 or not os.path.exists(final):
        return None, "remotion render failed (rc=%d): %s" % (
            proc.returncode, (proc.stderr or "")[-1500:])
    return final, "ok"


def tool_produce_scene(args):
    """REAL pipeline step: produce ONE planned scene via adapters.

    Wraps adapters.studio_overlay (title / motion_graphic when overlays='studio')
    or adapters.generate_overlay / adapters.generate_cinematic in mock mode. In
    SIMULATE mode every path resolves to adapters.synth_clip (a real, light ffmpeg
    color card) — no Remotion render, no paid generation. The produced clip is a
    real MP4 on disk that stitch_final consumes."""
    plan_path = (args.get("plan_path") or "").strip()
    scene_id = (args.get("scene_id") or "").strip()
    if not scene_id:
        return {"ok": False, "error": "scene_id is required"}
    plan, err = _load_plan(plan_path)
    if err:
        return {"ok": False, "error": err}

    scenes = plan.get("scenes", []) if isinstance(plan, dict) else []
    scene = next((s for s in scenes if s.get("id") == scene_id), None)
    if scene is None:
        return {"ok": False, "error": "scene %r not in plan" % scene_id,
                "available": [s.get("id") for s in scenes]}

    # ---- REAL / POLISHED path -------------------------------------------------
    # The Timeline engine renders the WHOLE picture in one pass, so produce_scene
    # builds the polished props ONCE (idempotent across the per-scene calls). The
    # actual single Remotion render happens in stitch_final. Higgsfield stays OFF
    # (PRODUCER_SIMULATE_PAID=1) — overlays + screenshots are genuinely rendered.
    if _real_requested(args):
        try:
            props_path, info = _build_real_props(plan_path, plan)
        except Exception as e:
            return {"ok": False, "error": "real produce_scene failed for %r: %s" % (scene_id, e)}
        exists = os.path.exists(props_path)
        return {
            "ok": True,
            "step": "produce_scene",
            "scene_id": scene_id,
            "scene_type": scene.get("type", "title"),
            "mode": "real",
            "simulated": _simulate_paid(),  # True => Higgsfield/cinematic still simulated OFF
            "real_render": "timeline",      # polished VO-driven studio Timeline render
            "props_path": props_path,
            "props_exists": exists,
            "props_reused": bool(info.get("reused")),
            "run_dir": info.get("run_dir"),
            "real_asset": True,
            "note": "polished props built (real overlays + screenshots); the single "
                    "Timeline Remotion render runs in stitch_final",
        }

    try:
        import adapters
        import remotion_codegen
    except Exception as e:
        return {"ok": False, "error": "could not import adapters: %s" % e}

    simulate = _simulate_paid()
    # SIMULATE forces mock mode so no paid generation / no Remotion render fires.
    mode = "mock" if simulate else (args.get("mode") or "mock")
    stype = scene.get("type", "title")
    work = _run_dir_for(plan_path)
    order = scenes.index(scene)
    out = os.path.join(work, "clips", "%02d_%s.mp4" % (order, scene_id))
    job = plan.get("job", {}) if isinstance(plan, dict) else {}
    company_url = job.get("company_url")

    try:
        if stype in ("title", "motion_graphic"):
            # generate_overlay(scene, out_path, mode, company_url) — mock => synth_clip.
            info = adapters.generate_overlay(scene, out, mode, company_url=company_url)
        elif stype == "cinematic":
            # generate_cinematic(scene, out_path, mode) — mock => synth_clip color card.
            info = adapters.generate_cinematic(scene, out, mode, company_url=company_url)
        elif stype == "walkthrough":
            # Walkthrough generation is heavy (NemoClaw capture) in real mode; in
            # SIMULATE we render the brand-tinted placeholder card directly via the
            # FREE synth_clip path (no native capture, no NIM) so the tool stays light.
            palette = remotion_codegen.palette_for(company_url)
            adapters.synth_clip(out, palette.get("accent", "0A0D0C").lstrip("#"),
                                scene.get("duration_s", 4))
            info = {"output_path": out, "real": False, "note": "simulated walkthrough placeholder card"}
        else:
            # Any other free type -> a synth color card at the type color.
            adapters.synth_clip(out, "0A0D0C", scene.get("duration_s", 3))
            info = {"output_path": out, "real": False}
    except Exception as e:
        return {"ok": False, "error": "produce_scene failed for %r: %s" % (scene_id, e)}

    exists = os.path.exists(out)
    size = os.path.getsize(out) if exists else 0
    try:
        dur = adapters.ffprobe_duration(out) if exists else 0.0
    except Exception:
        dur = 0.0
    return {
        "ok": True,
        "step": "produce_scene",
        "scene_id": scene_id,
        "scene_type": stype,
        "mode": mode,
        "simulated": simulate,
        "output_path": out,
        "output_exists": exists,
        "output_bytes": size,
        "duration_s": round(dur, 3),
        "real_asset": bool(isinstance(info, dict) and info.get("real")),
        "note": info.get("note") if isinstance(info, dict) else None,
    }


def tool_synthesize_vo(args):
    """REAL pipeline step: synthesize the voiceover via adapters.synthesize_voiceover.

    SIMULATE forces provider='edge' (free edge-tts) — it NEVER calls the paid
    ElevenLabs path. The script comes from the plan's voiceover.script (or an
    override arg). Produces a real voiceover.mp3 that stitch_final muxes."""
    plan_path = (args.get("plan_path") or "").strip()
    plan, err = _load_plan(plan_path)
    if err:
        return {"ok": False, "error": err}

    try:
        import adapters
    except Exception as e:
        return {"ok": False, "error": "could not import adapters: %s" % e}

    vo = plan.get("voiceover", {}) if isinstance(plan, dict) else {}
    script = (args.get("script") or vo.get("script") or "").strip()
    if not script:
        return {"ok": False, "error": "no voiceover script in plan or args"}
    voice = (args.get("voice") or vo.get("voice") or "").strip()

    # ---- REAL / POLISHED path: ElevenLabs VO -------------------------------
    # On the polished path the VO is synthesized by the Timeline engine INSIDE
    # produce_scene(real) (align_vo -> ElevenLabs beat MP3s, selected by
    # WS_VO_PROVIDER=elevenlabs). This tool then CONFIRMS that real ElevenLabs VO
    # on disk (per-beat MP3s + vo_alignment.json) rather than producing a separate
    # edge-tts voiceover.mp3 that the Timeline render would never use. It still
    # works as a fresh ElevenLabs synth if produce_scene(real) hasn't run yet.
    real = _real_requested(args) or (str(args.get("provider") or "").strip().lower() == "elevenlabs")
    if real:
        run_dir = _real_run_dir(plan_path)
        import glob
        # The ElevenLabs with-timestamps path yields ONE voiceover.mp3 + alignment
        # (tier='premium'); some plans also leave per-beat MP3s. Accept either as
        # proof the real VO is on disk.
        beats = sorted(glob.glob(os.path.join(run_dir, "voiceover.beat*.mp3")))
        single = os.path.join(run_dir, "voiceover.mp3")
        align = os.path.join(run_dir, "vo_alignment.json")
        have_key = bool(os.environ.get("ELEVENLABS_API_KEY"))
        engine = None
        if os.path.exists(align):
            try:
                with open(align, "r", encoding="utf-8") as fh:
                    engine = (json.load(fh) or {}).get("tier")
            except Exception:
                engine = None
        vo_audio = beats if beats else ([single] if os.path.exists(single) else [])
        # engine=='premium' is the load-bearing proof the ElevenLabs path ran.
        if vo_audio and engine == "premium":
            total = sum(os.path.getsize(b) for b in vo_audio)
            try:
                dur = adapters.ffprobe_duration(vo_audio[0]) if len(vo_audio) == 1 else 0.0
            except Exception:
                dur = 0.0
            return {
                "ok": True,
                "step": "synthesize_vo",
                "provider": "elevenlabs",
                "voice": voice or "(plan default)",
                "simulated": False,
                "paid": True,
                "engine_tier": engine,            # 'premium' => ElevenLabs path taken
                "script_chars": len(script),
                "vo_files": len(vo_audio),
                "output_bytes": total,
                "duration_s": round(dur, 3) if dur else None,
                "elevenlabs_key_present": have_key,
                "note": "ElevenLabs VO synthesized by the Timeline engine in "
                        "produce_scene(real); confirmed on disk (alignment tier=premium)",
            }
        # produce_scene(real) hasn't run yet (or VO not premium) — synthesize a
        # standalone ElevenLabs VO.
        provider = "elevenlabs"
    else:
        simulate = _simulate_paid()
        # SIMULATE pins the FREE edge-tts provider; never elevenlabs (paid).
        provider = "edge" if simulate else (args.get("provider") or "edge")
    if provider not in ("edge", "elevenlabs"):
        return {"ok": False, "error": "unknown provider %r" % provider}

    work = _run_dir_for(plan_path)
    out = os.path.join(work, "voiceover.mp3")
    try:
        info = adapters.synthesize_voiceover(script, voice, out, provider)
    except Exception as e:
        return {"ok": False, "error": "synthesize_vo failed: %s" % e}

    exists = os.path.exists(out)
    size = os.path.getsize(out) if exists else 0
    try:
        dur = adapters.ffprobe_duration(out) if exists else 0.0
    except Exception:
        dur = 0.0
    return {
        "ok": True,
        "step": "synthesize_vo",
        "provider": info.get("provider") if isinstance(info, dict) else provider,
        "voice": info.get("voice") if isinstance(info, dict) else voice,
        "simulated": (provider == "edge") and _simulate_paid(),
        "paid": (provider == "elevenlabs"),
        "script_chars": len(script),
        "output_path": out,
        "output_exists": exists,
        "output_bytes": size,
        "duration_s": round(dur, 3),
    }


def tool_stitch_final(args):
    """REAL pipeline step: stitch produced scene clips + VO into final.mp4 via
    adapters.stitch (ffmpeg concat + VO mux + verify). This is an ffmpeg concat,
    NOT a Remotion render. Reads the clips produced by produce_scene in plan order
    and the voiceover.mp3 from synthesize_vo."""
    plan_path = (args.get("plan_path") or "").strip()
    plan, err = _load_plan(plan_path)
    if err:
        return {"ok": False, "error": err}

    # ---- REAL / POLISHED path: render the single VO-driven <Timeline> picture ----
    # NOT an ffmpeg concat of per-scene cards — this renders the polished
    # kinetic-light studio composition (real overlays + screenshots + ElevenLabs VO,
    # built by produce_scene(real)) to final.mp4, the SAME render build_runner uses.
    if _real_requested(args):
        final, log = _render_real_final(plan_path)
        if final is None:
            return {"ok": False, "error": "real stitch_final (Timeline render) failed: %s" % log}
        try:
            import adapters
            dur = adapters.ffprobe_duration(final)
        except Exception:
            dur = None
        return {
            "ok": True,
            "step": "stitch_final",
            "render": "timeline",          # polished Remotion studio render (not concat)
            "clips_stitched": None,         # n/a — one Timeline render, not a concat
            "vo_muxed": True,               # ElevenLabs VO baked into the Timeline render
            "output_path": final,
            "output_exists": True,
            "output_bytes": os.path.getsize(final),
            "duration_s": round(dur, 3) if dur else None,
        }

    try:
        import adapters
    except Exception as e:
        return {"ok": False, "error": "could not import adapters: %s" % e}

    work = _run_dir_for(plan_path)
    clips_dir = os.path.join(work, "clips")
    scenes = plan.get("scenes", []) if isinstance(plan, dict) else []

    # Gather produced clips in PLAN ORDER. A scene that was declined/cut simply has
    # no clip on disk and is absent from the timeline (the pipeline's own behavior).
    clips = []
    missing = []
    for order, s in enumerate(scenes):
        sid = s.get("id")
        p = os.path.join(clips_dir, "%02d_%s.mp4" % (order, sid))
        if os.path.exists(p) and os.path.getsize(p) > 1000:
            clips.append(p)
        else:
            missing.append(sid)
    if not clips:
        return {"ok": False, "error": "no produced clips found in %s — run produce_scene first" % clips_dir,
                "missing": missing}

    vo_path = (args.get("vo_path") or os.path.join(work, "voiceover.mp3")).strip()
    if not os.path.exists(vo_path):
        vo_path = None  # stitch tolerates a missing VO (video is never cut)
    out = os.path.join(work, "final.mp4")

    try:
        rec = adapters.stitch(clips, vo_path, out, watermark=False)
    except Exception as e:
        return {"ok": False, "error": "stitch_final failed: %s" % e}

    exists = os.path.exists(out)
    return {
        "ok": True,
        "step": "stitch_final",
        "clips_stitched": len(clips),
        "scenes_cut": missing,
        "vo_muxed": bool(vo_path),
        "output_path": out,
        "output_exists": exists,
        "output_bytes": os.path.getsize(out) if exists else 0,
        "duration_s": (rec.get("duration_s") if isinstance(rec, dict) else None),
        "stitch_record": rec if isinstance(rec, dict) else None,
    }


def tool_earn_stripe(args):
    """REAL pipeline step: the 'agent earns' path via stripe_money.StripeMoney.earn().

    TEST MODE ONLY. With no key it returns the SIMULATED dev-mode earn block — no
    Stripe API call, no money. With a sk_test_/rk_test_ key present it DEFAULTS to
    creating a REAL test-mode Stripe Product+Price+Payment Link (a
    https://buy.stripe.com/test_... URL — test mode, no real settlement); the caller
    does not have to pass live=true, and can pass live=false to force dev mode. A LIVE
    key (sk_live_/rk_live_) is REFUSED outright — this tool never touches live money."""
    try:
        import stripe_money
    except Exception as e:
        return {"ok": False, "error": "could not import stripe_money: %s" % e}

    price_cents = int(args.get("price_cents") or 0)
    currency = (args.get("currency") or "usd").strip() or "usd"
    job_goal = (args.get("job_goal") or "").strip()

    # If a plan_path is given, fall back to its job goal / price for convenience.
    plan_path = (args.get("plan_path") or "").strip()
    if plan_path and (not job_goal or price_cents <= 0):
        plan, _err = _load_plan(plan_path)
        if isinstance(plan, dict):
            job = plan.get("job", {})
            job_goal = job_goal or job.get("goal", "")
            currency = currency or job.get("currency", "usd")

    if price_cents <= 0:
        return {"ok": False, "error": "price_cents must be > 0 (from price_job)"}

    # MONEY BRAKE: detect the key by PRESENCE/KIND only (never read/print value).
    key_info = stripe_money.detect_key()
    if key_info.get("kind") == "live":
        return {"ok": False,
                "error": "REFUSED: a LIVE Stripe key is present. earn_stripe is TEST MODE "
                         "ONLY and will not create a live charge. Configure a sk_test_/rk_test_ "
                         "key or run without a key (simulated dev mode).",
                "key_kind": "live"}

    # TEST-MODE DEFAULT-ON: when a sk_test_/rk_test_ key is present we DEFAULT to
    # creating the real test-mode Checkout link, so the agent reliably produces a
    # https://buy.stripe.com/test_... link even if the model never passes live=true.
    # The caller can still force dev-mode simulation by passing live=false explicitly.
    # A LIVE key is already REFUSED above (the money brake) and never reaches here,
    # so this default can NEVER create a live charge — test mode only, no settlement.
    is_test_key = bool(key_info.get("present")) and key_info.get("kind") == "test"
    live_arg = args.get("live")
    if live_arg is None:
        want_live = is_test_key  # default ON for a test key
    else:
        want_live = bool(live_arg) and is_test_key  # explicit override still test-gated
    money = stripe_money.StripeMoney(live=want_live)
    try:
        earn = money.earn(price_cents, currency, job_goal)
    except Exception as e:
        return {"ok": False, "error": "earn_stripe failed: %s" % e}

    return {
        "ok": True,
        "step": "earn_stripe",
        "test_mode": True,
        "live_api_used": bool(money.live),
        "key_present": bool(key_info.get("present")),
        "key_kind": key_info.get("kind"),
        "status": earn.get("status"),
        "provider": earn.get("provider"),
        "price_cents": price_cents,
        "currency": currency,
        "payment_link": earn.get("payment_link"),
        "earn": earn,
    }


def tool_simulate_payment(args):
    """REAL pipeline step: the customer PAYS the earn link with the 4242 test card.

    Closes the earn loop (link -> paid) by confirming a Stripe TEST-MODE
    PaymentIntent with the literal 4242 4242 4242 4242 Visa — a real *succeeded*
    payment in the test dashboard, no real money. Call AFTER earn_stripe. With no
    key it returns a faithful simulated `succeeded` block. A LIVE key is REFUSED
    (confirming a card charge on a live key would move real money)."""
    try:
        import stripe_money
    except Exception as e:
        return {"ok": False, "error": "could not import stripe_money: %s" % e}

    price_cents = int(args.get("price_cents") or 0)
    currency = (args.get("currency") or "usd").strip() or "usd"
    plan_path = (args.get("plan_path") or "").strip()
    if plan_path and price_cents <= 0:
        plan, _err = _load_plan(plan_path)
        if isinstance(plan, dict):
            job = plan.get("job", {})
            currency = currency or job.get("currency", "usd")
    if price_cents <= 0:
        return {"ok": False, "error": "price_cents must be > 0 (the amount the customer pays, from earn_stripe/price_job)"}

    key_info = stripe_money.detect_key()
    if key_info.get("kind") == "live":
        return {"ok": False, "key_kind": "live",
                "error": "REFUSED: a LIVE Stripe key is present. simulate_payment is TEST "
                         "MODE ONLY and will not confirm a live charge. Use a sk_test_/rk_test_ key."}

    is_test_key = bool(key_info.get("present")) and key_info.get("kind") == "test"
    money = stripe_money.StripeMoney(live=is_test_key)
    meta = {"job": (args.get("job_goal") or "filmo-video")[:200]}
    if args.get("payment_link_id"):
        meta["payment_link_id"] = str(args.get("payment_link_id"))
    try:
        pay = money.settle_payment(price_cents, currency, meta)
    except Exception as e:
        return {"ok": False, "error": "simulate_payment failed: %s" % e}

    return {
        "ok": bool(pay.get("paid")),
        "step": "simulate_payment",
        "test_mode": True,
        "live_api_used": bool(money.live),
        "key_present": bool(key_info.get("present")),
        "key_kind": key_info.get("kind"),
        "paid": pay.get("paid"),
        "status": pay.get("status"),
        "amount_cents": price_cents,
        "amount_received_cents": pay.get("amount_received_cents"),
        "currency": pay.get("currency", currency),
        "card_brand": pay.get("card_brand"),
        "card_last4": pay.get("card_last4"),
        "payment_intent_id": pay.get("payment_intent_id"),
        "charge_id": pay.get("charge_id"),
        "livemode": pay.get("livemode", False),
        "payment": pay,
    }


# --------------------------------------------------------------------------- #
# Tool registry (name -> (handler, schema))
# --------------------------------------------------------------------------- #
TOOLS = {
    "conversion_read": {
        "handler": tool_conversion_read,
        "schema": {
            "name": "conversion_read",
            "description": (
                "Run the Conversion Read on a company URL: fetch the page's "
                "visible copy and analyze it on a Nous/Nemotron model (via "
                "OpenRouter) into a validated Read (who the product is for, the "
                "core promise, proof points, the conversion goal). This is the "
                "first real step of a video-production job — call it before "
                "plan_job. Returns the Read JSON and which engine produced it."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Company/product URL to read."},
                    "brain": {
                        "type": "string",
                        "description": "Model brain key (default 'hermes' = Nous Hermes primary, Nemotron Ultra fallback).",
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
                "Writes the plan to disk and returns its path (feed that path to "
                "price_job and budget_gate)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "goal": {"type": "string"},
                    "duration": {"type": "integer", "description": "Target seconds (default 30)."},
                    "brain": {"type": "string", "description": "Planner brain (default 'super-free' = Nemotron 120B, $0)."},
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
                "properties": {"plan_path": {"type": "string", "description": "Path from plan_job."}},
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
                },
                "required": ["plan_path", "scene_id", "proposed_cost_cents", "spent_cents"],
            },
        },
    },
    "produce_scene": {
        "handler": tool_produce_scene,
        "schema": {
            "name": "produce_scene",
            "description": (
                "Produce ONE planned scene. Two paths:\n"
                "• SIMULATE (default, mock): renders a real but LIGHT ffmpeg color card "
                "(synth_clip) per scene — no Remotion render, no paid generation. The $0 "
                "proof path.\n"
                "• REAL / POLISHED (pass real:true): builds the polished VO-driven "
                "<Timeline> studio props ONCE for the whole job (real kinetic-light "
                "overlays + real website screenshots + ElevenLabs VO) — the SAME render "
                "build_runner uses. Higgsfield stays OFF (the paid cinematic generators "
                "are simulated). The actual single Remotion render runs in stitch_final, "
                "so per-scene real produce_scene calls are idempotent.\n"
                "Call once per scene AFTER budget_gate approves it. Cinematic scenes that "
                "budget_gate DECLINES should NOT be produced (they are absent from the cut)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plan_path": {"type": "string", "description": "Path from plan_job."},
                    "scene_id": {"type": "string", "description": "Which scene to produce."},
                    "mode": {"type": "string", "description": "mock (default; free synth card) or real (polished Timeline render)."},
                    "real": {"type": "boolean", "description": "true => build the polished Timeline props (real overlays + screenshots + ElevenLabs VO). Default false = SIMULATE mock card."},
                },
                "required": ["plan_path", "scene_id"],
            },
        },
    },
    "synthesize_vo": {
        "handler": tool_synthesize_vo,
        "schema": {
            "name": "synthesize_vo",
            "description": (
                "Synthesize / confirm the job's voiceover. Two paths:\n"
                "• SIMULATE (default): free edge-tts -> voiceover.mp3.\n"
                "• REAL / POLISHED (pass provider:'elevenlabs' or real:true): on the "
                "polished path the ElevenLabs VO is already synthesized by the Timeline "
                "engine inside produce_scene(real) (per-beat MP3s + alignment); this tool "
                "CONFIRMS that real ElevenLabs VO on disk (it's the track the Timeline "
                "render bakes in). Reads narration from the plan's voiceover.script. Call "
                "after the scenes are produced and before stitch_final."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plan_path": {"type": "string", "description": "Path from plan_job (carries voiceover.script)."},
                    "script": {"type": "string", "description": "Override narration text (else uses the plan's)."},
                    "voice": {"type": "string", "description": "Voice id/name (else uses the plan's)."},
                    "provider": {"type": "string", "description": "edge (free, default) or elevenlabs (paid, polished path)."},
                    "real": {"type": "boolean", "description": "true => confirm the ElevenLabs VO built by produce_scene(real)."},
                },
                "required": ["plan_path"],
            },
        },
    },
    "stitch_final": {
        "handler": tool_stitch_final,
        "schema": {
            "name": "stitch_final",
            "description": (
                "Render the final.mp4. Two paths:\n"
                "• SIMULATE (default): ffmpeg concat of the per-scene mock cards + VO mux.\n"
                "• REAL / POLISHED (pass real:true): renders the single polished VO-driven "
                "<Timeline> studio composition (real kinetic-light overlays + screenshots "
                "+ ElevenLabs VO built by produce_scene(real)) to final.mp4 — the SAME "
                "Remotion render build_runner uses. NOT a concat. Higgsfield stays OFF.\n"
                "Call LAST, after produce_scene for every kept scene and synthesize_vo. "
                "Returns the final.mp4 path and its duration."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "plan_path": {"type": "string", "description": "Path from plan_job."},
                    "vo_path": {"type": "string", "description": "Override VO path (SIMULATE concat path only)."},
                    "real": {"type": "boolean", "description": "true => render the polished Timeline picture (not a concat). Default false = SIMULATE concat."},
                },
                "required": ["plan_path"],
            },
        },
    },
    "earn_stripe": {
        "handler": tool_earn_stripe,
        "schema": {
            "name": "earn_stripe",
            "description": (
                "The 'agent earns' money path: create a Stripe TEST-MODE Checkout / "
                "Payment Link for the priced job (wraps stripe_money.StripeMoney.earn). "
                "TEST MODE ONLY — with no key it returns a simulated dev-mode earn block "
                "(no API call, no money); with a sk_test_/rk_test_ key it DEFAULTS to "
                "creating a real https://buy.stripe.com/test_... link (test mode, no "
                "settlement) — you do NOT need to pass live. A LIVE key is REFUSED. "
                "Call after price_job to set the "
                "price the customer pays; in the full loop this gates production on "
                "payment. Never creates a real charge."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "price_cents": {"type": "integer", "description": "Customer price in cents (from price_job)."},
                    "currency": {"type": "string", "description": "Currency (default usd)."},
                    "job_goal": {"type": "string", "description": "Job goal (product name on the Stripe link)."},
                    "plan_path": {"type": "string", "description": "Optional: pull goal/currency from the plan."},
                    "live": {"type": "boolean", "description": "Use the real test-mode Stripe API. DEFAULT (omit): on when a sk_test_/rk_test_ key is present (creates a real buy.stripe.com/test_... link); off (simulated) when no key. Pass false to force simulated dev mode. A LIVE key is always refused regardless."},
                },
                "required": ["price_cents"],
            },
        },
    },
    "simulate_payment": {
        "handler": tool_simulate_payment,
        "schema": {
            "name": "simulate_payment",
            "description": (
                "Simulate the CUSTOMER paying the earn link with Stripe's 4242 test "
                "card — closes the earn loop (link -> paid). Confirms a TEST-MODE "
                "PaymentIntent with the 4242 4242 4242 4242 Visa: a real *succeeded* "
                "payment in the Stripe test dashboard, no real money. Call AFTER "
                "earn_stripe, passing the same price_cents. With no key it returns a "
                "simulated paid block; a LIVE key is REFUSED (test mode only)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "price_cents": {"type": "integer", "description": "Amount the customer pays in cents (same as earn_stripe)."},
                    "currency": {"type": "string", "description": "Currency (default usd)."},
                    "job_goal": {"type": "string", "description": "Optional job goal, recorded on the payment metadata."},
                    "payment_link_id": {"type": "string", "description": "Optional earn payment_link id to tag the payment metadata."},
                    "plan_path": {"type": "string", "description": "Optional: pull currency from the plan."},
                },
                "required": ["price_cents"],
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
        # record of exactly which tools the runtime drove and with what params
        # (real/provider/brain). Never logs secrets — args here are plan paths,
        # scene ids, provider/brain flags, prices.
        try:
            _audit = {k: args.get(k) for k in
                      ("scene_id", "real", "mode", "provider", "brain",
                       "price_cents", "live") if k in args}
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
    _log("starting (%s v%s); tools: %s" % (SERVER_NAME, SERVER_VERSION, ", ".join(TOOLS)))
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
