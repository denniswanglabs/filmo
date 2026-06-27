# Filmo Web App — Review Brief V1

Reviewer: review subagent (read-only). Date: 2026-06-26.
Branch: `hosted-saas`. Live: https://filmostudio.vercel.app

## SUMMARY

Filmo is a polished, credible AI-video SaaS that a hackathon judge would find genuinely
impressive. The live site loads publicly (no SSO wall), branding is consistent ("Filmo" wordmark
== favicon), the "Powered by" strip correctly credits Hermes·Nemotron·Stripe, sign-in (Google +
email/password) is present and reachable, and — critically — the headline feature (in-browser
editor → Export → re-render) is **fully wired end-to-end**, not a mockup. The weaknesses are
finish-level, not structural: a couple of decorative-but-dead affordances, a hardcoded `mock`
build mode, and one brief assumption that turned out wrong (steps).

**Overall rating: 8.5/10** — demo-ready; the fixes below are polish that close "is this real?" gaps.

---

## STRENGTHS

- **Edit → Export → re-render chain is real and complete.** Traced fully:
  `app/runs/[id]/edit/page.tsx:104-112` (`handleExport` → `saveEditedProps` + `requestReRender`)
  → `app/actions.ts:114-118` (inserts `jobs` row `type:'rerender'`, nulls `edited_url`)
  → `worker/run.js:332-333` (`processJob` branches on `job.type === 'rerender'`)
  → `worker/run.js:260-319` (`processReRender`: reads `props_edited`, `downloadRunAssets`,
  `runRender`, uploads `edited.mp4`, sets `runs.edited_url`)
  → `app/runs/[id]/page.tsx:54-64` (keeps polling while a rerender job is queued/claimed)
  → `app/runs/[id]/page.tsx:111-129` (shows the "Edited" cut first, "Original" below).
  Export button is real: `_editor/Editor.jsx:330-331`.
- **Editor is a true live preview**, not a screenshot: `@remotion/player` Player + `_composition/Timeline`
  (`_editor/Editor.jsx:21-22,395`), inspector mutates props → Player re-renders instantly.
- **Branding consistent.** `app/icon.svg` path data is byte-identical to the `Wordmark` SVG in
  `app/components/Brand.tsx:30-36`. Live `/`, `/how-it-works`, `/login` all say "Filmo".
- **Powered-by credit correct and app-wide** (`PoweredBy.tsx:10-29`): Hermes·Nous, NVIDIA·Nemotron,
  Stripe·Payments; reused under composer and (compact) in footer. All three SVGs exist in `public/brands/`.
- **No SSO wall.** WebFetch on `/`, `/how-it-works`, `/login` all return public marketing/login HTML.
- **BuildProgress is reassuring and honest** (`BuildProgress.tsx`): stage tracker, elapsed timer,
  live Hermes/Nemotron/Stripe activity feed, indeterminate shimmer — good for a multi-minute run.
- **Resilient worker**: `unhandledRejection`/`uncaughtException` kept-alive + `supervise()` restart
  loop (`run.js:37-42,416-426`); idempotent uploads (`putObject` removes-before-upload, `run.js:101-106`);
  idempotent rerender (dedupes in-flight jobs, `actions.ts:104-112`).
- **OAuth round-trip UX**: composer state stashed in sessionStorage and auto-resumes the build on
  return (`app/page.tsx:107-145`) — a nice, working detail.
- All example assets present: `public/examples/{notion,linear,stripe}.{mp4,jpg}` + logos.

---

## WEAKNESSES → FIXES

### W1 — "Remix" and "Watch" chips on example cards are decorative-only (dead). **P1**
- **Where:** `app/components/landing/Examples.tsx:185-195` (and the whole `GalleryCard`, 122-197).
- **What's wrong:** The card is a `<figure>` with `onMouseEnter/onMouseLeave` only — no `onClick`,
  no `<Link>`, no `href` anywhere in the file (grep for `Link|href|onClick|<a ` returns nothing in
  Examples.tsx). The "Remix" pill and "Watch" chip render as interactive buttons but do nothing when
  clicked. A judge who clicks "Remix" (the section is literally titled "Explore & remix",
  Examples.tsx:209) gets no response — reads as unfinished.
