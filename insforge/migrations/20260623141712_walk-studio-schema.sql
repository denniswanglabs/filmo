-- Walk Studio schema — the cloud home for what runs/*/ledger.json holds today.
--   runs        one row per build (status, pricing, plan, Nemotron telemetry, final video URL)
--   run_events  append-only event stream — feeds the live view + the Hermes<->Nemotron activity feed
--   jobs        the worker queue (the Railway worker claims queued jobs)
-- Ownership model: the WORKER writes via the admin API key (bypasses RLS); the
-- FRONTEND uses anon/authenticated roles, and RLS scopes every read to the owner.

-- ════════════════════════════════ runs ════════════════════════════════
create table public.runs (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users(id) on delete cascade,
  run_key      text not null unique,                 -- the pipeline run-id, e.g. "wtfix2-linear"
  brand        text,
  company_url  text,
  goal         text,
  emphasis     text,
  quality      text not null default 'standard',     -- standard | premium
  brain        text not null default 'super-free',   -- super-free | ultra-paid | super-paid
  mode         text not null default 'mock',         -- mock | real
  status       text not null default 'queued',       -- queued | running | delivered | failed | aborted
  phase        text,
  price_cents  integer,
  cogs_cents   integer,
  margin       numeric,
  plan         jsonb,                                 -- the Nemotron scene plan
  selection    jsonb,                                 -- Nemotron telemetry: brain, tokens, finish_reason
  final_url    text,                                  -- storage URL of the delivered final.mp4
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index runs_user_created_idx on public.runs (user_id, created_at desc);

alter table public.runs enable row level security;
create policy "runs owner select" on public.runs for select using (user_id = (select auth.uid()));
create policy "runs owner insert" on public.runs for insert with check (user_id = (select auth.uid()));
create policy "runs owner update" on public.runs for update using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "runs owner delete" on public.runs for delete using (user_id = (select auth.uid()));

-- ── ownership helper (SECURITY DEFINER so run_events/jobs policies don't recurse
--    back through runs' own RLS) ──
create or replace function public.owns_run(p_run_id uuid)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public, pg_temp
as $$
  select exists (
    select 1 from public.runs r
    where r.id = p_run_id and r.user_id = (select auth.uid())
  );
$$;

-- ════════════════════════════ run_events ════════════════════════════
create table public.run_events (
  id          bigint generated always as identity primary key,
  run_id      uuid not null references public.runs(id) on delete cascade,
  seq         integer,
  actor       text not null default 'hermes',        -- hermes | nemotron | stripe
  level       text not null default 'info',
  msg         text not null,
  created_at  timestamptz not null default now()
);
create index run_events_run_seq_idx on public.run_events (run_id, seq);

alter table public.run_events enable row level security;
-- users read events for runs they own; the worker inserts via the admin key (RLS-exempt)
create policy "run_events owner select" on public.run_events for select using (public.owns_run(run_id));

-- ══════════════════════════════ jobs ══════════════════════════════
create table public.jobs (
  id          uuid primary key default gen_random_uuid(),
  run_id      uuid not null references public.runs(id) on delete cascade,
  status      text not null default 'queued',        -- queued | claimed | done | failed
  claimed_at  timestamptz,
  claimed_by  text,
  attempts    integer not null default 0,
  params      jsonb,
  error       text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index jobs_status_idx on public.jobs (status, created_at);

alter table public.jobs enable row level security;
-- users may read the job status for runs they own; jobs are written only by the worker (admin key)
create policy "jobs owner select" on public.jobs for select using (public.owns_run(run_id));

-- ── updated_at touch trigger (runs + jobs) ──
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
set search_path = pg_catalog, public, pg_temp
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;
create trigger runs_touch before update on public.runs for each row execute function public.touch_updated_at();
create trigger jobs_touch before update on public.jobs for each row execute function public.touch_updated_at();

-- ── privileges (RLS decides rows; grants decide who reaches the policies) ──
grant usage on schema public to anon, authenticated;
grant select, insert, update, delete on public.runs to authenticated;
grant select on public.run_events to authenticated;
grant select on public.jobs to authenticated;
