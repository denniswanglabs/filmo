# PIPELINE-PIVOT-ARCHITECTURE — VO-driven designed motion-graphics

**Date:** 2026-06-21
**Scope:** READ-ONLY architecture proposal (design input). NO code changed.
**Author:** architecture-audit subagent
**Supersedes the direction in** `VO-MISMATCH-ANALYSIS.md` (2026-06-20) — that doc's
fix (a/b/c, beat-per-scene schema) is ALREADY SHIPPED yet the mismatch persists,
because the real root cause is one layer deeper (durations are still authored
before the VO exists). This doc names that inversion and designs the pivot.

---

## 0. The pivot in one sentence

Today: **the plan locks scene durations first, then the VO is padded/squeezed into
those fixed slots.** Pivot: **synthesize the VO first, derive word-level
timestamps, then build the timeline so every scene/reveal is anchored to the
words** — and render *designed* motion-graphics in Dennis's proven styles instead
of generic AI b-roll, with Higgsfield demoted to textured backdrops and the
walk-agent optional.

---

## 1. CURRENT-STATE MAP (with file:line citations)

### 1.1 Where scene durations are born — BEFORE any audio exists

Durations are integers written into the plan at planning time and never revised
against the synthesized voice:

- **`plan_job.py:46-69`** — `plan_job()` calls Nemotron (`_plan_with_nemotron`,
  `plan_job.py:143-162`) or the deterministic fallback (`_template_plan`,
  `plan_job.py:165-258`). Every scene gets a hardcoded `"duration_s": <int>`
  (e.g. `plan_job.py:225-239` standard template: 3, 6, walk, 6, 5).
- **`plan_job.py:72-140`** — `_restyle_durations()` then REWRITES those integers
  per style (snappy→short holds, cinematic→long holds) to make the sum hit
  `target_duration_s` EXACTLY. Still no audio in the loop — it is pure arithmetic
  on a fixed total. **This is the lock.**
- **`planner-prompt.md:96-98`** (STRUCTURE RULE 6) — the model is *instructed*:
  "duration_s across ALL scenes MUST sum to EXACTLY target_duration_s. Verify the
  sum before you emit." The contract itself forces a fixed-slot timeline.
- **`plan_schema.py:137-138`** rejects any non-positive-int duration;
  `plan_schema.py:179-183` (strict) asserts the sum equals the target.

**Consequence:** by the time the VO is synthesized, the picture timeline is already
frozen. The VO can only be *fitted* to it.

### 1.2 Where the VO is synthesized and "aligned"

- **`orchestrator.py:518-535`** — the VOICEOVER phase runs AFTER the produce loop.
  It computes each PRODUCED clip's start offset by **summing the already-rendered
  clip durations** (`cursor += adapters.ffprobe_duration(path)`), i.e. the offsets
  come from the locked picture, not from the voice.
- **`orchestrator.py:537-549`** — beats are mapped onto those produced offsets;
  beats for cut scenes are dropped. Each beat's `start_s` is the SCENE's start, not
  a word-anchored cue.
- **`adapters.py:909-973`** — `synthesize_voiceover_aligned()` synthesizes one mp3
  **per beat**, then lays each beat down at its scene's `start_s` via
  `adelay=<ms>` and `amix` (`adapters.py:951-968`). It pads the whole track to
  `total_s` with `apad` (`adapters.py:960-962`). **The beat is anchored to the
  scene start and otherwise free-floats** — there is no guarantee the beat's
  *duration* matches the scene's, so a long beat overruns into the next clip and a
  short beat leaves dead air. Nothing stretches the picture to the beat or the beat
  to the picture; they are merely both pinned at one shared start instant.
- **`adapters.py:976-982`** (`_vo_edge`) / **`adapters.py:985-1001`**
  (`_vo_elevenlabs`) — neither requests or returns word-level timing. The only
  timing artifact is `dur_s = ffprobe_duration(seg_path)` (`adapters.py:942`),
  measured AFTER synthesis and never fed back into the picture.

