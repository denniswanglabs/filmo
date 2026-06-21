# Hermes Scene-Planner Prompt

This file holds the exact prompt the `producer-brain` step-1 PLAN call sends to Nemotron.
It turns a brief (`{company_url, goal, target_duration_s}`) into a **strict scene-plan
JSON** that the rest of the pipeline (pricing, Stripe earn, per-scene spend gate, render,
stitch) consumes.

The output JSON contract is **fixed** — another component reads these exact field names, so
the prompt must not rename, add, or drop top-level fields. Field names are frozen at:

```json
{
  "job":        {"company_url": str, "goal": str, "target_duration_s": int, "target_margin": float, "currency": "usd"},
  "scenes":     [ {"id": str, "type": "title|cinematic|motion_graphic", "brief": str, "model": str|null, "duration_s": int, "input_image": str|null} ],
  "voiceover":  {"voice": str, "beats": [ {"scene_id": str, "text": str} ]}
}
```

`voiceover.beats` carries **one narration beat per scene, keyed by scene id**, so the
stitch can place each line at its scene's start offset (the line lands on the picture
it describes) and **drop the beat for any scene the budget gate cut**. The legacy
single-`script` shape is still accepted by the pipeline (it is split into per-scene
beats as a fallback), but the planner MUST emit `beats`.

---

## Prompt approach (why it is shaped this way)

- **JSON-only, no prose.** The system prompt forbids markdown fences, preambles, and trailing
  commentary so the consumer can `json.loads` the raw completion. We also instruct the model
  to emit a single object whose first character is `{` and last is `}`.
- **The contract is restated verbatim** with allowed enum values and per-field rules, so the
  model has no room to invent fields. Reliability of small-model JSON comes from *constraining
  the surface*, not from asking nicely.
- **Structural invariants are spelled out as numbered rules** (open `title`, >= 2 (2-4)
  required `cinematic` for PREMIUM, close `title`, durations sum to target). NO walkthrough /
  screen-recording / product-tour scene is ever planned. The model is told to self-check the
  sum before emitting.
- **Quality gates the allowed scene types** (the upfront customer choice, threaded into the
  planner at PLAN time):
  - **STANDARD = Remotion-only.** Allowed scene types are ONLY `title` and `motion_graphic`.
    NO `cinematic` scene, NO `seedance_2_0` / `gpt_image_2` model — there is no Higgsfield /
    AI-footage stage in a standard build. The company's positioning is carried by 2-3
    `motion_graphic` feature beats between the opening and closing title cards. This keeps the
    storyboard the customer sees in sync with the stack that actually renders it.
  - **PREMIUM REQUIRES cinematic.** A premium plan MUST include AT LEAST 2 `cinematic` scenes:
    a cinematic **establishing** shot (`seedance_2_0`) and a cinematic **hero** shot
    (`gpt_image_2` or `seedance_2_0`), plus the opening/closing `title` cards and optional
    `motion_graphic` feature beats. Zero cinematic makes a premium plan INVALID — it would look
    identical to a standard build and skip the Higgsfield footage that defines the tier.
  The harness appends a per-quality guidance block to the SYSTEM PROMPT (after the style
  block), and a deterministic backstop enforces both ends: it coerces any stray
  `cinematic`/`walkthrough` scene to a `motion_graphic` for STANDARD, and for PREMIUM it
  upgrades feature beats to `cinematic` (assigning `seedance_2_0` then `gpt_image_2`, preserving
  ids/durations) if the small model returns fewer than 2 cinematic scenes.
- **Model selection is a lookup, not a judgment**: `seedance_2_0` for cinematic scenes that
  need motion, `gpt_image_2` for cinematic still plates; `title`/`motion_graphic`
  carry `model: null` (rendered by Remotion, no Higgsfield spend).
- **`temperature` is set low (0.2)** in the API call — planning is structured extraction, not
  creative writing; low temp improves schema adherence.
- **One repair retry path** is documented below for the harness: if `json.loads` fails, send
  the malformed text back with a one-line "return only valid JSON, fix the parse error"
  instruction. No expensive loop.

---

## SYSTEM PROMPT

