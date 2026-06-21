# Testing the Hermes producer brain — prove the judgment calls, spend $0

This harness proves the agent does the right thing — plans, prices, and **gates every
spend** (approve / downgrade / decline) — without spending a cent. Real generations
are mocked; the voiceover uses **edge-tts** (free) in place of ElevenLabs; the
Higgsfield **free cost preview** is real (it never generates); ffmpeg stitching is
real, so every test still yields a genuine, playable MP4.

```
./run_all_tests.sh            # everything below, $0
./run_all_tests.sh --no-eval  # skip the live-Nemotron part (offline)
```

## Three layers

**1. Engine — `tests/test_producer.py` (13 tests, deterministic, offline).**
Unit-tests `producer.py`: the cost estimate, the COGS→price formula, the per-scene
budget split, and every branch of the budget **gate** — approve, downgrade (a
seedance video → a gpt_image_2 still), decline (already on the cheapest model), and
the locked-budget override. Pricing is made deterministic with `PRODUCER_COST_STUB`
(no Higgsfield CLI, no network).

**2. Orchestrator — `tests/test_orchestrator.py` (6 tests, mock mode, $0).**
Runs the WHOLE loop (`orchestrator.py`) on crafted plans in `tests/scenarios/` and
asserts the per-scene judgment + the P&L. Real edge-tts + real ffmpeg run, so each
test also produces a real `final.mp4`. Covered:
- **approve** — comfortable budget, everything generated, margin at target.
- **downgrade** — an over-budget seedance hero auto-switches to a cheaper still and
  STILL ships (`seedance_2_0 → gpt_image_2`, spent at the cheaper price).
- **decline (the money-shot)** — an over-budget hero is auto-declined: not generated,
  `would_have_cost` recorded, overage avoided, the video still ships at a *higher*
  margin, and a Stripe-shaped authorization with `approved:false` is attached.
- **VO over budget** — the voiceover itself is declined; the video ships silent.
- **invalid plan** — rejected before any spend.

**3. Live brain — `hermes_judgment_eval.py` (7 scenarios, FREE Nemotron).**
The deterministic tests prove the *policy*; this proves the *LLM that runs the studio*
agrees with it. Each scenario is put to `nvidia/nemotron-3-super-120b-a12b` (the free
build.nvidia.com brain) and scored against `producer.py`'s golden verdict. Latest:
**7/7 (100%)** — including the money-shot decline (where an LLM is most tempted to
just spend). Needs `NVIDIA_API_KEY` (`source ~/.zshrc`). $0 on the free tier.

## How a decline is triggered deterministically
Budget == planned COGS by construction, so a decline only happens on a **cost
overrun** (a scene's real cost > its plan estimate — realistic; Higgsfield prices vary
by prompt/model). Two env levers make this exact and offline:
- `PRODUCER_COST_STUB` — planning prices (sets the budget). JSON `{model: credits}`.
- `PRODUCER_PRODUCTION_COST_STUB` — production-time cost per scene (the overrun). JSON
  `{scene_id: cents, "__voiceover__": cents}`. This is what pushes a scene over budget
  so the gate fires.

## The dashboard ("Producer Console")
`python3 dashboard/serve.py` → open **http://localhost:3030** in Safari. Reads each run's
`runs/<id>/ledger.json` (schema in `LEDGER.md`) and shows: the slate header, a printed-tape
**P&L receipt** (the decline line struck in red), an **NLE filmstrip** budget-gate timeline
(approve/downgrade/decline; the decline = a red CUT gap), the **Studio view**, the final
cut, and the Stripe/events log. Four demo runs ship in `runs/` (one per branch);
`runs/demo-3-decline` is the money-shot and auto-opens.

## Studio overlays — watch the agent write the motion graphics
`--overlays studio` makes the agent generate a real Remotion component per title/MG scene
(`remotion_codegen.py` → `studio/`) and render it (≈2.4s/clip). The generated `.tsx` source
is stored in the ledger; the dashboard's **Studio view** types it out with live syntax
highlighting, then plays the rendered clip (shown code == rendered clip). cinematic/walkthrough
render as a labelled animatic storyboard. The four demo runs use `--overlays studio`; the test
suite uses the default `--overlays mock` (instant color cards) so tests stay fast. Needs node +
the `studio/node_modules` symlink (to the shared Remotion install).

## Flipping to a real, paid run
Same orchestrator, two flags:
```
python3 orchestrator.py --plan <plan.json> --mode real --vo elevenlabs [--stripe-live]
```
- `--mode real` → real higgsfield-scene (PAID), walk-agent, motion-graphics.
- `--vo elevenlabs` → real ElevenLabs (PAID) instead of edge-tts.
- `--stripe-live` → real Stripe test-mode Issuing card + authorizations (see
  `STRIPE-SETUP.md`). Without it, Stripe is simulated (the brain's verdict, mirrored).
Everything else — the planning, pricing, gating, P&L, ledger, dashboard — is identical.
```
