# Video Content Quality — Design Spec

**Date:** 2026-06-26
**Status:** Approved (design); pending implementation plan
**Repo:** `walk-studio-hosted` (the deploy source — pipeline edits land here or are ported)
**Scope:** Approach **A + B** (+ a cheap slice of C). Standard-quality builds.

---

## 1. Problem

Generated videos repeat themselves across slides and the on-screen text drifts from
the voiceover. Concrete evidence — YC run `8966e1df-e801-4ab5-b426-c7cb719fe876`
(`www.ycombinator.com`, 550B/ultra-paid, delivered 2026-06-26), 6 scenes:

- The subtitle *"Y Combinator created a new model for funding early stage startups"*
  appears verbatim on **scenes 0, 2, 3, AND 4**.
- Scenes 2–4 (feature cards) share the **same 4 bullets, just reordered**, and each
  scene's title is literally one of its own bullets.
- The bullets are scraped **nav/section labels** — "Knowledge & News", "In Founders'
  Words", "Be in the room with…" — not product value props.
- Scene 1 shows "Y Combinator" as both kicker and eyebrow.

## 2. Root cause (verified against the code)

The planner LLM **does not author slide copy**. Per `planner-prompt.md`, each scene it
emits is `{id, type, brief, model, duration_s, input_image}` plus a `voiceover.beats[]`
entry `{scene_id, text}`. **All visible copy is derived afterward by `style_fill.py`**
from (brief + VO beat + brand facts). The repetition comes from three derivation gaps:

1. **Repeated subtitle** — `_shape_explainer` (`style_fill.py:~2285`) derives an
   explainer-card subtitle from the **shared brand tagline** when the plan provides no
   explicit subtitle, with **no cross-scene dedup** on that field. Same tagline → same
   subtitle on every card. (The dedup machinery `_used_supporting`/`_used_headlines`
   exists but only guards the `apple-screenshot` shaper, not explainer cards.)
2. **Identical bullets** — `_shape_explainer` (`style_fill.py:~2310-2322`) sources
   bullets from `brand["features"]` and rotates the **same small list** by
   `_feature_index` across cards. With ~4 features and 3 cards, rotation produces heavy
   overlap by construction.
3. **Nav junk as features** — `brand_extract.py` scraped YC's nav/section labels as
   "features," which then became the bullets. Garbage-in.

The VO beat is **already threaded into `style_fill`** (as `data._text`, seeded from the
timeline/brief), and titles/headlines already distill from it via `_title_from_text()`
/ `_grounded_headline()`. So the fix extends that derivation to the secondary fields and
removes the repetition sources — not a rewrite.

## 3. Locked decisions

- **Slide ↔ VO = Reinforce.** Each slide's text is a distilled 2–5 word key phrase of
  *its own* VO beat. Eyes and ears say the same thing; the slide emphasizes the beat.
- **Value bar = Arc built from proof.** The VO is a tight 4-beat narrative (tension →
  what they do → proof → CTA) where every beat is anchored to a concrete proof point
  (number / named entity / real feature) from the page.
- **Feature card = key phrase + 1 detail.** Hero key phrase + ONE distinct supporting
  line derived from that scene's *own* beat. **No bullets.** Never the shared tagline.
- **Scope = A + B**, plus the cheap nav-label slice of C.

## 4. Design

### 4.1 Approach A — voice-first slide derivation (mostly `style_fill.py`)