### 1.3 Where the mismatch ORIGINATES — the precise file:line

**Root cause: the dependency is inverted.** The picture timeline is locked at
`plan_job.py:72-140` (`_restyle_durations`, enforced by the
`planner-prompt.md:96-98` sum-to-target rule and `plan_schema.py:179-183`), and
the VO is forced to fit it at `orchestrator.py:531-534` (offsets summed from
produced clip durations) + `adapters.py:951-962` (`adelay`/`apad` into those fixed
slots). The single line that most embodies the lock is **`plan_job.py:117`**
(`base = max(2, min(target_hold, content_budget // n))`) — durations are computed
from a fixed budget divided across scenes, with the voice nowhere in the
expression.

The 2026-06-20 analysis correctly observed the symptom (flat track, drift, silent
tail) but its prescribed fix only changed *which start offset each beat gets*. It
did not remove the lock: durations are STILL authored first. That is why, even with
beats shipped, a 14s walkthrough clip (vs 10s planned, see
`VO-MISMATCH-ANALYSIS.md:35-37`) still desyncs — the clip length is independent of
the spoken line length.

### 1.4 The render layer (what produces the picture)

- **`remotion_codegen.py`** — the agent "writes" a Remotion TSX component per
  title/motion_graphic scene. `generate()` (`remotion_codegen.py:407-430`) fills
  one of three archetype templates (`_CENTERED`/`_EDITORIAL`/`_DIVIDER`,
  `remotion_codegen.py:196-320`) via `string.Template`, baking
  `DUR_FRAMES = duration_s * fps` (`remotion_codegen.py:411-412, 152-153`) into the
  component's `activeMeta`. Copy is derived from the brief deterministically
  (`_copy_from_brief`, `remotion_codegen.py:562-586`).
- **`adapters.py:855-893`** — `_studio_render()` writes that TSX to
  `studio/src/generated/active.tsx` (`adapters.py:863-864`) and runs
  `remotion render src/index.ts Scene <out>` (`adapters.py:867-869`). The studio
  registers exactly ONE composition `"Scene"` reading `activeMeta` for its frame
  count (`studio/src/Root.tsx:8-19`). **One render = one scene = one clip.** There
  is no multi-scene timeline composition.
- **`adapters.py:1023-1096`** — `stitch()` ffmpeg-concats the per-scene clips,
  normalizes them to 1920×1080, then muxes the pre-mixed VO at t=0 trimmed to video
  length (`adapters.py:1062-1072`).
- **`finish_cut.py`** — the polish pass: per-clip grade
  (`finish_cut.py:27, 86-93`), crossfade dissolves (`finish_cut.py:96-104`),
  walkthrough push-in (`finish_cut.py:89-91`), music duck under VO
  (`finish_cut.py:105-129`). It RE-PLACES per-beat VO at each scene's
  crossfade-timeline offset (`finish_cut.py:52-119`) — same scene-start anchoring,
  one layer later. **`finish_cut.py:47`** recomputes `total` from clip durations:
  the picture is authoritative here too.

### 1.5 What is reusable vs broken for the pivot

