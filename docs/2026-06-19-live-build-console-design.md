# Live Build Console — design spec (2026-06-19)

Turn the Producer Console dashboard from a post-hoc ledger VIEWER into a live
"watch the agent build your video" console.

## Decisions (locked)
- **Purpose:** both — demo the hackathon now, architected to productize.
- **Timing:** real-time, made watchable — run the REAL pipeline; the console streams
  genuine progress; the slow stretches get accelerated/cut for the 1–3 min submission.
- **Agent-click pane:** live page screenshots + an action feed ("clicked Developers").
  Achievable from data the pipeline produces. True sandbox video-stream = later stretch.
- **Input:** a command bar — paste a company URL + optional goal → Build. Not yet conversational.
- **Safety default:** Build runs in **mock+studio mode ($0)** unless a `real` toggle is set.
  No surprise paid generation. Real mode = explicit opt-in.

## Flow (what the user watches)
1. Paste URL + goal → **Build**.
2. **PLAN** — the agent (Nemotron) reads the brief and emits a scene plan; the console
   shows "visiting <url> · planning storyboard…", then the **storyboard scenes pop up**.
3. **PRICE** — producer.py estimate; the P&L ticker appears (price, budget, margin).
4. **PRODUCE** — each scene card transitions queued → working → done / declined, live.
   The **agent-browser pane** shows the walkthrough navigation (screenshots + action feed).
   The budget gate fires visibly (a scene goes red "declined" = the money-shot).
5. **DELIVER** — the finished video appears; the run becomes a normal completed ledger.

## Architecture (small, well-bounded units)
- **`orchestrator.py` (incremental):** writes `ledger.json` after every step, adds a
  top-level `phase` (planning|pricing|earning|producing|voiceover|stitching|delivered)
  and a per-scene `status` (queued|working|produced|declined). A scene is set `working`
  before its generation and updated after. Same ledger schema, just written live + with
  status/phase fields. Back-compat: completed runs unchanged.
- **`plan_job.py`:** URL + goal → a validated `plan.json` via the free Nemotron planner
  (reuses `validate_planner` prompt + schema). The "agent decides the storyboard" step.
- **`build_runner.py`:** orchestrates plan → orchestrate() for one job into `runs/<id>/`,
  setting `phase`/`status` as it goes. Launched as a subprocess by the server.
- **`dashboard/serve.py` (upgraded):** add `POST /api/build {url,goal,mode}` → spawns
  `build_runner.py`, returns `run_id`; `GET /api/active` → the currently-building run_id;
  keep static + Range serving. Stdlib only.
- **`dashboard/` live view:** a "Build" command bar + a live panel that polls
  `/runs/<id>/ledger.json` (~1s) and renders the storyboard (scenes pop in, states
  animate), the action feed, the agent-browser pane, and the P&L ticker. On `delivered`
  it swaps to the existing detail view. Dark Producer Console skin.

## Out of scope (later)
- True live browser video-stream from the sandbox.
- Conversational refinement / multi-turn chat.
- Multi-tenant accounts / abuse + spend caps for public use.
