# Walk Studio + Editor — UI Polish & Test Loop (1 hour, autonomous)
_2026-06-22 evening. Dennis away ~1hr. Mandate: TEST + POLISH the new video EDITOR and Walk Studio, with SPECIAL attention to UI beauty ("it has to look beautiful"). Use every resource — max parallelism, strongest models, 550B (`--brain ultra-paid`) where reasoning-limited. Quality + speed are the only metrics; token count is not._

## TWO TRACKS
- **A — Walk Studio dashboard** (`dashboard/index.html` / `app.js` / `styles.css` + the live walk-agent panel). Live on :3030; preview via the `hermes-static` server on :3099.
- **B — The video EDITOR** (`studio/editor/`, @remotion/player + panel). NEW DIRECTION (Dennis 2026-06-22): make it look like a real **iMovie-style timeline video editor**, premium, modeled on **Hera (hera.video)** — "amazing UI." Round-1 polish landed (dark Linear/Framer base); now RESTRUCTURE into a timeline editor with Hera's design language.

### HERA DESIGN LANGUAGE (studied via Chrome MCP) + iMovie STRUCTURE — the editor target
- **Floating glassmorphic header** (rounded, semi-transparent, blurred, floats over content).
- **Heavy rounded corners everywhere** (~16-22px) — cards, buttons, panels, canvas, timeline clips.
- **Floating pill toolbars** (rounded containers of icon buttons).
- **Gradient accent + glow** (Hera uses pink→coral; keep cohesion with Walk Studio's accent but adopt the gradient/glow treatment on PRIMARY actions).
- **Surface mix:** clean content areas + immersive dark canvas; the VIDEO is the hero on a dark, framed canvas.
- Generous whitespace, soft diffuse shadows, modern geometric sans (Hanken Grotesk), calm/minimal/premium.
- **iMovie layout:** floating top bar → big PREVIEW (dark canvas, centered, playback controls) → BOTTOM TIMELINE of scene clips (width ∝ duration, thumbnail + label, playhead, click-to-select seeks the player) → INSPECTOR (selected scene's text/geometry/theme/timing). Keep ALL live-edit + Save + Export functionality working.

## THE BEAUTY BAR (what "beautiful" means — the reference is Linear / Vercel / Stripe dashboards)
- **Typography:** clear 3-tier hierarchy, consistent type scale, tracked all-caps eyebrows, no cramped/orphaned text, tabular numerals where numeric.
- **Spacing & alignment:** generous, consistent rhythm on a grid; nothing misaligned, cramped, or overlapping; balanced whitespace.
- **Color & surface:** cohesive use of the existing palette; ONE accent used with intent; refined surfaces/elevation; sufficient contrast.
- **Components:** polished cards / panels / buttons / inputs; consistent radius + border + shadow; considered empty / loading / active / hover / focus states.
- **Motion & interaction:** smooth hovers/focus, the live panels feel slick, the LIVE pill + feeds read premium, transitions eased.
- **HOUSE STYLE:** NO EMOJIS anywhere — SVG icons / text badges only. Refined, intentional, never decorative-for-its-own-sake.
- **Feel:** a hackathon judge should think "this is a real, well-funded product."

## CANONICAL PALETTE & BRAND (Dennis 2026-06-22: "make the palette of the studio the same as the current website / the original app; one color scheme everywhere"). SINGLE source of truth = the existing dashboard `dashboard/styles.css :root`. BOTH the dashboard AND the editor use these — no divergence:
- `--bg #F4F5F7` (light page) · `--line #E4E7EC` · `--ink #14171C` (text) · **PRIMARY ACCENT coral `--amber #D6351C`** (used SPARINGLY) · `--on-accent #FFFFFF` · `--pos #0E9F6E` · `--neg #C01A2B` · `--video-bg #0C0E12` (dark, for VIDEO surfaces only).
- Fonts: **Hanken Grotesk** (sans) + **Newsreader** (serif). Radii: ctl 11px / card 15px / pill 999px.
- **EDITOR must MIGRATE to this** — light chrome (like the dashboard) + a dark `#0C0E12` video canvas + the **coral accent (NOT lime)** + Hanken/Newsreader. Kill the round-1 lime/dark-chrome. The editor and dashboard must look like ONE app.
- (NOTE: the product is now **Filmo** at https://filmostudio.vercel.app; the dashboard/editor brand should read as Filmo. Re-skin is reversible, CSS-vars only.)

## ANTI-"AI-GENERATED" BAR (Dennis: "does not look AI generated... looks more like the original app"). AVOID the tells: generic purple/indigo/blue or rainbow/multi-hue gradients; neon glow everywhere; emoji; over-rounded everything / inconsistent radii; too many accent colors (use ONE — coral — sparingly); centered-everything symmetric blandness; default shadcn/Tailwind-template look; glassmorphism overload; lorem/placeholder vibe; cramped or inconsistent spacing. INSTEAD: restrained + intentional, one accent used sparingly, a real grid + consistent spacing, true type hierarchy (Hanken/Newsreader), editorial confidence (restrained, premium SaaS-landing-page craft), tasteful neutral surfaces — the look of a real product designed by a human, matching the original app.

## PERSISTENT DESIGN WATCHDOG (Dennis: "a subagent constantly watching over the design, always improving it"). Run a design-critic EVERY round (it is the constant watcher): headless-screenshot BOTH UIs → critique vs (a) the CANONICAL PALETTE + cross-UI brand consistency, (b) the ANTI-AI-GENERATED bar, (c) "does this look like the real original app, human-designed?" → return a prioritized punch-list that DRIVES that round's polish agents. It never signs off as "done" while either UI drifts off-palette or reads AI-generated.

## LOOP MECHANICS (per round)
1. **CAPTURE** — screenshot every key screen (dashboard: composer "Got a video idea", build list/active, a build DETAIL with storyboard + script + agent-activity panel, a PRODUCING state showing the live walkcast panel; editor: preview + panel).
2. **CRITIQUE** vs the bar → prioritized punch-list (file:line, specific, by screen × dimension).
3. **POLISH** — fan out implementers by area (typography / spacing / color / components / live-panel). They EDIT files (no preview during editing → no browser-tab contention); a single verifier re-screenshots.
4. **VERIFY** — re-screenshot, confirm each fix improved it, no regressions; `node --check app.js`, dashboard still renders.
5. **FUNCTIONAL** (parallel) — smoke-test both: a $0 mock Walk Studio build end-to-end + the live panel; the editor load → edit → save → re-export.
6. Log the round; repeat until beautiful + solid or the hour's up → STOP + report with before/after screenshots.

## GUARDRAILS
- Editor is additive/isolated; geometry params are backward-compatible (existing videos verified byte-identical). RESTORE POINT: git tag `pre-video-editor-20260622-193030` + tarball `~/walk-studio-restore-20260622-193030.tgz`.
- $0 builds (mock + `WS_WALKTHROUGH_CACHE=/tmp/walk-smoke-short.mp4`); native `walk_native` is $0 (Playwright). 550B only where reasoning is the limiter; flag a real-money burst.
- Keep the test suite green (`./run_all_tests.sh --no-eval`) after edits. NEVER restart/disturb the :3030 server.
