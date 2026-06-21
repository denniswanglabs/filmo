# Production-Readiness Review — Hermes Video Agent

_Read-only audit, 2026-06-19. Reviewer: backend/architecture pass over the producer-brain
pipeline (plan → price → produce → deliver), the ledger/dashboard model, security, money
correctness, reliability, observability, tests, and ops._

**Scope note.** This audits durable architecture for a *production* product, not the
hackathon demo. The hackathon framing (mock-by-default, $0, Stripe simulated, Dennis's
submission video carries presentation) is already strong and is NOT what this critiques. A
Stripe pay-gate is being added concurrently to `build_runner.py` + `dashboard/*` + `ledger.py`;
"no payment gate exists" is intentionally NOT flagged here. Severity legend:
**BLOCKER** (must fix before any real user/network exposure) · **HIGH** · **MEDIUM** · **LOW**.

The system is well-built for what it is: a single-operator, single-tenant, localhost demo
engine with genuinely careful money-safety habits (no-retry on paid calls, key-by-presence,
test-only earn guard, locked budget). The gaps below are almost all "this was designed for one
trusted user on one Mac" assumptions that break the moment it is multi-user, networked, or
restarted.

---

## 1. ARCHITECTURE & DATA FLOW

### 1.1 Concurrent builds corrupt each other through a single shared TSX file — BLOCKER
`adapters.py:32` `STUDIO_ACTIVE = studio/src/generated/active.tsx` is a **single global path**.
Every studio render does `open(STUDIO_ACTIVE, "w")` then `remotion render … Scene …` from that
same file (`adapters.py:250-258`). Two concurrent builds (or even two scenes of one build if it
were ever parallelized) will interleave: build A writes its component, build B overwrites it,
build A's `remotion render` then renders **B's scene into A's clip**. The output is silently
wrong, not an error. `serve.py:_api_build` spawns an unbounded number of these via
`subprocess.Popen` with no lock, no queue, no per-run scratch dir. The dashboard even resumes
*one* active build (`app.js:init` → `d.active[0]`) but the backend cannot stop a second POST.
- **Fix:** render from a per-run temp file (`run_dir/_active_<scene>.tsx`) and pass it to
  Remotion explicitly, OR serialize builds behind a single-worker queue. The per-run-file route
  is the smaller change and also removes the global mutable file from version control churn.

### 1.2 No concurrency control on builds at all — HIGH
`POST /api/build` (`serve.py:106`) fires a detached `subprocess.Popen(..., start_new_session=True)`
per request with no cap. N requests = N orchestrators competing for CPU, ffmpeg, the shared
Remotion install, and the active.tsx file (1.1). For a real product this needs a job queue with
a concurrency limit and backpressure (return 429 / "queued") — not fire-and-forget subprocesses.

### 1.3 Ledger-JSON-as-source-of-truth + polling is fine at this scale, with caveats — MEDIUM
The model (orchestrator writes `runs/<id>/ledger.json` incrementally; dashboard polls every 1s)
is reasonable for a demo. The atomic `os.replace(tmp, path)` in `ledger.py:96` correctly
prevents a *torn* read (poller never sees half-written JSON). But:
- **Lost updates / no concurrency on `index.json`.** `orchestrator._update_index` (line 411) and
  `serve.py:_api_active` both walk `runs/` and the former rewrites `index.json` with a plain
  `open(...,"w")` — **not** atomic, and two finishing builds racing `_update_index` can clobber
  each other's write or read a partial file. Use the same tmp+`os.replace` pattern as the ledger.
- **Whole-file rewrite every poll-driving event.** Each `flush()` re-serializes and rewrites the
  entire ledger. Fine at 5 scenes; at hundreds of scenes / long event logs this is O(n) writes of
  O(n) data = O(n²) and the event list grows unbounded. Acceptable now; will not scale.
