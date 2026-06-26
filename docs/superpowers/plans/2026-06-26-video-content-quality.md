# Video Content Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generated videos' on-screen copy a non-repetitive, beat-grounded distillation of the voiceover (the "reinforce" model), and guarantee no phrase repeats across slides.

**Architecture:** The planner authors only `brief` + per-scene `voiceover.beats`; `style_fill.py` derives all visible copy. We (A) make the explainer-card derive its one supporting line from its own VO beat instead of the shared brand tagline and drop bullets, (B) add a deterministic render-time cross-scene dedup backstop plus a plan-time content-quality validator, and (C) strengthen the existing nav-label filter so section headings don't enter as "features."

**Tech Stack:** Python 3 (no pytest — tests use `unittest`, run with `python3 -m unittest`), Remotion/React (TSX, render side — no change needed this plan). Pipeline lives in `walk-studio-hosted` (the deploy source).

**Spec:** `docs/superpowers/specs/2026-06-26-video-content-quality-design.md`

**Run all tests:** `cd ~/Desktop/Projects/Hackathons/walk-studio-hosted && python3 -m unittest tests.test_style_fill tests.test_brand_extract tests.test_plan_content_quality -v`

---

## File structure

| File | Change | Responsibility |
|------|--------|----------------|
| `style_fill.py` | Modify `_shape_explainer` (~2267); add `_dedupe_cross_scene_secondary` + call in `build_props` (~3583); thread dedup lists into `ARCH_EXPLAINER` (~3540) | Slide-copy derivation + render-time dedup backstop |
| `plan_schema.py` | Add `validate_plan_content_quality(plan, company_facts)` | Plan-time content-quality checks (runtime module imported by `plan_job`) |
| `plan_job.py` | Wire the validator after `validate_plan` (~351) + one content re-plan | Trigger a single corrective re-plan on content failure |
| `brand_extract.py` | Extend `_NAV_SECTION_EXACT` / `_is_nav_segment` (~773) | Keep section-heading phrases out of `features` |
| `tests/test_style_fill.py` | Add tests | A + B2 |
| `tests/test_plan_content_quality.py` | New | B1 |
| `tests/test_brand_extract.py` | Add tests | C |

> NOTE: The spec referenced `validate_planner.py` for the content validator. Corrected here: `validate_planner.py` is the offline eval harness; the runtime validator `plan_job` calls lives in `plan_schema.py` (`from plan_schema import validate_plan`). The new function goes in `plan_schema.py`.

---

## Task 1: Render-time cross-scene dedup backstop (B2)

The hard guarantee: after all scenes are shaped, no SECONDARY on-screen string (subtitle/kicker/eyebrow/supporting/punchWord/caption) and no bullet appears on two slides. Hero lines (title/headline) are left intact (blanking a hero is worse than a rare repeat). This is the analogue of the `normalizeTimeline` guard.

**Files:**
- Modify: `style_fill.py` (add helper near other module helpers, ~line 940; call it in `build_props` before the `return` at ~3583)
- Test: `tests/test_style_fill.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_style_fill.py`:

