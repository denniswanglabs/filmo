#!/usr/bin/env python3
"""URL + goal -> a validated scene plan. The "agent decides the storyboard" step.

Calls the free Nemotron planner (reusing validate_planner's prompt) to decompose a
brief into a scene plan, validates it against the schema, and returns it. Falls back
to a deterministic template plan if Nemotron is unavailable, so the live console can
always proceed. Stdlib only.
"""

import json
import os
import sys

import validate_planner as vp
from plan_schema import validate_plan

# --- Style differentiation -------------------------------------------------
# The three user-facing styles control the OUTPUT (scene count / hold durations /
# cut rhythm), NOT just console pacing. `standard` is the historical default and
# MUST leave the planner prompt and the plan untouched so today's exact output is
# reproduced. `snappy` and `cinematic` add real variation.
VALID_STYLES = ("snappy", "standard", "cinematic")

# Extra guidance appended to the planner SYSTEM_PROMPT per style. `target_duration_s`
# stays constant (total ~30s) — only the number of scenes and the per-scene holds
# change. standard injects nothing (None).
_STYLE_PROMPT = {
    "snappy": (
        "\n\nSTYLE: SNAPPY. Cut fast and keep energy high. Favour MORE scenes with "
        "SHORTER holds: aim for 6-8 scenes total, most non-title holds around 2-4 "
        "seconds. Include the optional motion_graphic scene (a quick divider or stat "
        "card) to add a cut. The durations must "
        "still sum to EXACTLY target_duration_s."
    ),
    "cinematic": (
        "\n\nSTYLE: CINEMATIC. Let shots breathe. Favour FEWER scenes with LONGER "
        "holds: aim for 4-5 scenes total, non-title holds around 6-9 seconds. Skip "
        "the optional motion_graphic. For the cinematic scenes prefer the "
        "\"seedance_2_0\" model (motion plates) over still \"gpt_image_2\" so the "
        "footage moves. The durations must still sum to EXACTLY target_duration_s."
    ),
    "standard": None,
}

# --- Quality differentiation -----------------------------------------------
# QUALITY ("standard" | "premium") is the upfront cost-plus choice. It is
# ORTHOGONAL to STYLE (which only sets pacing/scene-count/holds) and it gates the
# ALLOWED SCENE TYPES at PLAN time, so the storyboard the customer sees matches the
# stack that will actually produce it:
#   - STANDARD => Remotion-renderable scenes ONLY: "title" + "motion_graphic".
#                 NO cinematic (no seedance_2_0 / gpt_image_2), NO walkthrough.
#   - PREMIUM  => cinematic establishing/hero shots allowed (today's behavior).
# This fixes the bug where a Standard shot list still listed Seedance / GPT-image
# cinematic scenes that the Standard produce stack would never render.
VALID_QUALITIES = ("standard", "premium")

# Appended to the planner SYSTEM_PROMPT per quality, AFTER the style guidance.
# premium REQUIRES cinematic (>=2) so the plan actually uses Higgsfield footage and
# is visibly different from standard; standard forbids cinematic (Remotion-only).
_QUALITY_PROMPT = {
    "standard": (
        "\n\nQUALITY: STANDARD (Remotion-only). For THIS plan you may use ONLY the "
        "scene types \"title\" and \"motion_graphic\". Do NOT plan any \"cinematic\" "
        "scene and do NOT use the models \"seedance_2_0\" or \"gpt_image_2\" — there "
        "is NO Higgsfield/AI-footage stage in a standard build. OVERRIDE structure "
        "rule 2: instead of 2-4 cinematic scenes, plan 2-3 \"motion_graphic\" feature "
        "beats (designed, animated cards) between the opening and closing title cards "
        "to convey the company's positioning. Every non-title scene is a "
        "\"motion_graphic\" with model null. Keep the opening \"title\", the closing "
        "\"title\" CTA, and the durations summing to EXACTLY target_duration_s."
    ),
    "premium": (
        "\n\nQUALITY: PREMIUM (Higgsfield cinematic). This plan MUST include AT LEAST "
        "2 \"cinematic\" scenes — this is a HARD REQUIREMENT, not a suggestion. A "
        "premium plan with zero cinematic scenes is INVALID and looks identical to a "
        "cheap standard build, which defeats the premium tier. You MUST include BOTH "
        "of these cinematic scenes between the opening and closing title cards:\n"
        "  1. a cinematic ESTABLISHING shot with model \"seedance_2_0\" (a moving "
        "establishing plate of what the company does), and\n"
        "  2. a cinematic HERO shot with model \"gpt_image_2\" (a composed hero still) "
        "or model \"seedance_2_0\" (a moving hero plate).\n"
        "You MAY add a 3rd/4th cinematic scene (2-4 cinematic total) and optional "
        "\"motion_graphic\" feature beats, plus the opening and closing \"title\" "
        "cards. Do NOT make every non-title scene a motion_graphic. Keep the durations "
        "summing to EXACTLY target_duration_s."
    ),
}


