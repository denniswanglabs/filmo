# Filmo Curated Pattern Library + Lookbook — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Filmo's scene-treatment system into a legible, curated **pattern library** (catalog-driven selection + ~4 new patterns + patterns harvested from Luceo Studio films) and make the curation visible on the landing page — the anti-slop moat.

**Architecture:** One `patterns.catalog.json` is the source of truth, read by both the Python **assembler** (`style_fill._assign_treatment_from_filled_copy`, which picks each scene's pattern from real filled data, honesty-guarded) and the **landing Lookbook** (renders the catalog through the real archetypes). New patterns are React/Remotion archetypes mirrored across the `studio/` (render) and `web/` (editor + landing) copies, exactly as the existing treatments are.

**Tech Stack:** Python 3.11 (pipeline + `unittest` tests, run via `python3 -m unittest`), React/TypeScript + Remotion (archetypes), Next.js (web landing), Vercel (web deploy), Railway (worker deploy).

**Reference files (read before starting):**
- `style_fill.py:2292-2460` — `_mine_stat_from_title`, `_assign_treatment_from_filled_copy` (the assembler).
- `studio/src/timeline/archetypes/ExplainerCard.tsx` — all treatment archetypes (TreatmentSplitStat ~603, TreatmentSplitMosaic ~448) + the `treatment` switch ~1428.
- `web/app/runs/[id]/edit/_composition/archetypes/ExplainerCard.tsx` — the mirror copy (keep in lockstep).
- `studio/src/timeline/types.ts:71-89` — the `treatment` enum + `featureEntities`/`entityLogos`.
- `tests/test_style_fill.py` — the `unittest` convention (hand-built brand+plan+alignment → `run_pipeline(do_align=False)` → assert treatments).
- Spec: `docs/superpowers/specs/2026-06-27-filmo-curated-pattern-library-design.md`.

**Run tests:** `python3 -m unittest tests.test_patterns -v` (new file) and `python3 -m unittest tests.test_style_fill -v` (regression).

---

## Task 1: Pattern catalog — single source of truth (M1)

**Files:**
- Create: `studio/src/timeline/patterns.catalog.json`
- Create: `patterns_catalog.py` (repo root — Python loader/validator, importable by `style_fill`)
- Create: `tests/test_patterns.py`

- [ ] **Step 1: Write `patterns.catalog.json` with the 7 existing patterns.** Each entry: `id`, `name`, `purpose`, `whenToUse`, `dataContract` (list of `scene.data` fields), `exampleProps` (a self-contained sample), `harvestedFrom` (null for now).

```json
{
  "version": 1,
  "patterns": [
    { "id": "split-stat", "name": "Split Stat", "purpose": "One hero number, text-left / number+bars-right.", "whenToUse": "Filled title carries exactly one real impressive number.", "dataContract": ["title", "stat.value"], "exampleProps": { "treatment": "split-stat", "kicker": "Y COMBINATOR", "title": "Companies funded", "stat": { "value": "5,000+", "label": "" } }, "harvestedFrom": null },
    { "id": "split-mosaic", "name": "Split Mosaic", "purpose": "Text-left / real-logo entity grid right.", "whenToUse": "3+ real named entities (companies/products/customers).", "dataContract": ["title", "featureEntities"], "exampleProps": { "treatment": "split-mosaic", "kicker": "Y COMBINATOR", "title": "Airbnb, Stripe, Dropbox, DoorDash, Coinbase, Reddit", "featureEntities": ["Airbnb","Stripe","Dropbox","DoorDash","Coinbase","Reddit"] }, "harvestedFrom": null },
    { "id": "big-number", "name": "Big Number", "purpose": "A single dominant number, centered.", "whenToUse": "Title is essentially just a number with no descriptor.", "dataContract": ["stat.value"], "exampleProps": { "treatment": "big-number", "kicker": "SCALE", "title": "$800B+", "stat": { "value": "$800B+", "label": "combined valuation" } }, "harvestedFrom": null },
    { "id": "icon-stat", "name": "Icon Stat", "purpose": "Curated icon + punchy stat headline.", "whenToUse": "A real stat plus a curated icon and a short headline.", "dataContract": ["icon", "title", "stat.value"], "exampleProps": { "treatment": "icon-stat", "icon": "bolt", "title": "Ships in 24 hours", "stat": { "value": "24h", "label": "turnaround" } }, "harvestedFrom": null },
    { "id": "icon-headline", "name": "Icon Headline", "purpose": "Centered icon + headline. The honest floor (fills white space when no data).", "whenToUse": "No real stat or entity list available — the honest fallback.", "dataContract": ["title"], "exampleProps": { "treatment": "icon-headline", "icon": "spark", "title": "Be in the room with top investors" }, "harvestedFrom": null },
    { "id": "logo-wall", "name": "Logo Wall", "purpose": "Centered header over a large branded logo/entity grid.", "whenToUse": "4+ real named entities and the scene is a dedicated customer/portfolio wall.", "dataContract": ["title", "featureEntities"], "exampleProps": { "treatment": "logo-wall", "title": "Trusted by", "featureEntities": ["Amazon","Google","Shopify","Lyft","Instacart","Slack","Figma","Notion"] }, "harvestedFrom": null },
    { "id": "feature-list", "name": "Feature List", "purpose": "A vertical list of check/dot rows.", "whenToUse": "3+ short feature/benefit lines (entities or bullet subtitle).", "dataContract": ["title", "featureEntities"], "exampleProps": { "treatment": "feature-list", "title": "Everything included", "featureEntities": ["Unlimited renders","Brand kit","Stripe payments","Editor"] }, "harvestedFrom": null }
  ]
}
```

- [ ] **Step 2: Write `patterns_catalog.py` — load + validate.**

```python
"""Single source of truth for Filmo's curated scene-pattern library.
Read by the assembler (style_fill) AND the landing Lookbook (via the JSON)."""
import json
import os

_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "studio", "src", "timeline", "patterns.catalog.json")
_REQUIRED = ("id", "name", "purpose", "whenToUse", "dataContract", "exampleProps")


def load_catalog(path=None):
    """Return the list of pattern dicts. Raises ValueError on a malformed catalog."""
    with open(path or _CATALOG_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    pats = data.get("patterns")
    if not isinstance(pats, list) or not pats:
        raise ValueError("catalog has no patterns")
    seen = set()
    for p in pats:
        for k in _REQUIRED:
            if k not in p:
                raise ValueError("pattern %r missing %r" % (p.get("id"), k))
        if p["id"] in seen:
            raise ValueError("duplicate pattern id %r" % p["id"])
        seen.add(p["id"])
    return pats


def pattern_ids(path=None):
    return [p["id"] for p in load_catalog(path)]
```

- [ ] **Step 3: Write the failing test in `tests/test_patterns.py`.**

```python
"""Deterministic ($0) tests for the curated pattern catalog + assembler selection."""
import unittest
import patterns_catalog


class TestCatalog(unittest.TestCase):
    def test_loads_seven_seed_patterns(self):
        ids = patterns_catalog.pattern_ids()
        for pid in ("split-stat", "split-mosaic", "big-number", "icon-stat",
                    "icon-headline", "logo-wall", "feature-list"):
            self.assertIn(pid, ids)

    def test_every_pattern_has_required_fields_and_example(self):
        for p in patterns_catalog.load_catalog():
            self.assertTrue(p["exampleProps"].get("treatment") == p["id"],
                            "exampleProps.treatment must equal id for %s" % p["id"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run — expect PASS.**

Run: `python3 -m unittest tests.test_patterns -v`
Expected: 2 tests PASS. (If FAIL, fix the catalog JSON so every `exampleProps.treatment` equals its `id`.)

- [ ] **Step 5: Commit.**

```bash
git add studio/src/timeline/patterns.catalog.json patterns_catalog.py tests/test_patterns.py
git commit -m "feat(patterns): pattern catalog source-of-truth (7 seed patterns) + loader + tests"
```

---

## Task 2: Assembler records the chosen pattern + reason (M2)

Make selection legible without changing today's outcomes. `_assign_treatment_from_filled_copy` already picks the treatment; add a `patternReason` and assert parity.

**Files:**
- Modify: `style_fill.py` (`_assign_treatment_from_filled_copy`, ~2316-2460)
- Modify: `tests/test_patterns.py`

- [ ] **Step 1: Add the failing test.** Append to `tests/test_patterns.py`:

```python
import style_fill


class TestAssemblerLegibility(unittest.TestCase):
    def _shape(self, data):
        out = dict(data)
        scene = {"data": dict(data)}
        style_fill._assign_treatment_from_filled_copy(out, scene, {"wordmark": "YC"})
        return out

    def test_split_stat_records_reason(self):
        out = self._shape({"title": "Companies funded 5,000+"})
        self.assertEqual(out.get("treatment"), "split-stat")
        self.assertTrue(out.get("patternReason"))
        self.assertIn("5,000+", out["patternReason"])

    def test_no_data_degrades_to_icon_headline_with_reason(self):
        out = self._shape({"title": "Be in the room"})
        self.assertEqual(out.get("treatment"), "icon-headline")
        self.assertIn("no real", out.get("patternReason", "").lower())
```

- [ ] **Step 2: Run — expect FAIL** (`patternReason` not set).

Run: `python3 -m unittest tests.test_patterns.TestAssemblerLegibility -v`
Expected: FAIL (KeyError/None on `patternReason`).

- [ ] **Step 3: Implement `patternReason`.** In `_assign_treatment_from_filled_copy`, at each point `treatment` is finalized (the `split-stat`/`split-mosaic`/`big-number`/`icon-headline` branches ~2405-2440), set `out["patternReason"]`. Examples: split-stat → `"split-stat: real stat %s" % use_stat["value"]`; split-mosaic → `"split-mosaic: %d real entities" % len(ents)`; icon-headline → `"icon-headline: no real stat/entities (honest floor)"`. Set it wherever `out["treatment"]` is assigned.

- [ ] **Step 4: Run — expect PASS.**

Run: `python3 -m unittest tests.test_patterns -v`
Expected: all PASS.

- [ ] **Step 5: Regression — existing style_fill tests + a live brand check.**

Run: `python3 -m unittest tests.test_style_fill -v` → expect PASS (no treatment changes).
Run: `set -a; source ~/.hermes/.env; set +a; python3 loop_measure.py loop2-iter3 2>&1 | grep treatment=` → expect the SAME treatments as before (split-mosaic, split-stat, icon-headline, split-stat).

- [ ] **Step 6: Commit.**

```bash
git add style_fill.py tests/test_patterns.py
git commit -m "feat(patterns): assembler records patternReason (legible curation, no outcome change)"
```

---

## Task 3: Add the 4 new patterns (M3)

Do these as four sub-tasks. Each follows the SAME shape; the per-pattern specifics (data contract, catalog entry, selection rule, layout) are given in full. The Remotion archetype mirrors an existing sibling's scaffold (prop threading, cue/animation wiring) — copy the nearest sibling listed and change only the marked body.

### Task 3a: `metric-row` (a strip of 3–4 small stats) — sibling: TreatmentSplitStat

**Files:** Modify `studio/src/timeline/types.ts`, `web/app/runs/[id]/edit/_composition/types.ts`, `studio/src/timeline/archetypes/ExplainerCard.tsx`, `web/app/runs/[id]/edit/_composition/archetypes/ExplainerCard.tsx`, `style_fill.py`, `studio/src/timeline/patterns.catalog.json`, `tests/test_patterns.py`.

- [ ] **Step 1: types.ts (BOTH copies)** — add to the `treatment` union `| "metric-row"` and add the field:

```ts
// metric-row: 3-4 small real stats shown as a horizontal strip.
metrics?: Array<{ value: string; label: string }>;
```

- [ ] **Step 2: Selection rule + test (TDD).** Add to `tests/test_patterns.py`:

```python
class TestMetricRow(unittest.TestCase):
    def _shape(self, data):
        out = dict(data); scene = {"data": dict(data)}
        style_fill._assign_treatment_from_filled_copy(out, scene, {"wordmark": "X"})
        return out

    def test_three_real_metrics_select_metric_row(self):
        out = self._shape({"title": "By the numbers",
                           "metrics": [{"value": "150M+", "label": "users"},
                                       {"value": "$9.9B", "label": "revenue"},
                                       {"value": "7M+", "label": "listings"}]})
        self.assertEqual(out.get("treatment"), "metric-row")

    def test_fewer_than_three_metrics_does_not_select_metric_row(self):
        out = self._shape({"title": "Just one", "metrics": [{"value": "1", "label": "x"}]})
        self.assertNotEqual(out.get("treatment"), "metric-row")
```

Run: `python3 -m unittest tests.test_patterns.TestMetricRow -v` → expect FAIL.

- [ ] **Step 3: Implement the rule** in `_assign_treatment_from_filled_copy`, BEFORE the split-stat branch: if `d.get("metrics")` has ≥3 entries each with a real numeric `value` (reuse `_TITLE_STAT_RE.search(value)` to confirm a real number), set `treatment = "metric-row"`, keep `out["metrics"]` = the validated list, `out["patternReason"] = "metric-row: %d real metrics" % n`. Honesty: drop any metric whose value has no number; if <3 remain, do NOT select metric-row.

Run: `python3 -m unittest tests.test_patterns.TestMetricRow -v` → expect PASS.

- [ ] **Step 4: Archetype (BOTH copies).** Add `TreatmentMetricRow` mirroring `TreatmentSplitStat` (copy its prop type + the kicker/title/cue scaffold). Replace the right-panel body with a horizontal flex row of up to 4 cards; each card: `theme.bgCard` bg, `theme.border`, value in `theme.accent` (fontSize 56, fontWeight 900), label `theme.text` (fontSize 16). Stagger each card in with `ease(frame, statAt + i*6, ..., 0, 1)`. Add the `treatment === "metric-row"` case to the switch (~1428 studio / equivalent web). Web copy uses the same JSX (no remote assets, so no `resolveSrc` needed here).

- [ ] **Step 5: Catalog entry.** Add to `patterns.catalog.json`:

```json
{ "id": "metric-row", "name": "Metric Row", "purpose": "A strip of 3-4 real stats.", "whenToUse": "A beat carries 3+ real numbers.", "dataContract": ["metrics"], "exampleProps": { "treatment": "metric-row", "kicker": "AIRBNB", "title": "By the numbers", "metrics": [ { "value": "150M+", "label": "users" }, { "value": "7M+", "label": "listings" }, { "value": "$9.9B", "label": "revenue" } ] }, "harvestedFrom": null }
```

- [ ] **Step 6: Render-verify.** Build a one-scene props file from the catalog `exampleProps` and render it:

```bash
python3 -c "import json,patterns_catalog as c; p=[x for x in c.load_catalog() if x['id']=='metric-row'][0]; open('runs/_pat/props.json','w').write(json.dumps({'scenes':[{'type':'explainer-card','durationInFrames':150,'data':p['exampleProps']}],'theme':json.load(open('runs/loop2-iter3/props.json'))['theme'],'fps':30,'width':1280,'height':720,'audio_path':'','voiceover':[]}))" ; mkdir -p runs/_pat
(cd studio && PATH="$PWD/node_modules/.bin:$PATH" remotion render src/index.ts Timeline ../runs/_pat/metric-row.mp4 --props=../runs/_pat/props.json --frames=0-120 --codec=h264 2>&1 | tail -1)
ffmpeg -y -ss 3 -i runs/_pat/metric-row.mp4 -frames:v 1 runs/_pat/metric-row.png 2>/dev/null
```
Read `runs/_pat/metric-row.png` — expect 3 stat cards in a row, light panel, accent numbers. Fix layout until clean. (Catalog `exampleProps` doubles as the render fixture AND the lookbook example — DRY.)

- [ ] **Step 7: Commit.**

```bash
git add studio/src/timeline/types.ts "web/app/runs/[id]/edit/_composition/types.ts" studio/src/timeline/archetypes/ExplainerCard.tsx "web/app/runs/[id]/edit/_composition/archetypes/ExplainerCard.tsx" style_fill.py studio/src/timeline/patterns.catalog.json tests/test_patterns.py
git commit -m "feat(patterns): metric-row pattern (3-4 real stats), honesty-guarded + tested"
```

### Task 3b: `device-frame` (product screenshot in a clean frame) — sibling: AppleScreenshot / TreatmentSplitStat

Same 7-step shape. Specifics:
- **types.ts (both):** add `| "device-frame"`; reuses the existing captured `imageSrc` field (already present for screenshot scenes) — no new data field.
- **Selection rule + test:** select `device-frame` when `d.get("imageSrc")` is a real captured screenshot AND the scene is flagged a product beat (`d.get("kind") == "product"` or the planner emitted `treatment == "device-frame"`); honesty: never select without a real `imageSrc`. Test: with `imageSrc` set → `device-frame`; without → not selected.
- **Archetype (both):** text-left / right a phone-or-browser frame wrapping `<Img src={resolveSrc?(imageSrc):imageSrc}>` (web uses `resolveLogo`/`resolveSrc` like split-mosaic; studio uses bare `<Img>`). Mirror `AppleScreenshot.tsx`'s frame chrome for the browser variant.
- **Catalog entry:** `exampleProps` references a checked-in sample screenshot at `studio/public/samples/device.png` (add a small real screenshot asset, ≤200KB per asset-hygiene).
- **Render-verify + commit** as 3a.

### Task 3c: `comparison-columns` (old way vs Filmo) — sibling: TreatmentFeatureList

- **types.ts (both):** add `| "comparison-columns"` and:
```ts
// comparison-columns: a two-column contrast.
compare?: { leftTitle: string; leftItems: string[]; rightTitle: string; rightItems: string[] };
```
- **Selection rule + test:** select when `d.get("compare")` has both sides with ≥2 items each (all from real copy). Honesty: only when the planner extracted a real contrast — never invent one; if `compare` absent → not selected. Test both branches.
- **Archetype (both):** two columns; left muted (`theme.textMuted`, the "old way"), right accented (`theme.accent` checkmarks, the Filmo way); each item a row with a dot/check. Mirror `TreatmentFeatureList` row scaffold.
- **Catalog entry** (`exampleProps` with leftTitle "The old way" / rightTitle "With Filmo"), **render-verify, commit** as 3a.

### Task 3d: `pull-quote` (testimonial) — sibling: TreatmentIconHeadline

- **types.ts (both):** add `| "pull-quote"` and:
```ts
// pull-quote: a large editorial testimonial.
quote?: string; quoteAttribution?: string;
```
- **Selection rule + test:** select ONLY when `d.get("quote")` is a real, non-empty quote (≥ ~6 words) extracted from the source — and `quoteAttribution` present. Honesty (critical): NEVER fabricate a quote; absent/short `quote` → not selected. Test: real quote → `pull-quote`; empty quote → not selected.
- **Archetype (both):** centered big serif quote (fontSize 64, `theme.text`), an accent quote-mark glyph, attribution line in `theme.textMuted`. Mirror `TreatmentIconHeadline` centering.
- **Catalog entry, render-verify, commit** as 3a.

---

## Task 4: Landing — Pattern Lookbook beside the Luceo films (M4)

**Files:** Create `web/app/components/landing/PatternLookbook.tsx`; Modify `web/app/page.tsx` (insert the section near `LuceoShowcase`); copy `studio/src/timeline/patterns.catalog.json` → `web/app/_data/patterns.catalog.json` (the mirror, kept in lockstep with the studio copy).

- [ ] **Step 1:** Mirror the catalog into the web project: `cp studio/src/timeline/patterns.catalog.json web/app/_data/patterns.catalog.json`. (Add a note in both files' first key `"_mirror": "keep in lockstep with studio/src/timeline/patterns.catalog.json"`.)

- [ ] **Step 2:** Write `PatternLookbook.tsx` — import the catalog JSON; render a responsive grid of cards, one per pattern: a **high-quality still** (`/lookbook/<id>.png`, generated from the render-verify stills in Task 3) + `name` + `whenToUse`. Section headline: *"Every Filmo video is assembled from this hand-curated library — never improvised."* Sub-copy ties to the Luceo films below.

- [ ] **Step 3:** Generate the lookbook stills: for each catalog pattern, render its `exampleProps` (reuse the Task 3 render-verify command per id) and copy the PNG to `web/public/lookbook/<id>.png` (≤200KB each, run `~/bin/lint-video-assets`).

- [ ] **Step 4:** Insert `<PatternLookbook />` into `web/app/page.tsx` immediately adjacent to `<LuceoShowcase />`, so the two read as one beat: the library + the films it's distilled from.

- [ ] **Step 5:** Verify: `cd web && npm run build` → expect success (no type errors). Then `vercel --prod --yes` and re-alias: `vercel alias set <new-url> filmostudio.vercel.app`. Open `filmostudio.vercel.app`, screenshot the section, confirm the lookbook + Luceo pairing renders.

- [ ] **Step 6: Commit.**
```bash
git add web/app/components/landing/PatternLookbook.tsx web/app/page.tsx web/app/_data/patterns.catalog.json web/public/lookbook/
git commit -m "feat(landing): Pattern Lookbook beside Luceo Studio films (curated, not improvised)"
```

---

## Task 5: Luceo Studio harvest (M5)

**Files:** new archetype(s) in both `ExplainerCard.tsx` copies + types + catalog entries with `harvestedFrom` set.

- [ ] **Step 1:** Confirm the source set exists: `ls -d Demos/lovio-fable5 Demos/apple-style-demo Projects/Orinovate/orinovate-video 2>/dev/null` (swap any missing for the nearest equivalent from `find` results).

- [ ] **Step 2:** Dispatch parallel read-only subagents (one per source video) to distill the 1–2 most reusable, beautiful **layout/motion patterns** from each project's `src/` — each returns: a proposed pattern `id`, data contract, a layout/motion description, and the exact source file:lines it came from. (Read-only; no edits.)

- [ ] **Step 3:** Pick the best 1–3 candidates. For each, implement it exactly as a Task-3 sub-task (types both copies + selection rule + test + archetype both copies + catalog entry **with `harvestedFrom` set to the source project** + render-verify + lookbook still).

- [ ] **Step 4: Commit** each harvested pattern separately (`feat(patterns): harvest <id> from <luceo-source>`).

---

## Task 6: Narrative + legibility polish (M6)

**Files:** Modify `web/app/page.tsx` (or the relevant landing copy component); optionally surface `patternReason` in the run/editor UI.

- [ ] **Step 1:** Add the "Curated, not improvised" one-liner + the Ploy-thesis framing to the landing (near the Lookbook). Keep copy tight; no emojis.
- [ ] **Step 2 (optional, if time):** Surface `data.patternReason` per scene in the editor/run view (a small "why this layout" caption) — proof the curation is real.
- [ ] **Step 3:** Final pass: pick a clean demo URL, run a full hosted gen, confirm every scene is a recognizable curated pattern, save the sample to `~/Desktop/filmo-videos/`.
- [ ] **Step 4: Commit + deploy** (worker `railway up --service walk-studio-hosted --ci`; web `vercel --prod --yes` + re-alias).

---

## Self-review notes (gaps checked against the spec)

- Spec §2 (one catalog, two consumers) → Task 1 (catalog + loader) + Task 4 (web mirror). ✓
- Spec §3 (seed 7) → Task 1. ✓  §4 (4 new patterns) → Task 3a–3d. ✓  §5 (assembly legible + honesty) → Task 2 + each 3x selection rule. ✓  §6 (landing pairing) → Task 4. ✓  §7 (Luceo harvest) → Task 5. ✓  §8 (narrative) → Task 6. ✓
- Honesty guard appears in every selection rule (3a–3d) and the icon-headline floor (Task 2). ✓
- Both `ExplainerCard.tsx` + both `types.ts` copies edited in every archetype task (drift risk mitigated). ✓
- Open confirmations deferred to build: final 4-pattern set (3a–3d are the proposal); Luceo source set (Task 5 step 1).
