# VO-MISMATCH-ANALYSIS — why the voiceover does not match the video

**Date:** 2026-06-20
**Scope:** READ-ONLY diagnosis. No files edited except this report. No rebuild, no paid VO/Higgsfield, $0 spent.
**Run analyzed:** `runs/demo-3-decline` (the Stripe "API keys" money-shot).

---

## 0. Run identification (confirmed)

| Signal | Value | Source |
|---|---|---|
| P&L margin | **0.6739** (≈ 0.674) | `runs/demo-3-decline/ledger.json` → `pnl.margin` (only ledger matching) |
| Goal / brief | "30-second explainer plus a walkthrough of finding your API keys" | `plan.json` → `job.goal` |
| Company | `https://docs.stripe.com` | `plan.json` → `job.company_url` |
| Money decision | `hero-still` scene **declined** at the budget gate (hence "decline" in the run name) | `ledger.json` → `scenes[hero-still].status = "declined"` |

This is unambiguously the run Dennis flagged.

---

## 1. The two artifacts, side by side

**The VO script** (`plan.json` → `voiceover.script`, 263 chars, synthesized to `voiceover.mp3` = **16.99 s** via edge-tts `en-US-AndrewNeural`):

> "Stripe powers internet businesses with one platform for payments and billing. Here is how developers get started fast. **Open the Dashboard, click Developers, then API keys, and copy your secret and publishable keys.** Start building today at docs dot stripe dot com."

**The video** (`final.mp4` = **26.79 s**, 4 clips; the planned 5th scene `hero-still` was cut at the money gate):

| # | scene id | type | clip dur | what's on screen |
|---|---|---|---|---|
| 1 | title-open | title | 3.05 s | Stripe wordmark + tagline |
| 2 | cine-establish | cinematic | 6.03 s | sweeping global payments network |
| 3 | walkthrough | walkthrough | **14.0 s** | Dashboard → Developers → **API keys reveal** |
| 4 | title-close | title | 5.06 s | CTA: start building at docs.stripe.com |

Note the walkthrough clip is **14 s**, not the 10 s in `plan.json` — the produced clip is longer than planned, so the real timeline already diverges from the plan before any audio is considered.

---

## 2. The desync, quantified

The VO is laid down as **one flat 17 s track starting at t≈0** (350 ms lead-in). The picture runs 26.79 s. Mapping VO sentences (proportional-by-character estimate; edge-tts is near-constant chars/sec) against the actual clip timeline:

```
VO sentence landing (≈)            VIDEO clip running at that moment
─────────────────────────────────────────────────────────────────────────────
0.3 – 5.4s  "Stripe powers …"      title-open (0–3) + cine-establish (2.6–8.2)
5.4 – 8.0s  "how developers …"     cine-establish (still the cinematic shot)
8.0 –14.2s  "Open the Dashboard,   walkthrough (7.7–21.3) — PARTIAL overlap only;
            …then API KEYS, copy   the API-keys line ends at ~14.2s but the
            your secret keys."     walkthrough screen keeps playing to 21.3s
14.2–17.3s  "Start building today  walkthrough STILL on screen (CTA spoken over
            at docs.stripe.com"     the dashboard, not over the CTA card)
17.3–26.8s  ── SILENCE ──          walkthrough tail (17.3–21.3) + the ENTIRE
                                   title-close CTA card (20.8–26.8) play mute
```

**Concrete failures this produces:**

1. **The CTA is spoken over the wrong picture.** "Start building today at docs.stripe.com" fires at ~14–17 s while the dashboard walkthrough is still on screen. The CTA *card* (the title-close, 20.8–26.8 s) — the one place that line belongs — has **no narration at all**.
2. **~9.5 s of silent tail.** Narration ends at ~17.3 s; the video continues to 26.79 s. The last third of the cut (walkthrough tail + the whole closing card) plays with only the music bed. The video ends nearly 10 seconds after the voice stops.
3. **The "API keys" payoff is only loosely co-timed.** The line lands at ~8–14 s; the walkthrough that *shows* the keys runs 7.7–21.3 s. It overlaps, but by luck of clip ordering, not by design — and the most visually important beat (the actual key reveal late in the 14 s clip) has no narration on it.