- **1s polling, no ETag/Last-Modified short-circuit on the JSON.** `Cache-Control: no-store`
  (`serve.py:236`) forces a full re-download of every ledger each second per open tab. Fine for
  one local tab; wasteful at any fan-out. A long-poll or SSE/websocket is the real-product answer.

### 1.4 Server restart mid-build orphans the run and the subprocess — HIGH
Builds are detached (`start_new_session=True`), so killing/restarting `serve.py` leaves the
`build_runner.py` child running but **un-reattachable** — and conversely, if the *child* is killed
the ledger is frozen at whatever phase it reached with `status:"running"` forever. There is no
heartbeat, no "stale running run" reaper, and `_api_active` will report a dead run as active
indefinitely. The dashboard will poll a frozen ledger with no timeout/failure transition.
- **Fix:** write a `pid` + `heartbeat_ts` into the ledger; have `_api_active` treat a run whose
  heartbeat is older than ~N seconds as `failed`/`stale`; add a startup sweep that marks orphaned
  `running` ledgers failed. (The `build_runner` exception handler at `build_runner.py:53` only
  catches in-process exceptions — a `kill -9` or restart writes nothing.)

### 1.5 `producer.py` invoked as a subprocess per scene — LOW (perf), MEDIUM (coupling)
`orchestrator.run_producer` shells out to `python3 producer.py …` (line 53) for every estimate and
every gate (twice on a downgrade). For a 5-scene plan that's ~8 interpreter spawns. It's clean for
"the brain is a separate tool" framing but it's pure overhead and it swallows the real failure mode
(a non-zero exit becomes a generic `RuntimeError` with only `stderr` — see 4.x). Importing
`producer` as a module and calling `cmd_estimate`/`cmd_gate` directly would be faster and let the
orchestrator distinguish error types. Keep the CLI for the "it's a real skill" story; call in-proc
for the hot path.

---

## 2. PERSISTENCE & STATE

### 2.1 JSON-files-on-disk is the whole datastore — HIGH (for "at scale")
There is no database. State = `runs/<id>/{ledger.json, plan.json, build.log, clips/…}` +
`runs/index.json`. This is fine for a demo and a handful of runs but has no:
- indexing/query (the dashboard re-reads and re-parses **every** ledger to build `index.json` on
  every finish, `orchestrator.py:414`; `_api_active` does the same per request, `serve.py:93`);
- retention/cleanup (runs accumulate forever; `clips/` + `final.mp4` are large);
- multi-host story (everything assumes one local filesystem).
- **Fix for product:** SQLite at minimum (one row per run, ledger blob + indexed status/created_at),
  object storage for media, and a periodic prune. Keep the JSON ledger as the in-run scratch if you
  like, but don't make `index.json` a full-table-scan rebuild.

### 2.2 Run-index integrity depends on a successful finish — MEDIUM
`index.json` is only rewritten at the *end* of `orchestrate` (line 395). A run that dies mid-flight
never enters the index, so the rail won't list it even though `runs/<id>/ledger.json` exists with
`status:"running"`. `_api_active` is the only thing that surfaces in-flight runs, and only if their
status is exactly `"running"`. Combined with 1.4, a crashed build is invisible in the rail and
"stuck active" in the poller. Rebuild the index from a directory scan on server start, and include
running/failed runs.

### 2.3 `created_at` is null for live builds — LOW
`build_runner` constructs the `Ledger` with no `now=` (it isn't threaded through `orchestrate`'s
default `now=None`), so every live build has `created_at: null` (confirmed in `runs/index.json`).
The rail can't sort by time. Pass a real timestamp in the live path.

### 2.4 No schema migration path — LOW
`schema_version: 1` is written but never read/checked anywhere. The day the ledger shape changes,
old runs and the dashboard diverge silently. Add a read-time version check (at least a warning).

---

## 3. SECURITY  (ranked by severity)