| Component | Verdict | Why |
|---|---|---|
| `remotion_codegen.py` archetype templates + brand palettes + motion vocab (`_HEADER` drift/AnimatedBg, L2/L3/L5 eases) | **REUSE (high value)** | Real designed motion already exists; just needs frame counts driven by word timings and a multi-scene timeline, not one-clip-per-render. |
| `palette_for()` + brand kit (`remotion_codegen.py:45-99`) | **REUSE as-is** | The brand-extraction seed for template-fill. |
| `studio/` single-`Scene` composition (`Root.tsx`) | **REBUILD** | Needs a `Timeline` composition that sequences all scenes with `<Sequence>` at word-anchored frames, consuming an audio track + a cue manifest. |
| `synthesize_voiceover_aligned` adelay/amix | **DEMOTE** | Keep edge/ElevenLabs synth; drop the "fit beat into fixed slot" placement — the timeline now owns placement. |
| `_restyle_durations` (`plan_job.py:72-140`) | **REPLACE** | The lock. Replace fixed-budget arithmetic with durations derived from measured VO segment lengths + reveal pacing. |
| `stitch` / `finish_cut` ffmpeg | **MOSTLY REUSE** | If the whole video becomes ONE Remotion render with audio baked in, stitch shrinks to a passthrough; finish (grade/music duck) still applies as a final ffmpeg pass. Keep music-duck logic. |
| Higgsfield `cinematic_prompt` formula (`adapters.py:447-510`) | **REUSE, DEMOTE role** | Excellent for textured backdrop plates; stop using it as the primary picture. |
| Walk-agent (`adapters.py:749-775`) | **KEEP OPTIONAL** | Slow/flaky; opt-in, never on the critical path. |
| Stripe money path (gate/authorize/active_budget bridge) | **DO NOT TOUCH (sacred)** | See §4. |

---

## 2. VO-DRIVEN TIMELINE DESIGN

### 2.1 The inverted flow

```
URL+goal
  └─> PLAN (Nemotron): scene LIST (type/order/brief/model) + per-scene VO line
                       + a target_duration as a SOFT hint (NOT a hard sum)
  └─> SYNTH VO first:  edge-tts (free) | ElevenLabs (premium) -> voiceover.mp3
  └─> ALIGN:           word-level timestamps
                         - ElevenLabs path: use the with-timestamps endpoint
                           (returns per-character/word start+end) — premium tier
                         - edge-tts path: whisper-cli (local, FREE, present at
                           /opt/homebrew/bin/whisper-cli + ggml-base.en.bin) ->
                           word timestamps from the rendered mp3
  └─> BUILD TIMELINE:  each scene's IN/OUT = the span of the words in its beat;
                       reveal cue points = word start times within the scene
  └─> RENDER:          ONE Remotion <Timeline> composition consumes the audio +
                       the cue manifest; <Sequence> per scene at word-anchored
                       frames; reveals fire on cue frames
  └─> FINISH:          grade + music duck (ffmpeg) — money path untouched
```

The picture now FOLLOWS the voice. A scene is exactly as long as the words spoken
over it (plus a small designed lead-in/tail), so nothing drifts and there is no
silent tail.

### 2.2 The DATA CONTRACT (what the plan/ledger must carry)

Three new structures. All are additive — the existing `job`/`scenes`/`voiceover`
keys stay; `duration_s` becomes a SOFT hint (kept for pricing back-compat, no
longer authoritative for the timeline).