```python
class TestCrossSceneDedup(unittest.TestCase):
    def test_duplicate_subtitle_dropped_on_later_scene(self):
        scenes = [
            {"id": "a", "archetype": "ln-card",
             "data": {"title": "Join the batch", "subtitle": "A new model for funding startups."}},
            {"id": "b", "archetype": "ln-card",
             "data": {"title": "Read founders' words", "subtitle": "A new model for funding startups."}},
        ]
        out = style_fill._dedupe_cross_scene_secondary(scenes)
        self.assertEqual(out[0]["data"]["subtitle"], "A new model for funding startups.")
        self.assertEqual(out[1]["data"]["subtitle"], "")  # later duplicate dropped

    def test_hero_title_never_blanked_even_if_duplicated(self):
        scenes = [
            {"id": "a", "archetype": "ln-card", "data": {"title": "Same Title"}},
            {"id": "b", "archetype": "ln-card", "data": {"title": "Same Title"}},
        ]
        out = style_fill._dedupe_cross_scene_secondary(scenes)
        self.assertEqual(out[1]["data"]["title"], "Same Title")  # hero left intact

    def test_duplicate_bullets_removed_across_scenes(self):
        scenes = [
            {"id": "a", "archetype": "ln-card", "data": {"bullets": ["Fast payouts", "Fraud tools"]}},
            {"id": "b", "archetype": "ln-card", "data": {"bullets": ["Fraud tools", "Recurring billing"]}},
        ]
        out = style_fill._dedupe_cross_scene_secondary(scenes)
        self.assertEqual(out[1]["data"]["bullets"], ["Recurring billing"])  # shared bullet gone

    def test_short_shared_words_not_nuked(self):
        scenes = [
            {"id": "a", "archetype": "ln-card", "data": {"kicker": "YC"}},
            {"id": "b", "archetype": "ln-card", "data": {"kicker": "YC"}},
        ]
        out = style_fill._dedupe_cross_scene_secondary(scenes)
        # single short token (< 2 words) is not treated as a dedupable phrase
        self.assertEqual(out[1]["data"]["kicker"], "YC")

    def test_clean_input_unchanged(self):
        scenes = [
            {"id": "a", "archetype": "ln-card", "data": {"subtitle": "Accept payments worldwide."}},
            {"id": "b", "archetype": "ln-card", "data": {"subtitle": "Stop fraud before it starts."}},
        ]
        out = style_fill._dedupe_cross_scene_secondary(scenes)
        self.assertEqual(out[0]["data"]["subtitle"], "Accept payments worldwide.")
        self.assertEqual(out[1]["data"]["subtitle"], "Stop fraud before it starts.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_style_fill.TestCrossSceneDedup -v`
Expected: FAIL with `AttributeError: module 'style_fill' has no attribute '_dedupe_cross_scene_secondary'`

- [ ] **Step 3: Write minimal implementation**

Add to `style_fill.py` (near the other text helpers, e.g. after `_is_fragment_subtitle` ~line 960):

```python
# Secondary on-screen fields that must never repeat across scenes. Hero fields
# (title, headline) are deliberately EXCLUDED — blanking a hero line is worse than
# a rare repeat; the shapers + plan-time validator handle hero dedup upstream.
_DEDUPE_SECONDARY_FIELDS = ("subtitle", "kicker", "eyebrow", "supporting", "punchWord", "caption")


def _norm_phrase(s: str) -> str:
    """Lowercased, whitespace-collapsed, punctuation-trimmed key for dedup."""
    return " ".join((s or "").lower().split()).strip(" .!?·•|-—–")


def _dedupe_cross_scene_secondary(scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deterministic backstop: drop any SECONDARY string or bullet that already
    appeared (normalized) on an earlier scene. Only phrases of >= 2 words are
    treated as dedupable (so shared short tokens like a kicker 'YC' survive).
    Mutates + returns `scenes`."""
    seen: set = set()
    for sc in scenes:
        data = sc.get("data") or {}
        for field in _DEDUPE_SECONDARY_FIELDS:
            val = data.get(field)
            if not isinstance(val, str) or not val.strip():
                continue
            key = _norm_phrase(val)
            if len(key.split()) < 2:
                continue  # never dedup a single short token
            if key in seen:
                data[field] = ""
            else:
                seen.add(key)
        bullets = data.get("bullets")
        if isinstance(bullets, list):
            kept = []
            for b in bullets:
                if not isinstance(b, str) or not b.strip():
                    continue
                key = _norm_phrase(b)
                if key and key in seen:
                    continue
                if len(key.split()) >= 2:
                    seen.add(key)
                kept.append(b)
            data["bullets"] = kept
        sc["data"] = data
    return scenes
```

Then in `build_props`, change the final return (currently `style_fill.py:3583`) so the scenes pass through the backstop first:

```python
    scenes = _dedupe_cross_scene_secondary(scenes)
    return {
        "fps": timeline.get("fps", 30),
        "total_frames": timeline.get("total_frames", 0),
        "audio_path": timeline.get("audio_path"),
        "lang": timeline.get("lang", "en"),
        "theme": style.theme(brand),
        "scenes": scenes,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_style_fill.TestCrossSceneDedup -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the full style_fill suite (no regressions)**

Run: `python3 -m unittest tests.test_style_fill -v`
Expected: OK (existing 78 + 5 new)

- [ ] **Step 6: Commit**

```bash
git add style_fill.py tests/test_style_fill.py
git commit -m "feat(content): render-time cross-scene dedup backstop in build_props"
```

---

## Task 2: Explainer-card reinforce model — beat-derived subtitle, no bullets (A)

The feature card becomes "key phrase (title, from the beat) + ONE distinct detail (subtitle, from the beat via `_supporting_line`, deduped), no bullets." Thread the existing dedup lists into explainer scenes so the subtitle dedups across cards.

**Files:**
- Modify: `style_fill.py` `_shape_explainer` (~2285–2371) and `build_props` `ARCH_EXPLAINER` threading (~3540)
- Test: `tests/test_style_fill.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_style_fill.py`:

```python
class TestExplainerReinforce(unittest.TestCase):
    def _scene(self, sid, text, feature_index=0, used=None):
        return {
            "id": sid, "type": "motion_graphic", "brief": "",
            "data": {"_text": text, "_feature_index": feature_index,
                     "_used_supporting": used if used is not None else []},
        }

    def test_explainer_emits_no_bullets(self):
        brand = _brand()  # has real features
        out = style_fill._shape_explainer(
            self._scene("f1", "Accept payments worldwide with one integration."), brand)
        self.assertEqual(out["bullets"], [])

    def test_subtitle_comes_from_beat_not_shared_tagline(self):
        brand = _brand()
        beat = "Accept payments worldwide. Settle in 135 currencies with one integration."
        out = style_fill._shape_explainer(self._scene("f1", beat), brand)
        # subtitle is a distinct second-sentence detail, NOT the brand tagline
        self.assertNotEqual(out["subtitle"].strip().lower(),
                            (brand.get("tagline") or "").strip().lower())
        self.assertTrue(out["subtitle"] == "" or "currenc" in out["subtitle"].lower()
                        or out["subtitle"] != out["title"])

    def test_two_cards_get_distinct_subtitles_via_shared_used_list(self):
        brand = _brand()
        used = []
        a = style_fill._shape_explainer(
            self._scene("f1", "Accept payments. Settle in 135 currencies fast.", 0, used), brand)
        b = style_fill._shape_explainer(
            self._scene("f2", "Stop fraud. Block bad charges before they post.", 1, used), brand)
        if a["subtitle"] and b["subtitle"]:
            self.assertNotEqual(style_fill._norm_phrase(a["subtitle"]),
                                style_fill._norm_phrase(b["subtitle"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_style_fill.TestExplainerReinforce -v`
Expected: FAIL — `test_explainer_emits_no_bullets` fails (bullets currently populated from brand features).

- [ ] **Step 3: Implement — replace the subtitle + bullets block in `_shape_explainer`**

In `style_fill.py`, replace the subtitle derivation and the entire bullets block (current lines ~2285–2364) with:

```python
    # Subtitle = ONE distinct DETAIL drawn from THIS scene's own VO beat (the second
    # sentence the title didn't use), deduped across scenes via the shared used list —
    # NOT the shared brand tagline (which produced the repeated-subtitle bug). Empty is
    # fine: a card with just the key phrase reads clean ("reinforce" model).
    used_supporting = d.get("_used_supporting")
    subtitle = d.get("subtitle")
    if subtitle is None:
        subtitle = _supporting_line(title, d.get("_text") or "", brief, brand,
                                    used=used_supporting)
    if _is_fragment_subtitle(subtitle):
        subtitle = ""
    if subtitle and isinstance(used_supporting, list):
        key = subtitle.strip().lower()
        if key in {u.strip().lower() for u in used_supporting}:
            subtitle = ""
        else:
            used_supporting.append(subtitle)

    # Reinforce model: feature cards show the key phrase + one detail, NO bullets.
    bullets: List[str] = []

    out: Dict[str, Any] = {
        "kicker": _decode(d.get("kicker") or ""),
        "title": _decode(title),
        "subtitle": _decode(subtitle or ""),
        "bullets": bullets,
    }
    return out
```

(Leave the `title = (...)` derivation above unchanged — it already distills the key phrase from the beat.)

- [ ] **Step 4: Thread the dedup lists into explainer scenes in `build_props`**

In `style_fill.py` `build_props`, the `ARCH_EXPLAINER` branch (currently ~3540) only sets `_feature_index`. Replace it with:

```python
        if archetype == ARCH_EXPLAINER:
            d.setdefault("_feature_index", feature_counter)
            feature_counter += 1
            # Share the SAME cross-scene dedup list screenshots use, so each feature
            # card's beat-derived subtitle is DISTINCT across the set.
            d["_used_supporting"] = used_supporting
            d["_used_headlines"] = used_headlines
```

- [ ] **Step 5: Run tests**

Run: `python3 -m unittest tests.test_style_fill.TestExplainerReinforce tests.test_style_fill.TestCrossSceneDedup -v`
Expected: PASS. Then full suite: `python3 -m unittest tests.test_style_fill -v` → OK (fix any existing test that asserted explainer bullets; update it to expect `[]` and note the reinforce-model change in the commit).

- [ ] **Step 6: Commit**

```bash
git add style_fill.py tests/test_style_fill.py
git commit -m "feat(content): explainer cards = beat-derived deduped subtitle, no bullets (reinforce model)"
```

---

## Task 3: Confirm ExplainerCard renders cleanly with empty bullets

No code change expected — `ExplainerCard.tsx:305` already gates the bullet block on `bullets.length > 0` and `:287` gates the subtitle on `subText`. This task verifies the render side typechecks and the empty-bullets path is intentional.

**Files:**
- Verify: `studio/src/timeline/archetypes/ExplainerCard.tsx`

- [ ] **Step 1: Confirm the gates exist**

Run: `grep -n "bullets.length > 0\|subText ?" studio/src/timeline/archetypes/ExplainerCard.tsx`
Expected: both gates present (lines ~305 and ~287). If `bullets.length > 0` is NOT a guard, wrap the bullet `<div>` in `{bullets.length > 0 ? (...) : null}`.

- [ ] **Step 2: Typecheck the studio**

Run: `cd studio && npx tsc --noEmit 2>&1 | tail -5; cd ..`
Expected: exit 0 (no new type errors).

- [ ] **Step 3: Commit (only if a guard was added)**

```bash
git add studio/src/timeline/archetypes/ExplainerCard.tsx
git commit -m "fix(render): guard explainer bullet block on non-empty bullets"
```

---

## Task 4: Plan-time content-quality validator (B1, pure function)

A deterministic checker over a plan's `voiceover.beats`: flags repeated beats, nav-label content, thin/bare beats, and a no-proof arc. Returns a list of issue strings (empty = clean).

**Files:**
- Modify: `plan_schema.py` (add `validate_plan_content_quality`)
- Test: `tests/test_plan_content_quality.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_plan_content_quality.py`:

```python
import unittest
import plan_schema


def _plan(beats):
    return {
        "job": {"company_url": "https://x.com", "goal": "g", "target_duration_s": 30},
        "scenes": [{"id": b["scene_id"], "type": "motion_graphic"} for b in beats],
        "voiceover": {"voice": "Adam", "beats": beats},
    }


class TestContentQuality(unittest.TestCase):
    def test_flags_repeated_beat(self):
        p = _plan([
            {"scene_id": "a", "text": "Y Combinator created a new model for funding startups."},
            {"scene_id": "b", "text": "Y Combinator created a new model for funding startups."},
        ])
        issues = plan_schema.validate_plan_content_quality(p, {})
        self.assertTrue(any("repeat" in i.lower() for i in issues))

    def test_flags_nav_label_beat(self):
        p = _plan([
            {"scene_id": "a", "text": "Stripe powers online payments for millions of businesses."},
            {"scene_id": "b", "text": "Knowledge & News"},
        ])
        issues = plan_schema.validate_plan_content_quality(p, {"nav_labels": ["knowledge & news"]})
        self.assertTrue(any("nav" in i.lower() for i in issues))

    def test_flags_thin_beat(self):
        p = _plan([{"scene_id": "a", "text": "Stripe."}])
        issues = plan_schema.validate_plan_content_quality(p, {"wordmark": "Stripe"})
        self.assertTrue(any("thin" in i.lower() or "short" in i.lower() for i in issues))

    def test_flags_no_proof_arc(self):
        p = _plan([
            {"scene_id": "a", "text": "We make powerful seamless innovative software for everyone."},
            {"scene_id": "b", "text": "It is next generation and revolutionary and great to use."},
        ])
        issues = plan_schema.validate_plan_content_quality(p, {})
        self.assertTrue(any("proof" in i.lower() for i in issues))

    def test_clean_arc_passes(self):
        p = _plan([
            {"scene_id": "a", "text": "Stripe powers payments for millions of businesses worldwide."},
            {"scene_id": "b", "text": "Accept cards and wallets in 135 currencies with one integration."},
            {"scene_id": "c", "text": "Block fraud automatically and settle funds in two days."},
            {"scene_id": "d", "text": "Start accepting payments today at stripe.com."},
        ])
        issues = plan_schema.validate_plan_content_quality(p, {"wordmark": "Stripe"})
        self.assertEqual(issues, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_plan_content_quality -v`
Expected: FAIL — `AttributeError: module 'plan_schema' has no attribute 'validate_plan_content_quality'`

- [ ] **Step 3: Implement in `plan_schema.py`**

Add at the end of `plan_schema.py`:

```python
import re as _re

# Generic buzzwords that signal an abstract, proof-free arc.
_BUZZWORDS = {
    "powerful", "seamless", "innovative", "revolutionary", "revolutionize",
    "next generation", "next-generation", "cutting edge", "cutting-edge",
    "world class", "world-class", "game changing", "game-changing", "robust",
    "synergy", "best in class", "best-in-class",
}


def _norm(s):
    return " ".join((s or "").lower().split()).strip(" .!?·•|-—–")


def _has_proof_token(text, facts):
    """A beat earns 'proof' if it carries a number/unit, or names a real entity
    from company facts (wordmark / a feature label)."""
    low = (text or "").lower()
    if _re.search(r"\d", low) or "%" in low or "$" in low:
        return True
    wm = _norm(facts.get("wordmark", "")) if facts else ""
    if wm and wm in low:
        # a bare wordmark-only line is not proof; require some other content too
        if len(low.split()) > 2:
            return True
    for f in (facts or {}).get("features", []) or []:
        label = _norm(f.get("title") if isinstance(f, dict) else f)
        if label and len(label.split()) >= 2 and label in low:
            return True
    return False


def validate_plan_content_quality(plan, company_facts):
    """Deterministic content-quality checks over voiceover.beats. Returns a list of
    human-readable issue strings (empty = clean). Advisory: callers may trigger ONE
    corrective re-plan; the render-time backstop guarantees no cross-scene repeats
    regardless."""
    facts = company_facts or {}
    problems = []
    beats = ((plan.get("voiceover") or {}).get("beats")) or []
    nav_labels = {_norm(x) for x in (facts.get("nav_labels") or [])}

    seen = {}
    proof_beats = 0
    content_beats = 0
    for i, b in enumerate(beats):
        text = (b.get("text") or "").strip()
        norm = _norm(text)
        if not norm:
            continue
        content_beats += 1
        # 1. Repetition (exact normalized OR high token-set overlap).
        for j, prev in seen.items():
            inter = set(norm.split()) & set(prev.split())
            union = set(norm.split()) | set(prev.split())
            if norm == prev or (union and len(inter) / len(union) >= 0.7):
                problems.append(f"beat[{i}] repeats beat[{j}]: {text!r}")
                break
        seen[i] = norm
        # 2. Nav-label content.
        if norm in nav_labels:
            problems.append(f"beat[{i}] is a nav/section label, not content: {text!r}")
        # 3. Thin / bare beat (word floor 4; bare wordmark).
        wm = _norm(facts.get("wordmark", ""))
        if len(norm.split()) < 4 or (wm and norm == wm):
            problems.append(f"beat[{i}] is too thin/short: {text!r}")
        # 4. proof accounting
        if _has_proof_token(text, facts):
            proof_beats += 1

    # 4. Arc-from-proof: at least 2 content beats (or all, if fewer) must carry proof.
    need = min(2, content_beats)
    if content_beats and proof_beats < need:
        problems.append(
            f"arc lacks proof: only {proof_beats}/{content_beats} beats carry a concrete "
            f"number/named-entity (need >= {need})")
    return problems
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_plan_content_quality -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add plan_schema.py tests/test_plan_content_quality.py
git commit -m "feat(content): plan-time content-quality validator (repeat/nav/thin/arc-from-proof)"
```

---

## Task 5: Wire the content validator into plan_job (one corrective re-plan)

Call `validate_plan_content_quality` after the schema check; when it trips on an LLM plan, attempt ONE re-plan with the issues appended as corrective guidance, then proceed regardless (the render backstop is the guarantee). Wiring is conservative: it only re-plans LLM plans, never loops.

**Files:**
- Modify: `plan_job.py` (~351, after `problems = validate_plan(plan)`)
- Test: `tests/test_plan_content_quality.py` (add a wiring test with a stubbed re-plan)

- [ ] **Step 1: Add the import + a small helper call site**

In `plan_job.py`, near the top imports (line ~17, beside `from plan_schema import validate_plan`):

```python
from plan_schema import validate_plan, validate_plan_content_quality
```

After the schema-check/fallback block (immediately after the existing `if problems:` block that ends at ~366, before the `plan["_planner"] = {` stamp at ~372), insert:

```python
    # CONTENT-QUALITY GATE (advisory + ONE corrective re-plan). Only LLM plans are
    # retried; template plans and a second failure fall through (the render-time
    # cross-scene dedup backstop guarantees no repeats regardless).
    content_problems = validate_plan_content_quality(plan, company_facts or {})
    if content_problems and plan_source == "llm" and not getattr(_plan_with_nemotron, "_no_retry", False):
        print("[planner] content-quality issues -> one corrective re-plan: %s"
              % "; ".join(content_problems), file=sys.stderr)
        fix = ("Your previous plan had these content problems: "
               + "; ".join(content_problems)
               + ". Rewrite the voiceover beats so each is distinct, names a concrete "
                 "proof point (a real number or named feature), and contains no nav/section "
                 "labels. Keep the same scene ids, types, and durations.")
        retry = _plan_with_nemotron(company_url, goal, target_duration_s, style, quality,
                                    brain, company_facts, meta=planner_meta, extra_user=fix)
        if retry is not None:
            retry_problems = validate_plan(retry)
            if not retry_problems:
                plan = retry
                print("[planner] corrective re-plan accepted", file=sys.stderr)
            else:
                print("[planner] corrective re-plan still invalid -> keeping original",
                      file=sys.stderr)
    elif content_problems:
        print("[planner] content-quality issues (advisory, not retried): %s"
              % "; ".join(content_problems), file=sys.stderr)
```

> Confirm `_plan_with_nemotron` accepts an `extra_user` (or equivalent) kwarg to append corrective guidance. If it does not, add an optional `extra_user: str = ""` parameter that, when present, is appended to the USER prompt content. Read its definition (`plan_job.py` ~264) before editing.

- [ ] **Step 2: Write a wiring test (stub the re-plan)**

Add to `tests/test_plan_content_quality.py`:

```python
class TestContentReplanWiring(unittest.TestCase):
    def test_validator_is_importable_from_plan_job(self):
        import plan_job
        self.assertTrue(hasattr(plan_job, "validate_plan_content_quality"))
```

- [ ] **Step 3: Run tests**

Run: `python3 -m unittest tests.test_plan_content_quality -v`
Expected: PASS. Sanity-import: `python3 -c "import plan_job"` → no error.

- [ ] **Step 4: Commit**

```bash
git add plan_job.py tests/test_plan_content_quality.py
git commit -m "feat(content): wire content-quality gate into plan_job with one corrective re-plan"
```

---

## Task 6: Strengthen the nav/section-label filter (C-slice)

`brand_extract._is_ui_label` already filters nav chrome but missed phrase section-headings like "Knowledge & News", "In Founders' Words", "Be in the room with…". Extend the detection and expose the nav-label set for the validator.

**Files:**
- Modify: `brand_extract.py` (`_NAV_SECTION_EXACT` and/or `_is_nav_segment` ~773)
- Test: `tests/test_brand_extract.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_brand_extract.py`:

```python
class TestNavSectionFilter(unittest.TestCase):
    def test_section_heading_phrases_are_ui_labels(self):
        for label in ["Knowledge & News", "In Founders' Words", "Be in the room with"]:
            self.assertTrue(brand_extract._is_ui_label(label), f"{label!r} should be nav chrome")

    def test_real_feature_is_not_a_ui_label(self):
        for feat in ["Recurring billing", "Built-in fraud protection", "Instant payouts"]:
            self.assertFalse(brand_extract._is_ui_label(feat), f"{feat!r} is a real feature")

    def test_features_drop_nav_sections(self):
        # exercise the cleaner: nav section headings must not survive into features
        data = {"features": [
            {"title": "Knowledge & News", "sub": ""},
            {"title": "Recurring billing", "sub": ""},
            {"title": "In Founders' Words", "sub": ""},
        ]}
        out = brand_extract._normalize_payload(data) if hasattr(brand_extract, "_normalize_payload") else None
        # If the normalizer name differs, assert via _is_ui_label directly (above).
        if out is not None:
            labels = [f["title"] for f in out.get("features", [])]
            self.assertIn("Recurring billing", labels)
            self.assertNotIn("Knowledge & News", labels)
```

> Before running, confirm the normalizer function name that contains the `feats = data.get("features")` cleaner (around `brand_extract.py:493`). Use that name in `test_features_drop_nav_sections`; if it is not directly callable, keep only the first two tests (the `_is_ui_label` unit tests), which fully cover the fix.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_brand_extract.TestNavSectionFilter -v`
Expected: FAIL on `test_section_heading_phrases_are_ui_labels` (these phrases currently pass through).

- [ ] **Step 3: Implement — extend the nav detection**

Read `brand_extract.py` around the `_NAV_SECTION_EXACT` / `_UI_LABEL_SUBSTR` definitions (search: `grep -n "_NAV_SECTION_EXACT\|_UI_LABEL_SUBSTR\|_NAV_SINGLE_WORDS" brand_extract.py`). Add a section-heading heuristic to `_is_nav_segment` (after its existing checks, before `return False`):

```python
    # Section-heading phrases that are site chrome, not product value props:
    #  - "<X> & <Y>" two-noun section labels ("Knowledge & News", "Press & Media")
    #  - possessive editorial sections ("In Founders' Words", "In Their Words")
    #  - directive nav blurbs ("Be in the room with ...", "Join the conversation")
    if _re.search(r"^\w+\s*&\s*\w+$", low):
        return True
    if low.startswith("in ") and ("words" in low or "'s" in low or "’s" in low):
        return True
    if low.startswith(("be in ", "join the ", "explore the ", "discover ")):
        return True
    return False
```

(Confirm `re` is imported in `brand_extract.py` as `re`; the snippet uses `_re` — adjust to the module's actual alias, which is plain `re` per existing `re.split` usage at line 764, so use `re.search`.)

Also expose the matched labels for the validator: ensure `extract_brand`'s returned theme (or `company_facts`) can carry a `nav_labels` list of strings that were filtered out, OR document that `validate_plan_content_quality` receives `nav_labels` from the caller. Minimum viable: the two `_is_ui_label` unit tests passing is the fix; the `nav_labels` plumbing is optional polish.

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest tests.test_brand_extract.TestNavSectionFilter -v`
Expected: PASS (real features still pass `_is_ui_label == False`; section phrases now `True`).
Then: `python3 -m unittest tests.test_brand_extract -v` → OK (no regressions).

- [ ] **Step 5: Commit**

```bash
git add brand_extract.py tests/test_brand_extract.py
git commit -m "feat(extract): filter section-heading phrases from brand features"
```

---

## Task 7: Integration verification — regenerate the YC video ($0)

Prove the fix on the original failure. Regenerate `www.ycombinator.com` through the real backend (super-free/mock = $0) and assert the props show distinct, beat-grounded copy with no repeats or nav labels.

**Files:**
- Use: `web/e2e-smoke.mjs` as the pattern; a one-off `web/_verify-content.mjs` (kept or removed)

- [ ] **Step 1: Deploy the worker with the changes**

The Railway worker builds from this branch. Run: `cd ~/Desktop/Projects/Hackathons/walk-studio-hosted && railway up --service walk-studio-hosted`, then watch `railway deployment list` until the new deploy is `SUCCESS` (per `HANDOFF-2026-06-26.md` deploy mechanics).

- [ ] **Step 2: Queue a YC build ($0) and pull its props**

Adapt `web/e2e-smoke.mjs` (or `web/_verify-content.mjs`): insert a `runs` row with `company_url='https://www.ycombinator.com'`, `brain='super-free'`, `mode='mock'`, `quality='standard'`; poll to `delivered`; then read `runs.props` for the run.

Run: `cd web && node _verify-content.mjs`
Expected: terminal status `delivered`.

- [ ] **Step 3: Assert content quality on the resulting props**

In the same script, after fetching props, assert:
- No `subtitle` string appears on more than one scene (the original bug).
- No explainer/feature scene has non-empty `bullets`.
- No on-screen string equals a known nav label ("Knowledge & News", "In Founders' Words", "Be in the room with").
- Print each scene's `{title, subtitle}` for an eyeball check.

Expected: zero repeated subtitles, zero bullets on feature cards, zero nav labels.

- [ ] **Step 4: Read the rendered video scene-by-scene**

Download the delivered mp4, build a contact sheet (`ffmpeg -i IN -vf "fps=2,scale=320:-1,tile=6x11" -frames:v 1 sheet.png`), and read it: each feature card should show a distinct key phrase + at most one distinct detail line, no repeated subtitle, no nav fragments. Compare against the original YC run `8966e1df`.

- [ ] **Step 5: Clean up + commit the verification harness (optional)**

```bash
git add web/_verify-content.mjs
git commit -m "test(content): YC re-gen content-quality verification harness"
```

---

## Definition of done

- `python3 -m unittest tests.test_style_fill tests.test_brand_extract tests.test_plan_content_quality -v` → OK.
- `studio` typecheck clean.
- YC re-gen shows distinct, beat-grounded copy on every slide: no repeated subtitle, no feature-card bullets, no nav labels — confirmed in props AND in the contact sheet.