def _normalize_quality(quality):
    q = str(quality or "").strip().lower()
    return q if q in VALID_QUALITIES else "standard"


def plan_job(company_url, goal, target_duration_s=30, target_margin=0.6,
             currency="usd", style="standard", quality="standard"):
    style = style if style in VALID_STYLES else "standard"
    quality = _normalize_quality(quality)
    plan = _plan_with_nemotron(company_url, goal, target_duration_s, style, quality)
    if plan is None:
        plan = _template_plan(company_url, goal, target_duration_s, style, quality)
    # force the brief fields so the rest of the pipeline is consistent
    plan.setdefault("job", {})
    plan["job"].update({"company_url": company_url, "goal": goal,
                        "target_duration_s": target_duration_s,
                        "target_margin": target_margin, "currency": currency})
    # Deterministic quality guard. STANDARD: coerce any cinematic/walkthrough to a
    # Remotion motion_graphic (title + motion_graphic only). PREMIUM: guarantee >= 2
    # cinematic by upgrading feature beats if the live model under-delivered. Runs
    # even when the model ignored the prompt.
    plan = _enforce_quality(plan, quality)
    # If PREMIUM still lacks >= 2 cinematic (too few non-title scenes to upgrade),
    # fall back to the deterministic premium template, which always has cinematic.
    if quality == "premium":
        n_cine = sum(1 for s in (plan.get("scenes") or [])
                     if isinstance(s, dict) and s.get("type") == "cinematic")
        if n_cine < 2:
            plan = _template_plan(company_url, goal, target_duration_s, style, quality)
            plan["job"].update({"company_url": company_url, "goal": goal,
                                "target_duration_s": target_duration_s,
                                "target_margin": target_margin, "currency": currency})
    # Deterministic backstop: redistribute the FIXED duration per style so the
    # rhythm differs even when the LLM ignores the prompt guidance. No-op for
    # standard (and for any plan that already matches the target shape closely).
    plan = _restyle_durations(plan, style, target_duration_s)
    problems = validate_plan(plan)
    if problems:
        # one more chance on the deterministic template before giving up
        plan = _template_plan(company_url, goal, target_duration_s, style, quality)
        plan["job"].update({"target_margin": target_margin, "currency": currency})
        problems = validate_plan(plan)
        if problems:
            raise ValueError("planner produced an invalid plan: " + "; ".join(problems))
    return plan