- **Fix:** Either (a) make each card a real action: wrap the figure in a button/Link that scrolls to
  `#start` and pre-fills `#hero-url` with that brand's URL (mirror `FloatingNav.jumpToComposer`,
  FloatingNav.tsx:33-43), so "Remix" actually seeds a build; or (b) if out of scope, demote the chips
  to non-affordance labels (remove the pill/chip styling so they don't look clickable). Option (a) is
  the stronger demo.

### W2 — Every public build is hardcoded to `mode:'mock'`. **P1 (judge-facing) / verify intent**
- **Where:** `app/page.tsx:91` — `createBuild({ ..., mode: 'mock' })`.
- **What's wrong:** The landing composer always submits `mode:'mock'`; the worker then sets
  `PRODUCER_SIMULATE_PAID=1` (`run.js:349`), i.e. Stripe earning is simulated, never a real charge.
  This is almost certainly intentional for a public demo (avoids real money — consistent with the
  money-gate policy), but a judge testing live will never exercise the *real* Stripe path the
  pitch implies. There is no UI toggle for `real`.
- **Fix:** Keep `mock` as the public default, but (a) add a one-line note in the activity feed or
  near the price stat that the demo runs payments in simulation, so it's transparent not hidden; and
  (b) if a guarded real path is wanted for a judge, gate it behind the existing dev-mode flag
  (`isDeveloper`, actions.ts:162-171) rather than exposing `real` to all. Confirm intent before
  changing — do not silently enable real charges.

### W3 — Brief's "should be 5 steps" is wrong; design is 4 and intentional. **P2 (no code change)**
- **Where:** `app/components/landing/HowItWorks.tsx:9-30` (4 steps) + heading "Four steps, fully
  autonomous" (HowItWorks.tsx:50); live `/how-it-works` also shows 4.
- **What's wrong:** Nothing in the app — the 4-step design is self-consistent (Read your page → Plan
  the cut → Price & produce → Ship the MP4) and matches the live site and the hero copy
  ("planned, priced, and produced"). The "5 steps" in the review brief is an outdated assumption.
- **Fix:** None required. Flagging so the orchestrator doesn't "fix" a non-bug. If 5 is genuinely
  wanted, the natural split is separating "Price" from "Produce" — but that contradicts the current
  locked copy, so treat as a product decision, not a defect.

### W4 — `Wordmark` `tone` prop is semantically inverted (confusing, not a visible bug). **P2**
- **Where:** `app/components/Brand.tsx:18-44`. `tone='light'` renders `text-[#0E1320]` (dark ink),
  `tone='dark'` renders `text-ink`. `FloatingNav.tsx:67` passes `tone="light"`.
- **What's wrong:** The nav bar is `bg-white/70` (FloatingNav.tsx:62), so dark ink is *correct* there
  and renders fine — no visible contrast problem today. But the prop naming is backwards (`'light'`
  yields dark text), which is a latent footgun: anyone reusing `Wordmark` on a dark surface and
  passing `tone='light'` expecting near-white text will get unreadable dark ink.
- **Fix:** Rename so `tone='light'` = light/near-white text for dark backgrounds (and update the one
  caller, FloatingNav.tsx:67, to whatever keeps the nav dark-on-light). Low urgency; cosmetic/DX.

### W5 — Editor empty-state asset 404s are silent-but-expected; preview can look sparse. **P2**
- **Where:** `app/runs/[id]/edit/page.tsx:83-92` comment + `worker/run.js:115-153` (uploadRunAssets).
- **What's wrong:** The editor preview resolves per-scene assets (screenshots/VO/music) against the
  bucket; the code comment (edit/page.tsx:85-87) acknowledges that for runs predating per-scene
  upload, those assets "404 gracefully" and only text/layout/motion render. For an older featured run
  a judge opens, the editor could look emptier than the delivered MP4. Not broken, but a possible
  "why does the preview look different from the video?" moment.
