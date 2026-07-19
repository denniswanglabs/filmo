#!/usr/bin/env python3
"""Run ONE live build job: URL + goal -> storyboard -> PAYMENT GATE -> produced video.

Launched as a subprocess by the dashboard server. The flow, watchable live in the
console via the incrementally-written ledger:

  1. PLAN     write a 'planning' ledger at once (so the console shows the agent
              thinking), then plan the storyboard via the free Nemotron planner.
  2. PRICE    price the plan with producer.py BEFORE producing, so the customer
              price is known before any money is spent.
  3. EARN/GATE create a REAL Stripe TEST-mode Checkout Session, write an
              `awaiting_payment` ledger (phase + earn block) so the dashboard
              renders the pay-gate card, then POLL the session's payment_status
              until 'paid' (webhook is blocked on `stripe login`; poll is the
              working path) or a ~15-min wall-clock cap.
  4. PRODUCE  on 'paid', hand off to orchestrator.orchestrate (carrying the paid
              earn block) which produces each scene under the budget gate and
              writes the rest of the ledger -> delivered.

Mode:
  mock  ($0) — real Remotion titles + storyboard placeholders, edge-tts VO.
  real  (paid) — real Higgsfield + walk-agent. "Always real ($)": a real customer
        payment triggers real production with no mock fallback.

$0 DEV AFFORDANCE — env `PRODUCER_SIMULATE_PAID=1`: the poll resolves to 'paid'
immediately (a real test session is still created for realism). Combined with
`--mode mock` this runs plan -> gate -> (simulated paid) -> mock production ->
delivered entirely at $0, with no real human payment and no Higgsfield spend.
In production: no simulate flag + mode=real.

Watchable pacing: sets PRODUCER_PACE so scene state-changes don't blink past.
"""

import json
import os
import re
import shutil
import sys
import time

import brain as brain_mod
import ledger as ledger_mod
import orchestrator
import plan_job
import producer
import stripe_earn
import stripe_money

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "runs")
BRANDING = os.path.join(HERE, "branding")

# The BRAIN is NVIDIA Nemotron. The Conversion Read runs on Nemotron 550B
# (`ultra-paid`), same family as planning, chosen INDEPENDENTLY of the planner brain
# so the operator's planner selection never drags the page diagnosis around. Paid,
# so no free-tier 429s. analyze.py falls ultra-paid -> super-paid -> minimal_read.
# (Hermes is the agent harness, not a model call.) Override with ANALYZE_BRAIN env.
ANALYZE_BRAIN = os.environ.get("ANALYZE_BRAIN", "ultra-paid")

# VO-DRIVEN ENGINE flag (the blank-scenes fix). When ON (default for the dashboard
# build path), the PICTURE is produced by the VO-driven <Timeline> engine
# (align_vo -> build_timeline -> style_fill.build_props -> Remotion render) which
# NEVER emits a blank scene: a cinematic/walkthrough beat with no real footage
# falls to the designed ExplainerCard, not the old flat solid-color synth_clip.
# When OFF, the legacy per-scene-clip path is the only picture (still reachable for
# the original demo). The SACRED money path (orchestrator's budget gate + Stripe
# authorize + ledger/P&L) runs UNCHANGED either way — the engine only replaces the
# final.mp4 picture, never the money/ledger flow.
VO_ENGINE_ENV = "WS_VO_ENGINE"
# The curated style the engine fills for the classic look.
VO_ENGINE_STYLE = "orinovate-kinetic-light"
# Visual style family (--look): "classic" renders the light Timeline; "engineered-night"
# renders the dark one-world NightTimeline (style_fill STYLES["engineered-night"]).
# Module-level so the render seam reads it without threading a new param through run().
ACTIVE_LOOK = "classic"


def vo_engine_enabled():
    """True unless WS_VO_ENGINE is explicitly a falsy flag ('0'/'false'/'no'/'off').

    Default ON for the dashboard build path (run()) so the blank-scenes fix is the
    shipped behavior; set WS_VO_ENGINE=0 to fall back to the legacy picture.
    """
    return (os.environ.get(VO_ENGINE_ENV) or "").strip().lower() not in ("0", "false", "no", "off")


# CONVERSION READ feature flag. build_runner runs the ANALYZE stage (read_pass ->
# analyze -> persist) BEFORE planning and seeds the planner with the Read, so the
# plan is Hermes-grounded and the "uses Nous Hermes" claim is true.
# DEFAULT ON: the Conversion Read runs unless PRODUCER_CONVERSION_READ is EXPLICITLY
# a falsy flag ('0'/'false'/'no'/'off'). Set it falsy to reproduce the legacy
# (ungrounded) planning path.
CONVERSION_READ_ENV = "PRODUCER_CONVERSION_READ"


def conversion_read_enabled():
    val = (os.environ.get(CONVERSION_READ_ENV) or "").strip().lower()
    if val in ("0", "false", "no", "off"):
        return False
    return True

# Poll cadence + wall-clock cap for the payment gate (webhook backstop).
PAYMENT_POLL_INTERVAL_S = 2.5
PAYMENT_TIMEOUT_S = 15 * 60  # 15 minutes


def _price_plan(plan, run_dir):
    """Price the validated plan via producer.py BEFORE production.

    Returns (price_cents, currency). We write plan.json into the run dir (the
    same path orchestrate uses later) so producer.estimate prices the exact plan.
    """
    plan_path = os.path.join(run_dir, "plan.json")
    with open(plan_path, "w") as f:
        json.dump(plan, f, indent=2)
    est = producer.cmd_estimate(plan)
    currency = (plan.get("job") or {}).get("currency", "usd")
    return est.get("suggested_price_cents"), currency, est


def _build_quote(est, currency="usd"):
    """Build the itemized customer QUOTE the dashboard reads, from the producer est.

    EXACT schema (a UI agent reads this — do not deviate):
      {"tier": str, "scenes": int, "duration_s": number,
       "line_items": [{"label": str, "amount_cents": int}],
       "price_cents": int, "band": {"min_cents": int, "max_cents": int},
       "currency": "usd"}

    Sourced entirely from est["menu"] (the dynamic banded quote) + est["signals"]
    (the storyboard the price was derived from). Returns None if the est carries no
    menu (e.g. the WS_PREMIUM_MENU=OFF path), so the caller can skip the quote write.
    """
    menu = est.get("menu")
    if not isinstance(menu, dict):
        return None
    signals = est.get("signals") or {}
    band = menu.get("band") or {}
    line_items = [
        {"label": li.get("label", ""), "amount_cents": int(li.get("amount_cents") or 0)}
        for li in (menu.get("line_items") or [])
    ]
    return {
        "tier": est.get("quality") or menu.get("quality") or "standard",
        "scenes": int(signals.get("scenes") or 0),
        "duration_s": signals.get("duration_s") or 0,
        "line_items": line_items,
        "price_cents": int(menu.get("total_price_cents") or 0),
        "band": {
            "min_cents": int(band.get("min_cents") or 0),
            "max_cents": int(band.get("max_cents") or 0),
        },
        "currency": currency,
    }


