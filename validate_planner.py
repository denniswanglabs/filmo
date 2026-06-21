#!/usr/bin/env python3
"""Validate the Hermes scene-planner prompt with ONE free NVIDIA Super call.

Stdlib only. Makes a single chat-completions call (one repair retry max if the
returned text is not valid JSON), saves the model's plan to example-plan.json,
and asserts it matches the fixed contract.
"""
import json
import os
import re
import sys
import urllib.request
import urllib.error

API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "nvidia/nemotron-3-super-120b-a12b"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "example-plan.json")

# --- Brief under test (from the task) ---
BRIEF = {
    "company_url": "https://docs.stripe.com",
    "goal": "30-second brand promo",
    "target_duration_s": 30,
}

# --- Prompts (kept in sync with planner-prompt.md) ---
SYSTEM_PROMPT = """You are the scene-planner for an autonomous video-production studio. You convert a brief into a STRICT JSON scene plan. You output JSON ONLY -- no markdown, no code fences, no explanation, no text before or after. The first character of your reply MUST be { and the last MUST be }.

OUTPUT SCHEMA (these top-level keys and field names are FIXED -- never rename, add, or omit):

{
  "job": {
    "company_url": string,        // echo the brief's company_url exactly
    "goal": string,               // echo the brief's goal exactly
    "target_duration_s": integer, // echo the brief's target_duration_s exactly
    "target_margin": number,      // always 0.6
    "currency": "usd"             // always the literal string "usd"
  },
  "scenes": [
    {
      "id": string,               // short kebab id, unique
      "type": string,             // one of EXACTLY: "title" | "cinematic" | "motion_graphic"  (NO "walkthrough")
      "brief": string,            // one-sentence direction for this scene
      "model": string or null,    // see MODEL RULES
      "duration_s": integer,      // whole seconds, >= 2
      "input_image": null         // always null at planning time
    }
  ],
  "voiceover": {
    "voice": "Adam",              // always the literal string "Adam"
    "beats": [                    // ONE narration beat per scene, keyed by scene id
      {
        "scene_id": string,       // MUST match a scenes[].id exactly
        "text": string            // the line spoken WHILE that scene is on screen
      }
    ]
  }
}

QUALITY (the upfront customer choice — controls which scene types are allowed):
- If the brief is STANDARD quality (Remotion-only build): use ONLY the scene types "title" and "motion_graphic". Do NOT plan any "cinematic" scene and do NOT use the models "seedance_2_0" or "gpt_image_2" — there is no AI-footage stage in a standard build. Convey the company's positioning with 2-3 "motion_graphic" feature beats (designed, animated cards, model null) between the opening and closing title cards.
- If the brief is PREMIUM quality: the plan MUST include AT LEAST 2 "cinematic" scenes — this is a REQUIREMENT, not an option. Premium is defined by real AI-generated cinematic footage; a premium plan with zero cinematic scenes is INVALID. You MUST include both of these cinematic scenes:
    1. a cinematic ESTABLISHING shot with model "seedance_2_0" (a moving establishing plate of what the company does), and
    2. a cinematic HERO shot with model "gpt_image_2" (a composed hero still) or model "seedance_2_0" (a moving hero plate).
  You MAY add a 3rd or 4th cinematic scene (2-4 total) and optional "motion_graphic" feature beats, plus the opening and closing "title" cards. NEVER emit a premium plan whose only non-title scenes are motion_graphic.
- Default to STANDARD (Remotion-only) when quality is unspecified.
A separate QUALITY guidance block may be appended after this prompt; when present it is authoritative for which scene types you may emit.

STRUCTURE RULES (the scenes array MUST satisfy ALL of these):
1. The FIRST scene has type "title" (the opening brand/title card).
2. (PREMIUM only) Next come 2 to 4 scenes with type "cinematic" that convey the company's positioning (what it is, who it serves, why it matters) -- inferred from the company_url and goal. PREMIUM REQUIRES AT LEAST 2 cinematic scenes: a cinematic establishing shot (model "seedance_2_0") AND a cinematic hero shot (model "gpt_image_2" or "seedance_2_0"). Fewer than 2 cinematic scenes makes a PREMIUM plan INVALID. For STANDARD, plan 2-3 "motion_graphic" feature beats instead of any cinematic scene.
3. NEVER include a "walkthrough", screen-recording, or product-tour scene. There is no walkthrough scene type. Do not plan one under any circumstance, even if the goal mentions a "walkthrough", "demo", "tour", or "show the product" -- convey the product through cinematic (premium) or motion_graphic (standard or premium) feature beats instead.
4. The LAST scene has type "title" (the closing card / CTA).
5. You MAY include "motion_graphic" scenes (a divider, stat card, or feature beat); they are optional for premium and the PRIMARY content type for standard. model is null.
6. duration_s across ALL scenes MUST sum to EXACTLY target_duration_s. Verify the sum before you emit. If it does not match, adjust scene durations until it does.

The ONLY allowed scene types are: an opening "title" card, "cinematic" establishing / feature shots (PREMIUM only), "motion_graphic" feature beats, and a closing "title" card.

MODEL RULES (the "model" field):
- type "cinematic": choose a Higgsfield model.
    - "seedance_2_0"  if the scene needs MOTION (camera moves, animated b-roll, flowing visuals).
    - "gpt_image_2"   if the scene is a STILL plate (a single composed hero/establishing image).
  Pick per scene based on its brief. Prefer at least one of each across the cinematic scenes.
- type "title": model is null.
- type "motion_graphic": model is null.

VOICEOVER RULES:
- "voice" is always "Adam".
- "beats" is an array of per-scene narration lines. Emit ONE beat for EVERY scene
  whose type is NOT "title" (i.e. every cinematic / motion_graphic
  scene), and a beat for each title card that should be narrated (normally the
  opening title and the closing CTA title). Each beat's "scene_id" MUST equal that
  scene's "id".
- Each beat's "text" is the line spoken WHILE THAT SCENE IS ON SCREEN, and it MUST
  describe what that scene shows. Write it from that scene's "brief". This is how
  narration stays locked to the picture.
- WORD BUDGET PER BEAT: a beat must fit inside its own scene's duration. Budget
  about 2.5 words per second of that scene's duration_s, and never exceed 3
  words/second (e.g. a 6s scene -> ~15 words, max ~18; a 3s title -> ~7 words). A
  beat that overruns its scene will be cut off, so keep each beat short.
- The CLOSING title's beat is the call to action (e.g. "Start building today at
  <company>") so the CTA lands ON the closing card, not earlier.
- Do NOT emit a single combined "script" — use the per-scene "beats" array only.

VALIDITY:
- Output must be a single JSON object that parses with a standard JSON parser.
- Use double quotes, no trailing commas, no comments in the actual output.
- Echo company_url, goal, and target_duration_s from the brief without altering them."""