- **Fix:** Ensure the demo/featured run was produced by the current worker (so `uploadRunAssets`
  staged its assets), or add a small inline note in the editor when `assetBaseUrl` assets fail to load
  ("preview shows layout; final render uses full media"). UNCERTAIN whether the featured run is
  current — could not verify the authed run page contents (see blind spots).

### W6 — Uncommitted key feature. **P1 (process, not code)**
- **Where:** `git status`: `worker/run.js` is modified-unstaged; the editor dirs
  (`app/runs/[id]/edit/_editor/`, `_composition/`) plus 3 InsForge migrations
  (`insforge/migrations/2026062*`) are present locally. The brief itself flags the editor as "built
  but uncommitted."
- **What's wrong:** The headline feature and the worker's rerender path are not committed. If the
  deployed Vercel build predates these, the live editor/export may not match the local source — a
  judge on the live site could hit an editor that lacks the verified Export wiring.
- **Fix:** Verify the live deploy includes the editor + the modified `worker/run.js` rerender path
  (the run page's rerender-polling at page.tsx:54-64 is the tell — if live shows that, it's deployed).
  Then commit. Do NOT let me (read-only) commit; surface to orchestrator.

---

## PASS-3 BLIND SPOTS (what I did NOT check)

1. **Authed surfaces.** WebFetch can't run JS/auth, so I never saw a real signed-in run page,
   the editor in a browser, or a completed `delivered` run with video. `/runs/featured` returned
   only the "Loading…" client shell. The Edit→Export chain is verified *in source*, not exercised live.
2. **Does a real build actually complete on the deployed worker?** I did not run one (paid Ultra
   tokens / real pipeline). Whether the Railway worker is up, claims jobs, and the python
   `build_runner.py` succeeds in the container is unverified. The web app is correct *given* a
   working worker.
3. **Mobile layout.** I read Tailwind responsive classes (sm:/lg: breakpoints look reasonable, nav
   hides center links < sm) but did not render at mobile widths. No viewport screenshot taken.
4. **Accessibility/contrast at runtime.** Inferred from classes only; no axe/contrast tooling run.
   `aria-hidden` usage looks correct; the URL input has a visible label (page.tsx:212). Not audited.
5. **RLS / security depth.** `saveEditedProps`/`requestReRender` do owner checks (actions.ts:29,96)
   and `pairDeveloper` keeps `DEV_MODE_KEY` server-side (actions.ts:136-159) — looks sound, but I did
   not test that RLS actually blocks cross-user run access on the live DB.
6. **Stripe path correctness.** Only confirmed `mode:'mock'` simulates it; did not inspect the
   python pricing/earning code (lives in `hermes-video-agent`, outside this review's scope).
7. **`/inside/[runId]` dev surface.** Confirmed it exists and is gated by `isDeveloper`; did not
   exercise the key-pairing flow.

---

## RECOMMENDED-PAID-STEP

**A real end-to-end live build is worth running, but flag it — do not auto-run.** Rationale: blind
spots #1 and #2 are the only things standing between "verified in source" and "verified working for a
judge." One real (or even one `mock`) build through the *deployed* stack would confirm (a) the Railway
worker claims and completes a job, (b) the editor opens on a real `props`-carrying run, and (c)
Export produces an `edited_url`. Because the public composer is hardcoded to `mode:'mock'`
(`PRODUCER_SIMULATE_PAID=1`), a **mock** build costs no real Stripe money and only the chosen brain's
tokens — prefer `super-free` (Nemotron 3 Super, free) for the smoke test, not `ultra-paid`. Reserve a
paid Ultra build only if the orchestrator wants to demo the flagship brain. Orchestrator's call on spend.

---

**Report path:** `/Users/dennis/Desktop/Projects/Hackathons/walk-studio-hosted/web/REVIEW-BRIEF-WEB-V1.md`