- **Explainer-card shaper (`_shape_explainer`, `style_fill.py:2267`):**
  - **Title / hero line:** keep — already distills the key phrase from `data._text`
    (the scene's VO beat) via `_title_from_text()`. Ensure it always wins from the beat,
    not the tagline.
  - **Remove the bullet path** (`style_fill.py:~2310-2362`). Under "key phrase + 1
    detail" there are no bullets; delete the brand-feature rotation and the synthesized-
    from-VO bullet fallback. (Leaves the `ExplainerCard` renderer rendering 0 bullets —
    confirm the Remotion component degrades cleanly with an empty/absent `bullets`; if
    not, pass `bullets: []` and gate the list render on length.)
  - **Replace the subtitle (`style_fill.py:~2285-2296`):** instead of the shared brand
    tagline, derive **one distinct supporting line from the same beat** (the part of the
    beat not captured by the key phrase), run through the shared dedup list (4.1b).
- **Thread dedup state through explainer cards (4.1b):** `build_props`
  (`style_fill.py:~3540-3563`) already threads `_used_supporting` / `_used_headlines`
  into screenshot scenes. Thread the **same shared lists** into `_shape_explainer` so a
  card's hero line and supporting line are checked against everything already shown and
  re-derived (or dropped) on collision.
- **Hero-title & screenshot shapers:** largely unchanged (they already derive from the
  VO beat). Verify the shared dedup lists cover their secondary fields too (kicker vs
  eyebrow duplication seen on YC scene 1 → ensure kicker is dropped when it equals the
  eyebrow/wordmark already shown).

### 4.2 Approach B — content-quality guards

**B1 — Plan-time validator** (`validate_planner.py`, new
`validate_plan_content_quality(plan, company_facts) -> list[str]`, called from
`plan_job.py:~351` right after `validate_plan`):
- **Repetition:** flag any `voiceover.beats[i].text` that near-duplicates another beat
  (normalized token-set / Jaccard over a threshold).
- **Nav labels:** flag any beat/brief containing a known nav/footer label (matched
  against the nav-label set from 4.3).
- **Thin/bare beats:** flag beats below the word floor or that are just the wordmark.
- **Arc-from-proof:** require at least N beats (e.g. ≥2 of the non-title beats) to
  contain a concrete token — a digit, a `$`/`%`/unit, or a named entity from
  `company_facts`. Empty/abstract arcs fail.
- **Wiring:** extend the planner's existing repair-retry (`plan_job` /
  `_plan_with_nemotron`) to do **one** content re-plan when this trips, appending a
  "fix these specific issues" instruction. One extra free-brain call at most, only on
  failure. If still failing after the retry, log and proceed (B2 is the backstop).

**B2 — Render-time dedup backstop** (`style_fill.build_props`, `style_fill.py:~3486`):
After all scenes are shaped, run a **final deterministic pass over every on-screen
string across all scenes**. Any phrase that would appear on 2+ slides has its later
occurrences dropped or replaced from that scene's beat. This is the hard guarantee that
does not depend on the model — the analogue of the `normalizeTimeline` guard shipped
earlier today. Same for "slide phrase not grounded in its beat" → drop/replace.

### 4.3 Cheap slice of C — nav-label filter in extraction

`brand_extract.py`: when assembling `features`, **filter out obvious nav/footer labels**
(a small curated stop-set + heuristics: short title-case menu items, "News", "Blog",
"Careers", "Login", "Pricing" as bare nouns, etc.). Keeps the junk out of the VO, the
brand grid (`card-ui`), and any residual derivation — without a full extraction rebuild.
Export the nav-label set so B1 can reuse it.

## 5. Success criteria & verification (all $0)

1. **Unit tests** (same pattern as `normalizeTimeline`):
   - `validate_plan_content_quality` flags synthetic plans with a repeated beat, a
     nav-label beat, a thin beat, and a no-proof arc; passes a clean arc-from-proof plan.
   - The `build_props` render-time dedup pass: given scenes with a duplicated string,
     output has it on exactly one slide; clean input is unchanged (no-op).
   - `brand_extract` nav filter: nav labels in → filtered out; real features survive.
2. **Live YC re-generation** through the real `createBuild` path (super-free/mock, $0):
   re-run `www.ycombinator.com`, then assert via the validator on the resulting props:
   **zero cross-slide repeated phrases, zero nav labels, every slide phrase grounded in
   its beat.** Read the contact sheet and compare slide copy before/after.

**Definition of done:** the YC re-gen shows distinct, beat-grounded copy on every slide
with no repeated subtitle and no nav labels, and the unit tests pass + typecheck/lint
clean.

## 6. Out of scope

- Full Approach C (a structured "proof bank" extraction stage) — revisit only if, after
  A+B, the bottleneck is clearly "no real proof was available to build from."
- Premium-quality (cinematic) tier — this spec targets standard builds.
- The chat-editor / web app — unaffected.
- Re-architecting `style_fill.py` — changes stay surgical within the named shapers and
  `build_props`.

## 7. Risks & mitigations

- **`style_fill.py` is 3,881 lines.** Mitigation: changes confined to `_shape_explainer`
  + `build_props` threading + a new dedup pass; no broad refactor; lint/typecheck gate.
- **Empty-bullets rendering.** The `ExplainerCard` Remotion component may assume bullets
  exist. Mitigation: verify it degrades with `bullets: []`; gate the list render on
  length if needed (small Remotion edit).
- **Over-aggressive dedup** could strip a legitimately-shared short word. Mitigation:
  dedup on phrases (≥N chars / multi-word), not single tokens; prefer drop-or-rederive,
  never blank a hero line.
- **Content re-plan latency/cost.** One extra free-brain call only on failure; bounded
  to a single retry.
- **Deployed-worker drift.** Confirm the Railway worker builds from this branch so the
  changes actually ship (per the deploy mechanics in `HANDOFF-2026-06-26.md`).
