-- Atomic job claim for the worker. SELECT ... FOR UPDATE SKIP LOCKED lets multiple
-- workers poll concurrently without ever grabbing the same job. Returns the claimed
-- job row, or NULL when the queue is empty. Called by the worker via the admin client
-- (`.rpc('claim_next_job', { p_worker })`); not granted to anon/authenticated.
create or replace function public.claim_next_job(p_worker text)
returns public.jobs
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
  j public.jobs;
begin
  select * into j
    from public.jobs
   where status = 'queued'
   order by created_at
   for update skip locked
   limit 1;

  if not found then
    return null;
  end if;

  update public.jobs
     set status = 'claimed',
         claimed_at = now(),
         claimed_by = p_worker,
         attempts = attempts + 1
   where id = j.id
   returning * into j;

  return j;
end;
$$;
