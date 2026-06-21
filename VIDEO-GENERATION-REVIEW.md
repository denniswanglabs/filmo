# Video-Generation Review — Hermes Video Agent

_Read-only review, 2026-06-19. Scope: **video generation pipeline + produced-video quality ONLY.**
Infra/security/money are covered by `PRODUCTION-READINESS-REVIEW.md`; experience/UX by `UX-IMPROVEMENTS.md`.
This report does not re-flag those. Findings are grounded in the actual code (`file:line`) and in frames
extracted from the real-footage runs (`demo-1-approve`, `demo-3-decline`) and mock runs
(`build-linear`, `build-notion`, `build-stripe`)._

## What I actually looked at

- ffprobed every clip + final.mp4 across 5 runs: resolution/fps/codec are **perfectly uniform**
  (1920×1080, 30fps, h264, AAC 48k stereo). That part is solid — no codec/SAR/timebase drift, the
  fast concat path is valid. Durations: title clips ~3.05/4.05/5.06s, cinematic 6/7s, walkthrough
  **14s** (demo-1/3) — the walkthrough is **43% of the 32.3s real cut**.
- Read frames from: the real Seedance globe cinematic, the real GPT-Image-2 Stripe-dashboard still,
  three points of the real walkthrough, and four Remotion-authored title/divider cards.

The headline: **the two Higgsfield-generated scenes are genuinely good; the walkthrough and the
authored titles are what hold the cut at B+.** The single biggest, cheapest quality win is fixing
the walkthrough framing — it is literally ~27% black bars.

---

## 1. Tool-per-scene mapping

**Verdict: the mapping is mostly right, but two scene types are produced by the weakest available tool.**

- `orchestrator.py:223-237` routes: `title`/`motion_graphic` → authored Remotion (`studio_overlay`),
  `walkthrough` → `generate_walkthrough` (walk-agent) or `studio_placeholder`, `cinematic` →
  `generate_cinematic` (Higgsfield), else `generate_overlay`. Clean and correct in principle.
- **HIGH — the walkthrough is the flattest element and gets no production tool at all.** It is a raw
  screen capture (`adapters.py:189-205`) piped straight in. Everything else gets *authored* motion or
  *generative* visuals; the walkthrough gets none. See §3.
- **MEDIUM — `motion_graphic` and `title` share three flat templates** (`remotion_codegen.py:227`). For
  an "all-in-one producer" the motion-graphic slot is where data viz / animated stat cards / kinetic
  type should live; right now it's a number badge + a hairline + one line of text (§4).
- **LOW — cinematic still vs video is a planner lookup, not a per-scene judgment of what reads well.**
  The planner is told "prefer at least one of each" (`planner-prompt.md:93`). That's fine, but the
  *still* path (GPT Image 2) is the one that garbles text under any push-in (§2), so defaulting hero/UI
  plates to a still is a quality risk, not just a cost choice.

---

## 2. Cinematic (Higgsfield) — the strong path, with one real defect

**Frames observed.** The Seedance establishing shot (demo-1 `01_cine-establish`, 6s) is a glowing
amber payment-network over a dark 3D globe; strong, smooth motion (the network of light-trails clearly
proliferates between t=1s and t=4.5s), no text to garble, on-theme for Stripe. This is the best-looking
thing in the cut. The GPT-Image-2 still (demo-1 `02_cine-hero-still`, 6s) is a convincing dark Stripe
**Developers dashboard** — the "Stripe" wordmark and the overall layout read as real at a glance.

