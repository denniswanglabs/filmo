# Hera Video — Animation & Transition Vocabulary Analysis

Source video made with **Hera** (hera.video, an AI motion-graphics tool). Goal: extract its
transition/animation vocabulary so we can re-author the moves in our own reference library.

## File facts

| Field | Value |
|---|---|
| Path | `/Users/dennis/Downloads/ec80612d-00c6-4784-bd14-a3b70920c056_720p_mp4_30_16-9.mp4` |
| Duration | 21.03 s |
| Resolution | 1280 x 720 (16:9) |
| Frame rate | 30 fps (630 frames) |
| Codec / size | H.264 / 2.94 MB |
| Hard cuts detected | **0** (scene threshold 0.3 and 0.1 both returned nothing) |
| Transition zones (soft) | ~6, from scene-score peak clusters |

Note: a faint **"Hera / Made with hera.video"** watermark sits top-left the whole time (free-tier
export). The piece is a Luceo Studio brand teaser; text beats spell out the studio's pitch.

### Why "0 hard cuts" matters
`ffmpeg ... select='gt(scene,0.3)'` found nothing, and even `gt(scene,0.1)` found nothing. Max
frame-to-frame scene score across the whole video is only **0.090**. This is the single most
important finding: **Hera never hard-cuts.** Every beat change is a continuous animated transition
(blob wipe / band wipe / edge wipe / cross-dissolve), so inter-frame deltas stay tiny. The
"transitions" below are score *peaks*, not cut points.

## Story / beat arc (from the contact sheet)

Alternating dark-charcoal ↔ light off-white backgrounds, sans-serif text, frequent two-tone
wording (one word solid, the next in grey):

1. (dark) "Built something brilliant?"
2. (light) "Luceostudio makes it look cinematic."
3. (light) "Cinematic" → "Cinematic visuals for technical brands"
4. (light) "AI-Powered"
5. (light) "Motion Graphics"
6. (light) "Launch films with product depth"
7. (dark) "Look as good as you built."
8. (light) "Luceostudio" (wordmark)
9. (light) "Luceostudio — Book your launch film today" (CTA)

## Transition timeline

Timestamps are the center of each scene-score peak cluster; type/motion read from
before/mid/after frame triplets straddling each.

| # | ~Time | Type | Motion (what moves, direction, ease) |
|---|------|------|--------------------------------------|
| T0 | 0.0–0.9 s | **Organic blob/lobe wipe-in** (opening) | Charcoal panel enters from the **right edge** as 2–3 stacked rounded-cap lobes (finger/pill shapes) that sweep **leftward** to flood the frame; "Built something brilliant?" resolves underneath with horizontal **motion blur** that settles. Ease-out, ~20 frames. |
| T1 | ~2.4–2.8 s | **Blob wipe + polarity flip** (dark→light) | Same rounded-lobe shape, now **light off-white**, grows from bottom-right and sweeps in; old dark text "Built so…" slides **off left** (motion-blurred) while "Luceostudio makes it look cinematic" fades up in place. Biggest peak in the video (score ~0.084). |
| T2 | ~7.0–7.3 s | **Cross-dissolve + fade-up text** (light→light) | No wipe (both scenes share light bg). New line "AI-Powered" simply **fades up from ~0 opacity** at center; nothing translates. Soft, slow. |
| T3 | ~8.6–8.9 s | **Staggered per-word fade-in** | "Motion Graphics": "Motion" reaches full dark first, "Graphics" still ghost-grey — words reveal **left→right** with a per-word delay (also drives the two-tone look). |
| T4 | ~13.9–14.1 s | **Center-out horizontal band wipe + polarity flip** (light→dark) | A thin dark **horizontal seam** appears mid-frame, then a charcoal band **expands vertically** (top & bottom edges push outward from center) to fill the frame; "Look as good…" reveals with staggered per-word fade. |
| T5 | ~17.2–17.7 s | **Vertical edge wipe + polarity flip** (dark→light) | Light off-white panel wipes across from the **right edge** to the left, leaving a thin dark strip on the far left mid-wipe; lands on "Luceostudio" wordmark. |
| T6 | ~18–20.5 s | **Delayed secondary-text reveal** (hold) | Wordmark holds; CTA subtitle "Book your launch film today" **fades in below** after a beat (delayed second line), then the video holds to end. |