# The production planner (plan_job._plan_with_nemotron) appends a per-quality
# guidance block AFTER this base prompt. main() validates the PREMIUM path, so it
# appends the same premium guidance the pipeline sends — this is what makes the live
# call reliably yield >= 2 cinematic (a strengthened REQUIREMENT, not a suggestion).
# Keep in sync with plan_job._QUALITY_PROMPT["premium"].
PREMIUM_QUALITY_GUIDANCE = (
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
)

USER_PROMPT = (
    "Build the scene plan for this brief. Output JSON only.\n\n"
    f"company_url: {BRIEF['company_url']}\n"
    f"goal: {BRIEF['goal']}\n"
    f"target_duration_s: {BRIEF['target_duration_s']}\n"
)


def call_model(messages):
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        sys.exit("NVIDIA_API_KEY not set in environment")
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.2,
        # This model emits hidden reasoning tokens that count against the
        # completion budget but are not returned in `content`, so the plan + its
        # reasoning needs generous headroom or the JSON truncates mid-object.
        "max_tokens": 8000,
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    choice = body["choices"][0]
    fr = choice.get("finish_reason")
    if fr and fr != "stop":
        print(f"[finish_reason={fr} usage={body.get('usage')}]", file=sys.stderr)
    return choice["message"]["content"]


