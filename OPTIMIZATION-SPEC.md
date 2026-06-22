# Walk Studio — Quality-Bar Spec (prompt-optimization loop scores against THIS)
_2026-06-22. Source: handpicked reference films in the dashboard lookbook. Target: generated Standard videos ≥4 on every dimension, ≥4.3 mean. Load-bearing weak points today: Dim 3 (grounding) + Dim 5 (real UI)._

## HANDPICKED REFERENCE FILMS (the bar) — all on disk, 1280×720@30
- `dashboard/assets/video/orinovate-launch-720.mp4` (79s) — Taiwan 3D-print/CNC; navy+blue; technical B2B tour
- `dashboard/assets/video/trayd-launch-720.mp4` (30s) — YC W24 construction payroll; navy+lime; mobile+desktop UI
- `dashboard/assets/video/kuli-launch-720.mp4` (30s) — AI influencer marketing; violet aurora; analysis grid
- `dashboard/assets/video/hotcake-launch-720.mp4` (58s) — salon CRM
- `dashboard/assets/video/jgb-launch-720.mp4` (60s) — property / smart-contract
- Manifest: `dashboard/app.js` `ABOUT_LOOKBOOK` (~1760). Cached ref frames: `/tmp/rubric-frames/{orinovate,trayd,kuli}/`.

## THE SHARED TEMPLATE (what the references DO)
Numbered act badges ("01 — WORKER APP") · navy/brand TITLE open + brand CTA close bookending a lighter product middle · imperative copy couplets ("Clock in. / Cash out.") · **native-rebuilt, fully-populated real product UI** (working payroll tables, ranked dashboards, faceted filters — NOT screenshots, NOT abstract blobs, NOT placeholders) · single accent used sparingly · concrete copy with real feature names + oddly-specific real numbers ("$11,438", "1.3M / 6.60%", "13m 46s").

## RUBRIC (score each generated video 1-5; 5 = matches references)
1. **Structure & arc** — hook → mechanism/features → proof → CTA; navy/brand bookends; explicit numbered act badges. 30s≈5 beats, 60-80s≈5-7.
2. **Pacing & scene length** — snappy ~4-7s beats; staged line-by-line/word reveals (active line white / pending gray); no static dead holds.
3. **Copy / VO grounding** ⟵ LOAD-BEARING — concrete, benefit-driven, grounded in the REAL product (real feature names, real domain detail, oddly-specific real-looking numbers). 1 = hollow/self-referential/generic-SaaS-speak/describes-the-animation/invented-round-numbers. **TripAdvisor-class bot-blocked brands score ~1-2 here today.**
4. **Copy rhythm** — tight imperative couplets for kinetic type; setup→payoff for stats. 1 = run-on/limp filler.
5. **Real imagery / UI fidelity** ⟵ LOAD-BEARING — native-rebuilt fully-populated real UI (mobile + desktop). 1 = abstract shapes / raster screenshots / empty mockups / orange placeholders. (Walk Studio uses real SCREENSHOTS + walkthrough today — a partial match; references REBUILD the UI.)
6. **Typography & hierarchy** — geometric sans; 3-tier (tracked all-caps eyebrow → heavy display → gray body); custom wordmark.
7. **Color / brand fidelity** — palette from the real brand; ONE accent used sparingly; brand color even in pure-type beats. 1 = off-brand or the orange-placeholder failure (NOW FIXED).
8. **Motion polish** — layered panels, soft elevation/glass depth, scan-line/counter motion, eased staggered reveals, animated transitions (not hard cuts).
9. **Overall feel** — reads as a real funded company's launch film; premium, trustworthy, B2B-credible; concrete specificity over spectacle.

**TARGET:** ≥4 every dim, ≥4.3 mean. Move Dim 3 (grounding) + Dim 5 (real UI) first.

## TEST-BRAND ROSTER (generality — majority of website types)
| # | URL | type | difficulty |
|---|---|---|---|
| 1 | https://linear.app | dev tool/SaaS | heavy JS |
| 2 | https://vercel.com | dev infra | heavy JS |
| 3 | https://www.notion.so | productivity SaaS | client-render |
| 4 | https://stripe.com | fintech | clean (grounding baseline PASS) |
| 5 | https://www.shopify.com | e-commerce platform | marketing-heavy |
| 6 | https://www.allbirds.com | e-commerce store | some bot-rate-limit |
| 7 | https://www.airbnb.com | marketplace | heavy JS, geo/login |
| 8 | https://www.tripadvisor.com.tw | travel marketplace | **BOT-BLOCKED → hollow copy. KEY target.** |
| 9 | https://www.theverge.com | media | ad/consent walls |
| 10 | https://www.plaid.com | fintech API | clean B2B |
| 11 | https://www.webflow.com | no-code SaaS | heavy JS |
| 12 | https://www.huckberry.com | DTC retail | lifestyle catalog |