### 3.1 Unauthenticated `POST /api/build` spends money / runs code — BLOCKER
`serve.py` binds `127.0.0.1:3030` (good — localhost only) but has **zero auth** (`grep` confirms no
token/origin/CSRF check). Anyone who can reach the port — any local process, any site via DNS-rebind
/ a CORS-less `fetch` from a malicious page the user visits (the endpoint sends no CORS headers but
*simple* POSTs with `Content-Type: application/json` are still preflighted, so DNS-rebinding is the
real vector), or anyone if it's ever bound to `0.0.0.0` — can POST `{url, goal, mode:"real"}` and
**trigger real Higgsfield/ElevenLabs spend** and arbitrary long-running subprocesses. For a product
this is the #1 issue: the build endpoint is an unauthenticated "spend money + run jobs" trigger.
- **Fix:** require an auth token (even a static bearer for single-user), check `Origin`/`Host`
  against an allowlist to defeat DNS-rebinding, and **never** expose `mode:"real"` without an
  explicit server-side authorization step. Keep the bind on loopback.

### 3.2 The `mode:"real"` flag is client-controlled — BLOCKER (with 3.1)
`serve.py:118` reads `mode` straight from the request body; `build_runner` then runs the genuine
paid pipeline. Real spend should never be a client-set boolean on an unauthenticated endpoint. Gate
real mode behind server-side auth + an explicit confirmed budget, independent of the request body.

### 3.3 Path traversal in the custom static/Range server — HIGH (verify)
`Handler` subclasses `SimpleHTTPRequestHandler` and reuses `self.translate_path` (`serve.py:154`),
which *does* normalize `..` and strips query/fragment — so the classic `GET /../../etc/passwd` is
handled by the stdlib. **However**, this handler overrides `send_head` and opens the file itself with
`open(path,"rb")`, and serves the **entire project root** (`PROJECT_ROOT`, line 31), not a public
subdir. That means `~/.hermes/.env` is not under root, but **everything in the repo is web-readable**:
`build.log` files (which may contain printed env/keys from a subprocess), `plan.json`, source code,
`.handoff-*.md`. Confirm `translate_path` is actually called for every served file (it is, via
`self.path` → `translate_path`) and add an explicit `os.path.realpath(...).startswith(realpath(root))`
guard in `send_head` as defense-in-depth, plus serve only `dashboard/` + `runs/` rather than the whole
project root. **Do not serve the repo root in production.**

### 3.4 Command-injection surface in `/api/build` — MEDIUM (currently mitigated, fragile)
`serve.py:125` builds a shell string for `zsh -lc` from `url`, `goal`, `run_id`. It *does* use
`shlex.quote` on `PROJECT_ROOT`, `url`, `goal`, `run_id` (good), and `mode`/`duration` are coerced
(`"real" if … else "mock"`, `int(...)`). So as written it is **not** trivially injectable. The risk is
fragility: this is hand-rolled shell-string construction one careless edit away from dropping a quote.
`url`/`goal` then flow unbounded into the ledger, the Nemotron prompt, and ffmpeg/Remotion text.
- **Fix:** drop the shell entirely — `subprocess.Popen([sys.executable, "build_runner.py", "--url",
  url, …])` and source the env in Python (read `NVIDIA_API_KEY` from a config) instead of relying on
  `zsh -lc` to source `~/.zshrc`. Validate/limit `url` (scheme allowlist, length, host shape) and
  `goal` length before accepting.

### 3.5 No input validation/limits on `url`/`goal`/`duration` — MEDIUM
`url` only gets `startswith(("http://","https://"))` after a prepend (`serve.py:115`); `goal` is
unbounded; `duration = int(body.get("duration") or 30)` accepts any int including negative/huge
(a negative duration flows into `_template_plan`'s `max(6, …)` so it's clamped there, but
`duration` also goes to ffmpeg `-t`/frame math elsewhere). The planner sends `url`+`goal` to
Nemotron with no length cap → prompt-cost / prompt-injection exposure (a hostile `goal` can try to
steer the model). Add: scheme allowlist, max lengths, duration bounds (e.g. 5–180s), and treat
`url`/`goal` as untrusted in the prompt (the system prompt is firm, but a real product should fence
user content).