def extract_json(text):
    """Strip fences, take first { to last }, return parsed obj or raise."""
    t = text.strip()
    # drop a leading ```json / ``` fence and trailing ```
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in model output")
    return json.loads(t[start : end + 1])


def schema_check(plan, target_duration_s, quality="premium"):
    """Assert the plan matches the fixed contract for the given quality.

    quality="standard": the plan MUST be Remotion-only — ZERO cinematic and ZERO
    walkthrough scenes (only title + motion_graphic). quality="premium": cinematic
    scenes ARE allowed (2-4 required, the historical contract). Default is
    "premium" so the existing live validation run (PREMIUM-equivalent) is unchanged.
    """
    quality = "standard" if str(quality).strip().lower() == "standard" else "premium"
    problems = []
    if set(plan.keys()) != {"job", "scenes", "voiceover"}:
        problems.append(f"top-level keys are {sorted(plan.keys())}, expected job/scenes/voiceover")

    job = plan.get("job", {})
    if set(job.keys()) != {"company_url", "goal", "target_duration_s", "target_margin", "currency"}:
        problems.append(f"job keys are {sorted(job.keys())}")
    if job.get("currency") != "usd":
        problems.append(f"job.currency={job.get('currency')!r}, expected 'usd'")
    if job.get("target_duration_s") != target_duration_s:
        problems.append(f"job.target_duration_s={job.get('target_duration_s')}, expected {target_duration_s}")

    scenes = plan.get("scenes", [])
    allowed_types = {"title", "cinematic", "motion_graphic"}
    if not scenes:
        problems.append("scenes is empty")
    else:
        for i, s in enumerate(scenes):
            if set(s.keys()) != {"id", "type", "brief", "model", "duration_s", "input_image"}:
                problems.append(f"scene[{i}] keys are {sorted(s.keys())}")
            if s.get("type") not in allowed_types:
                problems.append(f"scene[{i}].type={s.get('type')!r} not allowed")
            if s.get("input_image") is not None:
                problems.append(f"scene[{i}].input_image should be null")
        if scenes[0].get("type") != "title":
            problems.append("first scene is not title")
        if scenes[-1].get("type") != "title":
            problems.append("last scene is not title")
        n_walk = sum(1 for s in scenes if s.get("type") == "walkthrough")
        if n_walk != 0:
            problems.append(f"walkthrough count={n_walk}, expected 0 (walkthrough scenes are no longer planned)")
        n_cine = sum(1 for s in scenes if s.get("type") == "cinematic")
        if quality == "standard":
            # STANDARD is Remotion-only: ZERO cinematic (and zero walkthrough, above).
            if n_cine != 0:
                problems.append(f"cinematic count={n_cine}, expected 0 for STANDARD (Remotion-only: title + motion_graphic)")
            n_mg = sum(1 for s in scenes if s.get("type") == "motion_graphic")
            if n_mg < 1:
                problems.append(f"motion_graphic count={n_mg}, expected >=1 for STANDARD (it carries the content beats)")
        else:
            # PREMIUM REQUIRES >= 2 cinematic (a seedance establishing shot + a
            # gpt/seedance hero shot); 4 is the historical upper bound on cinematic
            # scenes. Zero cinematic means premium is indistinguishable from standard.
            if n_cine < 2:
                problems.append(f"cinematic count={n_cine}, expected >=2 for PREMIUM (cinematic establishing + hero shots required)")
            elif n_cine > 4:
                problems.append(f"cinematic count={n_cine}, expected <=4")
        for s in scenes:
            if s.get("type") == "cinematic" and s.get("model") not in {"seedance_2_0", "gpt_image_2"}:
                problems.append(f"cinematic scene {s.get('id')!r} model={s.get('model')!r} invalid")
            if s.get("type") in {"title", "motion_graphic"} and s.get("model") is not None:
                problems.append(f"{s.get('type')} scene {s.get('id')!r} model should be null")
        total = sum(int(s.get("duration_s", 0)) for s in scenes)
        if total != target_duration_s:
            problems.append(f"durations sum to {total}, expected {target_duration_s}")

    vo = plan.get("voiceover", {})
    if vo.get("voice") != "Adam":
        problems.append(f"voiceover.voice={vo.get('voice')!r}, expected 'Adam'")
    # Scene-aligned schema: voiceover.beats = one {scene_id, text} per scene.
    beats = vo.get("beats")
    extra_keys = set(vo.keys()) - {"beats", "voice", "script"}
    if extra_keys:
        problems.append(f"voiceover has unexpected keys {sorted(extra_keys)}")
    if not isinstance(beats, list) or not beats:
        problems.append("voiceover.beats must be a non-empty array of {scene_id, text}")
    else:
        scene_ids = {s.get("id") for s in scenes}
        non_title_ids = {s.get("id") for s in scenes if s.get("type") != "title"} or scene_ids
        beat_scene_ids = []
        for j, b in enumerate(beats):
            if set(b.keys()) != {"scene_id", "text"}:
                problems.append(f"voiceover.beats[{j}] keys are {sorted(b.keys())}, expected scene_id/text")
            if b.get("scene_id") not in scene_ids:
                problems.append(f"voiceover.beats[{j}].scene_id={b.get('scene_id')!r} is not a scene id")
            if not (b.get("text") or "").strip():
                problems.append(f"voiceover.beats[{j}].text is empty")
            beat_scene_ids.append(b.get("scene_id"))
        # Every content (non-title) scene should be narrated; title cards may be
        # silent, but a beat per content scene is the contract that fixes drift.
        missing = non_title_ids - set(beat_scene_ids)
        if missing:
            problems.append(f"voiceover.beats missing a beat for scenes {sorted(missing)}")
    return problems


