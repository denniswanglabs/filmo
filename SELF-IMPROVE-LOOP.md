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

## COMPETITIVE CONTEXT (NEW 01:20 — Dennis surfaced a rival)
A rival entry **VED / TechGyro** (Karthik @trackkartmac) hit the SAME hackathon: brief →
generative film (Nano Banana Pro + Veo) → **authorize-and-capture** bill to the customer,
sandboxed in NemoClaw on Nemotron-3. Their edges: (a) a complete NemoClaw security NARRATIVE
(keys never leave backend, masked proxy token, egress allow-list); (b) demo polish + cinematic
spectacle. Our edges: (a) the Stripe axis — **Issuing + real-time authorization decisioning**
where the agent's own budget brain DECLINES an over-budget charge, no human (rarer + more
agentic than authorize-and-capture); (b) real-product grounding (commerce, not art). The two
top loop priorities below exist to CLOSE THEIR GAPS and SHIP OUR KNOCKOUT. Live demo to
ground-truth (read-only): https://ved.techgyro.ovh/ + /hermes-admin/ , login judge / judge2026.

## Mission order (each firing: pick the highest-impact open item, do it, BACK IT UP)
0a. **TEE UP THE REAL STRIPE DECLINE (highest leverage — our knockout vs VED).** The real-time
   Issuing authorization decline is currently a SIM (`iauth_sim_…`), dry-run-verified only
   (OVERNIGHT-LOG.md:96, TECHNICAL-ROADMAP.md item 1.1). Convert to a REAL declined
   `issuing_authorization` so Dennis's morning is JUST `stripe login`. Loop does the $0,
   no-credential prep: re-verify orchestrator→`runs/active_budget.json` bridge end-to-end in
   dry-run; confirm the `--stripe-live` path routes the over-budget cinematic charge through the
   listener (not in-process `money.authorize()`); confirm `stripe_webhook.py --dry-run` decides
   correctly against the live budget file; write/refresh `.handoff-webhook-bridge.md` with the
   EXACT 4 commands Dennis runs (`stripe login` → `python3 stripe_webhook.py` → `stripe listen
   --events issuing_authorization.request` → over-budget `--mode real --stripe-live` run). DON'T
   run `stripe login` (Dennis's credential step). Goal: his 5 min captures a genuine decline.
0b. **CLOSE THE NemoClaw NARRATIVE GAP (vs VED's security story).** Finish the sandbox capture
   path (see item 3) AND write the talking points so we can say the same true things: provider
   keys stay backend-side, sandbox runs behind an egress allow-list, Nemotron planning via
   OpenRouter is separate from the NemoClaw execution sandbox. Put them in a SECURITY-NARRATIVE
   section of HANDOFF/DEMO-BEAT-SHEET. Only claim what's actually true — verify before writing.
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