def _resolve_brand_theme(url, run_dir):
    """Resolve the brand_theme the VO engine fills, and write it to run_dir.

    PREFERS a curated `branding/<host>-brand-theme.json` fixture (e.g. the
    hand-authored Orinovate light/navy/blue theme that produced the proven-good
    style-fill sample), because the generic `palette_for` fallback returns a
    dark+mint theme that is wrong for these brands (the diagnosis's FIX 3). Falls
    back to brand_extract.extract_brand(url) for any brand without a fixture.

    Returns the absolute path to the written brand_theme.json.
    """
    import remotion_codegen as rc

    host = rc._root_host(url) or ""
    label = host.split(".")[0] if host else ""
    theme = None
    if label:
        fixture = os.path.join(BRANDING, "%s-brand-theme.json" % label)
        if os.path.exists(fixture):
            try:
                with open(fixture) as f:
                    theme = json.load(f)
            except (OSError, ValueError):
                theme = None
    if theme is None:
        # No curated fixture — extract honestly (real name + palette + empty copy).
        import brand_extract
        # logo_from=run_dir: the accent chain samples the run's CAPTURED logo +
        # homepage pixels (real page colors — never an invented hue), and the
        # captured logo asset threads into theme.logo_src as before.
        theme = brand_extract.extract_brand(url, logo_from=run_dir)

    out = os.path.join(run_dir, "brand_theme.json")
    with open(out, "w") as f:
        json.dump(theme, f, indent=2)
    return out


def _facts_from_theme(theme):
    """Normalize a brand_theme dict -> the planner COMPANY-FACTS contract.

        {"wordmark": str, "tagline": str, "features": [str, ...]}

    Handles BOTH theme shapes the resolver can return:
      - the curated fixture (e.g. branding/orinovate-brand-theme.json): top-level
        `wordmark` + `tagline`, `features` as [{"label", "value"?, "sub"}, ...]; and
      - brand_extract.extract_brand output: `name` + `tagline`, `features` as
        [{"title", "sub"}, ...].
    Each feature is flattened to one human string ("3D Printing — FDM / SLA / SLS").
    Returns honest-empty fields when a fact is absent; NEVER fabricates. Never raises.
    """
    if not isinstance(theme, dict):
        return {"wordmark": "", "tagline": "", "features": []}
    wordmark = (theme.get("wordmark") or theme.get("brand") or theme.get("name") or "")
    if isinstance(wordmark, str) and wordmark.strip().lower() in ("", "the product"):
        wordmark = ""
    tagline = theme.get("tagline") or ""
    if not tagline:
        copy = theme.get("copy")
        if isinstance(copy, dict):
            tagline = copy.get("hook") or ""

    features = []
    for f in (theme.get("features") or []):
        if not isinstance(f, dict):
            if str(f).strip():
                features.append(str(f).strip())
            continue
        # fixture uses "label"; brand_extract uses "title".
        label = (f.get("label") or f.get("title") or "").strip()
        sub = (f.get("sub") or "").strip()
        if not label:
            continue
        features.append("%s — %s" % (label, sub) if sub else label)

    return {
        "wordmark": str(wordmark).strip(),
        "tagline": str(tagline).strip(),
        "features": features,
    }


def _brand_facts(url, run_dir):
    """Resolve the REAL brand facts for the planner BEFORE planning.

    Reuses _resolve_brand_theme (curated fixture preferred, brand_extract fallback)
    — the SAME resolver the visual side already fills cards from — so the voiceover
    the brain plans is grounded in the EXACT facts the picture shows. This is the
    fix for the VO-vs-visual incoherence bug (Orinovate's invented "data streams").

    Returns the normalized facts dict (possibly all-empty). On any failure returns
    empty facts so planning proceeds unchanged (the brain just gets no facts block).
    """
    try:
        brand_path = _resolve_brand_theme(url, run_dir)
        with open(brand_path) as f:
            theme = json.load(f)
        facts = _facts_from_theme(theme)
        # Carry the palette + display font for the reading-stage activity events
        # (additive — the planner facts block only reads wordmark/tagline/features).
        pal = theme.get("palette") or {}
        facts["palette"] = {k: pal[k] for k in ("accent", "navy", "bg", "text") if pal.get(k)}
        facts["font"] = ((theme.get("fonts") or {}).get("fontPrimary") or "").split(",")[0].strip()
        return facts
    except Exception:
        return {"wordmark": "", "tagline": "", "features": []}


def _maybe_conversion_read(url, run_dir, brain=ANALYZE_BRAIN,
                           read_pass_fn=None, analyze_fn=None):
    """Run the ANALYZE stage and return the Conversion Read dict, or None when the
    flag is OFF. Persists runs/<id>/conversion_read.json on success. Best-effort:
    a read-pass failure degrades to a minimal Read (video still proceeds); the Read
    is NEVER allowed to block the build. read_pass_fn/analyze_fn are injectable for
    tests; they default to the real read_pass.read_pass / analyze.analyze_read."""
    if not conversion_read_enabled():
        return None
    import analyze
    read_pass_fn = read_pass_fn or (lambda u, rd: __import__("read_pass").read_pass(u, rd))
    analyze_fn = analyze_fn or analyze.analyze_read
    try:
        rp = read_pass_fn(url, run_dir)
    except Exception as e:
        print("[build_runner] read_pass crashed: %s" % e, file=sys.stderr)
        rp = {"url": url, "body_text": "", "hero_screenshot_path": None,
              "headline": "", "degraded": True}
    # AGENTIC SITE READ (Dennis 2026-07-17): browse beyond the homepage — the
    # brain picks up to 4 subpages (pricing/features/customers/steps...), each
    # is captured (rendered text + screenshot), and the combined provenance
    # corpus feeds BOTH the analyze/plan stages and the VO-grounding guard.
    # SITE_BROWSE=0 disables; any failure degrades to the single-page read.
    corpus = rp.get("body_text", "")
    site_ledger = {"ok": False, "pages": []}
    if os.environ.get("SITE_BROWSE", "1") != "0":
        try:
            import site_read
            site_ledger = site_read.browse_site(
                url, run_dir, brain=brain,
                homepage_text=rp.get("body_text", ""))
            corpus = site_read.combined_corpus(rp.get("body_text", ""), site_ledger)
            if site_ledger.get("pages"):
                print("[build_runner] site read: +%d pages, corpus %d chars"
                      % (len(site_ledger["pages"]), len(corpus)), file=sys.stderr)
        except Exception as e:
            print("[build_runner] site read skipped (%s)" % e, file=sys.stderr)
    try:
        read = analyze_fn(url, corpus,
                          hero_path=rp.get("hero_screenshot_path"),
                          headline=rp.get("headline"), brain=brain)
    except Exception as e:
        print("[build_runner] analyze crashed: %s" % e, file=sys.stderr)
        read = analyze.minimal_read(url, rp.get("body_text", ""))
    if rp.get("degraded"):
        read["degraded"] = True
    read["hero_screenshot_path"] = rp.get("hero_screenshot_path")
    # Provenance for downstream stages: the grounding guard reads _ground_corpus;
    # the Night shapers match beats to per-page screenshots via design_brief.
    if isinstance(read, dict):
        read["_ground_corpus"] = corpus
        if site_ledger.get("pages"):
            read.setdefault("design_brief", {"story_shape": {}, "brand_vibe": {}})
            read["design_brief"]["site_pages"] = [
                {"slug": p.get("slug"), "title": p.get("title"), "shot": p.get("shot")}
                for p in site_ledger["pages"] if p.get("shot")
            ]
    # Guarantee the design brief key is present so downstream (plan_job / style_fill)
    # can always read conversion_read["design_brief"] without a guard. analyze_read /
    # minimal_read already set it; this defends against an injected analyze_fn (tests)
    # that returns a Read without one. Empty brief == honest "no corroborated material".
    if isinstance(read, dict):
        read.setdefault("design_brief", {"story_shape": {}, "brand_vibe": {}})
    try:
        with open(os.path.join(run_dir, "conversion_read.json"), "w") as f:
            json.dump(read, f, indent=2)
    except OSError as e:
        print("[build_runner] could not persist conversion_read.json: %s" % e, file=sys.stderr)
    return read