def main():
    # main() validates the PREMIUM path (schema_check defaults to premium), so send
    # the same base + premium guidance the production pipeline sends.
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + PREMIUM_QUALITY_GUIDANCE},
        {"role": "user", "content": USER_PROMPT},
    ]
    raw = call_model(messages)
    first_try_ok = True
    try:
        plan = extract_json(raw)
    except (ValueError, json.JSONDecodeError) as e:
        first_try_ok = False
        print(f"[first attempt did not parse: {e}] -> one repair retry", file=sys.stderr)
        repair = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "Your previous output did not parse as JSON. Return ONLY the corrected JSON object, nothing else."},
        ]
        raw2 = call_model(repair)
        plan = extract_json(raw2)  # let it raise if still bad

    with open(OUT, "w") as f:
        json.dump(plan, f, indent=2)

    problems = schema_check(plan, BRIEF["target_duration_s"])

    print(f"FIRST_TRY_VALID_JSON={first_try_ok}")
    print(f"SCHEMA_OK={not problems}")
    if problems:
        print("SCHEMA_PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
    print("---SCENE SUMMARY---")
    for s in plan["scenes"]:
        print(f"  {s['id']:<26} {s['type']:<14} {s['duration_s']:>2}s  model={s['model']}")
    total = sum(int(s["duration_s"]) for s in plan["scenes"])
    print(f"  TOTAL = {total}s (target {BRIEF['target_duration_s']}s)")
    # Scene-aligned schema: voiceover carries per-scene "beats", not a single "script".
    vo = plan.get("voiceover", {})
    beats = vo.get("beats") or []
    wc = sum(len((b.get("text") or "").split()) for b in beats)
    print(f"  voiceover: {len(beats)} beats, {wc} words, voice={vo.get('voice')!r}")
    print(f"  saved -> {OUT}")
    sys.exit(0 if (first_try_ok and not problems) or not problems else 2)


if __name__ == "__main__":
    main()
