# Conversion Read — design spec

**Date:** 2026-06-25
**Status:** approved design, pre-implementation
**Owner:** Dennis + Hermes producer-brain
**Context:** Hermes×NVIDIA×Stripe hackathon (due 2026-06-30). Walk Studio's
differentiator vs the rival (VED/StoryPrompting): we don't generate a pretty film —
we *diagnose* how a real product fails to convert, then produce the video that fixes it.

---

## 1. Goal

Add a **Conversion Read** stage to Walk Studio: before planning the video, the agent
reads the target page's real copy, scores how well it converts on 6 dimensions, and
emits a structured diagnosis. That diagnosis is shown to the user as a first-class
deliverable AND drives the video plan — so each prescribed fix maps to a scene and the
finished video *is* the diagnosis, fixed.

**Why this is the moat:** it's "taste/curation is the moat" (Bryant Chou) made concrete —
the analysis layer is what separates a real tool from generative slop. The rival makes a
gorgeous synthetic film; Walk Studio makes the prescribed fix to a diagnosed problem on a
real product. Different category, grounded in reality.

**Scope chosen:** "Read drives the video" (the balanced build) — full Ploy-grade
diagnosis whose fixes map to scenes. NOT full-parity (no toggleable fixes, no separate
priced Read, no next-steps/publish — those are post-hackathon).

---

## 2. Architecture & data flow

Today (`build_runner.py`): PLAN (Nemotron, abstract from URL+goal) → PRICE → PAY →
PRODUCE (capture+render+stitch) → DELIVER. Nemotron never reads the page; capture happens
at produce time.

New flow flips read-before-plan and inserts ANALYZE:

```
URL + goal
 → READ PASS    reuse capture: page copy (inner_text body) + 1 hero screenshot, up front
 → ANALYZE      brain.py → Nemotron scores 6 dimensions → Conversion Read JSON
 → PLAN         existing planner, SEEDED with the Read (COMPANY-FACTS + prescriptions)
 → PRICE → PAY → PRODUCE → DELIVER   (unchanged; Stripe P&L + autonomous Issuing decline intact)
```

The cockpit ledger gains an `analyzing` stage before `planning`, so the console shows the
agent "reading your page" before it plans.

---

## 3. Components

1. **`read_pass`** — a "text+hero only" mode over `capture_screenshots.py` (reuse the
   existing `page.inner_text("body")` extraction at `capture_screenshots.py:243` + one hero
   screenshot). Must NOT trigger the full walkthrough capture (that stays at produce time).
   Returns `{url, body_text (<=4000 chars), hero_screenshot_path, headline?}`.
2. **`analyze.py` + `analyzer-prompt.md`** (new) — mirrors `planner-prompt.md`'s
   strict-JSON discipline (JSON-only, frozen contract restated verbatim, numbered rules,
   self-check). Calls `brain.py` (default `super-free` Nemotron tier, same as the planner).
3. **Conversion Read JSON contract** (frozen — consumers read these exact names):
   ```json
   {
     "url": "str",
     "verdict": "str (1 line, the overall read)",
     "dimensions": [
       {"key": "promise|outcome|proof|show|specificity|cta",
        "score": 0,            // 0-5
        "finding": "str",      // what's wrong/right, grounded in the page's words
        "evidence": "str",     // the actual quote/element from the page
        "fix": "str"}          // the concrete change
     ],
     "priority_fixes": [
       {"rank": 1, "fix": "str", "maps_to": "scene-hint str"}
     ],
     "headline_fix": "str"     // the outcome-led hero line to OPEN the video with
   }
   ```
4. **Read → plan seeding** — extend the planner's COMPANY-FACTS input
   (`build_runner.py:164`) with the Read. Specifically:
   - `headline_fix` → the opening `title` scene's text.
   - each `priority_fix` → a scene directive in the brief (e.g. a `proof` fix → a beat that
     surfaces the real captured number/logo; a weak-`cta` fix → a stronger closing `title`).
   - The existing deterministic backstop (which already enforces the
     title→screenshot→walkthrough→title shape for STANDARD) is extended to guarantee the
     top fixes appear as beats, so a small model can't silently drop them.