### 3.6 SSRF via the walkthrough/real path — MEDIUM (real mode)
In `--mode real`, `generate_walkthrough` (`adapters.py:189`) hands the user-supplied `url` to the
walk-agent which navigates a real browser to it; the cinematic/earn paths fetch hosted assets with
`curl -fsSL <url>` from Higgsfield responses. A user-controlled `company_url` driving a server-side
browser is a textbook SSRF / internal-network-probe vector for a hosted product. Restrict to public
http(s), block private IP ranges, and run the browser in an egress-restricted sandbox.

### 3.7 Stripe key handling is genuinely good — LOW (keep it)
`stripe_money.detect_key` reads `~/.hermes/.env` then env, classifies by prefix, and **never prints
the value** (`stripe_money.py:33-53`); `_secret()` is only used inside the request header.
`stripe_earn._assert_test_key` hard-refuses live keys and asserts `livemode==false`
(`stripe_earn.py:49,138`). This is the right posture. Two notes: (a) `detect_key` calls
`_read_hermes_env()` **three times** per detection (lines 42-44) — minor; (b) `build.log` is created
by `serve.py:123` and is web-served (3.3) — if the real pipeline ever prints a key to stdout it lands
in a web-readable file. Audit that no subprocess echoes secrets, and move `build.log` out of the
served tree.

### 3.8 Webhook endpoint has no signature verification — HIGH (when wired)
`stripe_webhook.py:69` parses the POST body as JSON and acts on it **without verifying the Stripe
`Stripe-Signature` header**. As designed it sits behind `stripe listen` (a trusted local tunnel), but
if ever exposed, anyone can POST a fake `issuing_authorization.request` and drive approve/decline. If
this becomes a real endpoint, verify the webhook signature (HMAC over the raw body with the endpoint
secret) before trusting `event`.

---

## 4. ERROR HANDLING & RELIABILITY

### 4.1 Nemotron failure modes are handled, but truncation can pass silently — MEDIUM
`plan_job._plan_with_nemotron` (`plan_job.py:38`) does one repair retry then falls back to the
deterministic template on **any** exception — good resilience. But `validate_planner.call_model` uses
`max_tokens:8000` and only *prints* a warning to stderr on `finish_reason != "stop"`
(`validate_planner.py:117-119`); it still returns the (possibly truncated) content. `extract_json`
takes first-`{` to last-`}`, so a truncated-but-bracket-balanced object parses into a **wrong** plan
that may still pass `validate_plan` (which checks shape, not duration sums in the orchestrator path —
`strict_durations=False`). Net: a partially-generated plan can ship as if valid. Treat
`finish_reason=="length"` as a hard failure → fall back to template; or raise.

### 4.2 No timeout/recovery on the live Nemotron call inside a build — MEDIUM
`call_model` uses `urlopen(timeout=300)` — a single planner call can hang up to 5 minutes with the
dashboard showing "planning…" the whole time and no user-visible cancel. The HANDOFF notes the Ultra
model is unusable in loops; Super is the choice, but a 5-minute stall is still a bad UX with no
abort. Lower the timeout for the interactive path and surface a "planner slow, using template"
transition.

### 4.3 ffmpeg/edge-tts/Remotion failures are mostly fatal-to-the-run — MEDIUM
`adapters._run` raises `AdapterError` on non-zero exit; `orchestrate` has **no try/except around the
production loop**, so a single ffmpeg/edge-tts/studio-render failure aborts the whole build. The only
catch is in `build_runner.run` (line 53) which marks the ledger `failed` and re-raises — so the run
dies, no partial delivery, no per-scene retry. For free/local steps (synth_clip, edge-tts) a transient
failure killing a whole job is harsh. Add per-scene try/except that marks the scene `errored` and
continues (the gate/stitch already tolerate cut scenes), and an explicit retry (the no-retry rule is
correct for *paid* Higgsfield, but free/local steps can safely retry once).

