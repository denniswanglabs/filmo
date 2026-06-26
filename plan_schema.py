#!/usr/bin/env python3
"""Generic scene-plan validator (shared by the orchestrator + tests).

This is the duration-flexible cousin of validate_planner.py's schema_check. It
validates the SHAPE of a scene plan (the contract in SCHEMA.md) without being
tied to one fixed brief, so the orchestrator can reject a malformed plan before
spending a single (mock or real) cycle on it.

Returns a list of human-readable problems; an empty list means the plan is valid.
"""

ALLOWED_TYPES = {"title", "cinematic", "walkthrough", "motion_graphic", "screenshot"}
CINEMATIC_MODELS = {"seedance_2_0", "gpt_image_2", "nano_banana_flash", "nano_banana_2"}

# Cost-plus selection vocabulary. The active model has NO tiers and ONE customer
# choice, made upfront: a QUALITY dimension (standard | premium). It changes WHAT
# THE AGENT PRODUCES (standard = Remotion + edge-tts; premium = Higgsfield +
# ElevenLabs) and therefore the cost-plus price. Legacy tier/booster/premium_vo
# fields are TOLERATED on input (so old plans still validate) and bridged to
# quality downstream — the schema is intentionally permissive here.
SELECTION_QUALITY = {"standard", "premium"}


# Card-treatment vocabulary (SHARED DATA CONTRACT with the Remotion ExplainerCard
# archetype). These optional fields live on scene["data"] for motion_graphic /
# explainer-card scenes. ALL optional: a scene that omits them is still valid (the
# visual side renders a plain card). When present they must be well-shaped.
CARD_TREATMENTS = {"icon-stat", "split-mosaic", "split-stat", "icon-headline"}


def validate_scene_data(data):
    """Validate the OPTIONAL card-treatment fields on a scene's `data`. Returns [].

    Pass-through-but-validated: every field is optional (a `data` without them is
    valid), but a present field must be well-shaped:
      - treatment      one of CARD_TREATMENTS
      - icon           a non-empty string
      - stat           {"value": str, "label": str}
      - featureEntities list[str]   (NOT `entities` — that collided with an existing field)
    Unknown extra keys are tolerated (data carries many other archetype fields)."""
    problems = []
    if data is None:
        return problems
    if not isinstance(data, dict):
        return ["scene.data is not an object"]

    if "treatment" in data and data.get("treatment") not in CARD_TREATMENTS:
        problems.append("scene.data.treatment=%r must be one of %s"
                        % (data.get("treatment"), sorted(CARD_TREATMENTS)))
    if "icon" in data and not (isinstance(data.get("icon"), str) and data.get("icon").strip()):
        problems.append("scene.data.icon=%r must be a non-empty string" % data.get("icon"))
    if "stat" in data:
        stat = data.get("stat")
        if not isinstance(stat, dict):
            problems.append("scene.data.stat=%r must be an object {value,label}" % stat)
        else:
            for k in ("value", "label"):
                if not isinstance(stat.get(k), str):
                    problems.append("scene.data.stat.%s=%r must be a string" % (k, stat.get(k)))
    if "featureEntities" in data:
        ents = data.get("featureEntities")
        if not isinstance(ents, list) or not all(isinstance(e, str) for e in ents):
            problems.append("scene.data.featureEntities=%r must be a list of strings" % ents)
    return problems


def default_selection():
    """The documented default `selection` for plans that omit one.

    Cost-plus model: the default quality is "standard" (Remotion + edge-tts).
    Matches pricing.default_selection() exactly (duplicated here to keep
    plan_schema import-free). Plans WITHOUT a `selection` are valid (back-compat);
    a consumer that needs one can call this.
    """
    return {"quality": "standard"}


def validate_selection(selection):
    """Validate the SHAPE of a `selection` object. Returns [] if valid.

    The active cost-plus shape is {"quality": "standard"|"premium"}. To preserve
    back-compat, OLD selections that still carry the retired tier/boosters/options
    (incl. options.premium_vo) are ACCEPTED (those fields are bridged to quality
    downstream). We only reject a `quality` value that is present but not a known
    tier. This keeps the validator dependency-free and tolerant of stale plans.
    """
    problems = []
    if not isinstance(selection, dict):
        return ["selection is not an object"]

    if "quality" in selection:
        q = selection.get("quality")
        if q not in SELECTION_QUALITY:
            problems.append("selection.quality=%r must be one of %s"
                            % (q, sorted(SELECTION_QUALITY)))
    # Legacy options.premium_vo (if present) must still be a bool when carried.
    options = selection.get("options", {})
    if "options" in selection and not isinstance(options, dict):
        problems.append("selection.options must be an object")
        options = {}
    if "premium_vo" in options and not isinstance(options.get("premium_vo"), bool):
        problems.append("selection.options.premium_vo=%r must be a bool"
                        % options.get("premium_vo"))
    return problems