**(1) Per-word timings** — produced by the align step, stored at
`runs/<id>/vo_alignment.json`:
```json
{
  "provider": "elevenlabs|edge",
  "audio_path": "voiceover.mp3",
  "duration_s": 28.4,
  "words": [
    {"word": "Stripe", "start_s": 0.31, "end_s": 0.74, "beat_scene_id": "title-open"},
    {"word": "powers", "start_s": 0.74, "end_s": 1.10, "beat_scene_id": "cine-establish"},
    ...
  ]
}
```
Words carry `beat_scene_id` by mapping the alignment back onto the per-beat segment
boundaries (we already synth one mp3 per beat at `adapters.py:933-943`, so each
word's owning beat is known by which segment it came from — no fuzzy matching).

**(2) Per-scene in/out anchored to the VO** — the timeline, at
`runs/<id>/timeline.json`:
```json
{
  "fps": 30,
  "total_frames": 852,
  "audio_path": "voiceover.mp3",
  "scenes": [
    {"id": "title-open",     "type": "title",     "in_frame": 0,   "out_frame": 96,
     "vo_start_s": 0.31, "vo_end_s": 2.9, "lead_in_f": 9, "tail_f": 12},
    {"id": "cine-establish", "type": "cinematic", "in_frame": 96,  "out_frame": 330, ...},
    ...
  ]
}
```
Rule: `in_frame` = round((beat.vo_start_s − lead_in) · fps); `out_frame` = next
scene's `in_frame` (contiguous, no gaps). A scene with no beat (rare) gets a fixed
minimum hold. `total_frames` = align.duration_s · fps + outro tail. Cut scenes
(declined at the money gate) are simply absent — the following scene's `in_frame`
slides earlier, closing the gap deterministically.

**(3) Reveal cue points** — per scene, the frames at which designed reveals fire,
anchored to specific words:
```json
{"id": "walkthrough", "cues": [
  {"label": "step-open-dashboard", "word": "Dashboard", "at_frame": 318},
  {"label": "step-api-keys",       "word": "keys",      "at_frame": 372}
]}
```
The Remotion component reads its scene's `cues` and triggers each reveal
(spring/blur-in) at `at_frame`. This is what makes "every reveal choreographed to
word-level timestamps" literally true — the API-keys highlight pops on the word
"keys", not on a guessed offset.

### 2.3 Who writes what

- Planner (Nemotron) writes scenes + per-scene VO beats (already does, per
  `planner-prompt.md:109-123`) + optional `cues` hints naming which word in a beat
  should trigger a reveal. `target_duration_s` becomes advisory; drop the
  hard-sum rule from `planner-prompt.md:96-98`.
- A NEW `align_vo.py` module: synth (reusing `adapters.synthesize_voiceover`) →
  align (ElevenLabs-timestamps OR whisper-cli) → write `vo_alignment.json`.
- A NEW `build_timeline.py`: alignment + scene list + cues → `timeline.json`.
- Remotion `<Timeline>` composition consumes `timeline.json` + `voiceover.mp3`.

### 2.4 Why ElevenLabs as premium, edge-tts as free

- **ElevenLabs** has a text-to-speech-with-timestamps response that returns word/
  character start+end directly — highest-fidelity alignment, premium VO quality.
  Wire it in `_vo_elevenlabs` (`adapters.py:985-1001`) by switching the endpoint to
  the with-timestamps variant and returning the alignment alongside the audio.
- **edge-tts** (free, `adapters.py:976-982`) returns audio only → align with
  local `whisper-cli` (confirmed installed). Slightly noisier word boundaries but
  $0 and good enough for the free tier and tests.

---

## 3. TEMPLATE-FILL DESIGN (curated style → agent-fillable)

### 3.1 The model

A STYLE TEMPLATE is a curated Remotion timeline (one of Dennis's proven genres:
Zelios aurora-glass, Orinovate kinetic-light, Apple-style, Mintlify). Each template
is a set of scene-component archetypes + a theme contract. The agent:

1. **Extracts brand** — palette/logo/copy/features. Seed already exists:
   `palette_for()` (`remotion_codegen.py:93-99`) + the brand kit
   (`remotion_codegen.py:45-72`). Extend with a Chrome-MCP/`Brand Slurper` pull
   (per MEMORY: `project_luceo_lookbook`) to fill `brand.json`.
2. **Selects a style** — maps goal/brand → genre (reuse the `HERMES_STYLE` lever,
   `plan_job.py:17-43` + `remotion_codegen.py:105-115`, but expand it from a
   speed factor to a full genre selector).
3. **Fills slots** — per scene, the agent provides copy (from the beat/brief) +
   cues; the template owns the motion. This is the inversion of today's
   `remotion_codegen.generate()` where the agent "writes" raw TSX: instead the
   agent fills a typed PROPS object and the curated component renders
   deterministically.
4. **Renders deterministically** — one `<Timeline>` render, frame counts from
   `timeline.json`, all motion frame-derived (no `Math.random`/`Date`, exactly the
   discipline already in `_HEADER`, `remotion_codegen.py:164-166`).

### 3.2 Reusable vs rebuild (render layer)

**Reuse:**
- The three archetype templates' MOTION (`remotion_codegen.py:196-320`) — drift,
  AnimatedBg, blur-in/stagger/overshoot eases (L2/L3/L5). This is real designed
  motion; port the bodies into curated scene components.
- The deterministic-by-construction headless discipline
  (`remotion_codegen.py:133-194`): font stacks, frame-derived motion.
- Brand palette/copy derivation (`palette_for`, `_copy_from_brief`,
  `_section_label`, `_cta_title`).

**Rebuild:**
- `studio/src/Root.tsx` — replace the single `"Scene"` composition with a
  `"Timeline"` composition that takes `timeline.json` + `voiceover.mp3` as props
  (Remotion `<Audio>` + `<Sequence>` per scene). Frame count from
  `timeline.total_frames`.
- The "agent writes raw TSX into active.tsx" flow (`adapters.py:855-884`) — replace
  with "agent fills typed props; curated components render." Determinism improves
  (no codegen surface to break) and quality improves (curated > generated).
- `_studio_render` (`adapters.py:855-874`) becomes a single timeline render instead
  of N per-scene renders; `stitch`'s concat collapses to a passthrough (audio is
  baked into the Remotion render via `<Audio>`), though keeping ffmpeg `finish_cut`
  for grade + music duck is fine.

