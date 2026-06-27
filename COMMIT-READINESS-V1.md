# COMMIT-READINESS-V1

Read-only repo-hygiene audit for Filmo (NVIDIA×Stripe×Nous). No git state was mutated.
Date: 2026-06-26.

## VERDICT (one line)
**PASS — no real secret would be committed on either branch.** All secret-pattern hits are placeholders (`sk_test_xxx`), code that references key-type strings, or env-var *names* — zero literal key values. The real secrets file (`~/.hermes/.env`, referenced as `.hermes/`) is gitignored on both trees.

---

## 1. TOPOLOGY

The "three dirs" are NOT three repos. They are **one** GitHub repo (`denniswanglabs/walk-studio`) checked out as multiple **git worktrees**. The first two listed dirs share one toplevel.

| Dir | toplevel | branch | remote |
|-----|----------|--------|--------|
| `…/walk-studio-hosted/web/` | `…/walk-studio-hosted` (web/ is just a SUBDIR — no nested `.git`) | `hosted-saas` | `https://github.com/denniswanglabs/walk-studio.git` |
| `…/walk-studio-hosted/` | `…/walk-studio-hosted` | `hosted-saas` | same |
| `…/hermes-video-agent/` | `…/hermes-video-agent` (separate worktree) | `main` | same |

`git worktree list` (all worktrees of the repo):
- `…/hermes-video-agent`  → `[main]`  (the pipeline: python + studio)
- `…/walk-studio-hosted`  → `[hosted-saas]`  (landing + app; `web/` lives here)
- `…/walk-studio-conversion-read` → `[conversion-read]`  (a THIRD worktree, not in the brief — flagged for awareness; not audited this pass)

Key correction to the brief's premise: `web/` is a subdirectory of the `hosted-saas` worktree, not its own tree. The pipeline python files at `…/walk-studio-hosted/` root are tracked on `hosted-saas` (e.g. `worker/run.js`), while the *other* pipeline tree (`hermes-video-agent`) is on `main`.

---

## 2. CLEANUP PLAN (exact commands — NOT executed)

### 2a. The ~153 `.handoff*.md` scratch files
- **They live on `main` (the `hermes-video-agent` worktree), NOT on `hosted-saas`.** Exact count tracked: **153**.
- Sample: `.handoff-abort.md`, `.handoff-aboutpage.md`, `.handoff-align-vo.md`, `.handoff-analytics-backend.md`, `.handoff-apple-archetypes.md` …
- EXACT untrack command (run from the hermes worktree; leaves files on disk, removes from index):
  ```sh
  # from /Users/dennis/Desktop/Projects/Hackathons/hermes-video-agent
  git rm --cached $(git ls-files | grep '\.handoff')
  # then add an ignore rule and commit:
  #   echo '.handoff*.md' >> .gitignore
  #   git add .gitignore && git commit -m "chore: untrack .handoff scratch files"
  ```
  Null-safe variant if any path has spaces (none observed, but safer):
  ```sh
  git ls-files -z | grep -z '\.handoff' | xargs -0 git rm --cached
  ```
  > NOTE: `git rm --cached` is non-destructive to the working tree (keeps the files), but it IS a mutating git op — per brief rule 8 / read-only mandate, this is PRESENTED, not run.

### 2b. AI-tool dirs — keep UNTRACKED, add to `.gitignore`
On `main` (hermes), all 8 dirs **exist, are currently UNTRACKED and NOT ignored** — so a blanket `git add .` *would* sweep them in (confirmed via `git add -n .` dry-run: it queued `.agents/skills/...`). On `hosted-saas` none of these dirs exist.

| dir | exists (main) | tracked? | ignored? |
|-----|---------------|----------|----------|
| `.agents/`   | yes | untracked | NOT ignored ⚠ |
| `.augment/`  | yes | untracked | NOT ignored ⚠ |
| `.kilocode/` | yes | untracked | NOT ignored ⚠ |
| `.qoder/`    | yes | untracked | NOT ignored ⚠ |
| `.qwen/`     | yes | untracked | NOT ignored ⚠ |
| `.roo/`      | yes | untracked | NOT ignored ⚠ |
| `.trae/`     | yes | untracked | NOT ignored ⚠ |
| `.windsurf/` | yes | untracked | NOT ignored ⚠ |

Also untracked on main and worth ignoring: `.claude/skills/`, `skills/`, `skills-lock.json` (these duplicate the same vendored `upgrade-stripe` skill).

Recommended `.gitignore` additions (append to hermes `.gitignore`):
```gitignore
# ── AI-tool working dirs (never commit) ──
.agents/
.augment/
.kilocode/
.qoder/
.qwen/
.roo/
.trae/
.windsurf/
.claude/
# vendored skill mirrors
skills/
skills-lock.json
# scratch handoffs
.handoff*.md
```

---

## 3. STAGE PREVIEW (what a commit WOULD include)