def resolve_vo_beats(plan):
    """Return the voiceover as a list of per-scene beats: [{scene_id, text}, ...].

    Single source of truth for "which narration line belongs to which scene",
    used by the orchestrator to synthesize + place VO per scene. Handles BOTH
    schemas so old runs/tests never break:

      - NEW: voiceover.beats already keyed by scene_id -> returned as-is
        (text coerced to str, blank-text beats dropped).
      - OLD: a single voiceover.script string -> split into sentences and mapped
        onto the scene order so each scene still gets a beat. If there are more
        sentences than scenes, the tail sentences fold into the last scene's
        beat; if fewer, the remaining scenes get no beat (silent on that clip)
        rather than fabricating words.

    Beats whose scene_id is not in the plan are kept (the caller decides whether
    a stray beat is droppable); beats are NOT reordered — placement uses the
    scene's own offset, so order in the list is immaterial.
    """
    vo = plan.get("voiceover") or {}
    scenes = [s for s in (plan.get("scenes") or []) if isinstance(s, dict)]
    scene_ids = [s.get("id") for s in scenes]

    beats = vo.get("beats")
    if isinstance(beats, list) and beats:
        out = []
        for b in beats:
            if not isinstance(b, dict):
                continue
            text = str(b.get("text") or "").strip()
            if text and b.get("scene_id"):
                out.append({"scene_id": b.get("scene_id"), "text": text})
        return out

    # --- legacy single-script fallback: split sentences across scenes ---------
    script = str(vo.get("script") or "").strip()
    if not script or not scene_ids:
        return []
    sentences = _split_sentences(script)
    if not sentences:
        return []
    # Map sentences onto scenes 1:1; fold any overflow into the last scene so no
    # narration is ever dropped, and never invent text for the remainder.
    n = len(scene_ids)
    out = []
    for i, sid in enumerate(scene_ids):
        if i >= len(sentences):
            break
        if i == n - 1:
            text = " ".join(sentences[i:]).strip()       # last scene absorbs the tail
        else:
            text = sentences[i].strip()
        if text:
            out.append({"scene_id": sid, "text": text})
    return out


def _split_sentences(text):
    """Naive, dependency-free sentence splitter for the legacy script fallback."""
    import re
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def vo_script_from_beats(beats):
    """Flatten beats back into one script string (for cost estimation + the
    console projection, which still read voiceover.script)."""
    return " ".join(b.get("text", "").strip() for b in beats if b.get("text")).strip()


