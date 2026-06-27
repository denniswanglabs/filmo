# Pipeline Unification Plan — `main` → `hosted-saas` (deploy source)

**Author:** read-only analysis subagent (Filmo). PLAN ONLY — no edits/commits/deploy performed.
**Date:** 2026-06-26
**Goal:** Make the Railway worker (`walk-studio-hosted`, branch `hosted-saas`, deploys via manual `railway up`) run the CURRENT fixed pipeline from `main`, WITHOUT losing hosted-saas's genuine cloud adaptations, then ship real music and redeploy.

---

## 0. Topology (why this is clean)

- **merge-base:** `4627f4c`.
- **`hosted-saas`** branched at **`1afee42`** ("Cloud build…") and afterward did **web/landing/editor work ONLY** — it never received the post-split pipeline R&D.
- **`main`** got everything since the split: Conversion Read / ANALYZE stage, `807428b` (focus-ring OFF + cursor OFF), `9e45952` (4242 payment), plus an UNCOMMITTED working-tree BGM music-path fix in `style_fill.py` (lives in the sibling worktree `…/hermes-video-agent`).

**Consequence:** every pipeline file on `hosted-saas` is EITHER (a) byte-identical to merge-base (stale → take main wholesale) OR (b) one of exactly **4 files** that `1afee42` touched for the cloud. Verified with `git rev-parse hosted-saas:<f>` vs merge-base — see classification.

---

## 1. Divergence map & classification (evidence-backed)

### (A) PORT — take `main`'s version wholesale (hosted-saas left these UNTOUCHED at merge-base)
Confirmed identical to merge-base on hosted-saas; main has the fixes:

| File | Why port |
|---|---|
| `align_vo.py` | main evolved; uses `/opt/homebrew/bin/whisper-cli` + `~/.cache/whisper/ggml-base.en.bin` — **Dockerfile already provides both** (lines 27–31). Safe. |
| `build_timeline.py` | main-only pipeline evolution |
| `validate_planner.py` | Conversion Read prescriptions (additive) |
| `plan_job.py` | seed_plan_with_read + facts threading |
| `stripe_money.py` | main evolution (4242 path lives in build/web, but take newest) |
| `orchestrator.py` | main RESTORES the `WS_VO_PROVIDER=elevenlabs` override logic that hosted-saas's stale copy lacks |
| `brain.py` | main keeps the `hermes` / `hermes-405b` brain entries hosted-saas's stale copy lacks |
| `capture_screenshots.py` | main evolution (NemoClaw/egress) |
| `studio/src/timeline/archetypes/AppleScreenshot.tsx` | **the 807428b fix**: `SHOW_FOCUS_RING = false` (line 322) + cursor forced null (lines 350–354) |
| `studio/src/timeline/archetypes/WalkthroughPlayer.tsx` | the 807428b cursor cleanup |
| `studio/src/generated/active.tsx` | regenerated fixture; cosmetic, take main for consistency |

**Also PORT (main-only files hosted-saas deleted):** `analyze.py`, `read_pass.py`, `run_producer_brain.py`, `mcp_studio_server.py`, `analyzer-prompt.md`.
- The first three (`analyze.py`, `read_pass.py`, `run_producer_brain.py`) + `analyzer-prompt.md` are part of the ANALYZE / Conversion Read path that `build_runner.py` (main) now imports — **must be present or the ported build_runner can ImportError**. (UNCERTAIN — verify imports at execution time; see Risks.)
- `mcp_studio_server.py` is the local MCP studio server — NOT used by the worker. **Optional**; porting is harmless but not required. Skip to keep the image lean if desired.

### (B) PRESERVE/MERGE — the 4 cloud-fix files from `1afee42`
`1afee42` is the ONLY commit that touched pipeline files for the cloud. The fixes:

| File | Cloud-fix | Did `main` also change it? | Action |
|---|---|---|---|
| `style_fill.py` | `--concurrency=8`→`--concurrency=50%` (render_and_montage, ~L3841) | **No** (main == merge-base here) | **KEEP hosted-saas's** + ADD main's uncommitted BGM hunk (different region, ~L3217–3227) |
| `walk_native.py` | silent-audio `anullsrc` mux in `_stitch` (replaces `-an`; fixes linux-x64 Remotion ffprobe `a:0`) | **No** (main still has `-an`) | **KEEP hosted-saas's**; do NOT port main (would re-break cloud render) |
| `adapters.py` | `--concurrency=8`→`50%` (generate_overlay, ~L1718) + edge-tts retry loop in `_vo_edge` | **YES** (+114/−15) | **PORT main, then re-apply concurrency=50%**. main ALREADY has its own edge-tts retry (`for attempt in range(3)`, L1867) → drop hosted-saas's retry as superseded |
| `build_runner.py` | `--concurrency=8`→`50%` (_run_vo_engine, ~L294) | **YES** (+153/−5) | **PORT main, then re-apply concurrency=50%** |

> Net: only `adapters.py` and `build_runner.py` need a real merge (port main + re-apply the one-line concurrency tweak). `style_fill.py`/`walk_native.py` are kept as-is on hosted-saas (style_fill gets one extra BGM hunk).

