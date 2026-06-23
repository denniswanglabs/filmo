# Self-improving loop — state (read FIRST on each loop firing)

_Self-paced /loop. Mission: drive Walk Studio to hackathon-ready, improving each pass.
$0 mock builds only; work on BRANCHES (main = untouched local fallback); never commit
(Dennis gates). NemoClaw ops: single-line `exec`, hard `--timeout` + `perl -e 'alarm N'`,
`dangerouslyDisableSandbox` (NemoClaw ops die under the Bash sandbox)._

## Mission order
1. **NemoClaw FIRST** (Dennis requirement — the NVIDIA story): wire the app-walkthrough/
   site-capture to run INSIDE the `promo-agent` NemoClaw sandbox. Keep OpenRouter for the
   Nemotron planner (NemoClaw is the execution SANDBOX, not the brain). Frame: "plans on
   Nemotron 550B via OpenRouter, navigates your product in a NemoClaw sandbox, paid on Stripe."
2. Then **build→judge→fix→log** cycles across target brands: Stripe, Linear, Notion, Vercel,
   Beside, Ashlar. Each pass: build $0 mock → ffmpeg contact sheet → JUDGE THE WHOLE VIDEO
   scene-by-scene (not one frame) + catch reliability flakes → fix the highest-impact issue
   on a branch → append the lesson below. Improving, not just logging.
3. PAUSE at deploy gates (Railway `up` / Vercel = Dennis's account actions).

## NemoClaw integration — path (discovered iter 1)
- Sandbox `promo-agent` is healthy: Linux, Python 3.13.5, Node v22.22.2, pip 25.1.1.
  MISSING: Playwright + Chromium (needs install; sandbox has pypi/npm/brew policies).
- Invoke: `nemoclaw promo-agent exec --timeout <s> -- <SINGLE-LINE cmd>` (newlines are
  rejected → one line with `;`). exec works.
- NEXT (iter 2): install Playwright + Chromium in the sandbox
  (`pip3 install playwright; playwright install chromium` via exec, generous timeout),
  then run a small capture there and pull frames back. Then wire it as a guarded
  walkthrough/capture path in the pipeline (branch), falling back to native Playwright
  (`walk_native.py`) when the sandbox is unreachable.
- Cloud wrinkle: NemoClaw runs locally (:10254); the cloud Railway worker can't reach it →
  the DEMO (produced locally) uses NemoClaw; the hosted worker keeps the Remotion walkthrough.

## What's already DONE (don't redo)
- InsForge backend live (free tier fine). Worker PROVEN end-to-end + containerized
  (`walk-worker:dev` delivers in-container). Frontend built+verified (`walk-studio-cloud/web/`).
  hosted-saas worktree at `~/Desktop/Projects/Hackathons/walk-studio-hosted` (worker/ + Dockerfile).
- Pipeline fixes already on the hosted-saas branch: edge-tts retry (adapters._vo_edge).

## Lessons / improvements log (append each pass)
- iter1 (15:43): NemoClaw sandbox probed; integration path found (install Playwright+Chromium, exec single-line). No code change yet.
- iter-deploy (00:15): DEPLOYED Railway worker + Vercel frontend. Found 2 cloud issues: (1) Remotion `--concurrency=8` fails on Railway's 2-core box ("concurrency > CPU cores") → fixed to `50%` on hosted-saas branch (main keeps 8); (2) InsForge free-tier had a ~4min unresponsive/timeout window (transient, recovered; worker rode through via SDK retries) — demo-reliability risk, watch for recurrence / consider $25 Pro. Railway redeploying with the concurrency fix.
- iter-deploy2 (00:24): concurrency fix WORKED (rendered to frame 604/~900). NEW cloud bug: Remotion render fails on the WALKTHROUGH video asset — `getAudioChannelsAndDuration` ffprobe (`-select_streams a:0`) exits 1 on `walk-<run>-walkthrough-demo.mp4` (+ a localhost:3000/proxy 500). Renders fine on local arm64, fails on Railway amd64 → the walkthrough clip the cloud produced has no audio stream / is malformed for x64 ffprobe. FIX CANDIDATES (next pass): (a) add a silent audio track when assembling the walkthrough mp4 (ffmpeg `-f lavfi -i anullsrc ... -shortest`); (b) check the cloud CAPTURE actually produced a valid walkthrough (Playwright on Railway IPs may differ); (c) <OffthreadVideo muted> / drop audio probing. Deploys are LIVE; this is the one blocker to full cloud delivery.
- iter-walkfix (00:30): ROOT CAUSE of the cloud render fail = walk_native.py assembled the walkthrough mp4 with `-an` (no audio) → Remotion's linux-x64 ffprobe `-select_streams a:0` errors (arm64 tolerated it). FIX applied: mux a silent anullsrc stereo track (`-c:a aac -shortest`). Railway redeploying with it. NEXT LOOP PASS: (1) confirm the redeploy reaches SUCCESS; (2) enqueue a cloud mock build (ENQ via worker/enqueue.js) + poll runs.status to delivered → if delivered, the cloud loop is GREEN end-to-end; (3) then NemoClaw sandbox install + the per-brand build/judge/fix cycles. Watch InsForge for the cold-start timeout recurrence.