def validate_plan(plan, *, strict_durations=False):
    """Validate a scene plan dict. Returns [] if valid, else a list of problems.

    strict_durations=True additionally requires the scene durations to sum to
    job.target_duration_s (the planner contract). The orchestrator runs with
    strict_durations=False so a hand-crafted test plan need not hit the target
    exactly; validate_planner.py keeps the strict check for the live planner.
    """
    problems = []

    if not isinstance(plan, dict):
        return ["plan is not a JSON object"]

    # `selection` is an OPTIONAL fourth top-level key (the premium menu). Plans
    # without it remain valid (back-compat, esp. when WS_PREMIUM_MENU is OFF).
    # `_planner` is an OPTIONAL internal provenance block (plan_source / brain /
    # finish_reason / token usage) stamped by plan_job so EVERY build plainly shows
    # whether the real LLM planned it or it fell back to the deterministic template.
    allowed_top = {"job", "scenes", "voiceover", "selection", "_planner"}
    extra = set(plan.keys()) - allowed_top
    missing_core = {"job", "scenes", "voiceover"} - set(plan.keys())
    if extra or missing_core:
        problems.append(
            "top-level keys are %s, expected job/scenes/voiceover (+ optional selection)"
            % sorted(plan.keys())
        )

    job = plan.get("job", {})
    if not isinstance(job, dict):
        problems.append("job is not an object")
        job = {}
    # Required job keys (presence only — extras like the optional "emphasis" hint,
    # which carries the feature to demonstrate in the STANDARD walkthrough, are
    # tolerated so a grounded plan validates).
    for k in ("company_url", "goal", "target_duration_s", "target_margin", "currency"):
        if k not in job:
            problems.append("job missing %r" % k)
    margin = job.get("target_margin")
    if isinstance(margin, (int, float)) and not (0.0 <= margin < 1.0):
        problems.append("job.target_margin=%r must be in [0, 1)" % margin)

    scenes = plan.get("scenes", [])
    if not isinstance(scenes, list) or not scenes:
        problems.append("scenes must be a non-empty array")
        scenes = scenes if isinstance(scenes, list) else []

    seen_ids = set()
    for i, s in enumerate(scenes):
        if not isinstance(s, dict):
            problems.append("scene[%d] is not an object" % i)
            continue
        missing = {"id", "type", "brief", "model", "duration_s", "input_image"} - set(s.keys())
        if missing:
            problems.append("scene[%d] missing %s" % (i, sorted(missing)))
        sid = s.get("id")
        if sid in seen_ids:
            problems.append("scene[%d] duplicate id %r" % (i, sid))
        seen_ids.add(sid)
        stype = s.get("type")
        if stype not in ALLOWED_TYPES:
            problems.append("scene[%d].type=%r not in %s" % (i, stype, sorted(ALLOWED_TYPES)))
        dur = s.get("duration_s")
        if not isinstance(dur, int) or dur < 1:
            problems.append("scene[%d].duration_s=%r must be a positive int" % (i, dur))
        if stype == "cinematic":
            if s.get("model") not in CINEMATIC_MODELS:
                problems.append(
                    "cinematic scene %r model=%r not in %s"
                    % (sid, s.get("model"), sorted(CINEMATIC_MODELS))
                )
        elif stype in {"title", "walkthrough", "motion_graphic", "screenshot"}:
            if s.get("model") is not None:
                problems.append("%s scene %r model should be null" % (stype, sid))
        # OPTIONAL card-treatment fields on data (icon-stat/split-mosaic/...) — when
        # present they must be well-shaped; a scene that omits them stays valid.
        if "data" in s:
            problems.extend(validate_scene_data(s.get("data")))

    vo = plan.get("voiceover", {})
    if not isinstance(vo, dict):
        problems.append("voiceover is not an object")
    else:
        if "voice" not in vo:
            problems.append("voiceover missing 'voice'")
        # New scene-aligned schema carries per-scene `beats`; the legacy schema
        # carried a single `script` string. EITHER is valid (a single-script plan
        # is treated as one whole-video beat downstream). Require at least one.
        beats = vo.get("beats")
        script = vo.get("script")
        if beats is None and not script:
            problems.append("voiceover has neither 'beats' nor 'script'")
        if beats is not None:
            if not isinstance(beats, list) or not beats:
                problems.append("voiceover.beats must be a non-empty array when present")
            else:
                for j, b in enumerate(beats):
                    if not isinstance(b, dict):
                        problems.append("voiceover.beats[%d] is not an object" % j)
                        continue
                    if not b.get("scene_id"):
                        problems.append("voiceover.beats[%d] missing 'scene_id'" % j)
                    elif seen_ids and b.get("scene_id") not in seen_ids:
                        problems.append(
                            "voiceover.beats[%d] scene_id %r is not a scene id"
                            % (j, b.get("scene_id")))
                    if not b.get("text"):
                        problems.append("voiceover.beats[%d] has empty 'text'" % j)

    # Optional premium `selection` — validated only when present (back-compat).
    if "selection" in plan:
        problems.extend(validate_selection(plan.get("selection")))

    if strict_durations and scenes:
        total = sum(int(s.get("duration_s", 0)) for s in scenes if isinstance(s, dict))
        target = job.get("target_duration_s")
        if isinstance(target, int) and total != target:
            problems.append("durations sum to %d, expected %d" % (total, target))

    return problems


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        sys.exit("usage: plan_schema.py <plan.json>")
    with open(sys.argv[1]) as f:
        plan = json.load(f)
    probs = validate_plan(plan)
    if probs:
        print("INVALID:")
        for p in probs:
            print("  -", p)
        sys.exit(1)
    print("VALID")