### 4.4 `generate_overlay` silently degrades to a color card — MEDIUM (honesty)
In real mode, if Remotion fails, `generate_overlay` (`adapters.py:232`) swallows the error and ships a
solid color card with a `note`. That's a silent quality regression a user wouldn't notice. `studio_*`
correctly does NOT do this (it raises). Decide the policy and make it consistent; at minimum surface
the degradation as a `gate`/`error` event, not just a buried record field.

### 4.5 Higgsfield real path: no retry (correct) but no partial-failure recovery — MEDIUM
`_generate_cinematic_real` (`adapters.py:115`) submits → waits (up to 20m) → downloads. If the
download `curl` fails after a paid job *succeeded*, the money is spent but the run aborts and the asset
URL is only in a raised exception, not persisted — **paid work is lost**. Persist `job_id`/`asset_url`
to the ledger *before* the download so a failed download is recoverable without re-paying.

### 4.6 Orphaned subprocesses — HIGH (ties to 1.4)
Detached builds (`start_new_session=True`) survive server restart and have no supervision. A
walk-agent run can take 3-5 min and ffmpeg/Remotion are CPU-heavy; nothing tracks, limits, or reaps
them. No PID file, no `wait`, no kill-on-shutdown. A real deployment needs a process supervisor /
job runner.

### 4.7 Idempotency — LOW/MEDIUM
`run_id = build-<slug>-<uuid6>` (`serve.py:120`) is unique per request, so a double-clicked Build
spawns **two** independent runs (and two competing studio renders → 1.1). `apply_real_media` is
idempotent (same filename slot), which is good. The build trigger itself is not idempotent and has no
dedup key. For a product, accept a client idempotency key.

---

## 5. MONEY CORRECTNESS

### 5.1 Pricing/gate logic is sound and well-tested — LOW
`producer.cmd_estimate`/`cmd_gate` are clean: price = `round(COGS/(1-margin))`, budget locked at
COGS, largest-remainder budget split sums exactly (`_distribute`, with the all-zero even-split
branch). The downgrade/decline ladder and the "already on cheapest model → decline not self-downgrade"
guard (`producer.py:310-312`) are correct and covered by `test_producer.py`. The locked-budget pass-
through (`budget_cents`) correctly prevents a mid-job downgrade from silently shrinking the ceiling.
This is the strongest part of the codebase.

### 5.2 Cost-model constants are assumptions, flagged honestly — LOW
`HIGGSFIELD_CENTS_PER_CREDIT = 1.0` and `ELEVENLABS_PER_1K_CHARS_CENTS = 30` are documented guesses
(SCHEMA.md, producer.py:46-52). The Higgsfield *preview* gives real credits, but the credit→USD rate
is hard-coded; ElevenLabs has no preview so VO cost is a pure estimate. For a real P&L these must be
sourced from actual invoices/rate cards. Acceptable for demo, must be real for a business.

### 5.3 Simulated vs real Stripe boundary is clean and honest — LOW (keep)
`StripeMoney(live=…)` only goes live when a key is present (`stripe_money.py:83`); simulated
authorizations are clearly tagged `simulated:true` (line 173) and the design doc's "Reality tag"
(STRIPE-PRODUCER-DESIGN.md:211) explicitly owns that the decline↔Higgsfield-not-charged link is
*modeled, not physical*. The earn (Checkout/Payment Link) and spend (Issuing) sides are correctly
separated into distinct modules. On-screen claims in the dashboard ("simulated" notes in
`declineAuthNote`, `app.js:344`) match reality. This honesty is a strength — preserve it; the only
risk is the UI drifting from the data, so keep `simulated` surfaced wherever a decline is shown.

