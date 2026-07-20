-- Credit system (beta): append-only ledger, server-key writes only.
-- Balance is derived (SUM(delta)); spends are negative, refunds/grants positive.
-- Caps and prices live in the app (web/app/actions.ts) so tuning them never
-- needs a migration — and are deliberately NOT restated here, because a
-- second copy of a tariff rots silently the moment the first one moves.
create table if not exists public.credit_ledger (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  delta integer not null,
  reason text not null,
  run_id uuid,
  created_at timestamptz not null default now()
);

create index if not exists credit_ledger_user_created_idx
  on public.credit_ledger (user_id, created_at desc);

-- One spend per run per direction (guards double-charge and double-refund).
create unique index if not exists credit_ledger_run_reason_uniq
  on public.credit_ledger (run_id, reason) where run_id is not null;

alter table public.credit_ledger enable row level security;

-- Owners may read their own ledger; ALL writes come through the service key
-- (no insert/update/delete policies on purpose).
drop policy if exists credit_ledger_owner_read on public.credit_ledger;
create policy credit_ledger_owner_read on public.credit_ledger
  for select using (user_id = auth.uid());
