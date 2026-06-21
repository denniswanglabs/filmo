# Hermes Video Agent — Scene-Plan Schema + Producer Engine

`producer.py` is the deterministic pricing + budget layer (§B of
`STRIPE-PRODUCER-DESIGN.md`). It owns the canonical scene-plan schema documented
here. Python 3, standard library only, non-interactive, JSON to stdout.

It NEVER triggers a real generation. The only external call is the FREE
Higgsfield price preview `higgsfield generate cost <model> --prompt "..."`,
which estimates credits without creating a job and without spending.

---

## Scene-plan JSON schema

```json
{
  "job": {
    "company_url": "string",
    "goal": "string",
    "target_duration_s": 30,
    "target_margin": 0.6,
    "currency": "usd"
  },
  "scenes": [
    {
      "id": "string (unique)",
      "type": "title | cinematic | walkthrough | motion_graphic",
      "brief": "string (scene prompt / objective)",
      "model": "string | null",
      "duration_s": 6,
      "input_image": "string path/url | null"
    }
  ],
  "voiceover": {
    "voice": "string",
    "beats": [
      { "scene_id": "string (matches a scenes[].id)", "text": "string (line spoken on that scene)" }
    ]
  }
}
```

### `job`
| Field | Type | Meaning |
|---|---|---|
| `company_url` | string | target site for the video / walkthrough |
| `goal` | string | one-line job objective |
| `target_duration_s` | int | desired finished length, seconds |
| `target_margin` | float 0–1 | desired profit margin; price = COGS / (1 − margin) |
| `currency` | "usd" | reporting currency |

### `scenes[]`
| Field | Type | Meaning |
|---|---|---|
| `id` | string | unique scene id (used by `gate --scene`) |
| `type` | enum | `title` \| `cinematic` \| `walkthrough` \| `motion_graphic` |
| `brief` | string | scene prompt (also the prompt sent to the Higgsfield cost preview) |
| `model` | string \| null | model override; `null` falls back to the type default |
| `duration_s` | int | scene length, seconds |
| `input_image` | string \| null | start/reference image for I2V cinematic scenes |

### `voiceover`
| Field | Type | Meaning |
|---|---|---|
| `voice` | string | ElevenLabs voice id/name |
| `beats` | array | **scene-aligned narration**: one `{scene_id, text}` per scene. Each beat is synthesized as its own audio segment and placed at that scene's start offset, so the line lands on the picture it describes. A beat whose scene is cut at the budget gate is dropped (its narration never plays). |
| `beats[].scene_id` | string | must equal a `scenes[].id` |
| `beats[].text` | string | the line spoken while that scene is on screen; budget ≈ `scene.duration_s × 2.5` words |

**Backward compatibility / fallback.** A legacy plan that carries a single
`voiceover.script` string (no `beats`) is still accepted: `resolve_vo_beats()`
splits the script into sentences and maps them onto the scene order (one beat per
scene, the tail folding into the last scene), so old runs/tests keep working. The
orchestrator also mirrors the resolved beats back into a derived `voiceover.script`
on the written plan, so `producer.py` cost estimation (from `len(script)`) and any
legacy reader are unaffected. Cost is estimated from the full narration character
count regardless of which shape the plan used.

---

## Scene type → tool → cost

| Scene `type` | Tool | Paid? | Cost source |
|---|---|---|---|
| `title` | motion-graphics (Remotion) | free | $0 marginal (local) |
| `motion_graphic` | motion-graphics (Remotion) | free | $0 marginal (local) |
| `walkthrough` | walk-agent (walk-ultra, NVIDIA Nemotron) | free | $0 marginal (free NVIDIA tier) |
| `cinematic` | higgsfield-scene | **paid** | real preview via `higgsfield generate cost` |
| voiceover track | ElevenLabs TTS | **paid** | estimated from `len(script)` |

Only `cinematic` scenes and the voiceover pass through the budget gate; free
types are tagged `$0` and never touch the budget machinery.

---

## Cost model constants (top of `producer.py`)

