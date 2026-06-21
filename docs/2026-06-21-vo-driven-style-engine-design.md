# Walk Studio — VO-Driven Style-Fill Output Engine (design spec)

_2026-06-21. The output-quality pivot. Supersedes the generic-AI-b-roll output path._
_Inputs: `research/ELEVENLABS-RESEARCH.md`, `research/CURATED-DESIGN-LIBRARY.md`, `research/PIPELINE-PIVOT-ARCHITECTURE.md`._

## Problem
The agent's produced videos are not captivating and the VO does not match the
visuals. Root cause (audit): scene durations are locked **before** the VO exists
(`plan_job.py:117` — `duration = budget / N`, voice never consulted; enforced by
`planner-prompt.md:96-98`, `plan_schema.py:179-183`), then the VO is squeezed
into those fixed slots (`orchestrator.py:531-534`, `adapters.py:951-962`). The
visuals are also generic Seedance b-roll, not designed motion-graphics.

## The pivot (one line)
**Fill Dennis's curated style templates with the customer's brand, and slave the
whole timeline to a word-aligned voiceover** — so the picture is built from the
voice (it cannot drift) and every frame is designed, not generic.

## Decisions locked (2026-06-21)
1. **Output = designed motion-graphics** filling curated Remotion templates,
   choreographed to a VO transcript. No generic Seedance b-roll on the backbone.
2. **v1 style set (3 templates):**
   - **Orinovate kinetic-light** — PRIMARY/default. Pure Remotion, deterministic,
     already re-skinned 5×. Source: `~/Desktop/Projects/Orinovate/orinovate-kinetic-light/`.
   - **Apple-style** — "premium quiet". Pure Remotion, silent, `PATTERNS.md`.
     Source: `~/Desktop/Projects/Demos/apple-style-demo/` (+ trayd-promo).
   - **JGB cinematic** — Zelios six-act arc + Higgsfield plates as **textured
     backdrops behind native glass UI**, **cached per run** for deterministic
     re-render, behind a `--cinematic` flag. Source: `~/Desktop/Projects/Demos/jgb-promo/`.
3. **VO:** free tier first = edge-tts + local `whisper-cli` (installed) for
   word-timing. ElevenLabs `with-timestamps` = premium tier behind a flag. **No
   ElevenLabs spend until Dennis greenlights the paid plan ($5–22).**
4. **Multilingual = BUILT now** (demo centerpiece): translate script (Nemotron/
   Gemini) → per-language VO (edge-tts free / ElevenLabs premium) → per-language
   word-align (multilingual Whisper free / ElevenLabs) → re-anchor the timeline
   per language → render N videos. Producer prices per language (~N× revenue).
5. **Earn axis in the producer:** price line-items for added languages
   (+$29–49/lang, >99% margin), premium-VO tier, custom brand-voice (recurring →
   Stripe subscription). Surface in the P&L. (See ELEVENLABS-RESEARCH.md.)
6. **Walk-agent → demoted to an OPTIONAL NemoClaw inset** (one framed scene), not
   dropped — keeps the NVIDIA/NemoClaw sponsor axis. Never the backbone.
7. **SACRED — untouched:** the Stripe money path — serial budget-gate + authorize
   (`orchestrator.py:387-509`), `active_budget.json` bridge, `build_runner.py`
   pay-gate. No change proposed or allowed here.

## Architecture (new modules; existing scene path stays green behind a flag)
- **`align_vo.py`** — script → synth (reuse `adapters.synthesize_voiceover`) →
  word-level timestamps (whisper-cli free / ElevenLabs with-timestamps premium)
  → `vo_alignment.json`. $0, zero pipeline risk.
- **`build_timeline.py`** — inverts the dependency: scenes + alignment →
  `timeline.json` (each scene `in_frame`/`out_frame` from its word span; cut
  scenes slide the rest earlier; `total_frames` from audio duration).
  `duration_s` is demoted to an advisory/pricing-only hint.
- **Remotion `<Timeline>` composition** — rebuild `studio/src/Root.tsx`:
  `<Audio>` + per-scene `<Sequence>` at word-anchored frames, designed reveals
  firing on cue frames. Behind an `overlays=timeline` flag so the existing
  single-`<Scene>` path stays green for the test suite. Port archetype motion
  from `remotion_codegen.py:196-320`.
- **Style-fill engine** — a style registry of the 3 templates. Each exposes a
  normalized fill contract: `theme.ts` (palette + fonts) + per-scene copy/UI-data
  + brand wordmark SVG; motion frozen. Agent: pull brand from URL → pick style →
  fill → render. (This is exactly Dennis's manual re-skin workflow, automated.)
- **Multilingual module** — wraps align+timeline+render per language; producer
  multiplies price by language count.
- **JGB cinematic** — Higgsfield plates generated once, cached under the run dir,
  composited as backdrops; deterministic on re-render.

## Data contracts
- `vo_alignment.json`: `[{word, start_s, end_s, beat_scene_id}]` (+ per-language).
- `timeline.json`: `{fps, total_frames, scenes:[{id, in_frame, out_frame,
  style_archetype, cues:[{label, word, at_frame}]}], audio_path, lang}`.
- Style fill: `{style, theme:{palette, fonts}, scenes:[{id, copy, ui_data}],
  wordmark_svg}`.

## Build phases (~9 days to EOD 2026-06-30)
1. **VO-driven core on ONE template** (Orinovate kinetic-light): `align_vo.py` +
   `build_timeline.py` + `<Timeline>` behind flag. Prove VO-matched end-to-end,
   $0/mock. _Highest priority — this is the captivating-output fix._
2. **Style-fill engine** + register Apple-style; brand extraction; agent picks style.
3. **Multilingual** (translate + per-language render + per-language pricing).
4. **JGB cinematic** (cached Higgsfield backdrops) behind `--cinematic`.
5. **Finishing**: music-duck to the new timeline, captions from alignment, grade;
   integrate into `build_runner.py` + dashboard live console.
6. **Demo polish**: real renders in the chosen brand, the cut, P&L money story.

## Testing
- Keep `./run_all_tests.sh --no-eval` green throughout (new path behind flag).
- Add: `build_timeline` unit tests (word-span → frames; cut-scene slide), a
  render-smoke per template, an alignment sanity check (word count vs script).

## Risks
- **Scope** — multilingual + JGB add real load; phase 1 (the actual quality fix)
  must land first and stand alone.
- **JGB determinism/cost** — mitigated by cached plates + the `--cinematic` flag.
- **Multilingual alignment** — needs the multilingual Whisper model (free
  download); verify accuracy vs the English `.en` model.
- **Template seams differ per repo** — `theme.ts` shape varies; the style-fill
  contract must normalize them (a per-template adapter).
```
