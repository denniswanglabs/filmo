# Repo Public-Flip Readiness Audit — `denniswanglabs/walk-studio`

**Audited:** 2026-06-26 (read-only PREP/AUDIT subagent — no commits, no pushes, no visibility change made)
**Target:** flip private → public for the 2026-06-30 Hermes hackathon submission
**Branches in scope:** `main`, `hosted-saas` (deploy source), `conversion-read`, `hosted-saas-preunify-1782440000`, plus all `origin/*` mirrors — full history swept.

---

## (a) VERDICT: **GO-AFTER-FIXES**

No real secrets anywhere in history or either working tree. The only required pre-flip action is **adding a LICENSE** (a hackathon/OSI expectation, not a safety issue). Everything else listed below is optional polish. If you skip the optional items, the repo is still safe to make public the moment LICENSE lands.

---

## (b) Secret-sweep findings

**No real secrets found in git history. No real secrets found in either working tree.**

Swept across ALL branches + full history (`git log --all --full-history -p`) and both working trees (`walk-studio-hosted` on `hosted-saas`, `hermes-video-agent` on `main`), excluding `node_modules`/`.git`/`.next`/`dist`/`build`.

Patterns scanned: `sk_live` `sk_test` `sk-or-v1-` `xi-api-` `AKIA…` `-----BEGIN … PRIVATE KEY` `eyJ…`(JWT) and literal-value variants of `ELEVENLABS_API_KEY=` `OPENROUTER_API_KEY=` `INSFORGE_API_KEY=` `STRIPE_SECRET_KEY=` `PASSWORD=` `TOKEN=` requiring a 20+ char payload (env-references excluded).

**Result: zero literal secret payloads.** Every hit is one of:

| Category | Example | Why it's safe |
|---|---|---|
| Doc placeholders | `STRIPE-SETUP.md:44` `STRIPE_SECRET_KEY=sk_test_…` | literal `…` ellipsis, instructs the reader to add their own key to `~/.hermes/.env` |
| Stripe key-*type* labels in guard logic | `stripe_money.py:49-51`, `mcp_studio_server.py:690-725`, `build_runner.py:744` | `val.startswith(("sk_test_","rk_test_"))` — prefix strings used to classify/refuse keys; no payload |
| Env-var *names* / `os.environ` reads | `keystone-test.js` (`process.env.INSFORGE_API_KEY`), `align_vo.py:236` (`headers={"xi-api-key": key}` where `key` is read from env) | references, not values |
| Redaction regexes | `STRIPE-PRODUCER-DESIGN.md:30` | Hermes's own secret-scrubbing patterns |

**Secret hygiene confirmed:**
- `.gitignore` (root) ignores `.env`, `.env.*`, `*.env`, `*.pem`, `*secret*`, `*credentials*`, `client_secrets.json`; `web/.gitignore` ignores `.env*.local`. Verified `.env` is actively ignored (`git check-ignore` exit 0).
- **No `.env` / `.env.local` / `.env.*` file is tracked now** (`git ls-files | grep .env` → empty).
- **No secret-named file ever existed in history** (`git log --all --name-only` → no `.env`/`secret`/`credential`/`.pem`/`client_secret`).
- `~/.hermes/.env` (the real secrets store) does not exist inside either worktree and nothing is tracked under `.hermes/`. Secrets live correctly in `~/.hermes/.env` + Railway/Vercel env vars, referenced via `process.env`/`os.environ` only.
- The two tracked filenames containing "key"/"env" — `worker/keystone-test.js` and `web/next-env.d.ts` — are clean (the former uses `process.env.*` only; the latter is a Next.js type shim).

Demo target brands appearing in code/screenshots (Stripe, Plaid, Allbirds, Tripadvisor, Shopify, Linear, Vercel, etc.) are all **public companies used as demo URLs** — not private clients. No NDA/confidential/private-client markers found in tracked docs (the `confidential`/`internal` grep hits were benign words like "internal businesses", "secondary accent", "standalone tool").

---

## (c) LICENSE recommendation

**Recommend MIT.** Simplest, most permissive, the de-facto standard for hackathon submissions and small OSS projects; judges and contributors recognize it instantly. Full text is drafted at **`LICENSE.CANDIDATE`** (inert, uncommitted) with `Copyright (c) 2026 Dennis Wang`.

*Apache-2.0 alternative:* materially better ONLY if you want an explicit patent grant + contributor patent-retaliation clause (relevant if the agent/pricing logic might be patentable IP you want defensively covered). For a hackathon entry that's unlikely to matter, and Apache-2.0 adds a `NOTICE` file convention + more boilerplate. **MIT is the right call unless Dennis specifically wants patent-grant language.**

To activate: rename `LICENSE.CANDIDATE` → `LICENSE` (see command block below). Optionally add a year/owner line to the README footer.

---

## (d) Pre-flip checklist for Dennis

**Required (do before flipping):**
- [ ] **Add a LICENSE.** `mv LICENSE.CANDIDATE LICENSE` then commit (command block below). This is the only hard gate.

**Recommended (nice-to-have, not blockers):**
- [ ] Update the README footer line `Hermes hackathon entry. Private during development.` → drop "Private during development" (now public).
- [ ] (Optional) Generalize hardcoded absolute dev paths in **tracked** files so the repo is reproducible for others — these leak your local layout but no secrets:
  - `.claude/launch.json:14,20` — `/Users/dennis/Desktop/Projects/Hackathons/hermes-video-agent`
  - `adapters.py:1699` — `kit = "/Users/dennis/Desktop/Projects/Hackathons/motion-graphics-kit"`
  - `run_producer_brain.py:9` — `HERE = "/Users/dennis/Desktop/.../hermes-video-agent"`
  - (also present in several `*.md` design docs — cosmetic only)
- [ ] (Optional) Repo weight: **~168 MB of tracked PNGs** (75 files >800 KB; the `studio/public/shot-*.png` review screenshots run ~4–5 MB each). Not a safety issue, but it makes the public clone heavy and exceeds the asset-hygiene budget (raster ≤200 KB). Consider downsampling or dropping the per-round review screenshots before flipping. No tracked video/zip/binary junk otherwise.

**Already clean (no action):** secrets, `.gitignore`, README presentability (README.md is professional, 73 lines, accurate), no tracked `.env`, no private-client data.

---

## (e) Commands to flip — **DENNIS-EXECUTES** (not run by this audit)

```sh
cd ~/Desktop/Projects/Hackathons/walk-studio-hosted

# 1. Activate the LICENSE (MIT, drafted at LICENSE.CANDIDATE)
mv LICENSE.CANDIDATE LICENSE
git add LICENSE
git commit -m "Add MIT license"

# 2. (recommended) drop the "Private during development" README footer, then:
#    git add README.md && git commit -m "Prep README for public release"

# 3. Push the license commit to the branch you submit from
git push origin hosted-saas      # (or whichever branch the submission points at)

# 4. Flip visibility to public
gh repo edit denniswanglabs/walk-studio --visibility public --accept-visibility-change-consequences
```

> **Uncertain — Dennis decides:** which branch the hackathon submission points at (`hosted-saas` is the deploy source per the brief, but `main` may be the default the judges land on). Make sure LICENSE is committed on **whatever branch is the repo default** so it shows on the GitHub landing page. If unsure, land LICENSE on both `main` and `hosted-saas`.

> **Note:** `gh repo edit --visibility public` requires the `--accept-visibility-change-consequences` flag on current `gh`; if your `gh` version rejects it, drop the flag or flip via the GitHub web UI (Settings → Danger Zone → Change visibility).