### 5.4 The decline money-shot does not actually block spend in code — MEDIUM (product honesty)
In the real pipeline the gate decides decline/approve in `producer.py`, and the orchestrator simply
*chooses not to call* `generate_cinematic` on decline. The Stripe authorization is a parallel record,
not the thing that gates the CLI. That's exactly what the design doc says and is fine — but for a
*production* "agent spends under real controls" claim, the Issuing card would need to actually fund the
provider (the doc's stated future state). Until then, keep narrating it as modeled.

### 5.5 P&L counts VO/scene spend consistently — LOW
`compute_pnl` (`ledger.py:100`) sums `spent_cents` across scenes+VO and `would_have_cost_cents` for
declines into `overage_avoided`. Margin = `(price-cogs)/price`. Consistent with the gate. One edge:
if `price_cents` is `None` (margin≥1), `margin` is None and `gross_profit` is None — handled, but the
dashboard `livePnl` divides by `price` defensively. Fine.

---

## 6. OBSERVABILITY

### 6.1 Build logs exist but are unstructured and web-exposed — MEDIUM
Each build writes `runs/<id>/build.log` (stdout+stderr of the detached process, `serve.py:123`). That's
the only real log. It's plain text, not structured, **served over HTTP** (3.3/3.7), and the dashboard
never surfaces it — a failed build shows only the last event message (`liveFailed`, `app.js:556`). For
debugging a real failure you must SSH/Finder to the file. Add: structured logging, a `/api/log/<run>`
(authenticated) tail endpoint, and surface the tail in the failed-build UI.

### 6.2 Errors surface to the UI thinly — MEDIUM
`build_runner`'s except writes one `error` event with `str(e)` and sets `status:failed`. The exception
trace is lost (only in build.log). `orchestrator` failures before `build_runner`'s try (e.g. an import
error) won't update the ledger at all → dashboard stuck "starting…". Capture tracebacks into the
ledger event (truncated) so the console is debuggable without filesystem access.

### 6.3 No metrics/timing beyond `render_ms` — LOW
Studio renders record `render_ms`; nothing else is timed (planner latency, ffmpeg duration, total wall
time, spend totals over time). A product wants per-phase timing and a spend dashboard. The ledger is a
good place to accumulate these.

### 6.4 `log_message` writes to stderr only — LOW
`serve.py:241` routes access logs to stderr of the server process; in the current background-launch
they're captured by the shell snapshot, not a rotating file. Fine for dev.

---

## 7. WORKFLOW / UX FOR A REAL USER

### 7.1 No way to cancel/abort a build — HIGH
Once Build is clicked there is no stop button and no backend cancel. A wrong URL or a 5-minute planner
stall must be waited out (or the server killed). Add a cancel endpoint that kills the run's process
group and marks the ledger `cancelled`.

### 7.2 No download / share / delivery of the final video — MEDIUM
The final cut plays inline (`viewer`, `app.js:320`) but there's no download button, no shareable link,
no "deliver to customer" step — which is the actual *product* (the brief is "ship a finished video to a
paying customer"). The earn side creates a Checkout link but nothing connects payment → gated download
→ delivery. That end-to-end customer loop is the missing product spine (the pay-gate subagent is adding
the front half; make sure the back half — gated delivery — is part of it).

### 7.3 Live console assumes one build at a time — MEDIUM
`beginPoll`/`state.building` track a single live run; `init` resumes only `d.active[0]`. A real
multi-user product needs per-user run lists and a builds view, not a single-slot live console.

### 7.4 No editing / re-roll / approval of the plan before spend — MEDIUM
The agent plans → prices → produces with no human checkpoint to edit the storyboard, swap a model, or
reject a scene before generation. For a paid product (and to control real spend) a "review the plan and
budget, then approve" gate is expected. (This overlaps the pay-gate work — ensure plan-review is part
of it, not just payment.)

