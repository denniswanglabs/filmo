# Independent Verification Audit — Hermes Video Agent Fix-Wave

**Date:** 2026-06-20
**Scope:** Read-only, one-by-one verification that every change shipped this
session is PRESENT, CORRECT, and NOT regressed by a later same-file edit.
**Cost:** $0 (no paid API calls; only the deterministic/free test suite was run).
**Verdict:** **PASS.** All targeted multi-edit changes coexist with no
regressions. Every named change is present and correct. Test suite is GREEN.
Two non-blocking findings (one harness gap, one out-of-scope review backlog) are
flagged below.

---

## 1. Headline result

- **Multi-edit files (the clobber-risk surface): all changes coexist, zero regressions.**
  The three highest-risk files each carry every change-cluster the brief named,
  side by side, with no dead/duplicate/conflicting definitions:
  - `remotion_codegen.py` — palettes + brand-driven copy + art-direction all present.
  - `adapters.py` — brand field + hardened parse/sidecar + aligned VO all present.
  - `dashboard/{index.html,app.js,styles.css}` — all 7 change-clusters present, 53
    functions, no dup defs, CSS braces balanced 440/440.
- **Test suite GREEN.** `run_all_tests.sh --no-eval` → engine 13/13, orchestrator
  6/6, all OK, "$0 spent". The three NEW test files: adapters parse 25/25,
  build-runner failure 9/9, stripe-earn 15/15 — all pass.
- **All 11 audited code files compile/parse cleanly** (`py_compile` + `node --check`).

---

## 2. STATUS MATRIX

Legend: APPLIED = change present in current code · VERIFIED = how confirmed
(file:line or test) · REGRESSED = clobbered by a later edit? · all line numbers
are current-tree.

### `remotion_codegen.py` — THREE clusters must coexist (✅ all do)

| # | Change | APPLIED | VERIFIED | REGRESSED | Notes |
|---|--------|---------|----------|-----------|-------|
| 1 | Per-brand palettes `BRAND_PALETTES` | ✅ | L44 (stripe/linear/notion/vercel/_default) | No | — |
| 2 | `palette_for(url)` + `_brand_name(url)` | ✅ | L92, L77 | No | falls back to `_default` kit |
| 3 | Per-brand `font` field + `_DEFAULT_FONT` | ✅ | L48-74 | No | Söhne/Inter Display/Lyon serif/Geist/SF Pro |
| 4 | Brand-driven `_copy_from_brief` (no hardcoded Stripe) | ✅ | L454-476 | No | name/host/tagline from palette only |
| 5 | `_section_label(brief)` (no direction-as-title) | ✅ | L411-451 | No | strips directive scaffold, prefers quoted phrase |
| 6 | De-tooled kickers | ✅ | L465 "Get started", L468 "Introducing", L472/476 "Section" | No | no "PRODUCER CUT"/"CALL TO ACTION" in runtime path |
| 7 | Art-direction: FONT stacks wired into templates | ✅ | L135, L196/242/286/312, L361/402 | No | `fontFamily: FONT` everywhere |
| 8 | `AnimatedBg` drifting/breathing field | ✅ | L151-166, seeds 0/1.3/2.1/4.2 per archetype | No | Lissajous drift + 1.0→1.04 breathe |
| 9 | `drift()` continuous motion | ✅ | used across centered/editorial/divider | No | slow sine over full TOTAL |
| 10 | Entrance variety: blur-in / stagger / overshoot | ✅ | L182 blur-rise, L228 stagger damping 14, L274 overshoot damping 9 | No | three distinct vocabularies |

**Stripe-string check:** the only `"stripe"`/"Stripe" occurrences are the palette
domain KEY (L45), a docstring example (L78), and the `__main__` demo block
(L481-482). None are in the runtime copy path. **No hardcoded-Stripe regression.**

### `adapters.py` — THREE clusters must coexist (✅ all do)

| # | Change | APPLIED | VERIFIED | REGRESSED | Notes |
|---|--------|---------|----------|-----------|-------|
| 11 | `brand` field on studio record | ✅ | L425 `"brand": palette.get("_name")` | No | — |
| 12 | Hardened `_extract_job_id` (UUID-validated, recursive) | ✅ | L195-242, `_JOB_ID_KEYS`/`_JOB_ID_LIST_KEYS`/`_UUID_RE` | No | never raises; bare-string + plain-text fallback |
| 13 | Hardened `_extract_asset_url` (multi-key/wrapper) | ✅ | `_ASSET_URL_KEYS` L184 | No | raises with `_truncate(raw)` on miss |
| 14 | `.higgsfield.json` sidecar persistence | ✅ | `_persist_higgsfield_artifact`, called L165 (pre-wait) + re-persist L172 | No | merge-not-clobber on 2nd call |
| 15 | `synthesize_voiceover_aligned(beats,…)` | ✅ | L450, per-beat `adelay`/`amix`/`apad` L495-506 | No | returns `segments[]` |

