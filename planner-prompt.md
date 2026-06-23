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
- **Structural invariants are spelled out as numbered rules** (open `title`, the
  quality-specific content scenes, close `title`, durations sum to target). The model is told
  to self-check the sum before emitting.
- **Quality gates the allowed scene types** (the upfront customer choice, threaded into the
  planner at PLAN time):
  - **STANDARD = real-capture.** Allowed scene types are `title`, `screenshot`, and
    `walkthrough` (all model null). The plan is: opening `title` -> 1-2 `screenshot` scenes
    (real captured views of the company's website) -> ONE `walkthrough` scene (a guided,
    multi-step demonstration of the emphasized feature) -> closing `title` CTA. NO `cinematic`,
    NO `motion_graphic`, NO `seedance_2_0` / `gpt_image_2` model — there is no Higgsfield stage
    in a standard build. The captured screenshots and the produced walkthrough clip are wired
    into the matching scenes at render time.
  - **PREMIUM REQUIRES cinematic.** A premium plan MUST include AT LEAST 2 `cinematic` scenes:
    a cinematic **establishing** shot (`seedance_2_0`) and a cinematic **hero** shot
    (`gpt_image_2` or `seedance_2_0`), plus the opening/closing `title` cards and optional
    `motion_graphic` feature beats. PREMIUM does NOT use `screenshot` or `walkthrough`. Zero
    cinematic makes a premium plan INVALID — it would look identical to a standard build and
    skip the Higgsfield footage that defines the tier.
  The harness appends a per-quality guidance block to the SYSTEM PROMPT (after the style
  block), and a deterministic backstop enforces both ends: for STANDARD it forces the
  `title` -> 1-2 `screenshot` -> `walkthrough` -> `title` shape (re-typing any stray
  cinematic/motion_graphic content scene and rewriting the walkthrough's brief to the
  emphasis-specific multi-step goal), and for PREMIUM it upgrades feature beats to `cinematic`
  (assigning `seedance_2_0` then `gpt_image_2`, preserving ids/durations) if the small model
  returns fewer than 2 cinematic scenes.
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
      "type": string,             // STANDARD: "title" | "screenshot" | "walkthrough"; PREMIUM: "title" | "cinematic" | "motion_graphic"
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
- If the brief is STANDARD quality (real-capture build): use ONLY the scene types "title",
  "screenshot", and "walkthrough" (all model null). Do NOT plan any "cinematic" or
  "motion_graphic" scene and do NOT use the models "seedance_2_0" or "gpt_image_2". A STANDARD
  plan is: an opening "title", ONE or TWO "screenshot" scenes (real captured views of the
  company's website — homepage, then an optional key inner page), ONE "walkthrough" scene (a
  guided, multi-step screen demonstration of the emphasized feature), and a closing "title" CTA.
- If the brief is PREMIUM quality: the plan MUST include AT LEAST 2 "cinematic" scenes — this
  is a REQUIREMENT, not an option. You MUST include (1) a cinematic ESTABLISHING shot with
  model "seedance_2_0" and (2) a cinematic HERO shot with model "gpt_image_2" or "seedance_2_0",
  plus the opening/closing title cards and optional motion_graphic feature beats. A premium plan
  with zero cinematic scenes is INVALID. PREMIUM does NOT use "screenshot" or "walkthrough".
- Default to STANDARD (real-capture) when quality is unspecified.
A QUALITY guidance block is appended after this prompt; when present it is authoritative.

STRUCTURE RULES (the scenes array MUST satisfy ALL of these):
1. The FIRST scene has type "title" (the opening brand/title card).
2. (PREMIUM) Next come 2 to 4 scenes with type "cinematic" that convey the company's positioning
   (what it is, who it serves, why it matters) — inferred from the company_url and goal. PREMIUM
   REQUIRES AT LEAST 2 cinematic: a cinematic establishing shot (model "seedance_2_0") AND a
   cinematic hero shot (model "gpt_image_2" or "seedance_2_0"). Fewer than 2 cinematic makes a
   PREMIUM plan INVALID.
   (STANDARD) Next come 1 to 2 "screenshot" scenes (real captured website views) followed by
   exactly ONE "walkthrough" scene (a guided, multi-step demonstration of the emphasized
   feature). STANDARD has NO cinematic and NO motion_graphic scenes.
3. STANDARD plans include a "walkthrough" scene (the guided product demo of the emphasized
   feature) and "screenshot" scenes (the real site). PREMIUM plans NEVER include "walkthrough"
   or "screenshot" — premium conveys the product through cinematic shots only.
4. The LAST scene has type "title" (the closing card / CTA).
5. PREMIUM MAY include "motion_graphic" scenes (a divider or stat card, model null) as optional
   feature beats. STANDARD does NOT use "motion_graphic".
6. duration_s across ALL scenes MUST sum to EXACTLY target_duration_s. Verify the sum
   before you emit. If it does not match, adjust scene durations until it does.

The allowed scene types are: an opening "title" card; for STANDARD, "screenshot" (captured site
views) and ONE "walkthrough" (guided demo); for PREMIUM, "cinematic" establishing / feature
shots and optional "motion_graphic" feature beats; and a closing "title" card.

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
- WORD BUDGET PER BEAT (a FLOOR and a ceiling — you MUST hit the floor): write a COMPLETE
  sentence that FILLS the scene's duration. Aim for 2.0 to 2.6 words per second of that
  scene's duration_s and never exceed 3 words/second. So a 6s scene -> ~13-15 words (min 12),
  a 4s scene -> ~9-10 words, a 3s title -> ~6-8 words. Do NOT write 2-4 word fragments like
  "Here is how it works." or "Built for you." — a half-empty beat leaves dead air and is
  WRONG. If your line is shorter than the floor for its scene, expand it with a concrete
  detail until it fills the time. A beat that exceeds 3 words/second gets cut off, so stay
  under that ceiling too.