### 7.5 Mock vs real is invisible to the end user — LOW
A user can't tell from the finished UI whether they got real Higgsfield footage or storyboard
placeholders beyond a small badge. For a paying customer that distinction is the product. Make mode and
"real media applied" prominent and gate "deliver" on real media in real mode.

---

## 8. TESTING

### 8.1 What's covered — (good)
- `test_producer.py`: estimate/gate branches, `_distribute` sum-exactness, budget-lock override,
  margin=1 null-price. Deterministic via `PRODUCER_COST_STUB`. Solid unit coverage of the money brain.
- `test_orchestrator.py`: full loop in mock mode for approve / downgrade / decline (money-shot) /
  VO-over-budget / invalid-plan-rejected — and it asserts a real MP4 is produced (edge-tts + ffmpeg
  run for real). This is genuinely good end-to-end coverage of the *judgment*.
- `test_stripe_earn.py`: dry-run param shape + live-key refusal, offline. Good safety coverage.
- Plus the two free-Nemotron evals (judgment 7/7, skill-routing 19/19) as on-camera proof.

### 8.2 Notable untested paths — MEDIUM
- **`serve.py` entirely untested** — Range parsing (`_parse_range` suffix/overlong/416 branches),
  `_slug`, `_api_build` validation, `_api_active`. The Range handler is hand-rolled and Safari-
  critical; it deserves unit tests (valid range, suffix range, `bytes=-0`, start>end, `file_len==0`).
- **`stripe_money.py` live paths** — `provision_card`, `authorize` live branches, `earn` error branch
  are only exercised by hand via CLI. The simulated branches (the demo path) are untested too.
- **`stripe_webhook.decide`** — the actual approve/decline math and the dry-run vs live branch have no
  test; this is money logic.
- **`plan_job` fallback** — the "Nemotron invalid → template → still invalid → raise" ladder
  (`plan_job.py:28-34`) is untested.
- **`finish_cut.py` / `apply_real_media.py`** — no tests; complex ffmpeg filter graphs that silently
  produce wrong output if a filter errors (both use `check=True` so they'd raise, but no assertion that
  the *result* is correct duration/streams).
- **Concurrency** — nothing tests two builds at once (would expose 1.1).
- **No test runner config / CI** — `run_all_tests.sh` is a bash script; no `pytest.ini`, no GitHub
  Actions. Add CI that runs the offline subset on every change.

### 8.3 Tests mutate global `os.environ` and shared module state — LOW
`test_orchestrator.run` sets/pops `PRODUCER_PRODUCTION_COST_STUB` on the process env and the modules
are imported at top level with env already set; ordering-dependent. Works today; brittle. Prefer
passing stubs explicitly or `unittest` `setUp`/`tearDown` with `mock.patch.dict`.

---

## 9. DEPLOYMENT / OPS

### 9.1 Heavy, macOS-pinned local dependencies — HIGH (for hosting)
The pipeline shells out to: `ffmpeg`/`ffprobe`, `edge-tts`, `higgsfield` CLI, `remotion` (Node 19+),
`zsh`, `curl`, the walk-agent (NemoClaw/Docker). Hard-coded absolute macOS paths exist:
`/Users/dennis/Desktop/Projects/Hackathons/walk-ultra` (`adapters.py:196`),
`.../motion-graphics-kit` (line 219), `~/.hermes/.env`, `~/.zshrc` sourcing in `serve.py`. Python 3.14
specifics (`SimpleHTTPRequestHandler` has no Range → custom handler). None of this is containerized.
- **Fix for hosting:** containerize with pinned ffmpeg/Node/Remotion, parameterize every absolute path
  via config/env, drop the `zsh -lc` env-sourcing in favor of explicit env injection, and decide
  whether the walk-agent (Docker-in-Docker / NemoClaw) is even hostable or must be a separate service.