def _capture_screenshots_for_run(url, run_dir):
    """Capture real website screenshots into runs/<id>/screenshots/ (idempotent).

    Mode-independent + $0; called ONCE per job from _run_vo_engine before the
    render. Returns the manifest dict (or a not-ok manifest on failure). The
    apple-screenshot archetype + style_fill stager pick the PNGs up from here; a
    plan that has no apple-screenshot scene simply ignores them.
    """
    import adapters
    shots_dir = os.path.join(run_dir, "screenshots")
    manifest_path = os.path.join(shots_dir, "manifest.json")
    if os.path.exists(manifest_path):
        # already captured this run — don't re-fetch.
        try:
            with open(manifest_path) as f:
                return _salvage_screenshot_manifest(run_dir, shots_dir, json.load(f))
        except (OSError, ValueError):
            pass
    manifest = adapters.generate_screenshots(url, shots_dir, mode="mock", max_shots=2)
    return _salvage_screenshot_manifest(run_dir, shots_dir, manifest)


def _salvage_screenshot_manifest(run_dir, shots_dir, manifest):
    """#82: if the produce-time capture flaked (ok=false / no real shots), copy the
    REAL read-pass hero (runs/<id>/screenshots-read/shot-01.png) into screenshots/
    and rewrite the manifest as a real capture. Best-effort: returns the original
    manifest unchanged if there's no usable read-pass shot. Never raises."""
    try:
        if not isinstance(manifest, dict):
            return manifest
        real_shots = [s for s in (manifest.get("shots") or [])
                      if isinstance(s, dict) and not s.get("mock")]
        if manifest.get("ok") is not False and real_shots:
            return manifest  # already real
        read_manifest_path = os.path.join(run_dir, "screenshots-read", "manifest.json")
        if not os.path.exists(read_manifest_path):
            return manifest
        with open(read_manifest_path) as f:
            read_m = json.load(f)
        read_shots = [s for s in (read_m.get("shots") or [])
                      if isinstance(s, dict) and not s.get("mock") and (s.get("path") or s.get("file"))]
        if not read_shots:
            return manifest
        import shutil
        os.makedirs(shots_dir, exist_ok=True)
        salvaged = []
        for i, s in enumerate(read_shots, start=1):
            src_path = s.get("path") or os.path.join(run_dir, "screenshots-read", s.get("file"))
            if not src_path or not os.path.exists(src_path):
                continue
            fname = "shot-%02d.png" % i
            dst_path = os.path.join(shots_dir, fname)
            try:
                shutil.copyfile(src_path, dst_path)
            except OSError:
                continue
            rec = dict(s)
            rec["index"] = i
            rec["file"] = fname
            rec["path"] = dst_path
            rec.pop("mock", None)
            salvaged.append(rec)
        if not salvaged:
            return manifest
        new_m = {"url": manifest.get("url") or read_m.get("url"),
                 "count": len(salvaged), "shots": salvaged,
                 "ok": True, "real": True, "salvaged_from_read_pass": True}
        if read_m.get("logo"):
            new_m["logo"] = read_m["logo"]
        try:
            with open(os.path.join(shots_dir, "manifest.json"), "w") as f:
                json.dump(new_m, f, indent=2)
        except OSError:
            return manifest
        print("[build_runner] #82: salvaged %d real read-pass shot(s) into screenshots/"
              % len(salvaged), file=sys.stderr)
        return new_m
    except Exception as e:
        print("[build_runner] screenshot salvage skipped: %s" % e, file=sys.stderr)
        return manifest


