# PROOF: a genuine Hermes agent drove a complete video-production job (mock, $0)

This is the compliance-gap-closing artifact. It records a real, autonomous
`hermes chat` run in which the **Hermes agent runtime** — reasoning on the FREE
NVIDIA Nemotron model — drove a complete video-production business loop:
**PLAN → PRICE → GATE → PRODUCE → P&L**, calling `producer.py` / `plan_job.py` /
`orchestrator.py` as its **tools**. The deterministic engine was NOT rewritten;
the agent pulled the trigger on it. No `python3 build_runner.py`; no dashboard
`subprocess.Popen`.

- **Session ID:** `20260620_000754_46aa2a`  (resume: `hermes --resume 20260620_000754_46aa2a`)
- **Wall-clock:** 4m 33s · 9 model API calls · 8 tool turns · 16 tool calls
- **Raw verbose log:** `evidence/hermes-driven-run/session-raw.log`
- **Run artifact:** `runs/hermes-driven-01/` (`ledger.json` + `final.mp4` + `plan.json` + clips + `voiceover.mp3`)

## The brain (proof it is FREE — no paid provider)

Every reasoning turn ran on the free NVIDIA NIM, verified from the log:
```
model=nvidia/nemotron-3-super-120b-a12b
provider=nvidia  base_url=https://integrate.api.nvidia.com/v1
```
`~/.hermes/config.yaml` (lines 403-406):
```
model:
  base_url: https://integrate.api.nvidia.com/v1
  default: nvidia/nemotron-3-super-120b-a12b
  provider: nvidia
```
This is the free `build.nvidia.com` NIM Super-120B — NOT the paid OpenRouter Ultra.
(`OpenRouter via pool` lines in the raw log are Hermes' startup capability-probe for
vision/web_extract aux tools, which were never invoked; the only aux task that ran,
`title_generation`, also resolved to the same free Nemotron model.)

## How it was launched (the exact command)

```bash
cd /Users/dennis/Desktop/Projects/Hackathons/hermes-video-agent
hermes chat -v --yolo --max-turns 40 -s producer-brain -q "<brief>"
```
- `-s producer-brain` preloads the skill the agent followed.
- `-v` so the agent's reasoning + tool calls are captured to the log.
- `--yolo` is required for a NON-interactive run: `config.yaml` has
  `approvals.mode: manual`, so without it the agent's shell tool calls would block
  on a TTY approval prompt. Safe here because the whole run is mock / $0.
- Brief: produce a full promo + walkthrough for `https://stripe.com`,
  goal "30-second explainer plus a short walkthrough of how to find your API keys",
  30s, margin 0.6, `RUN_ID=hermes-driven-01`, mock mode only.

## The agent's trajectory (its reasoning + tool calls, in order)

The agent worked the `producer-brain` AUTONOMOUS RUN runbook step by step. Each
`$` line below is a real tool call the agent issued (verbatim from the log):

1. **Orient.** `[thinking]` enumerates the 5 steps; lists the project dir.
   `$ ls -la /Users/dennis/Desktop/Projects/Hackathons/hermes-video-agent/`

2. **PLAN (Nemotron).** The agent calls the planner tool, which sends the brief to
   Nemotron and returns a schema-validated 5-scene plan:
   ```
   $ python3 plan_job.py --url "https://stripe.com" \
       --goal "30-second explainer plus a short walkthrough of how to find your API keys" \
       --duration 30 > /tmp/producer-plan.json
   ```
   Then `read_file /tmp/producer-plan.json` to confirm the plan
   (title-open · cine-establish[seedance_2_0] · walkthrough · cine-hero[gpt_image_2] · title-close).

3. **PRICE (deterministic engine, as a tool).**
   ```
   $ python3 producer.py estimate --plan /tmp/producer-plan.json
   ```
   → COGS 32¢, suggested price 80¢ (60% margin), production budget locked at 32¢.