### `finish_cut.py` — TWO clusters must coexist (✅ both do)

| # | Change | APPLIED | VERIFIED | REGRESSED | Notes |
|---|--------|---------|----------|-----------|-------|
| 16 | −14 LUFS `loudnorm` final stage | ✅ | L129 `[amix]loudnorm=I=-14:TP=-1.0:LRA=11[aout]` | No | placed AFTER music duck/mix |
| 17 | Per-beat VO placement | ✅ | L108-119 `vo_segments` → per-beat adelay at crossfade offsets | No | legacy single-track fallback at L121-126 |

### `orchestrator.py`

| # | Change | APPLIED | VERIFIED | REGRESSED | Notes |
|---|--------|---------|----------|-----------|-------|
| 18 | `ledger.plan` projection | ✅ | L129-135, placed BEFORE `set_phase("planning")`+flush (L137-140) | No | "storyboard decided" event L138 |
| 19 | `earn=None` param (preserve, don't re-mint) | ✅ | L89 sig; L185-196 preserves pre-paid block | No | mints fresh only when `earn is None` (L197) |
| 20 | VO beat offset (cumulative `produced_offsets`) | ✅ | L367-372 | No | — |
| 21 | VO beat DROP for cut/absent scenes | ✅ | L378-388, logs dropped beats | No | `beats_total/aligned/dropped` on ledger L394 |

### `dashboard/serve.py` (brief's "serve.py")

| # | Change | APPLIED | VERIFIED | REGRESSED | Notes |
|---|--------|---------|----------|-----------|-------|
| 22 | `safe_run_dir` sanitizer | ✅ | L48-77 fullmatch + `..` reject + realpath-parent check | No | rejects empty/`.`/`..`/separators |
| 23 | `POST /api/delete` | ✅ | route L156, handler `_api_delete` L212-237 → `shutil.rmtree` L233 | No | 400 bad-id → 404 missing → 500 rmtree-err |
| 24 | `rebuild_runs_index()` after delete | ✅ | L80, called L236 | No | newest-first |
| 25 | `?paid=` redirect (query-preserving) | ✅ | `_redirect_root` L250-263, `partition("?")` carries query (L257) | No | 302 → `/dashboard/index.html?<query>` |

### `dashboard/{index.html, app.js, styles.css}` — 7 clusters (✅ all present, states render)

| # | Change | APPLIED | VERIFIED | REGRESSED |
|---|--------|---------|----------|-----------|
| 26 | Script panel (`liveScript`/`initLiveScript`/`toolForType`, `scriptTyper`/`scriptShown` state, `.script-grid`/`.vo-script`/`.shot`) | ✅ | app.js L851/898/891/6; styles.css L672-695 | No |
| 27 | Delivered hero (`deliveredHero` "Your <brand> promo is ready", autoplay-muted-loop, Download MP4 `<a download>`, Copy-link → `/runs/<id>/final.mp4`, `initDeliveredHero`/`shareConfirmed` rAF 1.6s revert) | ✅ | app.js L321/337/339/344-346/351/377-385; styles.css `.delivered-hero` L461 | No |
| 28 | `renderDetail` branch `status==="delivered" && l.stitch` → hero first, proof folds below | ✅ | app.js L267 | No |
| 29 | `?paid=` handler (`handleCheckoutReturn`, parse `?paid`/`?cancelled`, `history.replaceState`, "PAYMENT RECEIVED — producing your video" + beginPoll; "PAYMENT CANCELLED · no charge") | ✅ | app.js L1035-1101, called init() L1125 | No |
| 30 | Pay gate (`payGate` "Pay $X to produce" → `window.open(earn.checkout_url)`, `initPayGate`, PHASES incl. `awaiting_payment`, renderLive branch, livePnl at gate) | ✅ | app.js L779/839/834/661/746/749 | No |
| 31 | Declutter (`<details>` via `disclosure()` + `wireProofDisclosures`, run-delete `.run-wrap`/`.rc-del` ghost trash, `askDelete` 2-step `.rc-confirm` "Delete this build?", `confirmDelete` POST /api/delete) | ✅ | app.js L425/302/167/173/183-190; styles.css L152/171/186 | No |
| 32 | Motion polish (word-build `heroWords`/`heroWordsBrand`/`heroAuto`/`buildHeroTitle`, HERO_STEP=.085 accent-last; keyframes blur-rise/grow-in/ph-sweep/ph-now-pulse/sb-shimmer + `.hw`/`.hw-accent`/`.hw-brand`; planning anim `.ph-fill`/`.sb-prog`/`storyboardLead` "N of M scenes"/`.s-queued` shimmer; `prefers-reduced-motion` guard) | ✅ | app.js L30/32/52/75/217/963; styles.css L268/270/285-293/297/602/609/640/656 | No |
| 33 | Light/coral palette (`--bg #F4F5F7`, `--bg-1 #FFFFFF`, `--ink #14171C`, `--amber #D6351C` coral CTA, `--neg #C01A2B` distinct crimson decline, `--pos #0E9F6E`, `--video-bg`) | ✅ | styles.css L14-41 | No |
| 34 | index.html `#i-link`/`#i-play` SVG + `id="build-mock"` checkbox | ✅ | index.html L21/22/54 | No |

**Coexistence + structure:** 53 functions in app.js, no duplicate definitions
(`uniq -d` empty), styles.css braces 440/440 balanced. All states (idle /
building / awaiting_payment / delivered / failed) have distinct render paths.

### `walk-ultra/explainer-agent/agent.sandbox-v26.js` — 1440×900 BEAM fix (4 spots)

| # | Spot | APPLIED | VERIFIED | REGRESSED |
|---|------|---------|----------|-----------|
| 35 | Scout `setViewportSize` | ✅ | L1115 `{width:1440,height:900}` | No |
| 36 | Candidate `setViewportSize` | ✅ | L1226 | No |
| 37 | BEAM `newContext` viewport | ✅ | L2883 | No |
| 38 | Post-promotion resize (NEW) | ✅ | L3097-3099 (after `leadPage = winnerPage`), with explanatory comment | No |

All viewport refs now 1440×900 (also L1401 `--window-size`, L1441/1454 lead +
screencast, L3193/3202 action-log). **Note (benign):** one residual `1280×720`
remains at L106-107 — but it is a `Page.startScreencast` JPEG compression cap for
the scout *recording* (`everyNthFrame:1`), NOT a DOM viewport, so it does not
affect card geometry and was correctly left untouched. The L600 `1440x900`
reference is an NVIDIA-logo geometry comment. JS parses clean (`node --check`).

### `stripe_earn.py`

| # | Change | APPLIED | VERIFIED | REGRESSED | Notes |
|---|--------|---------|----------|-----------|-------|
| 39 | `create_checkout_session` test-mode helper | ✅ | L120, mode=payment, client_reference_id=job_id, dry_run | No | success_url `…/dashboard/index.html?paid=` L105 |
| 40 | `_assert_test_key` live-key refusal | ✅ | L49-67, `LiveKeyRefused` on missing/sk_live_/rk_live_ | No | + `LiveModeError` guards every live response (L142/168/178) |
| 41 | `build_session_params` single-source | ✅ | L92; `get_session_status`/`get_session` L159/174 | No | DASHBOARD_BASE=http://localhost:3030 |

### Supporting changes (named in review docs, tied to new tests)

| # | Change | APPLIED | VERIFIED | REGRESSED |
|---|--------|---------|----------|-----------|
| 42 | `ledger.py` `Ledger.load()` classmethod, restores `_seq` | ✅ | L99-118 | No |
| 43 | `build_runner.py` `_price_plan`/`_payment_gate`/`_record_failure` + `PRODUCER_SIMULATE_PAID` | ✅ | L53/164/126; sim L199-201 | No |
| 44 | `plan_schema.py` `resolve_vo_beats`/`vo_script_from_beats` (beats or legacy script) | ✅ | L16-44 | No |
| 45 | `apply_real_media.py` walkthrough-gated trim/crop (WT_SS=2.6, WT_DUR=7.5, WT_CROP=1440:960:240:60, `force_original_aspect_ratio=increase`) | ✅ | L36-86 | No |

---

## 3. Test-suite result

`./run_all_tests.sh --no-eval` (from repo root, `source ~/.zshrc` first):

```
1. ENGINE      tests.test_producer        13 tests  ... OK
2. ORCHESTRATOR tests.test_orchestrator     6 tests  ... OK  (51.3s — real edge-tts+ffmpeg)
ALL TESTS PASSED — $0 spent.   (exit 0)
```

The three NEW test files named in the brief (run directly — see finding F1):

```
tests.test_adapters_higgsfield_parse   25 tests  ... OK
tests.test_build_runner_failure         9 tests  ... OK   (incl. old-bug regression guard +
                                                            postpayment-failure-preserves-earn E2E)
tests/test_stripe_earn.py               15 checks, 0 failures   (incl. live-key refusal x2)
```

**All GREEN.** Live-Nemotron evals (`hermes_judgment_eval.py`, `hermes_skill_eval.py`)
were intentionally skipped (`--no-eval`); they are FREE Nemotron-Super-120B calls
gated on `NVIDIA_API_KEY` and network — not blocking, run separately when desired.

---

## 4. Findings (non-blocking)

**F1 — Test-runner gap (harness, not code).** `run_all_tests.sh` only invokes
`tests.test_producer` and `tests.test_orchestrator`. The three NEW test files the
fix-wave added are NOT wired into the runner:
- `test_adapters_higgsfield_parse` and `test_build_runner_failure` are standard
  `unittest.TestCase` files and pass via `python3 -m unittest`, but the runner
  never calls them — so a future regression in parse/sidecar/ledger-failure logic
  would be SILENT under the canonical `./run_all_tests.sh`.
- `tests/test_stripe_earn.py` is a **standalone script** (plain `def test_*` +
  `__main__`), NOT a TestCase. `python3 -m unittest tests.test_stripe_earn`
  reports "NO TESTS RAN" (0 collected). It only passes when run as
  `python3 tests/test_stripe_earn.py` (15/15). Both this and the discovery gap
  mean the demo's headline "$0 test suite" silently under-covers the new code.
  *Recommendation (out of scope for this read-only audit): add the three files to
  `run_all_tests.sh`, and either convert test_stripe_earn to TestCase or invoke it
  by path.* The test LOGIC is sound and GREEN — this is purely a wiring gap.

**F2 — PRODUCTION-READINESS review backlog (acknowledged, out of scope).** Several
hardening items from `PRODUCTION-READINESS-REVIEW.md` were recommendations, NOT
part of this fix-wave's committed change-list, and remain UN-applied. Most visible:
`dashboard/serve.py:208` still shells out via
`subprocess.Popen(["zsh","-lc", inner], …, start_new_session=True)` — i.e. the
review's "drop the shell" (#8), build concurrency/queue (#2), `/api/build` auth /
Origin allowlist (#6/#7), idempotency key (#16), and Stripe-webhook signature
verification (#21 — `stripe_webhook.py` still unverified). These are pre-existing
known gaps, not regressions; flagging for completeness since the brief asked for
"anything pending."

---

## 5. Pending / open gaps (from the change-list, explicitly noted)

- **Stripe webhook needs `stripe login`.** The pay-gate UI itself notes the webhook
  is "pending `stripe login`" (app.js `initPayGate`). The earn helper works in
  test mode without it (polls `get_session_status`); the webhook path is the
  push-confirmation half and is not yet wired/authenticated.
- **The paid re-run has not been executed.** Evidence shows the autonomous
  hermes-driven run (`evidence/hermes-driven-run/`, mode=mock, earn=dev_mode, $0)
  and a recovered Seedance asset (`evidence/recovered/cb5acbc2…`), but no committed
  run with a real `cs_test_` Checkout session driven through the live pay-gate.
  `PRODUCER_SIMULATE_PAID=1` is the $0 dev path used in tests/demo; a real
  test-mode Checkout run is still pending.

---

## 6. Bottom line

**45 audited changes across 12 files: 45/45 PRESENT + CORRECT, 0 REGRESSIONS.**
Every multi-edit file the brief flagged as clobber-risk carries all of its
change-clusters coexisting cleanly (`remotion_codegen.py` 3-way,
`adapters.py` 3-way, `finish_cut.py` 2-way, dashboard 7-way). The full
pay-gate loop is internally consistent across `stripe_earn.py` →
`dashboard/serve.py` → `dashboard/app.js`. All 11 code files compile/parse.
Test suite GREEN ($0). The only issues are a test-runner wiring gap (F1, the new
tests aren't in `run_all_tests.sh`; test_stripe_earn isn't unittest-discoverable)
and the pre-existing production-hardening backlog + two known pending items
(stripe webhook, real paid re-run) — none of which are regressions of this
fix-wave.