- BE SPECIFIC, NOT GENERIC: every beat must say something CONCRETE about THIS company — a
  REAL, NAMED feature ("recurring billing", "fraud detection", "issue tracking", "hotel
  reviews", "restaurant bookings"), the real audience, or a tangible benefit with a
  real-looking specific number ("135+ currencies", "millions of reviews", "ship in minutes").
  Prefer concrete nouns over empty buzzwords like "powerful", "seamless", "revolutionize",
  "innovative", or "next-generation".
- BANNED FILLER — NEVER write any of these (or close paraphrases); they describe the
  WEBSITE/ANIMATION instead of the PRODUCT and are an automatic FAIL:
    * "This is <Brand> — straight from the real site."
    * "Here is the product, exactly as you would see it."
    * "See the product in action, step by step." / "Here is how it works."
    * "See how to use the …" (and any "use the <noun>" stitch).
    * Anything narrating the capture, screenshot, camera, demo, or "the real site" —
      describe what the PRODUCT does, never what the video shows.
- IMPERATIVE COUPLETS for kinetic type: short title/feature beats are tight imperative
  couplets built from the REAL product verb-objects, like the reference films ("Clock in. /
  Cash out.", "One screen. / Whole crew.", "Book the stay. / Skip the guesswork."). Lead with
  a verb, name the real thing, land the payoff.
- THIN OR MISSING FACTS: if the COMPANY FACTS block is empty/sparse but the brand is
  RECOGNIZABLE from its URL (tripadvisor.com → traveler reviews, hotels, restaurants, things
  to do, booking; stripe.com → online payments, recurring billing, fraud protection), use your
  OWN knowledge of THAT specific real company to write real, verifiable value props naming its
  REAL features. Do NOT go hollow because scraping was thin. NEVER invent a DIFFERENT business.
- The CLOSING title's beat is the call to action and SHOULD name the real next step (e.g.
  "Start accepting payments at stripe.com.", "Find your next trip on Tripadvisor."), not a
  generic "get started", so the CTA lands ON the closing card.
- SCREENSHOT SCENES — ONE FEATURE EACH, COHERENT WITH THE SHOT (the text-left / screenshot-
  right layout shows the scene's headline NEXT TO the captured page, and a highlight box marks
  the named element, so the words and the picture MUST be about the same thing):
    * Each "screenshot" scene's "brief" names ONE concrete, on-page product capability the
      captured view will show (e.g. for stripe.com: "Accepting card and wallet payments through
      one integration"; "The dashboard's real-time revenue and payouts view"; "Going live with a
      few lines of code"). The brief is the SUBJECT the headline + highlight both point at.
    * That scene's VO "beat" describes THAT SAME feature — its first sentence is the value-prop
      the headline is built from; lead with the feature noun ("Accept payments…", "Every
      transaction…", "Go live…"). Do NOT narrate the page, the screenshot, or the brand tagline.
    * When there are TWO screenshot scenes, they MUST cover DIFFERENT features (e.g. payments
      then dashboard) — never repeat the same value-prop or the tagline across both. Distinct
      subjects per scene is required (the R1 failure: "Build internet businesses" repeated on
      every scene).
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

### COMPANY FACTS block (appended to the USER prompt when real facts are available)

The harness resolves the company's REAL brand facts **before** planning, from the
SAME brand resolver the visual side fills its cards from (a curated
`branding/<host>-brand-theme.json` fixture when present, else `brand_extract`). When
any fact is found, the harness appends this block to the USER prompt **after** the
brief. This grounds the brain so the voiceover and every scene brief describe the
ACTUAL product instead of an invented one — the fix for VO-vs-visual incoherence
(e.g. Orinovate, a 3D-printing / CNC on-demand manufacturer, previously got a
hallucinated "AI insight platform / data streams" voiceover while the visual cards
correctly showed *3D Printing / CNC Machining / Sheet Metal / Laser Sintering*).

```
COMPANY FACTS (the REAL product — these are verified, not inferred):
- Company / wordmark: {wordmark}
- Tagline / positioning: {tagline}
- Real product features / capabilities:
    * {feature 1}
    * {feature 2}
    * ...
Base the voiceover and EVERY scene's brief on THESE real facts. Each feature beat
must highlight ONE of the real features listed above. The opening title is the
company wordmark and the closing CTA names a concrete next step at the company.
Do NOT invent a DIFFERENT product, market, audience, or business than the one at
this URL — that guard is absolute. NEVER describe the video, screenshot, capture,
or "the real site"; describe what the PRODUCT does for the user.
```

**Thin / bot-blocked scrape (world-knowledge fallback).** When scraping returns few or
no facts (e.g. tripadvisor.com.tw blocks bots → empty tagline + features), the block does
NOT go silent. Instead it names the brand from the URL host and instructs the planner to
use its OWN knowledge of that RECOGNIZABLE real company to write real value props (for a
travel-reviews marketplace: traveler reviews, hotels, restaurants, things to do, price
comparison, bookings) — while keeping the absolute "never invent a DIFFERENT business"
guard. A truncated meta-description tagline (mid-word cut from brand_extract's 80-char cap)
is dropped rather than fed to the brain. This kills the hollow-template failure on
bot-blocked brands (TripAdvisor-class) that previously scored ~1 on grounding.

The block lives in `validate_planner.company_facts_block(facts, company_url)` and is threaded
`build_runner._brand_facts → plan_job → _plan_with_nemotron`. It is purely additive:
the frozen JSON schema, structure rules, `voice: "Adam"`, `temperature: 0.2`,
`max_tokens: 8000`, the word-budget VO rule, and the template fallback are all
unchanged.

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