### 3.3 Higgsfield demotion

Cinematic plates become BACKDROPS behind the designed type, not the foreground.
Keep `cinematic_prompt` (`adapters.py:447-510`) — it already targets abstract,
text-free, brand-graded plates (`_NO_TEXT`, `_color_dominance`), which is exactly
what a textured backdrop wants. A cinematic scene's Remotion component renders the
plate as a full-bleed background layer (`<Img>`/`<Video>` from the downloaded
asset) with the kinetic type composited on top. This also makes the money path
*more* meaningful: each backdrop is still a metered Higgsfield purchase the budget
gate governs, but a backdrop failing now degrades to a brand gradient (already the
`AnimatedBg`) instead of killing the scene.

---

## 4. SACRED — DO NOT TOUCH

The Stripe money path stays byte-identical:
- The strictly-serial budget gate + `money.authorize()` sequence in the produce
  loop (`orchestrator.py:387-509`).
- The `active_budget.json` bridge writes
  (`orchestrator.py:107-122, 246, 403, 443, 480, 496, 516`).
- The pre-production payment gate (`build_runner.py:170-242`).
- `producer.py` pricing/gating, `stripe_money.py`, `stripe_webhook.py`.

The pivot touches PLANNING, VO/ALIGN, RENDER, and FINISH — never the money loop.
The VO is already gated as a spend (`orchestrator.py:551-601`); keep that gate, it
just now runs BEFORE the picture is finalized (synth-first), so the VOICEOVER phase
moves earlier in the loop but its gate logic is unchanged.

---

## 5. PHASED 9-DAY PLAN (smallest shippable pivot)

Ordered so each phase ships an end-to-end improvement and de-risks the next.
Demo deadline: EOD Tue Jun 30. ~9 days.

### Phase 0 (Day 1) — Alignment spike, $0, no pipeline change
- Build `align_vo.py`: take an existing `runs/<id>/voiceover.mp3`, run `whisper-cli`
  → word timestamps → `vo_alignment.json`. Prove word timings are usable.
- Confirm the ElevenLabs with-timestamps response shape on ONE paid call
  (cost-preview + cap first, per HANDOFF working-mode). RISK: API shape; mitigated
  by the free whisper path being the default.
- **Deliverable:** `vo_alignment.json` for an existing run. No risk to anything.

### Phase 1 (Days 2-3) — Invert the timeline (the core fix)
- `build_timeline.py`: scenes + alignment → `timeline.json` (§2.2). Drop the
  hard-sum rule; make `duration_s` advisory. Keep `_restyle_durations` ONLY as a
  pricing-time hint generator (so `producer.estimate` still has integers), or
  freeze a nominal duration for pricing and let the timeline own the real one.
- **Deliverable:** a `timeline.json` whose scene in/out spans match the spoken
  lines. Verify by overlaying timeline boundaries on the existing VO waveform.