def _try_unlink(path):
    """Best-effort remove of a temp/partial file; never raises."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _validate_rendered_mp4(path, min_bytes=10000):
    """True only if `path` is a non-trivial, decodable video.

    Two gates: (1) size > min_bytes (a 0-byte / truncated exit-0 render fails),
    and (2) an ffprobe duration probe that returns a positive number of seconds.
    If ffprobe is unavailable (not installed / not on PATH), we degrade to the
    size check alone rather than rejecting a real render. Never raises.
    """
    try:
        if not os.path.exists(path) or os.path.getsize(path) <= min_bytes:
            return False
    except OSError:
        return False
    import subprocess as _sp
    try:
        out = _sp.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30, check=False)
    except FileNotFoundError:
        # ffprobe not on PATH — size check already passed, accept.
        return True
    except Exception:
        return False
    try:
        return float((out.stdout or "").strip()) > 0.0
    except (TypeError, ValueError):
        return False


def _run_vo_engine(plan, run_id, url, run_dir):
    """Produce the PICTURE via the VO-driven <Timeline> engine and replace the
    run's final.mp4 with it. NEVER-BLANK by construction (ExplainerCard floor).

    Runs entirely on the $0 free tier: edge-tts + local whisper-cli for alignment,
    Remotion for the render. Does NOT touch the ledger/money path — orchestrate has
    already written ledger.json (P&L, scenes, budget gate, Stripe) by the time this
    runs. We only overwrite the picture so the customer never sees a blank scene.

    Returns the path to the engine final.mp4 on success, or None if the engine
    could not run (in which case the legacy picture from orchestrate is left as-is).
    """
    import style_fill

    plan_path = os.path.join(run_dir, "plan.json")
    if not os.path.exists(plan_path):
        with open(plan_path, "w") as f:
            json.dump(plan, f, indent=2)
    brand_path = _resolve_brand_theme(url, run_dir)

    # SCREENSHOTS (mode-INDEPENDENT, $0): capture the real site ONCE per job before
    # the render so any apple-screenshot scene has a real PNG to display. Capture
    # runs in mock AND real mode (screenshots are deterministic + free), so a mock
    # Standard build still shows the real site in a white studio card. Best-effort:
    # a capture failure must NOT fail the (paid, delivered) render — the
    # apple-screenshot archetype has its own never-blank floor.
    try:
        _capture_screenshots_for_run(url, run_dir)
    except Exception as e:
        print("[build_runner] screenshot capture skipped: %s" % e, file=sys.stderr)

    # align_vo -> build_timeline -> style_fill.build_props -> props.json (+ stage
    # audio). do_render=False here so we render once, below, into the run's final.mp4.
    #
    # VO PROVIDER (independent of quality/Higgsfield): the VO engine is ALWAYS the
    # Remotion Timeline (VO_ENGINE_STYLE, no Higgsfield) regardless of provider. By
    # default the voice is $0 edge-tts + whisper (tier="free" below). Set
    # WS_VO_PROVIDER=elevenlabs in the environment to swap ONLY the voice engine to
    # real ElevenLabs VO (read inside align_vo.synth_full_script) — so a
    # `--quality standard` build (Higgsfield OFF) still gets premium ElevenLabs VO.
    # We don't pass tier="premium" here; the env switch alone selects the provider.
    engine_style = "engineered-night" if ACTIVE_LOOK == "engineered-night" else VO_ENGINE_STYLE
    res = style_fill.run_pipeline(plan_path, brand_path, engine_style, run_dir,
                                  fps=30, do_align=True, do_render=False)
    props_path = res["props_path"]

    # ENGINEERED NIGHT audio grammar: swap the staged bed for the Night build,
    # time-mapped so the climax lands on the brand-lockup resolve (close scene
    # arrival + ~1s lockup pop). Best-effort — on any failure the run keeps
    # whatever music the classic stager picked.
    if ACTIVE_LOOK == "engineered-night":
        try:
            import night_music
            with open(props_path) as f:
                props = json.load(f)
            fps = props.get("fps") or 30
            scenes = props.get("scenes") or []
            total_s = (props.get("total_frames") or 0) / fps
            if scenes and total_s > 4:
                target_climax = scenes[-1].get("in_frame", 0) / fps + 1.0
                bed_name = f"night-bed-{run_id}.mp3"
                bed_out = os.path.join(style_fill.STUDIO_DIR, "public", bed_name)
                bed = night_music.build_bed(target_climax, total_s, bed_out)
                if bed:
                    theme = props.setdefault("theme", {})
                    theme["music"] = bed_name
                    # §B beat grid: lets NightTimeline snap SFX + within-hold
                    # arrivals to the bed's musical beats (frames, output time).
                    if bed.get("spb_s"):
                        theme["musicMeta"] = {
                            "spbFrames": bed["spb_s"] * fps,
                            "phaseFrames": bed.get("first_beat_s", 0.0) * fps,
                        }
                    with open(props_path, "w") as f:
                        json.dump(props, f)
                    print(f"[night] music mapped: climax -> {target_climax:.2f}s "
                          f"of {total_s:.2f}s film", file=sys.stderr)
        except Exception as e:
            print(f"[night] music mapping skipped ({e})", file=sys.stderr)

    # Render the Timeline composition with the props into the run's final.mp4 — the
    # exact path the dashboard/stitch already point at, so nothing downstream changes.
    #
    # bug-C1 FIX: NEVER overwrite the already-verified final.mp4 with an unvalidated
    # render. A returncode-0 exit can still leave a 0-byte / truncated file (disk
    # full, killed encoder, etc.), and the old code shipped that as "delivered".
    # Render to a temp path, validate it (non-trivial size + an ffprobe duration
    # check), and only then os.replace() over the verified picture. On ANY failure
    # the verified picture from orchestrate is left untouched.
    # NOTE: the temp name must still end in .mp4 — Remotion's validateOutputFilename
    # rejects an h264+aac output whose extension isn't mp4/mkv/mov (so "final.mp4.tmp"
    # would fail the render outright). Use "final.tmp.mp4".
    final = os.path.join(run_dir, "final.mp4")
    tmp = os.path.join(run_dir, "final.tmp.mp4")
    studio = style_fill.STUDIO_DIR
    abs_props = os.path.abspath(props_path)
    env = dict(os.environ, PATH=os.path.join(studio, "node_modules", ".bin")
               + os.pathsep + os.environ.get("PATH", ""))
    import subprocess
    composition = "NightTimeline" if ACTIVE_LOOK == "engineered-night" else "Timeline"
    cmd = ["remotion", "render", "src/index.ts", composition, os.path.abspath(tmp),
           "--codec=h264", "--concurrency=50%", "--props=%s" % abs_props]
    r = subprocess.run(cmd, cwd=studio, env=env)
    if r.returncode != 0 or not os.path.exists(tmp):
        _try_unlink(tmp)
        return None
    if not _validate_rendered_mp4(tmp):
        print("[build_runner] VO-ENGINE render failed validation (%s) — keeping the "
              "verified picture" % tmp, file=sys.stderr)
        _try_unlink(tmp)
        return None
    # Atomic swap: the verified picture is only destroyed AFTER the new one validates.
    os.replace(tmp, final)
    return final


def _safe_run_id(run_id):
    """sec-C2: sanitize a run-id before it is used as a path component.

    `run_id` becomes runs/<run_id>/… — used verbatim it lets a crafted value
    (../../etc/cron.d/x, /abs/path, …) escape the runs dir and write as root.
    Reduce to a safe slug: keep [A-Za-z0-9._-], map everything else to '-',
    strip any leading dots/dashes, and reject the pure-dot traversal tokens.
    Always returns a non-empty, path-safe token.
    """
    raw = str(run_id or "").strip()
    # collapse any path separators / disallowed chars to '-'
    slug = re.sub(r"[^A-Za-z0-9._-]", "-", raw)
    # no leading dots/dashes (kills "..", "."-prefixed, and leading "-")
    slug = slug.lstrip(".-")
    # reject pure-traversal residue
    if slug in ("", ".", ".."):
        slug = "run"
    return slug[:128]


def run(url, goal, run_id, mode="mock", target_duration=30, pace=1.2, style="standard",
        quality="standard", brain="super-free", emphasis=""):
    run_id = _safe_run_id(run_id)  # sec-C2: path-traversal hardening on the run dir
    run_dir = os.path.join(RUNS, run_id)
    os.makedirs(run_dir, exist_ok=True)
    led_path = os.path.join(run_dir, "ledger.json")
    # The build's start epoch (seconds). Stamped on the planning ledger below AND
    # carried into orchestrate's ledger so created_at is DURABLE: orchestrate mints a
    # fresh Ledger during production, and without this it would reset created_at to
    # None, so a mid-build page reload would restart the dashboard's elapsed timer.
    started_at = time.time()
    job = {"company_url": url, "goal": goal, "target_duration_s": target_duration,
           "target_margin": 0.6, "currency": "usd"}

    # QUALITY (the upfront cost-plus choice) drives BOTH pricing + the produce stack.
    # Turn the cost-plus menu ON for dashboard builds so producer/orchestrator honor
    # the quality dimension (standard = Remotion + edge-tts, no Higgsfield/ElevenLabs,
    # price floors at $5; premium = cinematic Higgsfield + ElevenLabs VO, ~$6-9).
    quality = "premium" if str(quality).strip().lower() == "premium" else "standard"
    os.environ["WS_PREMIUM_MENU"] = "1"

    os.environ["PRODUCER_PACE"] = str(pace)
    # User-facing STYLE controls the actual output (scene count / holds / motion
    # intensity), decoupled from PRODUCER_PACE (the console beat). The render layer
    # (remotion_codegen) reads HERMES_STYLE for per-style ease intensity; standard
    # leaves it as today's default so the output stays byte-identical.
    style = style if style in plan_job.VALID_STYLES else "standard"
    os.environ["HERMES_STYLE"] = style
    # BRAIN (operator): which LLM plans the storyboard, all via OpenRouter. Default
    # super-free ($0) so a build never accidentally bills planner tokens. Stamped to
    # the env for observability (mirrors HERMES_STYLE); threaded into the planner call.
    brain = brain_mod.normalize_brain(brain)
    os.environ["HERMES_BRAIN"] = brain
    # NATIVE WALKTHROUGH in MOCK too: a real product build wants the SAME genuine
    # per-brand walk_native walkthrough whether or not the customer paid — a $0 mock
    # test build must match what a paying Standard customer gets. This flag makes
    # adapters.generate_walkthrough run the real walk_native capture in mock mode
    # (real mode always does). Mock and real then differ ONLY in payment (mock keeps
    # the simulated PRODUCER_SIMULATE_PAID gate) and brain ($0 super-free), not in the
    # walkthrough asset. The offline orchestrator-judgment unit tests call orchestrate
    # directly (never this entrypoint), so they don't set the flag and keep the fast
    # deterministic synth card — the suite stays $0/offline.
    os.environ["WS_WALKTHROUGH_NATIVE"] = "1"
    if mode == "mock":
        os.environ.setdefault("PRODUCER_COST_STUB",
                              json.dumps({"seedance_2_0": 22, "gpt_image_2": 7, "__default__": 10}))

    # immediate 'planning' ledger so the console has something to show at once.
    # Stamp created_at (epoch seconds, a plain number) at the very start so the
    # dashboard's live status panel can show a SERVER-TRUTH elapsed timer that
    # survives a page reload (previously created_at was always None, leaving the
    # timer to guess from the client's first poll). It only ADDS a value to a field
    # the schema already carries (index.json passes created_at through unchanged) —
    # no money/ledger logic moves.
    led = ledger_mod.Ledger(run_id, job, mode, now=started_at)
    led.set_status("running")
    led.set_phase("planning")
    led.event("info", "agent visiting %s — reading the site and planning the storyboard…" % url)
    led.write(led_path)

    try:
        # -- ANALYZE (Conversion Read) -- runs BEFORE planning, behind the flag.
        conversion_read = None
        if conversion_read_enabled():
            led.set_phase("analyzing")
            led.data["stage"] = "analyzing"
            led.event("info", "analyzing %s — reading the page and diagnosing how it "
                      "converts before planning the video" % url)
            led.write(led_path)
            # Conversion Read runs on Nous Hermes; planning stays on Nemotron.
            # Deliberately pass ANALYZE_BRAIN, NOT the planner `brain`, so the page
            # diagnosis stays on Hermes regardless of which Nemotron the operator picked.
            conversion_read = _maybe_conversion_read(url, run_dir, brain=ANALYZE_BRAIN)
            if conversion_read is not None:
                led.data["conversion_read"] = conversion_read
                scored = ", ".join("%s %d" % (d.get("key"), d.get("score", 0))
                                   for d in conversion_read.get("dimensions", []))
                led.event("info", "conversion read: %s — scores [%s]%s"
                          % (conversion_read.get("verdict", ""), scored,
                             " (degraded)" if conversion_read.get("degraded") else ""))
                led.set_phase("planning")
                led.data["stage"] = None
                led.write(led_path)

        # GROUND THE BRAIN IN REAL BRAND FACTS (the VO-vs-visual coherence fix).
        # Resolve the company's real wordmark/tagline/features from the SAME brand
        # resolver the visual cards use, BEFORE planning, and thread them into the
        # planner. Without this the brain only saw url+goal+duration and INVENTED a
        # product (Orinovate -> hallucinated "AI insight platform / data streams"
        # while the cards correctly showed 3D printing / CNC / sheet metal). Empty
        # facts => no facts block => planning is unchanged (graceful).
        company_facts = _brand_facts(url, run_dir)
        # Granular reading-stage activity — surface the SPECIFIC things the agent is
        # learning so the long read/plan step never looks frozen.
        _pal = company_facts.get("palette") or {}
        if _pal:
            led.event("info", "read the brand palette — %s"
                      % ", ".join("%s %s" % (k, v) for k, v in _pal.items()))
            led.write(led_path)
        if company_facts.get("font"):
            led.event("info", "matched the brand typeface: %s" % company_facts["font"])
            led.write(led_path)
        if company_facts.get("tagline"):
            led.event("info", "understood the product — %s" % str(company_facts["tagline"])[:140])
            led.write(led_path)
        if any(company_facts.get(k) for k in ("wordmark", "tagline", "features")):
            _feats = company_facts.get("features") or []
            _names = ", ".join(
                str(f.get("label") or f.get("title") or f) if isinstance(f, dict) else str(f)
                for f in _feats[:4])
            led.event("info", "found %d real product features%s"
                      % (len(_feats), (": " + _names) if _names else ""))
            led.write(led_path)

        # Thread QUALITY into the planner so the storyboard's SCENE TYPES match the
        # produce stack: standard => Remotion-only (title + motion_graphic, no
        # cinematic); premium => cinematic shots allowed. (Previously quality was
        # only stamped onto plan["selection"] AFTER planning, so a standard plan
        # could still list Seedance / GPT-image cinematic scenes.)
        plan = plan_job.plan_job(url, goal, target_duration, style=style,
                                 quality=quality, brain=brain,
                                 company_facts=company_facts, emphasis=emphasis,
                                 conversion_read=conversion_read)
        # Carry the upfront QUALITY choice onto the plan so producer.cmd_estimate
        # prices it (standard floors at $5; premium includes Higgsfield + ElevenLabs
        # COGS) and orchestrate produces the matching stack. Stamp the chosen BRAIN
        # too (operator observability / future planner-COGS; default super-free=$0).
        # Carry the planner PROVENANCE (set by plan_job._planner) into selection so
        # the dashboard/ledger plainly shows whether the REAL LLM planned this build
        # or it fell back to the deterministic template — and WHY (finish_reason /
        # reason) plus the token usage. This is what makes "testing on Super"
        # trustworthy: a template build is no longer indistinguishable from an LLM
        # one. plan_source defaults to "llm" if the provenance block is absent.
        _prov = plan.get("_planner") or {}
        plan_source = _prov.get("plan_source", "llm")
        plan["selection"] = {
            "quality": quality,
            "brain": brain,
            "plan_source": plan_source,
            "finish_reason": _prov.get("finish_reason"),
            "planner_reason": _prov.get("reason"),
            "planner_usage": _prov.get("usage"),
        }
        if plan_source == "template":
            led.event("info",
                      "planner: brain=%s produced NO LLM plan (reason=%s) — this "
                      "build used the DETERMINISTIC TEMPLATE, not the LLM"
                      % (brain, _prov.get("reason")))
        else:
            led.event("info", "planner: brain=%s planned this build (LLM, finish_reason=%s)"
                      % (brain, _prov.get("finish_reason")))

        # -- PRICE before producing -------------------------------------------
        price_cents, currency, est = _price_plan(plan, run_dir)
        # Surface the priced storyboard so the console can render the script +
        # price the moment planning completes (mirrors orchestrate's projection).
        vo_plan = plan.get("voiceover") or {}
        led.data["plan"] = {
            "voiceover": {"script": vo_plan.get("script", ""), "voice": vo_plan.get("voice")},
            "scenes": [{"id": s.get("id"), "type": s.get("type"), "model": s.get("model"),
                        "duration_s": s.get("duration_s"), "brief": s.get("brief", "")}
                       for s in plan.get("scenes", [])],
        }
        led.set_pricing(est)

        # -- ITEMIZED QUOTE (the dashboard's pay-gate card reads this) --------
        # Write the dynamic banded quote to ledger["quote"] with the exact schema
        # the UI agent expects. The quote's price_cents is the SOURCE OF TRUTH for
        # what Stripe charges: force the gate price to it so earn.price_cents ==
        # quote.price_cents (they already agree — suggested_price_cents IS
        # menu.total_price_cents — but pin it explicitly so they can never drift).
        quote = _build_quote(est, currency=currency)
        if quote is not None:
            led.data["quote"] = quote
            price_cents = quote["price_cents"]
        led.event("info", "storyboard decided: %d scenes, priced at %sc"
                  % (len(plan.get("scenes", [])), price_cents))

        # -- EARN / payment gate ---------------------------------------------
        earn = _payment_gate(led, led_path, run_id, price_cents, currency, job, mode)
        if earn is None:
            return  # gate failed/timed out — ledger already records it

        # -- PRODUCE (only after payment) ------------------------------------
        led.event("money", "payment received — $%.2f" % ((price_cents or 0) / 100.0))
        led.set_phase("producing")
        # SUB-STAGE signal for the live status panel: the producing PHASE spans
        # several sub-steps (capture screenshots -> orchestrate the scenes ->
        # render), and the long screenshot-capture step below is otherwise SILENT
        # (no scene/phase change), so the panel would sit on a static "producing"
        # chip. `stage` is a tiny advisory string the dashboard reads to advance its
        # checklist; it NEVER gates money/ledger logic (the SACRED path keys off
        # status/phase/earn only). Absent => the dashboard falls back to phase.
        led.data["stage"] = "capturing"
        led.write(led_path)

        # SCREENSHOTS (mode-independent, $0): capture the real site BEFORE orchestrate
        # so the orchestrator's screenshot scenes build their clips from real PNGs.
        # Idempotent: _run_vo_engine's later capture call becomes a no-op. Best-effort
        # — a capture failure must NOT fail the paid render (the archetypes + the
        # screenshot-clip adapter both have never-blank floors).
        try:
            _capture_screenshots_for_run(url, run_dir)
        except Exception as e:
            print("[build_runner] pre-produce screenshot capture skipped: %s" % e, file=sys.stderr)

        data, _ = orchestrator.orchestrate(
            plan, run_id, mode=mode,
            # Carry the build's start epoch so the production ledger keeps the SAME
            # created_at the planning ledger had — keeps the dashboard elapsed timer
            # correct even if the customer reloads mid-build (otherwise orchestrate's
            # fresh ledger would reset created_at to None). Reproducible-safe: `now`
            # is only the ledger's created_at value, never used in any computation.
            now=started_at,
            # Studio overlays (the white, brand-authored Remotion cards) render in
            # EVERY mode now — decoupled from mock. Previously real mode forced
            # overlays="mock", which routed title/motion_graphic scenes to the flat
            # orange synth placeholder (TYPE_COLOR motion_graphic #B45309). Real
            # MEDIA (walkthrough / Higgsfield) is still gated on `mode` inside
            # orchestrate (by scene TYPE + budget), so this only changes the
            # CARD rendering (white vs orange), never real-asset generation.
            overlays="studio",
            earn=earn)

        # RE-ATTACH the Conversion Read to the DELIVERED on-disk ledger. orchestrate()
        # just minted a FRESH Ledger and wrote it to runs/<id>/ledger.json with NO
        # conversion_read — clobbering the diagnosis the ANALYZE stage put on the
        # run-level `led` above. The dashboard's Analysis panel reads l.conversion_read
        # ONLY from this delivered ledger (dashboard/app.js), so without this re-attach
        # the panel renders empty on every finished run. Reload the delivered ledger,
        # restore conversion_read + re-emit the 'analyzing' event so run history shows
        # it, and write it back. This single re-attach covers BOTH render paths:
        #   - VO-OFF: orchestrate is the LAST writer, so this is the final on-disk state.
        #   - VO-ON : the VO-engine tail below reloads disk_led from THIS file (565),
        #             so Ledger.load's merge carries conversion_read into the last write.
        # Guarded so a flag-OFF run (conversion_read is None) stays byte-identical.
        if conversion_read is not None:
            try:
                delivered_led = ledger_mod.Ledger.load(led_path)
            except (OSError, ValueError):
                delivered_led = None
            if delivered_led is not None and delivered_led.data.get("conversion_read") is None:
                delivered_led.data["conversion_read"] = conversion_read
                scored = ", ".join("%s %d" % (d.get("key"), d.get("score", 0))
                                   for d in conversion_read.get("dimensions", []))
                delivered_led.event("info", "analyzing — conversion read attached to the "
                                    "delivered ledger: %s — scores [%s]%s"
                                    % (conversion_read.get("verdict", ""), scored,
                                       " (degraded)" if conversion_read.get("degraded") else ""))
                delivered_led.write(led_path)

        # PICTURE via the VO-driven engine (the blank-scenes fix). The SACRED money
        # path (budget gate + Stripe authorize + ledger/P&L) has ALREADY run inside
        # orchestrate above; here we only replace the final.mp4 picture with the
        # never-blank <Timeline> render so a cinematic/walkthrough beat with no real
        # footage SHOWS the narrated point (ExplainerCard) instead of a blank.
        # Behind WS_VO_ENGINE (default ON); set WS_VO_ENGINE=0 for the legacy picture.
        if vo_engine_enabled():
            # Append the VO-ENGINE event to the RICH delivered ledger orchestrate()
            # just wrote to disk (scenes/pnl/budget-gate verdicts/status=delivered),
            # NOT to the in-memory run-level `led` — which only holds the planning +
            # payment-gate events. Writing `led` here would clobber the paid, delivered
            # record (scenes=[], pnl=null, status stuck at 'running'/phase='producing').
            # Mirrors _record_failure's reload-before-write to protect the paid record.
            try:
                disk_led = ledger_mod.Ledger.load(led_path)
            except (OSError, ValueError):
                disk_led = led  # no readable ledger on disk — keep the event somewhere
            try:
                # Advisory sub-stage for the live panel during the otherwise-silent
                # final render (the slowest, no-scene-change tail). Same contract as
                # the "capturing" stage above: read-only hint, never a gate.
                disk_led.data["stage"] = "rendering"
                disk_led.write(led_path)
                final = _run_vo_engine(plan, run_id, url, run_dir)
                if final:
                    disk_led.event("info", "VO-ENGINE: rendered never-blank <Timeline> "
                                   "picture -> final.mp4 (WS_VO_ENGINE on)")
                else:
                    # H5: the engine couldn't produce/validate a picture. Non-fatal
                    # (the legacy picture still ships), but stamp it durably + warn so
                    # a silent degrade is observable instead of looking like a clean run.
                    print("[build_runner] WARN VO-ENGINE render unavailable — kept the "
                          "legacy picture for run %s" % run_id, file=sys.stderr)
                    disk_led.data["vo_engine_failed"] = True
                    disk_led.event("info", "VO-ENGINE: engine render unavailable — kept the "
                                   "legacy picture for this run")
                disk_led.data["stage"] = None  # render finished — clear the advisory
                disk_led.write(led_path)
            except Exception as e:  # never let the picture step fail a delivered run
                # H5: the engine threw — non-fatal (legacy picture ships) but stamp +
                # warn so the failure is observable in logs and on the ledger.
                print("[build_runner] WARN VO-ENGINE raised (%s) — kept the legacy "
                      "picture for run %s" % (e, run_id), file=sys.stderr)
                disk_led.data["vo_engine_failed"] = True
                disk_led.event("info", "VO-ENGINE: skipped (%s) — kept the legacy picture" % e)
                disk_led.data["stage"] = None
                disk_led.write(led_path)
        return data
    except SystemExit:
        raise
    except Exception as e:  # surface the failure into the ledger the console polls
        _record_failure(led_path, led, run_id, job, mode, e)
        raise


def _record_failure(led_path, run_led, run_id, job, mode, exc):
    """Flip the run to 'failed' WITHOUT wiping the paid record.

    A post-payment failure (e.g. a production-side parse error) must KEEP the
    earn/pricing/plan/scenes already written to the ledger — otherwise a paid run
    looks like it was never paid (the build-orinovate-edf804 symptom: earn=null
    despite a confirmed payment). The old handler constructed a FRESH Ledger and
    wrote it, clobbering all of that. Instead:
      1. Load the freshest ledger from disk — during production the orchestrator
         writes scenes/plan/pnl (and the carried earn block) there.
      2. Backfill earn/pricing/plan from the in-memory run-level ledger if an EARLY
         failure (before orchestrate set them on disk) beat them to disk; the
         run-level ledger holds them from the planning + payment gate.
      3. Only set status/phase=failed and append the error event.
      4. Refresh runs/index.json so it doesn't go stale at 'running' on failure —
         the index is otherwise only rebuilt by orchestrate on a successful deliver.
    """
    try:
        led = ledger_mod.Ledger.load(led_path)
    except (OSError, ValueError):
        # No readable ledger on disk — fall back to the in-memory run-level ledger,
        # which still carries earn/pricing/plan if the payment gate had passed.
        led = run_led
    # Preserve the paid record across the early-failure window where a disk ledger
    # exists but predates the earn/pricing/plan blocks (the run-level ledger has them).
    for key in ("earn", "pricing", "plan"):
        if not led.data.get(key) and run_led.data.get(key):
            led.data[key] = run_led.data[key]
    led.set_status("failed")
    led.set_phase("failed")
    led.event("error", "build failed: %s" % exc)
    led.write(led_path)
    try:
        orchestrator._update_index(RUNS)
    except OSError:
        pass


def _payment_gate(led, led_path, run_id, price_cents, currency, job, mode):
    """Create a real TEST-mode Checkout Session, write the awaiting_payment ledger,
    then poll the session until paid (or time out).

    Returns the paid `earn` block (to carry into production) or None on
    timeout/failure (the ledger is set to failed in that case).
    """
    brand = (job.get("company_url") or "").replace("https://", "").replace("http://", "")
    brand = brand.replace("www.", "").split("/")[0] or "the product"
    product_name = "%s promo video" % brand

    simulate = os.environ.get("PRODUCER_SIMULATE_PAID") == "1"

    # H3: price_cents is the SOURCE OF TRUTH for what Stripe charges — it must be a
    # positive integer before we create a checkout. A None / 0 / negative / non-int
    # price would mint a $0 (or bogus) Checkout Session and ship a "delivered" video
    # the customer never paid for. A real (non-simulate) build with a bad price FAILS
    # cleanly; the $0 simulate dev path is allowed to proceed (it never settles money).
    try:
        price_ok = isinstance(price_cents, int) and not isinstance(price_cents, bool) \
            and price_cents > 0
    except Exception:
        price_ok = False
    if not price_ok and not simulate:
        led.event("error", "refusing checkout: invalid price_cents=%r" % (price_cents,))
        led.set_phase("checkout_failed")
        led.set_status("failed")
        led.write(led_path)
        return None

    # Create the real test-mode session ($0 — creating a test session never settles).
    # Guard it: a missing/bad Stripe key or a Stripe 4xx must FAIL the run cleanly, not
    # leave it parked at awaiting_payment with no Pay button (which strands the user).
    #
    # DEV AFFORDANCE: under PRODUCER_SIMULATE_PAID=1 with NO Stripe TEST key present,
    # session creation can't run (the earn helper is TEST-key-only). Rather than fail
    # the $0 simulated build, degrade to a keyless simulated-paid session — the exact
    # "with no key it degrades to a $0 simulated-paid block" path the simulate flow
    # documents below. The real human-pays path (no simulate flag) still FAILS cleanly
    # on a missing/bad key, so this never weakens a paid build.
    try:
        session = stripe_earn.create_checkout_session(
            run_id, int(price_cents or 0), currency=currency, product_name=product_name)
    except Exception as e:
        if simulate:
            led.event("info", "no Stripe checkout (%s) — PRODUCER_SIMULATE_PAID degrading "
                      "to a $0 simulated-paid session" % e)
            session = {"session_id": None, "url": None, "livemode": False,
                       "payment_status": "unpaid"}
        else:
            led.event("error", "could not create Stripe checkout: %s" % e)
            led.set_phase("checkout_failed")
            led.set_status("failed")
            led.write(led_path)
            return None

    earn = {
        "enabled": True,
        "provider": "stripe",
        "mode": "test",
        "status": "awaiting_payment",
        "session_id": session.get("session_id"),
        "checkout_url": session.get("url"),
        "price_cents": price_cents,
        "currency": currency,
        "product_name": product_name,
        "livemode": session.get("livemode"),
        "payment_status": session.get("payment_status") or "unpaid",
    }
    led.set_earn(earn)
    led.set_phase("awaiting_payment")
    led.set_status("running")
    led.event("money", "payment gate: Stripe TEST Checkout for $%.2f — awaiting payment"
              % ((price_cents or 0) / 100.0), session_id=earn["session_id"])
    led.write(led_path)

    # `simulate` was resolved above (before session creation) so the keyless degrade
    # can use it. Human-pays flow with no checkout URL = the user can never complete payment. Fail
    # cleanly rather than poll-to-timeout while the UI shows a Pay button that goes
    # nowhere. (Simulated-pay doesn't need a URL — it settles below.)
    if not simulate and not earn.get("checkout_url"):
        led.event("error", "checkout session has no payment URL — cannot collect payment")
        led.set_phase("checkout_failed")
        led.set_status("failed")
        led.write(led_path)
        return None
    if simulate:
        # Simulate the CUSTOMER paying the link with Stripe's 4242 test card. With a
        # sk_test_/rk_test_ key this is a REAL test-mode succeeded PaymentIntent
        # (visible in the Stripe test dashboard — no real money); with no key it
        # degrades to a $0 simulated-paid block. A live key is refused inside settle.
        try:
            pay = stripe_money.StripeMoney(live=True).settle_payment(
                int(price_cents or 0), currency,
                {"run_id": str(run_id), "session_id": earn.get("session_id") or ""})
        except Exception as e:
            pay = {"paid": True, "simulated": True, "status": "succeeded", "error": str(e),
                   "card_brand": "visa", "card_last4": "4242"}
        if pay.get("paid"):
            earn["status"] = "paid"
            earn["payment_status"] = "paid"
            earn["payment_intent_id"] = pay.get("payment_intent_id")
            earn["charge_id"] = pay.get("charge_id")
            earn["card_brand"] = pay.get("card_brand") or "visa"
            earn["card_last4"] = pay.get("card_last4") or "4242"
            earn["payment_simulated"] = bool(pay.get("simulated"))
            led.set_earn(earn)
            led.event("money", "customer paid $%.2f via %s ****%s — PaymentIntent %s (%s)" % (
                (price_cents or 0) / 100.0, (earn["card_brand"]).title(), earn["card_last4"],
                pay.get("payment_intent_id") or "succeeded",
                "real test-mode payment, no settlement" if not pay.get("simulated") else "simulated $0"),
                payment_intent_id=earn.get("payment_intent_id"))
            led.write(led_path)
            return earn
        # settle did not confirm — fall through to the normal poll loop below.
        led.event("info", "simulate-pay did not confirm (%s) — falling back to payment poll" % pay.get("status"))

    deadline = time.monotonic() + PAYMENT_TIMEOUT_S
    while True:
        if simulate:
            status = "paid"
        else:
            try:
                status = stripe_earn.get_session_status(earn["session_id"])
            except Exception as e:
                # transient network/Stripe error — record once and keep polling
                led.event("info", "payment poll error (will retry): %s" % e)
                status = earn.get("payment_status") or "unpaid"

        if status != earn.get("payment_status"):
            earn["payment_status"] = status
            led.set_earn(earn)
            led.write(led_path)

        if status in ("paid", "no_payment_required"):
            earn["status"] = "paid"
            led.set_earn(earn)
            led.write(led_path)
            return earn

        if time.monotonic() >= deadline:
            earn["status"] = "payment_timeout"
            led.set_earn(earn)
            led.set_phase("payment_timeout")
            led.set_status("failed")
            led.event("error", "payment gate timed out after %d min — no payment received; build cancelled"
                      % (PAYMENT_TIMEOUT_S // 60))
            led.write(led_path)
            return None

        time.sleep(PAYMENT_POLL_INTERVAL_S)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--goal", default="")
    ap.add_argument("--emphasis", default="",
                    help="feature/area to emphasize; becomes the STANDARD walkthrough's "
                         "specific multi-step goal (avoids the one-nav-link loop)")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--mode", choices=["mock", "real"], default="mock")
    ap.add_argument("--duration", type=int, default=30)
    ap.add_argument("--pace", type=float, default=1.2)
    ap.add_argument("--style", choices=list(plan_job.VALID_STYLES), default="snappy",
                    help="user-facing output style (DEFAULT snappy = more+shorter "
                         "scenes, ~6-8 scenes, 2-4s holds, faster cut rhythm) | "
                         "standard (legacy ~4-5 scenes, longer holds) | "
                         "cinematic (fewest+longest scenes)")
    ap.add_argument("--quality", choices=["standard", "premium"], default="standard",
                    help="video quality (the upfront cost-plus choice): standard "
                         "(Remotion + edge-tts, no Higgsfield/ElevenLabs, ~$5) | premium "
                         "(cinematic Higgsfield + ElevenLabs VO, ~$6-9)")
    ap.add_argument("--look", choices=["classic", "engineered-night", "walkrec"],
                    default="classic",
                    help="visual style family: classic light Timeline, "
                         "engineered-night dark one-world, or walkrec — the "
                         "agent-toured film (BETA: free, Sonnet-planned, "
                         "narrated live via agent_events)")
    ap.add_argument("--brain", choices=list(brain_mod.VALID_BRAINS), default=brain_mod.DEFAULT_BRAIN,
                    help="planner LLM (operator), all via OpenRouter: ultra-paid | "
                         "super-free (default, $0) | super-paid")
    a = ap.parse_args()
    if a.look == "walkrec":
        # WALKREC BETA (Dennis 2026-07-19): the agent-toured film. Free while
        # in beta (no payment gate), Sonnet-planned (the hackathon-era
        # Nemotron lock is scoped to classic per Dennis's sign-off), fully
        # narrated through run_events -> agent_events.
        import shutil as _sh
        import proto_walkrec
        import run_events
        from run_events import emit
        run_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "runs", a.run_id)
        # TERMINAL EVENTS ARE PART OF THE BUS CONTRACT (no silent endings):
        # hosted runs used to skip the run.start/run.done wrapper (it lived
        # only in the proto CLI), so the workspace never saw a terminal
        # state. The wrapper lives HERE now — the one entry point the
        # claimer actually runs.
        emit(run_dir, "run.start", f"Opening {a.url}",
             "Walkrec build claimed by the studio worker.")
        try:
            out = proto_walkrec.build_tour_film(a.url, a.run_id)
        except BaseException as e:
            emit(run_dir, "run.error", "The run hit a wall",
                 f"{type(e).__name__}: {e}")
            raise
        # PYTHON OWNS WALKREC DELIVERY (shared contract with the director
        # path): strategy-flow upload (no gateway cap) + runs.final_url as
        # the receipt the claimer verifies.
        run_events.ship_final(run_dir, a.run_id, out)
        emit(run_dir, "run.done", "Film delivered",
             "The tour film is rendered and shipped.")
        run_events.flush_sinks()
        print(f"[walkrec] final: {os.path.join(run_dir, 'final.mp4')}")
        return
    goal = a.goal or ("%d-second promo plus a short product walkthrough" % a.duration)
    globals()["ACTIVE_LOOK"] = a.look
    run(a.url, goal, a.run_id, a.mode, a.duration, a.pace, a.style,
        quality=a.quality, brain=a.brain, emphasis=a.emphasis)


if __name__ == "__main__":
    main()