## Overall motion language (4–6 bullets)

- **No hard cuts, ever.** Every beat boundary is a continuous animated transition. The whole 21 s
  reads as one uninterrupted flow. This is the defining trait to reproduce.
- **Pacing is calm/medium, not snappy.** Beats hold ~2–4 s each; transitions are ~0.5–0.8 s of
  smooth motion. Feel is **ease-out / ease-in-out**, NOT bouncy spring — closer to a smooth
  Apple-style glide than a kinetic-typography snap.
- **Polarity flipping is the rhythm device.** Backgrounds alternate dark charcoal ↔ light off-white,
  and most wipes carry that flip with them. The color change *is* the punctuation between beats.
- **Signature move = organic rounded-lobe "blob" wipe.** A soft mask made of 2–3 stacked
  pill/finger shapes with rounded caps sweeps in from a frame edge (usually right). This is Hera's
  fingerprint and the most recognizable element.
- **Text appears two ways:** (a) under a wipe, with horizontal **motion blur** that settles, or
  (b) on shared backgrounds, a **staggered per-word fade-up** (left→right). The two-tone wording
  (solid word + grey word) is a byproduct of the staggered reveal frozen at the holding frame.
- **Cards/panels barely exist** — there are no glass cards, UI mockups, or depth layers. It's pure
  full-frame typography + full-frame color masks. Layering/parallax: **none observed** (uncertain
  whether subtle scale drift exists; not visible at 1 fps sampling).

## Reusable transition recipes (named)

Distilled so we can re-author each (frame counts at 30 fps; treat as starting points, tune to taste):

1. **hera-blob-wipe** — soft mask of 2–3 stacked rounded-cap lobes sweeps in from the right edge to
   flood the frame; ~16–22f, ease-out. The signature move. Carry a bg-color flip with it.
2. **hera-blob-wipe-flip** — same blob wipe but the incoming panel is the *opposite* polarity
   (dark↔light); outgoing text slides off-screen left with motion blur as new text fades up in place.
3. **hera-band-expand** — a thin horizontal seam appears at vertical center, then a solid band grows
   top+bottom outward to fill frame; ~14–18f, ease-in-out; pairs with a polarity flip.
4. **hera-edge-wipe** — solid panel wipes straight across from one edge (here right→left) with a
   hard vertical leading edge; ~12–16f, linear-ish/ease-out; good for landing on a wordmark.
5. **hera-text-motionblur-settle** — text rides in under a wipe with horizontal motion blur, then
   blur decays to 0 over ~6–8f as it locks to final position. Pairs with recipes 1–4.
6. **hera-word-stagger-fade** — words fade up from 0 opacity one at a time, left→right, ~3–5f
   stagger per word, each ~8f fade. Produces the solid-word / grey-word two-tone if read mid-reveal.
7. **hera-ghost-fade-up** — single line cross-dissolves up from ~0 opacity at center on an unchanged
   background; ~12–18f, slow ease-in. Use when two consecutive beats share a bg color (no wipe).
8. **hera-delayed-subline** — after a wordmark/headline settles, a secondary CTA line fades in
   below it ~10–15f later; the delay makes the wordmark "earn" the tagline.
9. **hera-polarity-flip** (modifier, not standalone) — any wipe simultaneously swaps the global
   bg between charcoal (#6b6b66-ish) and off-white (#f0eee8-ish). Use as the through-line rhythm.

## Uncertainties

- Exact easing curves are inferred from 3-frame triplets, not per-frame — "ease-out vs ease-in-out"
  labels are best-guess (**uncertain**).
- The blob mask's exact lobe count/shape varies; "2–3 rounded-cap lobes" is approximate.
- Whether beats have subtle continuous scale/position drift while holding is **uncertain** (not
  resolvable at 1 fps; would need a 30 fps diff to confirm).
- Background hex values are eyeballed from compressed 720p frames, not sampled (**uncertain**).