- RISK: pricing reads `duration_s`. MITIGATION: keep a frozen nominal
  `duration_s` for pricing; the timeline is a separate artifact. Money path
  untouched.

### Phase 2 (Days 3-5) — Remotion `<Timeline>` composition (one render)
- Rebuild `studio/src/Root.tsx` → `"Timeline"` composition: `<Audio src=voiceover>`
  + `<Sequence from=in_frame durationInFrames=out-in>` per scene, each rendering a
  curated scene component. Port the existing archetype MOTION
  (`remotion_codegen.py:196-320`) into the components.
- Wire `cues` so reveals fire on word frames.
- **Deliverable:** ONE designed video, VO baked in, every scene landing on its
  words. This is the captivating-output milestone.
- RISK: the single-clip-per-render model is deeply wired (`adapters._studio_render`,
  `stitch`). MITIGATION: build `<Timeline>` ALONGSIDE the existing `"Scene"` comp
  behind an `overlays=timeline` flag (mirrors today's `overlays=studio` flag,
  `orchestrator.py:173-178`); the old path stays green for the test suite.

### Phase 3 (Days 5-6) — Curated style templates + template-fill
- Convert the three archetypes into 1-2 curated GENRES (start with one: the
  approved Orinovate kinetic-light or Zelios aurora-glass). Agent fills typed props
  from brand + beats instead of writing raw TSX.
- Higgsfield plates become backdrop layers (§3.3).
- **Deliverable:** brand-correct, genre-styled output for 2+ test brands.

### Phase 4 (Days 6-7) — ElevenLabs premium VO wired end-to-end
- `_vo_elevenlabs` returns alignment directly (skip whisper for the premium tier).
- `--vo elevenlabs` produces the highest-fidelity sync.
- **Deliverable:** premium path demoable; free path is the default/$0 test path.

### Phase 5 (Days 7-8) — Finish pass + music on the timeline render
- Adapt `finish_cut.py` grade + music-duck to run on the single timeline render
  (audio is already baked, so duck music UNDER the baked VO track). Keep the
  loudnorm/fade logic (`finish_cut.py:126-135`).
- **Deliverable:** shipped final.mp4, B+ polish, VO-locked.

### Phase 6 (Day 9) — Demo capture + buffer
- Re-record the 1-3 min demo (HANDOFF Dennis-gated item #1) on the new output.
- Buffer for slip. The Stripe money-shot demo is unaffected and can be shown
  independently if the render pivot runs long.

### Stays UNTOUCHED throughout
- Entire Stripe money path (§4). The test suite's money assertions stay green.
- `producer.py` pricing (reads a frozen nominal `duration_s`).
- The parallel-walkthrough threading (`orchestrator.py:300-326`) — walkthrough is
  optional now, but the isolation/threading machinery is harmless to leave.

### Fallback if the render pivot slips
Phase 1's `timeline.json` + a minimal `finish_cut` change that places each beat at
its WORD-anchored start (not scene start) already kills the drift on the EXISTING
clip pipeline — a non-Remotion-rewrite hedge that ships even if Phases 2-3 run long.

---

## 6. Summary

- **Root cause of the mismatch:** durations are locked before the VO exists
  (`plan_job.py:72-140` `_restyle_durations`, forced by `planner-prompt.md:96-98`
  and consumed at `orchestrator.py:531-534` / `adapters.py:951-962`). Beats-per-
  scene (already shipped) only changed start offsets; it did not remove the lock.
- **The pivot:** synth VO → word timestamps (ElevenLabs API / local whisper-cli) →
  `timeline.json` whose scene in/out + reveal cues are anchored to words → one
  Remotion `<Timeline>` render in a curated genre, Higgsfield as backdrop only.
- **Sacred:** the strictly-serial Stripe budget-gate + authorize sequence is never
  touched.
- **Highest-value first three builds:** (1) `align_vo.py` (free, whisper),
  (2) `build_timeline.py` inverting the dependency, (3) the Remotion `<Timeline>`
  composition behind a flag.