There is no mechanism anywhere in the pipeline that aligns a narration beat to the clip that depicts it. The overlap that does exist is incidental.

---

## 3. Is the script generic / a template fallback? — NO

The generic template fallback (`plan_job.py` → `_template_plan`, lines 81–84) produces:

> "<brand> helps you do more with less. Here is how it works, end to end. Get started today."

demo-3-decline's script is **not** this. It names Stripe specifically and walks the API-keys steps ("Open the Dashboard, click Developers, then API keys, and copy your secret and publishable keys"). So:

- **The script content is scene-aware and specific** — it was produced by the Nemotron planner (`_plan_with_nemotron`) or a hand-authored plan, not the generic fallback.
- **Therefore the root cause is NOT a template fallback.** The words are fine; the problem is structural — the script is authored as one prose blob with no binding to scene ids/durations, and it is muxed with no per-scene timing.

(For completeness: the script *is* good enough that, with correct timing, it would mostly work — the explainer sentences want to land on title-open + cinematic, the walkthrough sentence wants the walkthrough clip, the CTA wants the closing card. The information is there; the alignment is not.)

---

## 4. MUX behavior in code — confirmed: ONE flat track, zero per-scene alignment

**VO synthesis** (`adapters.py` → `synthesize_voiceover` / `_vo_edge`, lines 441–456): takes the entire `script` string and produces a **single** `voiceover.mp3`. No segmentation, no per-sentence files, no scene mapping. The script is one opaque blob to the synth layer.

**Raw stitch** (`adapters.py` → `stitch`, lines 497–528): concats clips in order, then muxes the VO with
```
-map 0:v:0 -map 1:a:0 -t <vdur>
```
i.e. the VO starts at t=0 of the concatenated video and is trimmed to video length. No offset, no alignment to any scene boundary. The docstring even says it just "leaves trailing silence" when the VO is shorter — which is exactly the 9.5 s silent tail observed.

**Finishing pass** (`finish_cut.py`, lines 80–91), which produced the shipped `final.mp4`:
```
[vo] adelay=350|350, aresample=48000, asplit ...      # single global 350ms delay
[mus] volume=0.5 → sidechaincompress(threshold=0.02…) # duck music under VO
amix=inputs=2 → loudnorm=I=-14                          # mix whole-track
```
The VO is delayed by a single flat 350 ms and ducked/mixed across the **entire** timeline as one stream. **There is no per-scene VO segment, no offset tied to any clip's start or duration, anywhere in the pipeline.** This matches the VIDEO-GENERATION-REVIEW finding: the narration is a flat full-length track that drifts off the matching visuals.

**Orchestrator** (`orchestrator.py`, lines 345–392): the VOICEOVER phase synthesizes the one blob and the STITCH phase calls `adapters.stitch` with the single `vo_path`. The orchestrator never passes scene timing to the VO, and never tells the stitch where any line should land. So the timing gap is structural, not a one-off.

---

## 5. Root cause (precise)

**Primary root cause — no scene-level VO timing/sync.** The VO is authored as one prose blob and muxed as one flat full-length track (single 350 ms lead-in) with no binding between narration beats and scene start/duration. Because the produced walkthrough clip is 14 s (vs 10 s planned) and `hero-still` was cut, the 17 s of speech and the 26.79 s of picture drift apart: the CTA line lands mid-walkthrough, and the final ~9.5 s (including the entire CTA card) is silent. This is the dominant cause and is independent of script quality.

**Contributing cause — the script is not authored against the final scene list/durations.** It is scene-aware in *content* but written as free prose, with no per-scene beats, no awareness that a scene can be cut at the money gate, and no target word-count per clip. So even a perfect muxer has nothing to align to.

**Not a cause — template fallback.** Ruled out (Section 3). The Nemotron/authored script is specific and correct in content.

---

## 6. Prioritized fix proposal (impact vs effort, before 2026-06-30)

Ranked best-first. (a) is the highest impact-per-effort and should ship first.

