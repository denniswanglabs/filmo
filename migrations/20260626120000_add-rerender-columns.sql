-- Phase 3 (editor "Export → re-render"): two columns.
--
--   jobs.type        the worker now branches on job type. Default 'build' keeps
--                    every existing queued job behaving exactly as before (full
--                    capture/plan/price/produce pipeline). A new 'rerender' job
--                    skips capture/plan/price and just re-renders the run's
--                    edited props (runs.props_edited) into a NEW mp4.
--
--   runs.edited_url  the URL of the re-rendered ("Edited") video. Kept SEPARATE
--                    from final_url so the original delivered video is never
--                    overwritten — the run page can surface both.
--
-- Both are additive nullable/defaulted columns; the existing "runs/jobs owner"
-- RLS policies and the table-wide grants to `authenticated` already cover them,
-- so no policy or grant changes are required.
alter table public.jobs add column if not exists type text not null default 'build'; -- 'build' | 'rerender'
alter table public.runs add column if not exists edited_url text;                     -- re-rendered ("Edited") video URL