def _enforce_quality(plan, quality):
    """Deterministically make the plan match its quality tier (defense-in-depth).

    The SYSTEM_PROMPT + _QUALITY_PROMPT already steer the model, but small models
    drift, so this guarantees the contract no matter what the LLM returns:

    - STANDARD: coerce any cinematic/walkthrough scene to a Remotion motion_graphic
      (model null). A STANDARD plan can NEVER carry a cinematic or walkthrough scene
      by the time it leaves plan_job.
    - PREMIUM: GUARANTEE at least 2 cinematic scenes. If the model under-delivers
      (returns < 2 cinematic — the live-Nemotron bug), upgrade enough non-title
      feature beats (preferring motion_graphic, then any non-title) to cinematic so
      premium always has its establishing + hero shots. The first upgraded scene gets
      "seedance_2_0" (establishing/motion), the second "gpt_image_2" (hero still).
      Walkthrough scenes (which should never appear) are upgraded/normalized to
      cinematic here rather than dropped.

    Scene ids, order, durations, briefs, and voiceover beats are always preserved;
    only `type` and `model` are rewritten.
    """
    q = _normalize_quality(quality)
    scenes = [s for s in (plan.get("scenes") or []) if isinstance(s, dict)]
    if q == "standard":
        for s in scenes:
            if s.get("type") in ("cinematic", "walkthrough"):
                s["type"] = "motion_graphic"
                s["model"] = None
        return plan

    # PREMIUM: ensure >= 2 cinematic scenes with valid Higgsfield models.
    # First, normalize any stray walkthrough to cinematic (walkthrough is retired).
    for s in scenes:
        if s.get("type") == "walkthrough":
            s["type"] = "cinematic"
    # Fix any cinematic scene missing a valid model before counting.
    for s in scenes:
        if s.get("type") == "cinematic" and s.get("model") not in ("seedance_2_0", "gpt_image_2"):
            s["model"] = "seedance_2_0"

    cine = [s for s in scenes if s.get("type") == "cinematic"]
    if len(cine) >= 2:
        return plan

    # Under-delivered: upgrade feature beats to cinematic. Prefer motion_graphic
    # scenes (the model's "feature beats"); fall back to any non-title scene. Never
    # touch the opening/closing title cards. Preserve id, brief, duration; set type +
    # model. Assign seedance_2_0 (establishing/motion) then gpt_image_2 (hero still).
    need = 2 - len(cine)
    upgrade_models = ["seedance_2_0", "gpt_image_2"][len(cine):2]
    candidates = [s for s in scenes if s.get("type") == "motion_graphic"]
    if len(candidates) < need:
        candidates += [s for s in scenes if s.get("type") not in ("title", "cinematic", "motion_graphic")]
    for s, model in zip(candidates[:need], upgrade_models):
        s["type"] = "cinematic"
        s["model"] = model
    return plan


