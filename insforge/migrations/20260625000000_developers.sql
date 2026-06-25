-- Developer mode — key-gated "see the machinery" access for hackathon judges.
-- A signed-in account pairs a secret DEV_MODE_KEY (validated server-side in a Next.js
-- server action) and gets a row here. `developer = true` unlocks /inside/[runId].
--
-- Why a table (not auth.users.profile): the InsForge admin REST API exposes no
-- profile-write endpoint for an arbitrary user, and the SDK's setProfile() only
-- mutates the *current session* user — neither fits a server action that flips the
-- flag for the signed-in user's account from the server. A user-id-keyed table is
-- functionally equivalent and writes cleanly with the existing admin key.
--
-- Ownership model (mirrors runs/jobs): the server action WRITES via the admin API
-- key (bypasses RLS); the authenticated user may READ only their own row via RLS.

create table public.developers (
  user_id     uuid primary key references auth.users(id) on delete cascade,
  developer   boolean not null default true,   -- the flag the /inside gate checks
  paired_at   timestamptz not null default now(),
  source      text default 'dev_mode_key'      -- how the flag was set (provenance, never the key)
);

alter table public.developers enable row level security;
-- A user can read their own developer row (so a client could reflect dev state).
-- Writes happen only through the admin key (RLS-exempt) in the pairDeveloper action.
create policy "developers owner select" on public.developers
  for select using (user_id = (select auth.uid()));

grant usage on schema public to anon, authenticated;
grant select on public.developers to authenticated;
