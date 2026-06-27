-- Persist the editor's saved props (in-browser edits) separately from the clean,
-- worker-generated `props`. The /runs/[id]/edit editor writes this via the
-- saveEditedProps server action (admin key, RLS-exempt), mirroring how `props`
-- was added. The existing "runs owner update/select" RLS policies and the
-- table-wide grants to `authenticated` already cover this new column, so no
-- policy or grant changes are required. Keeping `props` untouched lets the
-- editor offer a "revert to original" at any time.
alter table public.runs add column if not exists props_edited jsonb; -- editor-saved props (in-browser edits)