def _restyle_durations(plan, style, target_duration_s):
    """Deterministic re-timer: redistribute the fixed total across scenes per style.

    Keeps the scene LIST as the planner decided it (count, types, order, models,
    voiceover) and only rewrites `duration_s` so the total still equals
    target_duration_s while the per-scene holds reflect the style:
      - snappy   : compress non-title holds toward a SHORT floor (punchier cuts)
      - cinematic: expand non-title holds toward a LONG target (slower, breathing)
      - standard : identity — return the plan untouched (safety invariant)

    Title scenes keep their planner durations (the open/close cards are framing,
    not the content that should stretch/compress). All durations stay >= 2s
    integers and the sum is corrected to exactly target_duration_s.
    """
    if style == "standard":
        return plan
    scenes = plan.get("scenes") or []
    if not scenes:
        return plan
    titles = [s for s in scenes if s.get("type") == "title"]
    content = [s for s in scenes if s.get("type") != "title"]
    if not content:
        return plan

    # Title policy per style. The plan keeps 2-4 cinematic content scenes (no
    # walkthrough), so cinematic can't drop BELOW ~2 content scenes — the lever that
    # separates cinematic from standard is therefore HOLD LENGTH. Compress the framing title
    # cards to a tight floor for cinematic so that freed budget flows into long
    # content holds (clearly longer than a default-paced standard plan). Snappy
    # leaves titles as planned (its win is the higher cut count from the prompt).
    if style == "cinematic":
        for s in titles:
            s["duration_s"] = 2  # schema floor; frees max budget for long holds
    title_total = sum(max(2, int(s.get("duration_s", 3))) for s in titles)
    content_budget = target_duration_s - title_total
    if content_budget < 2 * len(content):
        # not enough room to re-time without starving scenes — leave as planned
        return plan

    # Per-style target hold for content scenes; we bias toward it but always
    # spend exactly `content_budget` across the content scenes. Cinematic aims
    # HIGH (10s) so even a 3-content-scene plan reads slower than standard's
    # natural ~6-8s holds; snappy aims short (3s) for punchy cuts.
    target_hold = 3 if style == "snappy" else 10  # snappy short, cinematic long
    n = len(content)
    base = max(2, min(target_hold, content_budget // n))
    durs = [base] * n
    # distribute the remainder so the sum hits content_budget exactly
    remainder = content_budget - base * n
    i = 0
    # snappy spreads leftover thinly (keeps holds short); cinematic piles leftover
    # onto the earlier (usually cinematic) scenes so a few shots run long.
    order = range(n) if style == "snappy" else range(n)
    idxs = list(order)
    if style == "cinematic":
        idxs = sorted(idxs, key=lambda k: 0 if content[k].get("type") == "cinematic" else 1)
    while remainder > 0:
        durs[idxs[i % n]] += 1
        remainder -= 1
        i += 1
    while remainder < 0:  # over budget (base floor too high) — trim round-robin
        k = idxs[i % n]
        if durs[k] > 2:
            durs[k] -= 1
            remainder += 1
        i += 1
    for s, d in zip(content, durs):
        s["duration_s"] = int(d)
    return plan


def _plan_with_nemotron(company_url, goal, target_duration_s, style="standard",
                        quality="standard"):
    if not os.environ.get("NVIDIA_API_KEY"):
        return None
    # Quality guidance goes LAST so its scene-type constraint overrides any style
    # text that mentions cinematic/seedance (e.g. the cinematic style preset).
    system = (vp.SYSTEM_PROMPT + (_STYLE_PROMPT.get(style) or "")
              + (_QUALITY_PROMPT.get(_normalize_quality(quality)) or ""))
    user = ("Build the scene plan for this brief. Output JSON only.\n\n"
            "company_url: %s\ngoal: %s\ntarget_duration_s: %d\n"
            % (company_url, goal, target_duration_s))
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    try:
        raw = vp.call_model(messages)
        try:
            return vp.extract_json(raw)
        except (ValueError, json.JSONDecodeError):
            repair = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "Your previous output did not parse. Return ONLY the corrected JSON object."}]
            return vp.extract_json(vp.call_model(repair))
    except Exception:
        return None  # any network/model failure -> fall back to the template


