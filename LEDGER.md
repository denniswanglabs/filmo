# Run Ledger schema (`runs/<run_id>/ledger.json`)

The ledger is the single artifact every consumer reads — the test assertions, the
dashboard, and the demo P&L. One ledger per production run. Written by
`orchestrator.py` via `ledger.py`. `runs/index.json` is the list view.

## `runs/index.json`
```json
{ "runs": [ {
  "run_id": "demo-3-decline", "mode": "mock", "status": "delivered",
  "created_at": "2026-06-19T01:03:00Z",
  "goal": "...", "company_url": "https://docs.stripe.com",
  "price_cents": 92, "cogs_spent_cents": 30, "margin": 0.6739,
  "overage_avoided_cents": 60, "declines": 1
} ] }
```

## `ledger.json` (top level)
| Field | Type | Meaning |
|---|---|---|
| `run_id` | string | unique run id (also the folder name) |
| `schema_version` | int | currently `1` |
| `mode` | `"mock"` \| `"real"` | mock = $0 test phase; real = paid pipeline |
| `created_at` | string\|null | ISO timestamp |
| `job` | object | `{company_url, goal, target_duration_s, target_margin, currency}` |
| `status` | `"running"` \| `"delivered"` \| `"failed"` | terminal status |
| `plan` | object | the storyboard the agent decided on — surfaced live during `phase=="planning"` (see below). Persists through the build. |
| `pricing` | object | the `producer.py estimate` output (see below) |
| `earn` | object | Stripe EARN block (see below) |
| `card` | object | Issuing card block (see below) |
| `scenes` | array | per-scene production records (see below) — **the gate decisions** |
| `voiceover` | object | the VO production record (a scene-shaped record, id `__voiceover__`) |
| `stitch` | object\|null | final assembly record |
| `pnl` | object | profit & loss summary (the headline) |
| `events` | array | ordered timeline: `{seq, level, msg, ...}` |

### `pricing`
`{ total_cogs_cents, suggested_price_cents, production_budget_cents,
   scenes:[{id,type,tool,model,est_cost_cents,per_scene_budget_cents,note}],
   voiceover:{...same shape, id "__voiceover__"} }`. Budget is LOCKED at COGS.

### `plan` — the storyboard the agent wrote (the "watch it script" feature)
A trimmed projection of the validated scene plan, written by `orchestrator.orchestrate()`
before any production work so the live console can render the SCRIPT the moment planning
completes (and it remains for the whole build).
`{ voiceover:{script, voice}, scenes:[{id, type, model, duration_s, brief}] }`.
- `voiceover.script` — the full VO narration the agent generated (the readable script).
- `scenes[]` — the ordered scene breakdown: each scene's `brief`, `type`
  (`title`|`cinematic`|`walkthrough`|`motion_graphic`), the `model`/tool that will
  produce it (null for the free types), and `duration_s`.
The dashboard's live build view renders this as a "Script" panel framed as *watch the
agent write the script before it shoots it*. Distinct from `scenes[]` (the per-scene
**production** records with gate verdicts) — `plan` is the agent's intent, captured up front.

### `earn`
`{ enabled, provider:"dev"|"stripe", status:"dev_mode"|"awaiting_payment"|"error",
   price_cents, currency, payment_link, key:{present,kind,source,length} }`.
`dev_mode` = no Stripe key (payment gate skipped). Never contains the secret.

### `card`
`{ enabled, provider:"simulated"|"stripe", spending_limit_cents, card_id, ... }`.

### `scenes[]` — one record per scene, **in plan order**
| Field | Meaning |
|---|---|
| `id`, `type`, `order`, `brief`, `model`, `duration_s` | scene identity |
| `decision` | `"free"` \| `"approve"` \| `"downgrade"` \| `"decline"` — **the judgment** |
| `tool` | `motion-graphics` \| `walk-agent` \| `higgsfield-scene` |
| `preview_cost_cents` | the production-time cost the gate saw |
| `cost_overrun_cents` | (optional) production cost − planned cost, if it overran |
| `spent_cents` | what was actually spent (0 for free / declined) |
| `would_have_cost_cents` | (declines) the overage the gate SAVED |
| `downgraded_from` / `final_model` | model swap on a downgrade |
| `remaining_after_cents` | budget remaining after this scene |
| `status` | `"produced"` \| `"declined"` \| `"free"` |
| `output_path` | clip path relative to the run dir (null if declined) |
| `stripe_authorization` | `{id, approved:bool, amount_cents, decline_reason, simulated:bool}` — the physical gate; `approved:false` on the money-shot |
| `studio` | present when the run used `--overlays studio` (real Remotion). See below. `null` for mock color-card clips and for declined scenes. |

### `scenes[].studio` — the agent's Remotion render (the "watch it code" feature)
Present when overlays=studio. Two kinds:
- `kind: "authored"` (title / motion_graphic) — **the agent wrote this code.** Fields:
  `generated_code` (the full real TSX source that rendered — replay this typing),
  `archetype` (`centered`|`editorial`|`divider`), `code_lines`, `render_ms`,
  `composition` (`"Scene"`). The dashboard's Studio view types `generated_code` out,
  then plays the scene's `output_path` clip — shown code == rendered clip.
- `kind: "placeholder"` (cinematic / walkthrough) — a labelled storyboard/animatic
  stand-in (real media is Higgsfield/walk-agent in `--mode real`). Fields:
  `archetype: "placeholder"`, `render_ms`. No `generated_code` (not agent-authored) —
  the dashboard shows it as a storyboard frame, NOT a code-replay.

Top-level `overlays: "studio"` and `brand_palette: {bg,accent,fg,dim,...,_brand}`
appear when studio overlays are used. The palette is the CLIENT brand (e.g. Stripe
navy/blurple), distinct from the dashboard's own UI theme.

### `pnl`
`{ price_cents, cogs_spent_cents, gross_profit_cents, margin,
   overage_avoided_cents, declines:[{id,would_have_cost_cents}], cost_lines:[...] }`.
- **margin** = `(price − cogs_spent) / price`.
- **overage_avoided_cents** = money the budget gate saved by declining — the
  headline of the money-shot. A run can finish *above* target margin precisely
  because it auto-cut an over-budget scene.

### `events[]`
Ordered timeline. `level` ∈ `info | gate | spend | decline | money | error`.
`gate`/`decline`/`money` events are the ones worth highlighting on the dashboard.

## Canonical examples to render against
- `runs/demo-1-approve` — clean, everything approved, margin at target.
- `runs/demo-2-downgrade` — a seedance hero downgraded to a still, came in under.
- `runs/demo-3-decline` — **the money-shot**: an over-budget hero declined (real
  Stripe-shaped declined authorization), 60¢ overage avoided, margin rises to 67%.
- `runs/demo-4-vo-over` — the voiceover itself declined for over-budget.