### (a) Per-scene VO segments timed to each clip — **HIGH impact / MEDIUM effort** ← do this first
Change the plan/schema so `voiceover` is a **list of beats keyed by scene id** instead of one `script` string, e.g. `[{scene:"walkthrough", line:"Open the Dashboard…"}, …]`. Then:
- `synthesize_voiceover` renders **one mp3 per beat** (edge-tts per line — still free).
- The stitch/finish places each beat at its scene's **start offset** (`adelay = cumulative-clip-start-minus-crossfade`), padding/silence to fit the clip, instead of one flat track.
- Beats whose scene was **declined/cut at the money gate are dropped or reflowed** — fixes the CTA-spoken-over-walkthrough bug directly, because the CTA beat is now pinned to the title-close card.

This single change kills all three observed failures (wrong-picture CTA, silent tail, loose API-keys timing). It is the smallest change that makes narration land on the matching visual. Reuses existing edge-tts + ffmpeg `adelay`; no new dependency.

### (b) Generate the VO script FROM the final scene briefs — **HIGH impact / LOW–MEDIUM effort**
Make the planner emit the per-scene `line` field in (a) directly from each scene's `brief`, so narration provably describes what's on screen, with a soft word-budget per clip (≈ duration_s × ~2.5 words/s). Pairs naturally with (a) — (a) is the plumbing, (b) is the content that fills it. Low effort because it's a planner-prompt + schema change, not a new runtime.

### (c) Planner-prompt change tying narration beats to scenes — **MEDIUM impact / LOW effort**
Edit `planner-prompt.md` / `validate_planner.SYSTEM_PROMPT` to require the VO be returned as one beat per scene (id + line + target words), and to keep the closing CTA line on the closing title scene. This is the schema/prompt half of (a)+(b); do it together with them. Cheap, but inert without (a)'s timing plumbing.

### (d) Align the stitch so narration lands on the matching scene — **(subsumed by (a))**
This is exactly what (a) implements (offset each beat to its scene start). Listed separately only to note: if a no-schema-change stopgap is needed before the deadline, a minimal version is to **anchor the existing single VO track to the walkthrough's start offset** (so the "Open the Dashboard… API keys" sentence sits on the walkthrough clip) rather than t=0 — a one-line `adelay` change in `finish_cut.py`. That is a band-aid (it doesn't fix the silent tail or the mis-timed CTA), but it's a 10-minute hedge if (a) can't land in time.

**Recommended path for the deadline:** ship **(a) + (b) + (c) together** — they are one coherent change (beat-per-scene schema, planner emits the beats, stitch times them). Keep **(d)'s one-line `adelay` band-aid** in your back pocket as the fallback if the schema change runs long.

---

## Appendix — evidence index (all read-only)

- `runs/demo-3-decline/plan.json` — goal, 5-scene plan, single `voiceover.script` string.
- `runs/demo-3-decline/ledger.json` — `pnl.margin = 0.6739`; `scenes[hero-still].status = "declined"`; `voiceover.provider = edge-tts`, `voice = en-US-AndrewNeural`, `chars = 263`; `stitch.scenes_included = [title-open, cine-establish, walkthrough, title-close]`, `scenes_cut = [hero-still]`; `finish.ducked = true`.
- `voiceover.mp3` = 16.99 s; `final.mp4` = 26.79 s (ffprobe).
- clip durations (ffprobe): title-open 3.05, cine-establish 6.03, walkthrough **14.0**, title-close 5.06.
- `adapters.py:441–456` — `synthesize_voiceover` renders the whole script as one mp3.
- `adapters.py:497–528` — `stitch` muxes VO at t=0, trim-to-video, no offset.
- `finish_cut.py:80–91` — VO `adelay=350|350` then ducked/mixed across the whole track; no per-scene offset.
- `plan_job.py:59–85` — `_template_plan` fallback VO ("…do more with less…end to end…get started today") — does NOT match demo-3-decline's script, so fallback is ruled out.
- No local whisper available; silencedetect found no clean sentence gaps. The script-vs-scene + code evidence proves the desync without transcription.