### Branch `main` (hermes-video-agent) — 32 porcelain entries (13 modified, 19 untracked)
Modified (tracked) — `git diff --stat` totals **+760 / −225** across 13 files:
- `.handoff-webhook-bridge.md`, `HOSTED-SAAS-SPEC.md`
- `adapters.py`, `align_vo.py`, `build_runner.py`, `build_timeline.py`, `orchestrator.py`, `plan_job.py`, `stripe_money.py`, `validate_planner.py`
- `studio/src/generated/active.tsx`, `studio/src/timeline/archetypes/AppleScreenshot.tsx`, `studio/src/timeline/archetypes/WalkthroughPlayer.tsx`

Untracked (19) — would only be added by `git add .` / `git add <path>`:
- AI-tool dirs (8) + `.claude/skills/`, `skills/`, `skills-lock.json`  → **should stay untracked / be ignored (see §2b)**
- `HANDOFF-2026-06-25.md`, `RESUME-NOW.md`  (scratch docs)
- `mcp_studio_server.py`, `run_producer_brain.py`  (code)
- `studio/public/brand-logo-exp-vercel-1.png`  (asset)
- `dashboard/.hermes-mark-preview.png`, `dashboard/.recents-search-full.png`, `dashboard/.recents-search-linear.png`  (screenshots)

### Branch `hosted-saas` (walk-studio-hosted) — 9 porcelain entries (1 modified, 8 untracked)
Modified (tracked) — `+273 / −16`:
- `worker/run.js`

Untracked (8) — all benign (SQL migrations, research notes, one capture png):
- `insforge/migrations/20260625191303_add-props-to-runs.sql`
- `insforge/migrations/20260626040000_add-props-edited-to-runs.sql`
- `insforge/migrations/20260626120000_add-rerender-columns.sql`
- `migrations/`
- `research/ellipsus-direction.md`, `research/hera-landing-capture.md`, `research/tappay-iphone-analysis.md`
- `nemoclaw-capture.png`

---

## 4. SECRETS TABLE (evidence: file:line; values redacted to prefix + nature)

Patterns scanned across BOTH branches' full committable surface (tracked diffs + all untracked text files): `sk_live` `sk_test` `rk_live/test` `whsec_` `xi-api-key` `nvapi-` `sk-or-` `AWS_(ACCESS|SECRET)` `SUPABASE_*` `INSFORGE` `password=` `Bearer <token>` `AKIA…` `eyJ…(JWT)` and literal-value variants requiring 20+ char payloads.

| File:line | branch | match | redacted | verdict |
|-----------|--------|-------|----------|---------|
| `align_vo.py:118` (diff) | main | `xi-api-key: <key>` | docstring placeholder `<key>` | **false-positive** (header doc) |
| `align_vo.py:157` (diff) | main | `headers={"xi-api-key": key,` | `key` = var read from `os.environ.get("ELEVENLABS_API_KEY")` (line 45) | **false-positive** (var, not value) |
| `*/skills/upgrade-stripe/SKILL.md:55,79,84,168,175` (×8 mirror dirs: `.agents/.augment/.claude/.kilocode/.qoder/.qwen/.roo/.trae/.windsurf/`+`skills/`) | main (untracked) | `sk_test_xxx` | literal `sk_test_` + `xxx…` | **false-positive** (vendored Stripe doc placeholder) |
| `mcp_studio_server.py:690,694,721,725,940` | main (untracked) | `sk_test_/rk_test_`, `sk_live_/rk_live_` | string literals used as key-TYPE labels in guard logic; no payload | **false-positive** (mode-guard logic) |
| `HANDOFF-2026-06-25.md:102` | main (untracked) | `INSFORGE`, `acct_1TTyp9...`, env-var names | `acct_1TTyp9…` = Stripe *account id* (truncated), names only: `STRIPE_SECRET_KEY`,`INSFORGE_URL`,`INSFORGE_API_KEY`,`OPENROUTER_API_KEY` | **test-key-ok-but-review** (no values; describes WHERE keys live — `~/.hermes/.env`, `~/.zshrc`) |

### Literal-value scan (real key prefixes + 20+ char payloads), both branches: **ZERO hits.**
- main committable content: 0 literal keys.
- hosted-saas committable content: 0 literal keys.

### Prior-leak commit `4c189c0`
- Inspected: its diff content yields **no** secret-pattern matches (the commit is planner/framework code; no key values surface in it).
- The real secrets file lives at `~/.hermes/.env`; `.hermes/` is **gitignored on both worktrees** (`git check-ignore .hermes/` → matches on both). No `.env`, `*.key`, `*.pem`, `*secret*`, or `*credentials*` file is tracked on either branch.
- UNCERTAIN: I did not deep-rewrite-scan the entire historical pack for `4c189c0`'s exact leaked bytes beyond pattern-grepping its diff; if a value was force-pushed/rewritten earlier it could persist in unreachable objects. Working-tree and committable surface are clean — that is what a *new commit* would expose, and it is clean.

---

## SUMMARY
- Topology: ONE repo, 3 worktrees (`main` / `hosted-saas` / `conversion-read`); `web/` is a subdir of `hosted-saas`.
- 153 `.handoff*.md` are tracked on **main** — untrack command provided (not run).
- 8 AI-tool dirs untracked + un-ignored on **main**; `git add .` would catch them — `.gitignore` additions provided.
- **No real secret would be committed on either branch.** PASS.