def _standard_template_plan(brand, company_url, goal, target_duration_s, style):
    """Remotion-only deterministic plan: title + motion_graphic feature beats + title.

    No cinematic, no walkthrough — every content scene is a designed motion_graphic
    (model null) so a standard build renders entirely in Remotion. Durations sum to
    EXACTLY target_duration_s here (and stay summed after _restyle_durations).
    """
    # Three motion-graphic feature beats give the standard plan the same 5-scene
    # shape as the premium template, so pacing/pricing surfaces look familiar.
    open_d, close_d = 3, 5
    body = max(2, target_duration_s - open_d - close_d)
    n = 3
    base = max(2, body // n)
    feat_durs = [base] * n
    rem = body - base * n
    i = 0
    while rem > 0:
        feat_durs[i % n] += 1
        rem -= 1
        i += 1
    while rem < 0:
        k = i % n
        if feat_durs[k] > 2:
            feat_durs[k] -= 1
            rem += 1
        i += 1

    scenes = [
        {"id": "title-open", "type": "title", "brief": "%s wordmark and tagline" % brand,
         "model": None, "duration_s": open_d, "input_image": None},
        {"id": "feature-what", "type": "motion_graphic",
         "brief": "Animated feature beat: what %s is and who it serves" % brand,
         "model": None, "duration_s": feat_durs[0], "input_image": None},
        {"id": "feature-how", "type": "motion_graphic",
         "brief": "Animated feature beat highlighting how %s works" % brand,
         "model": None, "duration_s": feat_durs[1], "input_image": None},
        {"id": "feature-why", "type": "motion_graphic",
         "brief": "Animated stat/feature card on why %s matters" % brand,
         "model": None, "duration_s": feat_durs[2], "input_image": None},
        {"id": "title-close", "type": "title", "brief": "Call to action: get started with %s" % brand,
         "model": None, "duration_s": close_d, "input_image": None},
    ]
    beats = [
        {"scene_id": "title-open", "text": "%s." % brand},
        {"scene_id": "feature-what", "text": "%s helps you do more with less." % brand},
        {"scene_id": "feature-how", "text": "Here is how it works."},
        {"scene_id": "feature-why", "text": "Built for the way you work."},
        {"scene_id": "title-close", "text": "Get started with %s today." % brand},
    ]
    return {
        "job": {"company_url": company_url, "goal": goal,
                "target_duration_s": target_duration_s, "target_margin": 0.6, "currency": "usd"},
        "scenes": scenes,
        "voiceover": {"voice": "Adam", "beats": beats},
    }


def _template_plan(company_url, goal, target_duration_s, style="standard",
                   quality="standard"):
    brand = _brand_name(company_url)
    quality = _normalize_quality(quality)

    # STANDARD: Remotion-only deterministic fallback. NO cinematic, NO walkthrough —
    # an opening title, 2-3 motion_graphic feature beats, a closing title CTA. This
    # is the path the NVIDIA_API_KEY-unset console uses, so it must satisfy the
    # standard=Remotion-only contract on its own. (PREMIUM keeps the cinematic
    # template below.) _restyle_durations re-times the holds for snappy/cinematic
    # style while keeping the scene TYPES Remotion-only.
    if quality == "standard":
        plan = _standard_template_plan(brand, company_url, goal, target_duration_s, style)
        return _restyle_durations(plan, style, target_duration_s)

    # durations sum to target (3 + 6 + feat + 6 + close). `feat` is the middle
    # cinematic feature beat that replaced the retired walkthrough scene.
    feat = max(6, target_duration_s - 3 - 6 - 6 - 5)

    if style == "snappy":
        # MORE scenes, SHORTER holds: add a motion_graphic divider + a 3rd cinematic
        # so the cut count is higher than the default 5-scene template.
        scenes = [
            {"id": "title-open", "type": "title", "brief": "%s wordmark and tagline" % brand,
             "model": None, "duration_s": 3, "input_image": None},
            {"id": "cine-establish", "type": "cinematic",
             "brief": "Cinematic establishing shot of what %s does" % brand,
             "model": "seedance_2_0", "duration_s": 4, "input_image": None},
            {"id": "motion-divider", "type": "motion_graphic",
             "brief": "Quick divider card with the text 'Built for teams'",
             "model": None, "duration_s": 3, "input_image": None},
            {"id": "cine-feature", "type": "cinematic",
             "brief": "Fast b-roll montage of %s features" % brand,
             "model": "seedance_2_0", "duration_s": 4, "input_image": None},
            {"id": "feature-beat", "type": "motion_graphic",
             "brief": "Animated feature beat highlighting what %s does best" % brand,
             "model": None, "duration_s": 5, "input_image": None},
            {"id": "cine-hero", "type": "cinematic",
             "brief": "Clean hero plate of the %s product UI" % brand,
             "model": "gpt_image_2", "duration_s": 4, "input_image": None},
            {"id": "title-close", "type": "title", "brief": "Call to action: get started with %s" % brand,
             "model": None, "duration_s": 4, "input_image": None},
        ]
        beats = [
            {"scene_id": "title-open", "text": "%s." % brand},
            {"scene_id": "cine-establish", "text": "%s helps you do more with less." % brand},
            {"scene_id": "motion-divider", "text": "Built for teams."},
            {"scene_id": "cine-feature", "text": "Powerful features, fast."},
            {"scene_id": "feature-beat", "text": "Here is what makes it work."},
            {"scene_id": "cine-hero", "text": "Built for the way you work."},
            {"scene_id": "title-close", "text": "Get started with %s today." % brand},
        ]
    elif style == "cinematic":
        # FEWER scenes, LONGER holds: drop the second cinematic + lean on seedance
        # motion plates so the few shots breathe.
        scenes = [
            {"id": "title-open", "type": "title", "brief": "%s wordmark and tagline" % brand,
             "model": None, "duration_s": 4, "input_image": None},
            {"id": "cine-establish", "type": "cinematic",
             "brief": "Slow cinematic establishing shot of what %s does" % brand,
             "model": "seedance_2_0", "duration_s": 9, "input_image": None},
            {"id": "cine-feature", "type": "cinematic",
             "brief": "Slow cinematic feature montage of %s in action" % brand,
             "model": "seedance_2_0", "duration_s": 8, "input_image": None},
            {"id": "title-close", "type": "title", "brief": "Call to action: get started with %s" % brand,
             "model": None, "duration_s": 9, "input_image": None},
        ]
        beats = [
            {"scene_id": "title-open", "text": "%s." % brand},
            {"scene_id": "cine-establish", "text": "%s helps you do more with less." % brand},
            {"scene_id": "cine-feature", "text": "See it in action, end to end."},
            {"scene_id": "title-close", "text": "Get started with %s today." % brand},
        ]
    else:  # standard — UNCHANGED from the historical default (safety invariant)
        scenes = [
            {"id": "title-open", "type": "title", "brief": "%s wordmark and tagline" % brand,
             "model": None, "duration_s": 3, "input_image": None},
            {"id": "cine-establish", "type": "cinematic",
             "brief": "Cinematic establishing shot of what %s does" % brand,
             "model": "seedance_2_0", "duration_s": 6, "input_image": None},
            {"id": "cine-feature", "type": "cinematic",
             "brief": "Cinematic feature montage of %s in action" % brand,
             "model": "seedance_2_0", "duration_s": feat, "input_image": None},
            {"id": "cine-hero", "type": "cinematic",
             "brief": "Clean hero plate of the %s product UI" % brand,
             "model": "gpt_image_2", "duration_s": 6, "input_image": None},
            {"id": "title-close", "type": "title", "brief": "Call to action: get started with %s" % brand,
             "model": None, "duration_s": 5, "input_image": None},
        ]
        beats = [
            {"scene_id": "title-open", "text": "%s." % brand},
            {"scene_id": "cine-establish", "text": "%s helps you do more with less." % brand},
            {"scene_id": "cine-feature", "text": "See it in action, end to end."},
            {"scene_id": "cine-hero", "text": "Built for the way you work."},
            {"scene_id": "title-close", "text": "Get started with %s today." % brand},
        ]

    plan = {
        "job": {"company_url": company_url, "goal": goal,
                "target_duration_s": target_duration_s, "target_margin": 0.6, "currency": "usd"},
        # Scene-aligned beats: one narration line per scene, keyed by scene id,
        # each sized to its scene's duration so it lands on the matching picture.
        "scenes": scenes,
        "voiceover": {"voice": "Adam", "beats": beats},
    }
    # Re-time the deterministic fallback per style too, so the durations always sum
    # to target_duration_s and the holds match the style (standard = identity).
    return _restyle_durations(plan, style, target_duration_s)


def _brand_name(url):
    u = (url or "").lower().replace("https://", "").replace("http://", "").replace("www.", "")
    host = u.split("/")[0].split(".")
    name = host[-2] if len(host) >= 2 else (host[0] if host else "the product")
    return name.capitalize()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--goal", default="")
    ap.add_argument("--duration", type=int, default=30)
    ap.add_argument("--style", choices=list(VALID_STYLES), default="standard")
    ap.add_argument("--quality", choices=list(VALID_QUALITIES), default="standard",
                    help="standard => Remotion-only (title + motion_graphic, no cinematic); "
                         "premium => cinematic shots allowed")
    a = ap.parse_args()
    p = plan_job(a.url, a.goal or ("%d-second promo" % a.duration), a.duration,
                 style=a.style, quality=a.quality)
    json.dump(p, sys.stdout, indent=2)
    print()
