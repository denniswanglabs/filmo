# RESTORE POINT — before the video-editor experiment
Captured: 20260622-193030

Dennis asked to build an experimental Remotion video editor and to be able to revert
to the pre-experiment state if it doesn't pan out. This file records how.

## How to revert
1. Git snapshot (working tree incl. uncommitted at capture time):
   - tag: `pre-video-editor-20260622-193030` -> commit `54d7cca0e8c7c7ee4837df4350246702677946c3`
   - HEAD at capture: `be4cd05cc1106ca7ff7272df6eec9de6ce37981b` (198 dirty files)
   - restore source: `git checkout pre-video-editor-20260622-193030 -- .`  (or `git stash apply 54d7cca0e8c7c7ee4837df4350246702677946c3`)
2. Full source tarball (no node_modules/.git/runs/venv): `/Users/dennis/walk-studio-restore-20260622-193030.tgz`
   - restore: extract over the repo.

## Isolation guarantee
The editor experiment is ADDITIVE — built as new files in a separate dir; it does NOT
modify the existing video-generation pipeline (studio/ compositions, build_runner,
adapters, orchestrator, plan_job, style_fill, brand_extract). Reverting = delete the
experiment dir. The snapshot above is the absolute fallback.