5. **Dashboard surfacing** — an **Analysis** panel renders the Read before the video: the
   6 dimensions with scores + the prioritized fixes, then the video framed as the fix.
   Reuse existing dashboard/cockpit components. The run page shows: Analyzing → Read →
   Planning → … → Delivered.
6. **Persistence** — write `conversion_read.json` into the run dir + a ledger event;
   (cloud) store on the run row in InsForge so the hosted dashboard renders it.

---

## 4. The 6 dimensions

Message conversion (how clearly value lands in motion), the video analog of CRO:

| key | question | 0 | 5 |
|---|---|---|---|
| `promise` | does the first 5s say what it is + who it's for? | makes you work for it | instantly clear |
| `outcome` | sells the buyer's result vs listing features? | feature/spec list | outcome-led |
| `proof` | credible evidence — numbers, demo, logos? | none | strong, specific |
| `show` | shows the product *working* vs abstract b-roll? | all tell | real demo shown |
| `specificity` | concrete vs vague adjectives? | "powerful" | "10× faster" |
| `cta` | one clear next step? | none/many | single obvious CTA |

`proof` and `show` are the highest-leverage (matching Ploy's "zero social proof is the
biggest lever") and are where Walk Studio's real screen-capture beats AI-film rivals cold.

---

## 5. Guardrails

- **Feature-flagged** (`PRODUCER_CONVERSION_READ=1`). `main`'s current behavior is untouched;
  purely additive, consistent with the rest of this session's work.
- **Built on a feature branch**, not `main` (keeps the fallback intact). Branch base +
  local-demo-vs-cloud reconciliation finalized in the implementation plan.
- **Never blocks the video.** Read pass fails (page unreachable / no text) → fall back to
  today's URL+goal planning + a best-effort Read flagged `degraded`. Malformed Nemotron JSON
  → retry (brain.py), then a minimal deterministic Read so the pipeline never crashes.
- **Standard (real-capture) tier first** — the grounded, anti-VED flow. Premium later.
- **$0 mock parity** — the Read runs in `--mode mock` with no spend (Nemotron `super-free`),
  so the whole flow is demoable at $0.

---

## 6. Scope boundary (v1)

IN: Read generated → shown as a deliverable → drives the video plan; `analyzing` ledger
stage; dashboard Analysis panel; feature-flagged; standard tier; $0 mock.

OUT (post-hackathon): toggleable/editable fixes, the Read as a separately-priced Stripe
deliverable, "suggested next steps," publish/export, premium-tier Read.

---

## 7. Demo narrative

Judge drops a URL → watches the agent **read** the page (`analyzing` ledger) → a Conversion
Read appears ("feature-led hero, zero proof, weak CTA — scores 2/1/2") → the agent plans +
produces the 30s that fixes exactly those (outcome-led open, a real proof beat, one clear
CTA) → priced → the autonomous Stripe Issuing decline on the over-budget scene → delivered.
The Read makes Walk Studio feel like it *understands the business*, not just generates.

---

## 8. Testing

- Unit: `analyze.py` parses a fixed page-text fixture → valid Read JSON (mock Nemotron) →
  all 6 dimensions present, scores in range.
- Mapping: a Read with a low `proof` score → the resulting plan contains a proof beat;
  `headline_fix` lands as the opening title text.
- Fallbacks: unreachable URL → degraded Read + video still produced; malformed JSON →
  deterministic minimal Read.
- $0 mock end-to-end on a known URL via the existing `run_all_tests.sh` harness.

---

## 9. Open decisions (resolve in implementation plan)

1. **Branch base & demo unification** — feature branch off `main` (local demo baseline) vs
   off `hosted-saas` (cloud, has the amd64 pipeline fixes). The local Stripe-Issuing demo
   runs from `main`; the Conversion Read must be present there for the demo.
2. **Read-pass vs full capture reuse** — confirm `capture_screenshots.py` can run a cheap
   text+hero pass without side effects (gate-handling, SPA hydration) firing the full flow.
3. **Cloud surfacing** — InsForge schema add for `conversion_read` on the run row + the
   hosted dashboard render (may slip to v1.1 if local demo is the hackathon target).