| Constant | Value | Why |
|---|---|---|
| `ELEVENLABS_PER_1K_CHARS_CENTS` | `30` | ElevenLabs has no free cost-preview call, so VO is estimated at ~$0.30 per 1000 characters of script. |
| `HIGGSFIELD_CENTS_PER_CREDIT` | `1.0` | The Higgsfield CLI prices in *credits* and exposes no USD rate. Higgsfield credit packs price at ≈ $0.01/credit, so 1 credit = 1 cent is the defensible default. Override if the plan rate differs. |
| `DEFAULT_CINEMATIC_VIDEO_MODEL` | `seedance_2_0` | default cinematic video model |
| `DEFAULT_CINEMATIC_STILL_MODEL` | `gpt_image_2` | cheaper still used by the downgrade path |

**Higgsfield preview parsing:** `higgsfield generate cost <model> --prompt "<brief>" --json`
returns `{"credits": int, "credits_exact": float}`. The engine prefers
`credits_exact`, multiplies by `HIGGSFIELD_CENTS_PER_CREDIT`, and rounds to cents.
On any CLI error (not found, timeout, non-zero exit, unparseable JSON) it returns
0 cents plus an explanatory `note` and does **not** retry — keeping the engine
deterministic, non-blocking, and never auto-retrying a Higgsfield call.

---

## Subcommands

### `estimate`
```
python3 producer.py estimate --plan <plan.json>
```
Output fields:
- `scenes[]` — per scene: `id`, `type`, `tool`, `model`, `est_cost_cents`,
  `note`, `per_scene_budget_cents`.
- `voiceover` — same shape, id `__voiceover__`.
- `total_cogs_cents` — Σ scene costs + VO estimate.
- `suggested_price_cents` — `round(total_cogs / (1 − target_margin))`
  (`null` if `target_margin ≥ 1.0`).
- `production_budget_cents` — the variable-spend ceiling (== COGS).

`per_scene_budget_cents` distributes the total COGS across all cost lines
(scenes + VO) **proportional to each line's est cost**, using a largest-remainder
split so the allocations sum exactly to COGS (no integer-cent drift). Free scenes
get 0.

### `gate`
```
python3 producer.py gate --plan <plan.json> --scene <id> \
    --proposed_cost_cents N --spent_cents M
```
Computes `remaining = production_budget − spent_cents` and decides:

| Condition | `decision` | `suggested_cheaper_model` |
|---|---|---|
| `proposed ≤ remaining` | `approve` | `null` |
| over budget, cheaper model exists for the scene type | `downgrade` | the cheaper model (e.g. `gpt_image_2` for a `cinematic` scene) |
| over budget, no cheaper option | `decline` | `null` |

Output fields: `scene`, `scene_type`, `decision`, `reason`,
`remaining_budget_cents`, `suggested_cheaper_model`, plus echoed
`production_budget_cents`, `spent_cents`, `proposed_cost_cents`.

The cheaper-model map (`CHEAPER_MODEL`) currently downgrades a `cinematic`
video scene to a `gpt_image_2` still. Scene types with no entry (e.g.
`walkthrough`) can only `approve` or `decline`.

---

## Worked example (`sample-plan.json`)

A 30s Stripe-Docs brand explainer: 1 title + 3 cinematic (`seedance_2_0`) +
1 walkthrough + a voiceover, `target_margin` 0.6.

`estimate` → each cinematic ≈ 22c (22.5 credits), VO 9c (293 chars),
`total_cogs_cents` = 75, `suggested_price_cents` = `round(75 / 0.4)` = 188.

`gate` examples (budget = COGS = 75c):
- approve: `--scene s2_hero --proposed_cost_cents 22 --spent_cents 30` → remaining 45 ≥ 22.
- downgrade: `--scene s4_network --proposed_cost_cents 22 --spent_cents 70` → remaining 5 < 22, cinematic has a cheaper still → `gpt_image_2`.
- decline: `--scene s5_walkthrough --proposed_cost_cents 22 --spent_cents 70` → remaining 5 < 22, no cheaper model for a walkthrough.

---

## Budget rules / safety

- **No real generation, ever.** Only the free `generate cost` preview is called.
- **No auto-retry** on the Higgsfield CLI — a failed preview degrades to 0c + note.
- **Standard library only**, non-interactive, JSON to stdout.
- Free scene types are excluded from the budget gate entirely.
