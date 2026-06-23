# Self-improving loop — state (read FIRST on each loop firing)

_Self-paced /loop. Mission: drive Walk Studio to hackathon-ready, improving each pass.
Dennis is ASLEEP (went to bed ~01:00, 2026-06-24) — FULL AUTONOMY, no questions.
$0 mock builds only. `main` = untouched local fallback (never touch)._

## CANONICAL DIR (changed 01:00 — consolidated)
**`~/Desktop/Projects/Hackathons/walk-studio-hosted`** (branch `hosted-saas`) is now the
SINGLE source for the whole cloud build: pipeline + `worker/` + `Dockerfile` + `web/` (Next.js
frontend) + `insforge/migrations/`. It is self-sufficient (gitignored, present on disk):
`web/.vercel` (Vercel link → walkstudioprojects), `web/.env.local`, `.insforge` (InsForge CLI
link), `worker/.env`. The old `walk-studio-cloud/` dir is DEPRECATED — work here.
- Deploy frontend: `cd web && vercel --prod --yes` (→ https://walkstudioprojects.vercel.app)
- Deploy worker:   `RAILWAY_CALLER=skill:use-railway@1.3.0 railway up --detach` (from repo root)
- InsForge ops:    `npx @insforge/cli ...` (or worker/enqueue.js to enqueue a cloud build)

## GITHUB BACKUP — the safety net (NEW, Dennis 01:00, STANDING AUTHORIZATION)
Dennis: _"keep the GitHub updated such that if anything goes wrong, we always have a backup
we can go back to."_ So after EVERY meaningful change (code, fix, deploy-worthy edit):
1. SECRET-SCAN staged content FIRST — never commit `.env*`, `.insforge`, `.vercel`, or any
   `sk_*`/`ik_*`/`whsec_*`/`eyJ...` key material. (`.gitignore` already covers these; verify.)
2. `git add -A && git commit` (end msg with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`)
3. `git push origin hosted-saas`.
This is the restore point: `git checkout hosted-saas` brings the whole cloud build back.
Backup discipline is autonomous for THIS loop only; `main` stays untouched.

## Mission order (each firing: pick the highest-impact open item, do it, BACK IT UP)
1. **Verify cloud delivery GREEN end-to-end.** Confirm the Railway walkthrough-fix rebuild
   reached SUCCESS (`railway deployment list --json`) → enqueue a $0 mock cloud build
   (worker/enqueue.js) → poll `runs.status` to `delivered`. If delivered, cloud loop is GREEN.
   Then rebuild to ship the staged activity-classifier fix (run.js) too.
2. **Drive + fix the LIVE app** (Chrome MCP, walkstudioprojects.vercel.app) — judge's-eye pass.
   DONE: demo auto-login (frictionless), canonical cursor-mark logo, project renamed clean.
   OPEN: Build button resting style reads as disabled (light coral) though enabled — brighten
   to solid coral so it invites the click; re-check the run page, delivered view, recents.
3. **NemoClaw** (NVIDIA story): install Playwright+Chromium in `promo-agent` sandbox
   (`nemoclaw promo-agent exec --timeout <s> -- <single-line>`, `dangerouslyDisableSandbox`),
   run a capture, wire as a guarded walkthrough path; keep OpenRouter for the Nemotron planner.
   Cloud wrinkle: NemoClaw is local-only (:10254) → the LOCAL demo uses it; the Railway worker
   keeps the Remotion walkthrough. Frame: "plans on Nemotron 550B, navigates in a NemoClaw sandbox, paid on Stripe."
4. **Per-brand build→judge→fix→log** (Stripe, Linear, Notion, Vercel, Beside, Ashlar): $0 mock
   → ffmpeg contact sheet → JUDGE THE WHOLE VIDEO scene-by-scene (not one frame) + catch flakes
   → fix highest-impact issue → BACK IT UP (commit+push) → append a lesson below.

## Pending one-shot (handle on first firing if still queued)
- `daily-synth` scheduled task — claim atomically then execute
  `/Users/dennis/.claude/scheduled-prompts/daily-synth.md` (`.due`→`.claimed` mv, rm on success).

## NemoClaw integration — path (discovered iter 1)
- Sandbox `promo-agent` healthy: Linux, Python 3.13.5, Node v22.22.2, pip 25.1.1.
  MISSING: Playwright + Chromium. Invoke: single-line `exec` (newlines rejected), hard `--timeout`.

## Lessons / improvements log (append each pass)
- iter1 (15:43): NemoClaw sandbox probed; integration path found. No code change yet.
- iter-deploy (00:15): DEPLOYED Railway worker + Vercel frontend. Fixed Remotion concurrency=8→50% (2-core box). Flagged InsForge ~4min cold-start timeout window (transient, recovered).
- iter-deploy2 (00:24): concurrency fix worked. Cloud render fails on the WALKTHROUGH mp4 — ffprobe `-select_streams a:0` exits 1 (amd64 only).
- iter-walkfix (00:30): ROOT CAUSE = walk_native.py assembled walkthrough with `-an` (no audio). FIX: mux silent anullsrc stereo (`-c:a aac -shortest`). Railway redeploying.
- iter-frontend (01:00): Dennis drove the LIVE app + flagged the logo. Fixed: (a) demo auto-login (AuthProvider auto-signs-in shared demo@walk.studio → no sign-in friction); (b) renamed Vercel project web→walkstudioprojects (clean URL, needed vercel.json framework pin); (c) canonical cursor-mark logo replaces the "W" badge; (d) activity classifier over-broad "stripe" cue removed (run.js, staged — needs a worker rebuild to deploy). VERIFIED full flow live: composer→Build→run page→Railway worker claims it→Nemotron plans→activity streams. OPEN: Build button looks disabled. GITHUB BACKUP set up: hosted-saas branch pushed to denniswanglabs/walk-studio with the whole cloud build. Worktree is now canonical + self-sufficient.