- **HIGH — GPT-Image-2 stills garble all body text and will not survive a push-in.** In the dashboard
  still, the API-key rows ("pk_live_…", "sk_live_…"), nav labels, and the "Create" button are fuzzy
  gibberish on inspection. It passes at 1× for ~1s but the moment you hold it 6s or zoom it, the fake
  text is obvious. The HANDOFF "minimal-motion + overlay-real-text" workaround is **only applied to
  Seedance video, not to GPT-Image-2 stills.** Fix: (a) for any UI/dashboard plate, prefer a real
  walk-agent screenshot or a Remotion-rebuilt UI over a GPT-Image-2 hallucination; (b) if you must use
  GPT-Image-2, steer the prompt away from legible text ("blurred UI in soft focus, no readable text,
  bokeh") and/or overlay a real lower-third with the actual label; (c) never push-in on a generated
  still that contains fake text.
- **MEDIUM — the brief→prompt path is thin.** `_generate_cinematic_real` (`adapters.py:121`) passes
  `scene["brief"]` to Higgsfield **verbatim** with no prompt engineering — no style/lighting/lens/
  negative-prompt scaffolding, no brand-color injection, no "no text/no logos/no watermark" guard
  (exactly the guard the HANDOFF says Seedance needs). The brief is a one-sentence *direction*
  ("Sweeping look at a global payments network…"), not a *generation prompt*. Quality is currently
  carried by the planner happening to write evocative briefs. Add a `cinematic_prompt(brief, brand)`
  builder that wraps the brief in a consistent cinematic style token + negative prompts + the brand's
  accent color, so look is consistent across scenes and across brands.
- **MEDIUM — Seedance duration is clamped to the brief but the brief duration is arbitrary.**
  `adapters.py:145` requests `min(15, max(4, duration_s))`. Fine, but 6s of one continuous AI clip with
  no cut tends to drift/loop; consider requesting a slightly longer gen and hard-cutting to the best
  4-5s window rather than using the whole render.
- **LOW — 720p→1080p normalize is correct but lossy.** Seedance renders 720p; `apply_real_media.normalize`
  (`apply_real_media.py:27-41`) upscales to 1080p with a plain `scale`. It works (the globe looks clean
  because it's soft/dark) but a sharper UI plate would show the upscale. Acceptable; flag if you ever
  go 4K.
- **LOW — no brand fidelity check on generated cinematic.** Nothing verifies the Seedance output uses
  brand colors; the globe happens to be amber/blue (close enough to Stripe). For a non-blue brand the
  generated cinematic could clash with the title cards. Inject brand accent into the prompt (above).

---

## 3. Walkthrough (walk-agent) — the #1 fixable quality problem

**Frames observed (demo-1 `03_walkthrough`, 14s).** Three issues, all visible in a single frame:

1. **~27% of the frame is black bars.** `cropdetect` on the live frame returns
   `crop=1440:960:240:60` — the real captured content is only **1440×960 inside a 1920×1080 frame**,
   offset x=240/y=60. The browser viewport floats as a centered card in black. This is the dominant
   reason it "reads flat": it isn't full-bleed, it's a small window.
   - **Root cause — BLOCKER-for-quality: `apply_real_media.normalize` letterboxes instead of filling.**
     `apply_real_media.py:31-33` uses `force_original_aspect_ratio=decrease` + `pad=…:color=black`.
     The walk-agent capture is not 16:9, so it gets padded with black. Note the **inconsistency**:
     `finish_cut.py:61` uses `force_original_aspect_ratio=increase` + `crop` (fill). So the swap step
     letterboxes, then the finish step crops the *already-letterboxed* frame — you can't recover the
     pixels. **Fix:** change `normalize` to `increase`+`crop` (fill) for video captures, OR capture the
     walk-agent at native 16:9, OR crop to the actual browser content rect before scaling. This one
     change reclaims a quarter of the most-screen-time scene.
2. **It opens on the walk-agent's own internal title card, not the product.** At t=1s the frame is a
   black card reading **"EXPLAINER AGENT · FEASIBILITY DEMO / Open the Stripe Dashboard… / Nemotron 3
   Super 120B · driving Chromium · docs.stripe.com"** in the *studio default green* (#7CFFB2), not
   Stripe purple. This is internal tooling leaking into a client-facing promo. **HIGH** — trim the
   walk-agent's intro/outro cards before the clip enters the cut (the HANDOFF already notes the raw
   output is a 66s "canonical Explainer" that must be windowed; the windowing isn't dropping the title
   card). The 14s clip in the cut still includes the agent's own chrome.
3. **It captures the docs site, not the product.** The brief was "Open the Dashboard, go to Developers,
   reveal the API keys" but the frames show **docs.stripe.com** documentation pages ("Developer
   resources", "Developers Dashboard" doc article) — the agent is reading docs *about* the dashboard,
   not performing the task in the live dashboard. **MEDIUM** (honesty/usefulness): the walkthrough
   doesn't actually show the promised task. For a real product the walk-agent needs to land on the
   app, not the docs; at minimum the planner's walkthrough `brief`/URL should target the app subdomain.

Additional walkthrough notes:
- **MEDIUM — lower-third instruction captions are the agent's QA overlays, not promo design.** Numbered
  green badges ("2 Click 'Developers Dashboard…'", "3 Click 'Developers'") are baked into the capture in
  the studio-green palette, with the agent's verbose internal phrasing. They're useful as captions but
  read as an internal test tool. For a promo, either suppress them and add brand-styled callouts in
  finish, or restyle them to the brand palette.
- **MEDIUM — the only motion applied is a 1.12× push-in.** `finish_cut.py:63-65` zoompans walkthrough
  clips to a max 1.12× zoom. Because the content is already letterboxed, the push-in zooms the black
  bars too. After the framing fix, a stronger Ken-Burns (1.0→1.18 with slight pan toward the action) +
  a couple of designed cursor-click highlights would lift it a lot.
- **LOW — tiny default OS cursor + faint click-halo.** Low production value. A larger designed cursor
  and a clear click-ripple (added in finish, or by the walk-agent) reads more "produced."
- **HIGH (pacing) — 14s is too long.** At 43% of the cut the walkthrough dominates and is the weakest
  element. HANDOFF NEXT-action #6 already calls for ~7-8s. Cut it to one tight task loop (§8).

---

## 4. Remotion-authored scenes — clean and on-brand, but templated and sparse

**Frames observed.** Stripe open (editorial archetype): navy #0A2540 bg, Stripe-purple #635BFF accent
rule + kicker, white "Stripe" wordmark, "Build internet businesses" subtitle — correct brand palette.
Stripe close (centered): "Start building" + gradient rule + "docs.stripe.com". Linear open: near-black
#0B0C0E, indigo #5E6AD2, "Plan and build products". **Brand-palette routing works and is the best part
of the authored path** (`remotion_codegen.BRAND_PALETTES`, `palette_for` at `remotion_codegen.py:64`).

But:

- **HIGH — internal-tooling copy leaks onto client title cards.** Every open card kicker is the literal
  string **"PRODUCER CUT"** and closes are **"CALL TO ACTION"** (`remotion_codegen.py:315-319`). These
  are placeholder labels, not creative copy, and "PRODUCER CUT" is internal language. A real agency
  card would carry a positioning line, not the word "cut". Replace the hardcoded kickers with copy
  derived from the brief/VO (or just brand-appropriate words: "PAYMENTS INFRASTRUCTURE", "GET STARTED").
- **HIGH — meta-direction is rendered as on-screen copy (a real bug).** The motion-graphic divider
  (build-stripe `04_motion-divider`) shows **"Simple animated divider with the text 'Built for"** —
  i.e. the planner's *scene direction* is printed verbatim and truncated at 48 chars
  (`remotion_codegen.py:321` `brief[:48]`). The card should display the *content* ("Built for
  developers") not the *instruction*. Either have the planner emit a separate `on_screen_text` field,
  or strip leading directive phrases ("Simple animated divider with the text '…'") before rendering.
- **MEDIUM — only 3 archetypes, chosen by a hash of the scene id** (`remotion_codegen.py:73-78`). centered
  title, editorial title, numbered divider. No stat card, no logo lockup, no two-up comparison, no
  kinetic word-by-word build. For a producer that bills itself as "agency-made," 3 static layouts is
  thin variety; titles in the same video can collide on the same archetype.
- **MEDIUM — typography is `Helvetica, Arial, sans-serif`, hardcoded in every template**
  (`remotion_codegen.py:117,149,184,209`). Not the brand's font (Stripe ≈ sohne; Linear ≈ Inter Display).
  Reads generic-corporate, not brand-specific. Bundle 2-3 brand-ish webfonts or map a font per palette.
- **MEDIUM — vast dead negative space + no background texture/motion.** The open card has its text in
  the lower-left third with ~70% empty flat navy; the cards hold a *still* frame after a ~1s entrance.
  No gradient wash, grain, ambient particles, drifting brand mark, or parallax. This is the difference
  between "a slide" and "a title sequence." Add a subtle animated background (gradient drift / low-opacity
  brand glyph / grain) and keep one element in slow continuous motion through the hold.
- **LOW — the wordmark is set type, not the real logo.** "Stripe"/"Linear" are rendered in Helvetica,
  not the actual brand logo. A real brand promo opens on the logo. Consider an SVG logo lockup per brand
  (memory note: native SVG over raster; no raster screenshots).
- **LOW — animation vocabulary is one spring + linear `ease` interpolations.** Competent, but every
  scene uses the same rise/sweep/pop. No overshoot, stagger-by-letter, blur-in, or whip — the named
  motions in the Zelios/Jitter vocab (memory) would add variety for free.

---

## 5. Voiceover

- **MEDIUM — edge-tts is the synthetic tell.** `adapters._vo_edge` (`adapters.py:298`) maps the planned
  "Adam" voice to `en-US-AndrewNeural`. It's intelligible but flat/robotic vs ElevenLabs. The HANDOFF
  owns this (B+, no ElevenLabs spend yet). For the *submission* cut specifically, one ElevenLabs pass
  (`_vo_elevenlabs` is already wired, `adapters.py:307`) on the hero video is the single biggest
  perceived-quality lift per dollar. ~263 chars ≈ a few cents.
- **MEDIUM — VO is one monolithic track muxed under the whole video; there is no scene sync.**
  `stitch` (`adapters.py:371-376`) and `finish_cut` (`finish_cut.py:80-86`) lay the full VO over the
  whole timeline with a flat 350ms `adelay`. Nothing aligns a sentence to its scene. The script *reads*
  in order (planner is told to time it, `planner-prompt.md:99`) but timing is by luck — if the
  walkthrough is 14s, the "open the Dashboard, click Developers, then API keys" line may finish long
  before the on-screen action does, or vice-versa. There's no per-scene VO segmentation, no timestamp
  map, no silence padding to a scene boundary. For real sync, split the script per scene and lay each
  segment at its scene's offset (or have the planner emit `script` per scene).
- **MEDIUM — script quality is decent but generic.** Stripe: "Stripe powers internet businesses with one
  platform… Here is how developers get started fast…" (plan.json). Reads like competent boilerplate.
  The template fallback is worse: "{Brand} helps you do more with less. Here is how it works, end to end.
  Get started today." (`plan_job.py:82`) — pure filler. Tighten the prompt toward a concrete hook + one
  proof point + one CTA, and improve the fallback.
- **LOW — VO can be shorter than the picture, leaving dead-air tails.** `stitch` trims VO to video
  length but doesn't pad/extend; with a 32s video and ~263-char script (~18-20s of speech) there's a
  long musical tail. Fine with music, but the pacing budget should target VO ≈ 80-90% of runtime.
- **LOW — `voice` is always "Adam"** (forced in the prompt, `planner-prompt.md:104`). No brand/tone
  matching. Minor, but a producer would pick voice per brand.

---

## 6. Assembly & finishing

`finish_cut.py` is the craft layer and it's the reason the cut clears B+. It's competent ffmpeg.

- **MEDIUM — the unifying grade is applied to ALL clips including the authored titles, which don't need
  it.** `finish_cut.py:27,60-62` applies `eq(contrast=1.07,sat=1.14,bright=0.012,gamma=0.98)` + a global
  `unsharp` to every clip. The grade helps the heterogeneous real footage cohere, but the `unsharp=3:3:0.25`
  on already-pristine Remotion text adds faint ringing to type edges, and the saturation bump shifts the
  carefully-chosen brand accent colors. Consider grading only the camera/screen-capture sources
  (cinematic + walkthrough) and leaving authored vector scenes ungraded, or a much gentler unsharp.
- **MEDIUM — every transition is the same 0.45s `xfade=fade` (dissolve).** `finish_cut.py:71-72`. Uniform
  crossfades read "slideshow," not "edit." Cutting hard into the cinematic (energy) and dissolving out of
  it, or using a dip-to-brand-color between acts, would feel more intentional. At minimum vary the
  transition by boundary (title→cinematic = cut; cinematic→walkthrough = dissolve).
- **LOW — the crossfade eats real seconds and isn't reflected back into the plan.** `total = sum(durs)
  - XF*(n-1)` (`finish_cut.py:47`): with 5 clips that's 1.8s lost to overlaps, so a 30s plan ships at
  ~28.2s (mock) / 32.3s (real, because the walkthrough is 14s not the planned 10s). The plan's duration
  contract and the delivered duration diverge. Account for transition overlap in the planner's duration
  math, or trim to hit the target.
- **LOW (good) — the audio mix is the most professional part.** Music bed `atrim`+`afade` in/out, VO
  `adelay 350` + `aresample`, **sidechain-compress the music under the VO** (threshold 0.02, ratio 7,
  attack 15, release 380) then `amix` (`finish_cut.py:80-86`). That's a real ducking chain and it works.
  Levels match the memory note (BGM+VO). Keep it. One nit: the duck is keyed off `vokey` pre-delay-split
  so the duck and the audible VO are aligned — verify the 350ms delay didn't desync the sidechain key.
- **LOW — single fixed 51.5s music bed** (`assets/music-bed.mp3`). One track for every brand/mood. A
  producer would pick from a small library by tempo/energy and trim to the cut. See §10.
- **LOW (good) — fade-to-black + audio tail outlasting the visual fade** (`finish_cut.py:76`,
  audio fade `total-1.2`) matches the house style (memory: audio outlasts visual fade). Correct.

**Coherence across heterogeneous sources:** the grade + uniform crossfade + music bed *do* make
real-footage + authored-Remotion + screen-capture hang together as one piece — that's the finish pass
earning its keep. The seams that remain are tonal: the Seedance globe is rich/cinematic, the authored
titles are flat/minimal, and the walkthrough is a letterboxed browser. They cohere as "one editor cut
this" but not as "one art director designed this."

---

## 7. Overall coherence & the quality bar (B+ vs A)

The cut convincingly reads as "a real agency made a competent explainer." What separates it from an A:

1. **The walkthrough.** It's a third of the runtime, letterboxed, opens on internal chrome, and shows
   docs instead of the product. Fixing framing + trim + brand-styling alone moves the whole piece up
   half a grade. (§3 — highest leverage.)
2. **Generated-still text garble.** The one moment a viewer might catch the AI is the GPT-Image-2
   dashboard if it's held or zoomed. (§2)
3. **Authored-title craft.** On-brand but sparse, generic font, "PRODUCER CUT" placeholder copy, no
   background motion. These read as "good slides," not "title sequence." (§4)
4. **VO.** edge-tts is the audible tell; no scene sync. (§5)
5. **Sameness of motion/transitions.** One spring, one dissolve, one push-in, one grade. An A cut
   varies its rhythm. (§4, §6)

Visual consistency is good on the *technical* axis (perfectly uniform specs) and good on *brand color*
(palette routing). It's weakest on *art direction* (the three sources have three different polish
levels) and *typographic identity* (one generic font).

---

## 8. Pacing & structure

- **HIGH — the walkthrough breaks the pacing budget.** 14s real (43%); memory pacing budget says no
  scene > 9s. Trim to ~7-8s of one tight task loop. (Ties to §3.)
- **MEDIUM — fixed 5-beat skeleton (title / 2-3 cinematic / 1 walkthrough / title)** is enforced by the
  planner prompt (`planner-prompt.md:76-86`) and the template (`plan_job.py:66-80`). Safe and on-genre,
  but every video has the identical arc and beat count. No B-roll interludes, no stat beats, no rhythm
  variation. For variety, allow the planner to insert a motion-graphic stat beat or a second short
  cinematic where the goal warrants.
- **MEDIUM — durations are whole-second and summed to target, but transition overlap isn't modeled** (§6),
  so delivered length drifts from plan.
- **LOW — title cards hold static for most of their duration.** A 5s close card animates in ~1s then
  holds 4s still. Either shorten or keep something moving (§4).
- **LOW — no act-level structure beyond the linear list.** The motion-graphic "divider" exists as a
  pacing device (`planner-prompt.md:84`) but only build-stripe used one, and it rendered the bug from §4.

---

## 9. Reliability of generation

- **MEDIUM — truncated planner output can ship as a valid-looking plan.** `validate_planner.call_model`
  uses `max_tokens:8000`, only *prints* a warning on `finish_reason != "stop"` (`validate_planner.py:117-119`),
  and still returns the (possibly truncated) content; `extract_json` takes first-`{` to last-`}`. A
  truncated-but-bracket-balanced object can parse and pass shape validation → a wrong/short plan drives
  generation. (PRODUCTION-READINESS §4.1 flags this for *correctness*; calling it out here because the
  **video** consequence is a malformed storyboard / cut-off VO script feeding the renderers.) Treat
  `finish_reason=="length"` as a hard failure → template fallback.
- **MEDIUM — no per-scene try/except in the produce loop** (`orchestrator.py:209+`). A single
  edge-tts/Remotion/ffmpeg hiccup aborts the whole video. For *free/local* generation steps (synth,
  edge-tts, studio render) one retry then error-the-one-scene-and-continue would make the produced video
  resilient. (Keep no-retry on paid Higgsfield — correct.)
- **MEDIUM — `generate_overlay` silently degrades to a flat color card** if Remotion fails
  (`adapters.py:232-234`) — a silent *visual-quality* regression (a blank card in the cut) the user never
  sees flagged. `studio_overlay` correctly raises instead. Make the policy consistent and surface the
  degradation.
- **LOW — determinism is good where it matters.** Authored Remotion is fully deterministic
  (archetype by id hash, all values baked, `remotion_codegen.py`). Planner temp is 0.2 (low variance).
  Seedance/GPT-Image-2 are inherently non-deterministic (no seed pinned) — fine for a one-shot, but a
  re-roll gives a different look; if you ever need reproducibility, pin a seed.
- **LOW — paid asset URL not persisted before download** (`adapters.py:154`): a failed `curl` after a
  paid Seedance job loses the paid work (also in PRODUCTION-READINESS §4.5; relevant here because it
  means a transient network blip can cost a generation and drop the scene from the cut).

---

## 10. What's MISSING for an all-in-one producer

These are capabilities a "from a URL, produce a finished promo" product is expected to have and the
pipeline currently lacks:

- **HIGH — burned-in captions / subtitles.** No subtitle track and no on-screen captions synced to the
  VO. Social/explainer video is watched muted; captions are table stakes. You already have the VO text
  in the plan and edge-tts can emit word timings — generate an SRT and burn styled captions in
  `finish_cut`.
- **HIGH — real brand logo insertion.** Wordmarks are set in Helvetica (§4). No actual logo asset is
  fetched or placed. A producer should pull the brand's logo (favicon/SVG) and lock it up on the
  open/close cards and as a persistent corner bug.
- **MEDIUM — brand-styled lower-thirds / callouts on the walkthrough.** The only callouts are the
  walk-agent's internal green captions (§3). A producer adds its own brand-palette lower-thirds, key
  highlights, and pointer emphasis.
- **MEDIUM — aspect-ratio variants.** Everything is hardcoded 1920×1080 16:9 (`adapters.py:35`,
  `finish_cut.py:25`, `remotion_codegen.py:22`). No 9:16 vertical or 1:1 square for social — which is
  where promos actually run. The frame spec is a single global; parameterize W/H/FPS per output target
  and re-layout the authored scenes responsively (memory: 9:16 top-12% safe area).
- **MEDIUM — a thumbnail / poster frame.** No still export for the video's YouTube/social thumbnail. Easy
  win: render one designed end-card frame or pick a hero frame.
- **MEDIUM — music selection & licensing.** One fixed royalty-free bed for all brands (§6). A producer
  picks by mood/tempo and tracks the license. At minimum a small library keyed by brand energy.
- **MEDIUM — B-roll / transition stings.** No interstitial b-roll, no branded transition sting between
  acts (just the uniform dissolve, §6). These are what make a cut feel "produced."
- **LOW — intro/outro brand sting + logo animation.** The close is a static text card; a short animated
  logo reveal would be a stronger CTA beat.
- **LOW — on-screen text overlays on cinematic.** The HANDOFF's "overlay-real-text" workaround for
  Seedance garbling isn't implemented anywhere — there's no overlay-text compositing step over cinematic
  clips. Adding it both fixes garble (§2) and adds a value-prop callout beat.

---

## TOP 7 GENERATION-QUALITY WINS (ordered by impact ÷ effort)

1. **Fix the walkthrough letterbox — fill instead of pad.** `apply_real_media.py:31-33`: switch
   `force_original_aspect_ratio=decrease`+`pad(black)` → `increase`+`crop`, or crop to the real browser
   content rect. Reclaims **~27% of the most-on-screen scene's pixels** (`cropdetect=1440:960:240:60`).
   _Tiny change, biggest visible lift._ (§3)

2. **Trim the walkthrough to ~7-8s and drop the walk-agent's intro card.** Window the capture past its
   own "EXPLAINER AGENT · FEASIBILITY DEMO" green title card and the internal QA captions before it
   enters the cut. Rebalances the cut (was 43%) and removes the internal-tooling tell. (§3, §8)

3. **Kill the placeholder/meta copy on authored cards.** Replace hardcoded `"PRODUCER CUT"` /
   `"CALL TO ACTION"` kickers and fix the divider that prints the scene *direction*
   ("Simple animated divider with the text 'Built for") instead of the content
   (`remotion_codegen.py:315-326`, `brief[:48]`). Cheap, removes two obvious "this is a template" tells.
   (§4)

4. **Stop pushing-in on / holding GPT-Image-2 stills with fake text; steer the prompt off legible text,
   or rebuild UI in Remotion.** The dashboard still garbles all body text under any hold/zoom
   (`adapters.py:128-141`). For UI/hero plates prefer a real screenshot or a Remotion-built UI; if using
   GPT-Image-2, add "no readable text, soft focus" to the prompt. (§2)

5. **Add a `cinematic_prompt(brief, brand)` builder + a `caption/SRT` burn-in.** Wrap the bare brief in a
   consistent cinematic style + negative prompts + brand accent before sending to Higgsfield
   (`adapters.py:121`), and generate burned-in styled captions from the VO text in `finish_cut`. Two
   medium changes that lift both the cinematic consistency and the muted-watch experience. (§2, §10)

6. **Give the authored titles art direction: brand font + animated background + one moving element on
   hold.** Map a brand-ish webfont per palette (drop generic Helvetica), add a subtle gradient/grain/
   drifting-glyph background, and keep something in slow motion through the static hold
   (`remotion_codegen.py` templates). Turns "good slides" into "title sequence." (§4)

7. **One ElevenLabs pass on the submission hero + rough per-scene VO sync.** Flip `--vo elevenlabs`
   (already wired, `adapters.py:307`) for the demo cut — biggest perceived-quality-per-dollar lift — and
   split the VO so each sentence lands on its scene rather than a flat full-track mux. (§5)

_Out of scope here (covered elsewhere): the shared `active.tsx` render race, auth on `/api/build`,
restart resilience, the static-server lockdown — see `PRODUCTION-READINESS-REVIEW.md`._