### 9.2 The stdlib server is not a production server — HIGH
`ThreadingMixIn` + `HTTPServer` is dev-grade: no request limits, no timeouts on slow clients, no TLS,
no graceful shutdown, no worker management, threads can pile up streaming large MP4s. Fine as a demo
viewer; for a product put a real ASGI/WSGI app behind nginx (or serve media from object storage/CDN and
keep the app stateless).

### 9.3 Secrets in `~/.zshrc` / `~/.hermes/.env`, sourced via login shell — MEDIUM
`serve.py` runs builds with `zsh -lc "source ~/.zshrc; …"` to get `NVIDIA_API_KEY` (line 124). That
couples build execution to a developer's login shell. In prod, inject secrets via the orchestrator's
environment / a secrets manager and read them in Python; never source `~/.zshrc`.

### 9.4 No config system — MEDIUM
Ports (3030, 4242), paths, model ids, cost constants, frame spec (1920×1080×30), pace, and the brand
palette table are all hard-coded across files. A product needs a single config (env/file) and per-job
overrides (resolution, fps, target margin already exists). The brand-palette dict (`remotion_codegen.py:28`)
is a hard-coded allowlist — fine, but document how a new brand is onboarded.

### 9.5 No process manager / restart story — MEDIUM
The server is launched manually in the background (confirmed: a `zsh -c … python3 dashboard/serve.py`
under PID 80345). No LaunchAgent/systemd, no auto-restart, no health check. The memory notes a
`studios` LaunchAgent pattern exists for other projects — adopt that (with `BROWSER=none` per the known
gotcha) or a container restart policy.

---

## TOP 5 TO DO FIRST (for production)

1. **Fix the shared `active.tsx` render race (§1.1) + serialize/queue builds (§1.2).** This is the one
   bug that silently produces *wrong videos* under concurrency. Render each scene from a per-run temp
   TSX path (small change) and put a concurrency limit / job queue in front of `/api/build`.

2. **Authenticate `/api/build` and take `mode:"real"` off the client (§3.1, §3.2).** Today any local
   process (or a malicious page via DNS-rebinding) can trigger real spend and arbitrary subprocesses on
   an unauthenticated endpoint. Add a bearer token + Origin/Host allowlist; gate real-money mode behind
   server-side authorization, not a request-body boolean. Keep the loopback bind.

3. **Stop serving the project root; lock the static server (§3.3, §3.7, §6.1).** Serve only `dashboard/`
   and `runs/media`, add a realpath-under-root guard in `send_head`, and move `build.log` out of the
   web-served tree (it can capture subprocess output incl. secrets). Add unit tests for the Range
   handler while you're in there (§8.2).

4. **Add crash/restart resilience: heartbeats + stale-run reaper + cancel (§1.4, §2.2, §4.6, §7.1).**
   Write `pid`+`heartbeat_ts` to the ledger, mark heartbeat-stale `running` runs as `failed` on a sweep
   and at server start, rebuild `index.json` from a directory scan (atomically, §1.3), and add a cancel
   endpoint that kills the run's process group. This makes the system survive the very common
   "server/child died mid-build" case instead of freezing.

5. **Harden the plan→produce path against bad model output and partial failure (§4.1, §4.3, §4.5).**
   Treat Nemotron `finish_reason=="length"` as failure → template fallback; wrap the per-scene
   production loop so a transient ffmpeg/edge-tts error errors *one* scene and the build still delivers;
   and persist Higgsfield `job_id`/`asset_url` to the ledger *before* download so paid work is never
   lost to a failed `curl`. (Keep the no-retry rule for *paid* generation; allow one retry for
   free/local steps.)

---

_Strengths worth preserving: the deterministic pricing/budget engine and its test coverage (§5.1,
§8.1); the key-by-presence, test-only, never-print Stripe posture (§3.7, §5.3); the explicit
"modeled, not physical" honesty about the decline shot; the atomic ledger write (§1.3). The work to do
is almost entirely about turning a careful single-user localhost demo into a multi-user, networked,
restart-safe, hostable service._
