-- Feedback capture (beta): what people tell us from inside the studio.
--
-- DURABILITY BEFORE DELIVERY. The point of this table is that a note can
-- never be lost because a mail provider was misconfigured, rate-limited, or
-- simply not wired yet. The server action writes the row FIRST and only then
-- attempts to notify; a failed notification leaves the feedback intact and
-- readable here. Nothing about sending mail is a precondition for accepting
-- it.
create table if not exists public.feedback (
  id uuid primary key default gen_random_uuid(),
  -- Null for a signed-out sender: we would rather take anonymous feedback
  -- than refuse it. `on delete set null` keeps the note when an account goes.
  user_id uuid references auth.users(id) on delete set null,
  -- Whatever address we can attribute it to (the signed-in account, or one
  -- the sender typed). Free text, never trusted as an identity.
  email text not null default '',
  message text not null,
  -- Where they were standing when they wrote it — a run id, a route. Makes a
  -- vague note actionable without asking them for context.
  context text not null default '',
  -- Did a notification actually go out? Lets a later digest sweep up
  -- everything that never reached an inbox, rather than re-sending blindly.
  notified boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists feedback_created_idx
  on public.feedback (created_at desc);
-- Partial index for the "what never got delivered" sweep.
create index if not exists feedback_undelivered_idx
  on public.feedback (created_at desc) where notified = false;

alter table public.feedback enable row level security;

-- Writes go through the server action on the service key, which is also the
-- only thing that should ever read this table — feedback is not user-facing
-- content and one person's note is not another's business. No anon/authenticated
-- policy is granted deliberately: absence of a policy is the deny.
drop policy if exists feedback_no_client_access on public.feedback;