---

## 2. What `1afee42` introduced that MUST survive (the cloud-fix list)
1. **Remotion `--concurrency=50%`** in 3 render call-sites (2-core Railway box): `adapters.py`, `build_runner.py`, `style_fill.py`.
2. **`walk_native.py` silent-audio track** (`-f lavfi -i anullsrc=… -c:a aac -shortest`) so the walkthrough mp4 has an `a:0` stream (linux-x64 Remotion ffprobe fails on audio-less mp4; arm64 tolerates).
3. **edge-tts retry** (already independently present on main — no port needed).
4. **Dockerfile / worker / migrations / .gitignore** cloud scaffolding — NOT in scope here (excluded surface), leave intact EXCEPT the music block (§3).

---

## 3. Music / Dockerfile fix (the silent-video root cause)

### The bug
- New code (main's uncommitted `style_fill.py`) expects repo-relative `assets/music/fintech.mp3` + `assets/music/calm.mp3`.
- The Dockerfile's **lines 53–60** bake a **60s SILENT** `anullsrc` mp3 at the OLD absolute paths `/Users/dennis/Desktop/Projects/Demos/{tappay,kuli}-promo/public/music.mp3`. → prod videos are silent.

### Dockerfile edit (exact)
**Remove lines 53–60** of `hosted-saas:Dockerfile` (the whole `# ── music bed …` block, from the comment through the `cp … kuli-promo/public/music.mp3`). **No replacement step is needed** — the real mp3s ship via the existing `COPY . /app` (line 40), landing at `/app/assets/music/*.mp3`, which is exactly where the new `_MUSIC_DIR = <repo>/assets/music` resolves inside the container.

### `.gitignore` LANDMINE (single biggest risk — see §6)
- hosted-saas `.gitignore` **line 35 is a global `*.mp3`** ignore. There is **NO `!assets/music` exception** (the only negation is line 81 for `dashboard/assets/styles/*.jpg`).
- `git check-ignore -v assets/music/fintech.mp3` → **`.gitignore:35:*.mp3`** (PROVEN ignored).
- The mp3s are currently **untracked on BOTH branches**; they exist only as untracked files in the `hermes-video-agent` worktree (`assets/music/{calm.mp3=3.7MB, fintech.mp3=1.2MB}`).
- The uncommitted main comment claims "git-tracked via the !assets/music exception" — **that exception does not exist.** If you `git add assets/music/*.mp3` it will be silently skipped → `COPY . /app` ships nothing → silent video persists.

**Fix (pick ONE, prefer the negation so future adds work):**
- Add to hosted-saas `.gitignore`:
  ```
  !assets/music/
  !assets/music/*.mp3
  ```
  (place AFTER line 35; the directory negation is required because git won't descend into an ignored dir to see the file negation — include both lines.)
- THEN `git add assets/music/fintech.mp3 assets/music/calm.mp3` (or `git add -f` as a belt-and-suspenders).
- Verify: `git check-ignore -v assets/music/fintech.mp3` must return **nonzero / no output**, and `git status` must show both mp3s staged.

---

## 4. Step-by-step execution recipe (for the orchestrator)

> Run from the **`walk-studio-hosted`** worktree (branch `hosted-saas`). `MAIN=/Users/dennis/Desktop/Projects/Hackathons/hermes-video-agent` (the `main` worktree). Use `git checkout main -- <file>` from inside hosted-saas (same repo, both branches present) so you copy committed `main` blobs cleanly.

0. **Pre-flight:** `git status` clean-ish; stash/commit nothing destructive. Confirm on `hosted-saas`. Back up: `git branch hosted-saas-prefix-$(date +%s)`.

1. **PORT main wholesale** (group A) — from hosted-saas:
   ```
   git checkout main -- align_vo.py build_timeline.py validate_planner.py plan_job.py \
     stripe_money.py orchestrator.py brain.py capture_screenshots.py \
     analyze.py read_pass.py run_producer_brain.py analyzer-prompt.md \
     studio/src/timeline/archetypes/AppleScreenshot.tsx \
     studio/src/timeline/archetypes/WalkthroughPlayer.tsx \
     studio/src/generated/active.tsx
   ```
   (Optionally also `mcp_studio_server.py` — not needed by the worker; skip for a lean image.)

2. **PORT + re-apply cloud-fix** — `adapters.py`, `build_runner.py`:
   ```
   git checkout main -- adapters.py build_runner.py
   ```
   Then RE-APPLY `--concurrency=50%` (replace the single `--concurrency=8` occurrence in each):
   - `adapters.py` `generate_overlay` (the `remotion render … Overlay …` call, ~L1718).
   - `build_runner.py` `_run_vo_engine` (the `remotion render … Timeline …` call, ~L361 on main).
   (Leave main's own edge-tts retry as-is; do NOT re-add hosted-saas's.)

3. **KEEP hosted-saas's `walk_native.py`** — do nothing (already has the anullsrc fix; main has none to add).

4. **`style_fill.py`** — keep hosted-saas's committed version (has `concurrency=50%`), and ADD main's BGM music-path hunk (the `_MUSIC_DIR = …/assets/music` block replacing the two absolute sibling-repo paths). Easiest: open `style_fill.py` and apply the exact hunk shown in main's uncommitted working tree (region ~L3217–3227). Result must have BOTH `concurrency=50%` AND repo-relative `_MUSIC_DIR`.

5. **Bundle the music:**
   ```
   mkdir -p assets/music
   cp "$MAIN/assets/music/fintech.mp3" "$MAIN/assets/music/calm.mp3" assets/music/
   ```

6. **`.gitignore` negation** (REQUIRED — see §3): add `!assets/music/` and `!assets/music/*.mp3` after line 35. Verify with `git check-ignore -v assets/music/fintech.mp3` → no output.

7. **Dockerfile:** delete the music-bed block (lines 53–60). No replacement.

8. **Stage & verify before commit:**
   ```
   git add -A
   git status                         # MUST show assets/music/*.mp3 staged
   git check-ignore assets/music/*.mp3  # MUST be empty
   grep -rn "concurrency=8" adapters.py build_runner.py style_fill.py   # MUST be empty (all 50%)
   grep -n "anullsrc" walk_native.py  # MUST match (silent-audio kept)
   grep -n "_MUSIC_DIR" style_fill.py # MUST match (repo-relative BGM)
   grep -n "/Users/dennis" Dockerfile # MUST be empty (music block gone)
   ```

9. **Commit on hosted-saas** (single commit), then **deploy:**
   ```
   git commit -m "unify(pipeline): port main pipeline onto hosted-saas + bundle real music"
   railway up        # manual deploy from THIS dir
   ```
   (Push to origin/hosted-saas too if that's the discipline.)

---

## 5. Files explicitly NOT touched
`web/**`, `worker/**`, `insforge/**`, `insforge.toml`, `Dockerfile` (except music block), `.dockerignore`, all hosted-saas-only docs. These are the cloud frontend/worker surface and stay on hosted-saas as-is.

---

## 6. RISK list (what could break the worker)
1. **[BIGGEST] `*.mp3` gitignore silently drops the music.** If §3/§6 negation is skipped, the commit looks fine, the build runs, but `assets/music/` is empty in the image → silent video AGAIN (and the new code may now also fail/log if it `os.path.exists`-guards the track, vs the old placeholder that at least existed). MUST verify `git check-ignore` empty AND files staged before committing.
2. **Ported `build_runner.py` ImportErrors** if it imports `analyze` / `read_pass` / `run_producer_brain` and one wasn't ported. Mitigation: ported all four in step 1; after porting, run `python3 -c "import build_runner"` (UNCERTAIN — may need pipeline deps; at minimum grep `build_runner.py` for `import analyze`/`read_pass`/`run_producer_brain` and confirm each exists).
3. **Conversion Read / ANALYZE stage may invoke tools the container lacks** (NemoClaw, egress allowlist, extra models). main's analyze path is flag-gated (`PRODUCER_CONVERSION_READ`); ensure the worker does NOT enable a flag the container can't satisfy. (UNCERTAIN — check `worker/run.js` env + `build_runner.py` flag defaults; out of this plan's read scope.)
4. **Re-applying concurrency wrong:** porting main re-introduces `--concurrency=8`; if the re-apply is missed, render uses 8 workers on a 2-core box → slower / possible OOM. The grep in step 8 guards this.
5. **`walk_native.py` accidentally overwritten by a stray `git checkout main --`** would re-break the cloud render (main has `-an`). Keep it OUT of step 1's checkout list (it is).
6. **`active.tsx` is a generated fixture** — harmless, but if the worker regenerates scenes it's moot. Non-blocking.

## 7. Post-deploy VERIFICATION checklist (fresh build)
- [ ] Kick a fresh run end-to-end (NOT a cached/old `final.mp4` — frozen at render-time code).
- [ ] **Music present:** `ffprobe -show_streams <new final.mp4>` shows a NON-silent `a:0`; or extract audio and check RMS > silence. (Judge the WHOLE video, not one frame — per Dennis's standing rule.)
- [ ] **No focus-ring / no cursor** on screenshot scenes: pull a ffmpeg contact sheet across the screenshot beats and read scene-by-scene (the AppleScreenshot reveal must have no highlight box, no moving cursor/ripple). WalkthroughPlayer keeps its own cursor — that's expected.
- [ ] **Render succeeded on linux-x64** (no ffprobe `a:0` failure) → confirms walk_native anullsrc fix is live.
- [ ] Container has `/app/assets/music/fintech.mp3` + `calm.mp3` (railway logs / shell): non-zero size, NOT the 60s silent placeholder.
- [ ] Build logs show `--concurrency=50%` in the remotion render commands.

---

### Single biggest risk (one line)
The global `*.mp3` rule in hosted-saas `.gitignore:35` will SILENTLY drop the bundled `assets/music/*.mp3` (proven by `git check-ignore`), so without adding a `!assets/music/` + `!assets/music/*.mp3` negation and confirming the files are actually staged, the redeploy will look correct but ship silent video exactly as before.