4. **GATE the money-shot (live budget judgment, on camera).** The agent set the
   deterministic cost stub and called the gate explicitly to show the verdict:
   ```
   $ PRODUCER_COST_STUB='{"seedance_2_0": 22, "gpt_image_2": 7, "__default__": 10}' \
       python3 producer.py gate --plan /tmp/producer-plan.json --scene cine-hero \
       --proposed_cost_cents 7 --spent_cents 22
   $ ... producer.py gate --plan ... --scene cine-establish \
       --proposed_cost_cents 22 --spent_cents 0
   ```
   → both APPROVE within remaining budget. (The decline beat is reproducible by
   raising a scene's proposed cost above the remaining budget — see demo-3-decline /
   demo-4-vo-over for the canonical money-shot ledgers.)

5. **PRODUCE (the engine is the agent's tool — mock, $0).**
   ```
   $ PRODUCER_PACE=0 PRODUCER_COST_STUB='{"seedance_2_0": 22, "gpt_image_2": 7, "__default__": 10}' \
       python3 orchestrator.py --plan /tmp/producer-plan.json --run-id hermes-driven-01 \
       --mode mock --vo edge --overlays studio          # 21.3s
   ```
   The orchestrator re-validated, re-locked the budget, ran the per-scene gate for
   every scene, **simulated** the Stripe earn/card (no real money), authored + rendered
   the Remotion title scenes, rendered storyboard placeholders for the
   cinematic/walkthrough scenes, synthesized free `edge-tts` VO, and stitched a verified
   30.0s `final.mp4`.

6. **DELIVER + P&L.** The agent `read_file runs/hermes-driven-01/ledger.json` and
   reported the P&L (below).

## What the agent reported (its final message)

```
🎬 PRODUCTION SUMMARY
- Company: Stripe (https://stripe.com)
- Goal: "30-second explainer plus a short walkthrough of how to find your API keys"
- Target duration: 30s → Actual: 30.0s
- Run ID: hermes-driven-01
- Mode: mock (zero spend — no Higgsfield/ElevenLabs/walk-agent calls fired)
- Overlay set: studio (Remotion-authored titles)
- Voice provider: edge-tts (free, offline)

Scene execution (all in plan order, under budget gate):
1. ✅ title-open     — free Remotion title
2. ✅ cine-establish — approved Higgsfield seedance_2_0 (simulated)
3. ✅ walkthrough    — free NemoClaw walkthrough
4. ✅ cine-hero      — approved Higgsfield gpt_image_2 (simulated)
5. ✅ title-close    — free Remotion title
6. ✅ voiceover      — approved edge-tts synthesis
7. ✅ final stitch   — ffmpeg concat + VO mux (verified)

P&L:  price 80¢ · COGS spent 32¢ · gross profit 48¢ · margin 60.0% · declines 0

NVIDIA USAGE DISCLOSURE
- Planner: Scene plan generated by NVIDIA Nemotron-3-Super-120B-A12B
- Walkthrough segment: Nemotron inside a NemoClaw sandbox (walk-agent, in real mode)

ARTIFACTS DELIVERED
- Final video: runs/hermes-driven-01/final.mp4 (H.264/AAC, 30.0s, audio, all scenes)
- Audit trail: /tmp/producer-plan.json + runs/hermes-driven-01/ledger.json
```

## Honesty notes (for the on-camera VO — do not overclaim)

- **Mock mode.** Cinematic scenes are storyboard placeholders, not real Higgsfield
  generations; the walkthrough is a placeholder card, not a live NemoClaw sandbox run.
  A real-media (paid) version is a SEPARATE, later step.
- **The Stripe authorizations in this ledger are `simulated: true` (`iauth_sim_…`).**
  Do not narrate them as real Stripe declines/approvals. Earn here is `dev_mode`
  (no real Stripe session created on this autonomous path).
- **What is genuinely real and load-bearing here:** the Hermes runtime drove the run;
  the scene plan was produced by a live Nemotron call; the budget gate / pricing math
  ran as the agent's tools; the Remotion titles and the stitched MP4 are real files.