```
You are the scene-planner for an autonomous video-production studio. You convert a brief into
a STRICT JSON scene plan. You output JSON ONLY — no markdown, no code fences, no explanation,
no text before or after. The first character of your reply MUST be { and the last MUST be }.

OUTPUT SCHEMA (these top-level keys and field names are FIXED — never rename, add, or omit):

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
      "id": string,               // short kebab id, unique, e.g. "open-title", "scene-positioning-1"
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
- If the brief is STANDARD quality (Remotion-only build): use ONLY the scene types "title"
  and "motion_graphic". Do NOT plan any "cinematic" scene and do NOT use the models
  "seedance_2_0" or "gpt_image_2". Convey the company's positioning with 2-3 "motion_graphic"
  feature beats (designed, animated cards, model null) between the opening and closing titles.
- If the brief is PREMIUM quality: the plan MUST include AT LEAST 2 "cinematic" scenes — this
  is a REQUIREMENT, not an option. You MUST include (1) a cinematic ESTABLISHING shot with
  model "seedance_2_0" and (2) a cinematic HERO shot with model "gpt_image_2" or "seedance_2_0",
  plus the opening/closing title cards and optional motion_graphic feature beats. A premium plan
  with zero cinematic scenes is INVALID.
- Default to STANDARD (Remotion-only) when quality is unspecified.
A QUALITY guidance block is appended after this prompt; when present it is authoritative.

STRUCTURE RULES (the scenes array MUST satisfy ALL of these):
1. The FIRST scene has type "title" (the opening brand/title card).
2. (PREMIUM only) Next come 2 to 4 scenes with type "cinematic" that convey the company's
   positioning (what it is, who it serves, why it matters) — inferred from the company_url and
   goal. PREMIUM REQUIRES AT LEAST 2 cinematic: a cinematic establishing shot (model
   "seedance_2_0") AND a cinematic hero shot (model "gpt_image_2" or "seedance_2_0"). Fewer than
   2 cinematic makes a PREMIUM plan INVALID. For STANDARD, plan 2-3 "motion_graphic" feature
   beats instead of any cinematic scene.
3. NEVER include a "walkthrough", screen-recording, or product-tour scene. There is no
   walkthrough scene type. Do not plan one under any circumstance, even if the goal mentions
   a "walkthrough", "demo", "tour", or "show the product" — convey the product through
   cinematic (premium) or motion_graphic feature beats instead.
4. The LAST scene has type "title" (the closing card / CTA).
5. You MAY include "motion_graphic" scenes (a divider or stat card); they are optional for
   premium and the PRIMARY content type for standard. model is null. Use a motion_graphic
   feature beat to highlight a specific product feature.
6. duration_s across ALL scenes MUST sum to EXACTLY target_duration_s. Verify the sum
   before you emit. If it does not match, adjust scene durations until it does.

The ONLY allowed scene types are: an opening "title" card, "cinematic" establishing /
feature shots (PREMIUM only), "motion_graphic" feature beats, and a closing "title" card.

MODEL RULES (the "model" field):
- type "cinematic": choose a Higgsfield model.
    - "seedance_2_0"  if the scene needs MOTION (camera moves, animated b-roll, flowing visuals).
    - "gpt_image_2"   if the scene is a STILL plate (a single composed hero/establishing image).
  Pick per scene based on its brief. Prefer at least one of each across the cinematic scenes.
- type "title": model is null.
- type "motion_graphic": model is null.

VOICEOVER RULES:
- "voice" is always "Adam".
- "beats" is an array of per-scene narration lines. Emit ONE beat for EVERY scene whose type
  is NOT "title" (every cinematic / motion_graphic scene), plus a beat for each
  title card that should be narrated (normally the opening title and the closing CTA title).
  Each beat's "scene_id" MUST equal that scene's "id".
- Each beat's "text" is the line spoken WHILE THAT SCENE IS ON SCREEN and MUST describe what
  that scene shows — write it from that scene's "brief". This is what keeps the narration
  locked to the picture instead of drifting.
- WORD BUDGET PER BEAT: each beat must fit inside its own scene's duration. Budget ~2.5 words
  per second of that scene's duration_s and never exceed 3 words/second (e.g. a 6s scene ->
  ~15 words, max ~18; a 3s title -> ~7 words). A beat that overruns its scene gets cut off.
- The CLOSING title's beat is the call to action, so the CTA lands ON the closing card.
- Do NOT emit a single combined "script" — use the per-scene "beats" array only.

VALIDITY:
- Output must be a single JSON object that parses with a standard JSON parser.
- Use double quotes, no trailing commas, no comments in the actual output.
- Echo company_url, goal, and target_duration_s from the brief without altering them.
```

## USER PROMPT (template)

```
Build the scene plan for this brief. Output JSON only.

company_url: {company_url}
goal: {goal}
target_duration_s: {target_duration_s}
```

---

## Harness notes (how the producer-brain calls this)

- **API:** `POST https://integrate.api.nvidia.com/v1/chat/completions`, `Authorization:
  Bearer $NVIDIA_API_KEY`. Production planning uses Nemotron 3 Ultra; the cheap tier
  `nvidia/nemotron-3-super-120b-a12b` is sufficient for this structured task and is what the
  validation run below used.
- **Params:** `temperature: 0.2`, `max_tokens` large enough for the plan + the model's
  hidden reasoning tokens (**8000**; the per-scene beats array is longer than the old single
  script, and Nemotron's reasoning counts against the budget, so do not lower this).
- **JSON extraction / repair (recommended, do not skip):** small models occasionally wrap the
  object in prose or a ```json fence despite instructions. The harness should:
  1. Strip a leading/trailing markdown fence if present, then take the substring from the
     first `{` to the last `}`.
  2. `json.loads` it.
  3. On failure, ONE repair retry: resend the model's raw text with
     "Your previous output did not parse as JSON. Return ONLY the corrected JSON object,
     nothing else." Then parse again. If it still fails, surface the error — do not loop.
- **Post-parse schema assertion** (cheap, deterministic — run it even when parse succeeds):
  top-level keys == {job, scenes, voiceover}; scenes[0].type == "title";
  scenes[-1].type == "title"; NO walkthrough scene; **STANDARD: ZERO cinematic (Remotion-only:
  title + motion_graphic), PREMIUM: >= 2 cinematic (2-4)** with every cinematic.model in
  {seedance_2_0, gpt_image_2}; sum(duration_s) == target_duration_s; voiceover.voice == "Adam";
  voiceover.beats is a non-empty array of {scene_id, text} with one beat per non-title scene and
  every scene_id matching a scenes[].id. These are the same checks the validation script applies.
