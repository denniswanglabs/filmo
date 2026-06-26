-- Persist the render-ready props.json the editor needs. Mirrors the existing
-- plan/selection jsonb columns on runs. The worker (admin key, RLS-exempt) writes
-- it after a build; the existing "runs owner update/select" RLS policies and the
-- table-wide grants to `authenticated` already cover this new column, so no policy
-- or grant changes are required.
alter table public.runs add column if not exists props jsonb; -- render-ready props.json for the in-browser editor
