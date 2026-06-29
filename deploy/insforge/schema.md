# InsForge schema — the Filmo backend (Postgres + storage)

InsForge is the shared backend for the website (Vercel) and the worker (Hetzner).
Project URL: `https://jd3mdkqr.ap-southeast.insforge.app`. Postgres tables + one
public storage bucket. Columns below were confirmed against the LIVE project with
read-only `select … limit 1` and cross-checked against the code's usage. RLS is
on; the worker + admin server-actions use the admin key (`INSFORGE_API_KEY`) which
bypasses RLS.

## Job flow across the tables

`runs` is the per-build record (created by the web app or a direct insert).
`jobs` is the work queue the worker polls (`claim_next_job` does an atomic claim).
`run_events` is the append-only LIVE activity feed ("watch the agent work").
`developers` is the dev-mode allowlist that unlocks the `/inside/<runId>` view.

```
web app / insert  ──►  runs (1)  ──►  jobs (1, queued)
                                          │  worker claims (claim_next_job)
                                          ▼
                                   build_runner / Hermes conduct
                                          │  emits rows
                                          ▼
                                     run_events (N)
                                          │  on delivery
                                          ▼
                       runs.final_url + walk-videos/<run_key>/final.mp4
```

## Table: `runs`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid (pk) | run id |
| `user_id` | uuid | owner (auth.users); admin client joins to it |
| `run_key` | text | human/worker key, e.g. `web-1782432342562-c4bgo`; also the asset prefix in `walk-videos` |
| `brand` | text | e.g. `stripe.com` |
| `company_url` | text | the target product URL |
| `goal` | text | one-line job objective |
| `emphasis` | text \| null | optional emphasis line |
| `quality` | text | `standard` \| (premium tiers) |
| `brain` | text | brain tag, e.g. `ultra-paid` / `super-paid` (Nemotron) |
| `mode` | text | `mock` \| `real` |
| `status` | text | `queued` \| `running` \| `delivered` \| `failed` \| … |
| `phase` | text | fine-grained stage (e.g. `planning`, `delivered`) for the progress UI |
| `price_cents` | int \| null | quoted price |
| `cogs_cents` | int \| null | cost of goods |
| `margin` | numeric \| null | |
| `plan` | jsonb \| null | the resolved scene plan (when persisted) |
| `selection` | jsonb \| null | selection stamp |
| `final_url` | text \| null | delivered video URL (walk-videos object) |
| `props` | jsonb \| null | per-run extras; the worker stamps `props.producer` (`hetzner-curated`/`hetzner-hermes`) + `props.produced_on` |
| `props_edited` | jsonb \| null | editor overrides |
| `edited_url` | text \| null | re-rendered (edited) video URL |
| `checkout_url` | text \| null | Stripe checkout URL for a human-pays job |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

## Table: `jobs`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid (pk) | |
| `run_id` | uuid | → `runs.id` |
| `type` | text | e.g. `build` |
| `status` | text | `queued` \| `claimed` \| `done` \| `failed` |
| `params` | jsonb | the build params (goal, url, mode, brain, pay_mode, …) |
| `attempts` | int | claim attempt count |
| `claimed_at` | timestamptz \| null | |
| `claimed_by` | text \| null | worker id, e.g. `hetzner-curated-<host>-<pid>` |
| `error` | text \| null | failure reason |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

`claim_next_job` is the atomic claim (oldest `queued` job → `claimed`, stamping
`claimed_by`/`claimed_at`), so multiple workers never double-process a job.

## Table: `run_events`

| Column | Type | Notes |
|---|---|---|
| `id` | bigint (pk) | autoincrement |
| `run_id` | uuid | → `runs.id` |
| `seq` | int | per-run ordering |
| `actor` | text | who emitted it, e.g. `hermes`, `worker` (sponsor-tagged for the live feed) |
| `level` | text | `info` \| `warn` \| `error` |
| `msg` | text | the activity line shown in the LIVE feed |
| `created_at` | timestamptz | |

## Table: `developers`

Dev-mode allowlist. A server action (`pairDeveloper`) validates `DEV_MODE_KEY`
and inserts the verified caller; `isDeveloperId` reads it to gate `/inside/<runId>`.
Columns derived from `web/app/actions.ts` (insert `{ user_id, developer: true,
source: 'dev_mode_key' }`, select `developer`):

| Column | Type | Notes |
|---|---|---|
| `user_id` | uuid | → auth.users; the verified caller |
| `developer` | bool | `true` unlocks the inside view forever for that account |
| `source` | text | how the flag was granted, e.g. `dev_mode_key` |
| `created_at` | timestamptz | (standard InsForge column) |

## Storage bucket: `walk-videos`

- **Public** bucket (confirmed via `GET /api/storage/buckets`), created 2026-06-23.
- Per-run assets are keyed `"<run_key>/<asset>"`, e.g.
  `walk-videos/<run_key>/final.mp4`, plus per-scene stills / logos
  (`brand-logo-*.svg`, `shot-*.png`).
- The worker + the `produce_and_ship` MCP tool upload here via the Node
  `@insforge/sdk` helper (`insforge_upload.mjs`), and `runs.final_url` /
  `runs.edited_url` point at these objects. The web editor resolves per-run assets
  from `…/api/storage/buckets/walk-videos/objects/<run_key>`.

> Note: the bucket name `walk-videos` is intentionally NOT renamed to "filmo" —
> renaming it would break the live deploy (see CLAUDE.md "Rename scope").
