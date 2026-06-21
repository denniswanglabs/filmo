/* HERMES — Producer Console. Vanilla JS, no deps. Reads runs/<id>/ledger.json
   (schema in LEDGER.md) and renders the job ledger, the P&L receipt, the budget
   gate as an NLE filmstrip, the Studio view (the agent typing its real Remotion
   code), the final cut, and the Stripe/events log. */

const state = { runs: [], selected: null, ledger: null, typer: null, scriptTyper: null, scriptShown: null, shareTimer: null, liveGoalShown: null, payForShown: null, pace: "standard",
  /* COST-PLUS PRICING — `pricing` is the fetched canonical pricing.json (the
     SINGLE source of truth; numbers are NEVER hand-duplicated). There are NO
     tiers and NO boosters: the agent prices each video cost-plus from its own
     scene plan (plan_cogs * markup, floored + rounded). The ONE customer choice,
     made UPFRONT on the composer, is `selection.quality` ("standard" | "premium"):
       - standard = Remotion designed motion-graphics + a clean synthetic voice
         (edge-tts). No Higgsfield, no ElevenLabs. Cheapest, lands at the $5 floor.
       - premium  = cinematic AI footage (Higgsfield) + a natural voice (ElevenLabs).
         Richer / costs more (~$6-9).
     It changes WHAT the agent produces, so it is chosen before Build and threaded
     into the /api/build payload as { quality }. */
  pricing: null,
  view: null,   // null = build console; "analytics" = the operator P&L view
  selection: { quality: "standard" } };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const cents = (c) => (c == null ? "—" : "$" + (c / 100).toFixed(2));
const pct = (f) => (f == null ? "—" : (f * 100).toFixed(1) + "%");
const icon = (id, cls) => `<svg class="${cls || "ic"}" aria-hidden="true"><use href="#${id}"/></svg>`;

/* ---- HERO word-by-word build (D2 + D3) -------------------------------------
   The single highest-impact "polished" move: the ONE hero line of each state
   builds word-by-word on the blur-rise motion preset, and the key clause lands
   LAST in --amber as its own beat ("the accent carries the payload"). Apply ONLY
   to the one hero line per state — never to body copy.

   `setup` is the plain text that builds first (near-ink); `accent` is the clause
   that resolves second in amber. Either may already contain markup-safe text
   only (we escape per word). Words animate via CSS `hero-blur-rise` with a
   per-word `animation-delay` (~85ms apart) so the build reads as authored motion
   the instant a judge sees the screen. The accent words pick up after the setup,
   with a small extra beat of gap so the punchline lands distinctly.

   Deterministic: delays are derived purely from word index, no rAF/clock — the
   same string always animates identically (matters for the demo + headless). */
const HERO_STEP = 0.085;      // s between words
const HERO_ACCENT_GAP = 0.12; // s extra beat before the accent clause lands
function heroWords(setup, accent) {
  const words = [];
  const setupArr = String(setup == null ? "" : setup).split(/\s+/).filter(Boolean);
  const accentArr = String(accent == null ? "" : accent).split(/\s+/).filter(Boolean);
  let i = 0;
  setupArr.forEach((w) => {
    words.push('<span class="hw" style="animation-delay:' + (i * HERO_STEP).toFixed(3) + 's">' + esc(w) + "</span>");
    i++;
  });
  // the accent clause resolves as a second beat, in amber, after a small gap
  const base = setupArr.length ? setupArr.length * HERO_STEP + HERO_ACCENT_GAP : 0;
  accentArr.forEach((w, k) => {
    words.push('<span class="hw hw-accent" style="animation-delay:' + (base + k * HERO_STEP).toFixed(3) + 's">' + esc(w) + "</span>");
  });
  return '<span class="hero-build">' + words.join(" ") + "</span>";
}

/* Variant for "Your <brand> promo is ready" — a bold-ink brand word sits inside
   the setup (its own emphasis), then the accent clause lands last in amber. Same
   per-word blur-rise build + deterministic delays as heroWords. */
function heroWordsBrand(pre, brand, mid, accent) {
  const words = [];
  let i = 0;
  String(pre || "").split(/\s+/).filter(Boolean).forEach((w) => {
    words.push('<span class="hw" style="animation-delay:' + (i * HERO_STEP).toFixed(3) + 's">' + esc(w) + "</span>"); i++;
  });
  if (brand) {
    words.push('<span class="hw hw-brand" style="animation-delay:' + (i * HERO_STEP).toFixed(3) + 's">' + esc(brand) + "</span>"); i++;
  }
  String(mid || "").split(/\s+/).filter(Boolean).forEach((w) => {
    words.push('<span class="hw" style="animation-delay:' + (i * HERO_STEP).toFixed(3) + 's">' + esc(w) + "</span>"); i++;
  });
  const base = i * HERO_STEP + HERO_ACCENT_GAP;
  String(accent || "").split(/\s+/).filter(Boolean).forEach((w, k) => {
    words.push('<span class="hw hw-accent" style="animation-delay:' + (base + k * HERO_STEP).toFixed(3) + 's">' + esc(w) + "</span>");
  });
  return '<span class="hero-build">' + words.join(" ") + "</span>";
}

/* Auto-accent variant for free-text hero lines (the live build goal): builds
   word-by-word, and the final clause (last `tail` words, default 2) lands last
   in amber so even an arbitrary goal string gets the "payload lands second"
   rhythm. Falls back gracefully on 1-2 word strings. */
function heroAuto(text, tail) {
  const arr = String(text == null ? "" : text).split(/\s+/).filter(Boolean);
  if (!arr.length) return "";
  const n = Math.min(tail || 2, Math.max(1, arr.length - 1));
  const setup = arr.slice(0, arr.length - n).join(" ");
  const accent = arr.slice(arr.length - n).join(" ");
  return heroWords(setup, accent);
}

/* ============================================================================
   COST-PLUS PRICING  —  no tiers, no boosters, no consent.

   The agent prices each video from its OWN scene plan: the variable production
   COGS times a MARKUP, with a price FLOOR, rounded to a clean increment. The
   customer never picks a tier — they make ONE upfront choice, QUALITY:
     - standard = Remotion designed motion-graphics + a clean synthetic voice
       (edge-tts). No Higgsfield, no ElevenLabs. COGS ~free -> price floors at $5.
     - premium  = cinematic AI footage (Higgsfield) + a natural voice (ElevenLabs).
       Those land in COGS -> the cost-plus price rises (~$6-9).
   Quality changes WHAT the agent makes, so it is chosen BEFORE Build and threaded
   into the /api/build payload as { quality }. The pay-gate then shows the single
   quote the backend priced for that quality (no add-on toggle anymore).

   SINGLE SOURCE OF TRUTH: every number comes from the fetched canonical
   pricing.json (state.pricing) — markup / price_floor_cents / round_to_cents /
   quality.{standard,premium}. Nothing is hand-coded. The cost-plus rule mirrors
   pricing.price_for_plan() EXACTLY:
     price = max(price_floor_cents, round_to_nearest(round_to_cents, plan_cogs * markup))
   ========================================================================== */

// Fetch the canonical pricing.json ONCE. Served at the project root by serve.py
// (docroot = PROJECT_ROOT), so /pricing.json is already available — no extra
// route needed. On failure pricing is left null: the quote falls back to the
// priced ledger (earn.price_cents) and the build still works (the backend
// prices the plan itself).
async function loadPricing() {
  try {
    const res = await fetch("/pricing.json", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    state.pricing = await res.json();
  } catch (e) {
    state.pricing = null;  // silent fallback: quote reads the priced ledger
  }
}

// The config block for a quality tier from pricing.json (label/blurb/cogs_floor).
function qualityDef(quality) {
  const q = (state.pricing || {}).quality || {};
  return q[quality] || {};
}
function qualityLabel(quality) {
  return qualityDef(quality).label || (quality === "premium" ? "Premium" : "Standard");
}

// COST-PLUS price from a plan's variable COGS, mirroring pricing.price_for_plan().
// Used as a fallback when the ledger hasn't surfaced a concrete price yet, and to
// preview the chosen quality's "from $X" floor on the composer.
function costPlusPrice(planCogsCents) {
  const p = state.pricing || {};
  const markup = p.markup != null ? p.markup : 6.0;
  const floor = p.price_floor_cents != null ? p.price_floor_cents : 500;
  const step = p.round_to_cents != null ? p.round_to_cents : 50;
  const raw = (planCogsCents || 0) * markup;
  const rounded = step > 0 ? Math.round(raw / step) * step : Math.round(raw);
  return Math.max(floor, rounded);
}

// The "from $X" floor price for a quality tier (the cheapest it can be): the price
// floor for standard; the cogs_floor x markup (or the floor, whichever is higher)
// for premium. Mirrors what the backend would price on a thin plan.
function qualityFromPrice(quality) {
  const floorCogs = qualityDef(quality).cogs_floor_cents || 0;
  return costPlusPrice(floorCogs);
}

/* Resolve the per-video price for a priced ledger (the single quote — there is no
   add-on in the quality model). Priority: the producer's own priced number
   (earn.price_cents, else earn.base_price_cents), then a cost-plus compute from
   the plan COGS, then the legacy pricing.suggested_price_cents. Returns null when
   nothing is priced yet (the gate shows "pricing…"). */
function ledgerPriceCents(l) {
  const earn = l.earn || {};
  if (earn.price_cents != null) return earn.price_cents;
  if (earn.base_price_cents != null) return earn.base_price_cents;
  const cogs = (l.pricing || {}).plan_cogs_cents != null ? l.pricing.plan_cogs_cents
             : (l.plan || {}).cogs_cents;
  if (cogs != null) return costPlusPrice(cogs);
  const sugg = (l.pricing || {}).suggested_price_cents;
  return sugg != null ? sugg : null;
}

/* ---------------- index + rail ---------------- */
async function loadIndex(isRefresh) {
  const btn = $("refresh");
  if (isRefresh && btn) btn.classList.add("spin");
  try {
    const res = await fetch("/runs/index.json", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    state.runs = (data && data.runs) || [];
    renderRail();
    setConn("ok", state.runs.length + " jobs");
    // If a live build poll currently owns the selected run, leave its live view
    // alone — re-running selectRun here would overwrite the BUILDING/production
    // view with the static post-hoc detail (the bug that made a just-paid,
    // still-producing run look like a finished one on the ?paid return).
    if (state.building && state.building === state.selected) {
      // rail refreshed; the active poll keeps rendering the stage.
    } else if (state.selected && state.runs.some((r) => r.run_id === state.selected)) {
      // A build is already open (an explicit sidebar click or a checkout return) —
      // keep it shown across rail refreshes.
      selectRun(state.selected, true);
    }
    // A fresh load with nothing selected stays on the COMPOSER empty state. We no
    // longer auto-open a past build on boot — opening one is an explicit sidebar
    // click (like Claude's "New chat" default vs. picking a past chat).
  } catch (e) {
    setConn("err", "console offline");
    const list = $("rail-list");
    if (list && !state.runs.length) list.innerHTML = '<div class="rail-empty">Couldn\'t reach the console &mdash; is the server running? <span class="re-detail">' + esc(e.message) + "</span></div>";
  } finally {
    if (btn) setTimeout(() => btn.classList.remove("spin"), 500);
  }
}

function setConn(cls, txt) {
  const d = $("conn-dot"), t = $("conn-text");
  if (d) d.className = "rec-dot " + cls;
  if (t) t.textContent = txt;
}

/* ---- rail row TITLE: an Anthropic/Claude-style DESCRIPTIVE conversation title --
   Claude's sidebar rows read "<thing> — <what about it>", not a bare noun. We do
   the same per build: "<Brand> — <video descriptor>" derived from the ledger's
   job.goal + company_url, single line, ellipsis-truncated.
     · BRAND, in priority order:
         1) the registrable brand label of the company_url host — the segment just
            BEFORE the public suffix, so subdomains don't win:
            "docs.stripe.com" → "Stripe", "linear.app" → "Linear", "notion.so" → "Notion"
         2) the run-id slug between "build-" and the trailing hash
            ("build-orinovate-edf804" → "Orinovate"; "demo-2-downgrade" → "Demo 2 Downgrade")
     · DESCRIPTOR: a short video-type phrase mined from the goal text (e.g. a goal
       of "30-second promo plus a short product walkthrough" → "promo + walkthrough").
       Falls back to a generic "promo" when the goal names no recognizable type, so
       every row still reads as a video, never a bare brand. */
// extract the registrable brand label from a host: the dotted segment immediately
// before the public suffix (handles common two-part suffixes like co.uk / com.tw).
function brandFromHost(host) {
  const parts = host.split(".").filter(Boolean);
  if (parts.length <= 1) return parts[0] || "";
  // two-part public suffixes where the brand is parts[len-3]
  const twoPart = new Set(["co", "com", "org", "net", "gov", "edu", "ac"]);
  const secondLast = parts[parts.length - 2];
  if (parts.length >= 3 && twoPart.has(secondLast.toLowerCase())) return parts[parts.length - 3];
  return parts[parts.length - 2];  // e.g. stripe in docs.stripe.com, linear in linear.app
}
// just the brand label (title-cased), no descriptor — the left half of the title.
function railBrand(r) {
  let base = "";
  const url = (r.company_url || "").trim();
  if (url) {
    const host = url.replace(/^https?:\/\//i, "").replace(/^www\./i, "").split("/")[0];
    if (host) base = brandFromHost(host);
  }
  if (!base) {
    base = String(r.run_id || "")
      .replace(/^build[-_]/i, "")
      .replace(/[-_][0-9a-f]{6,}$/i, "");  // trailing hex hash
  }
  base = base.replace(/[-_.]+/g, " ").trim();
  if (!base) base = r.run_id || "build";
  return base.split(/\s+/).map((w) =>
    w ? w.charAt(0).toUpperCase() + w.slice(1) : w).join(" ");
}
// mine a short video-type descriptor from the free-text goal. We look for the
// known video shapes (explainer / walkthrough / promo / social ad / launch film /
// demo) IN THE ORDER they appear, dedupe, and join the first one or two with " + "
// so a compound goal ("promo plus a walkthrough") reads "promo + walkthrough".
function railDescriptor(goal) {
  const g = String(goal || "").toLowerCase();
  if (!g) return "promo";
  const TYPES = [
    [/walk-?through/, "walkthrough"],
    [/explainer/, "explainer"],
    [/launch film/, "launch film"],
    [/social ad/, "social ad"],
    [/\bpromo\b|promotional/, "promo"],
    [/\bdemo\b/, "demo"],
    [/brand (video|film|story)/, "brand video"],
  ];
  const hits = [];
  TYPES.forEach(([re, label]) => {
    const m = g.match(re);
    if (m) hits.push([m.index, label]);
  });
  hits.sort((a, b) => a[0] - b[0]);
  const labels = [];
  hits.forEach(([, label]) => { if (!labels.includes(label)) labels.push(label); });
  if (!labels.length) return "promo";
  return labels.slice(0, 2).join(" + ");
}
// the full single-line title: "<Brand> — <descriptor>", ellipsis-truncated.
function railTitle(r) {
  const brand = railBrand(r);
  const desc = railDescriptor(r.goal);
  return clip(brand + " — " + desc, 42);
}
/* a faint second meta line (Anthropic-style): the relative date when a timestamp
   exists, else the run's mode (mock/real). Kept clean — one short token. */
function railMeta(r) {
  const rel = relTime(r.created_at);
  if (rel) return rel;
  const mode = (r.mode || "").toLowerCase();
  return mode ? mode : "";
}
// compact relative time ("today", "3d", "2w") from an ISO timestamp; "" if none.
function relTime(ts) {
  if (!ts) return "";
  const t = Date.parse(ts);
  if (isNaN(t)) return "";
  const diff = Date.now() - t;
  if (diff < 0) return "today";
  const day = 86400000;
  if (diff < day) return "today";
  const d = Math.floor(diff / day);
  if (d === 1) return "yesterday";
  if (d < 7) return d + "d";
  if (d < 30) return Math.floor(d / 7) + "w";
  if (d < 365) return Math.floor(d / 30) + "mo";
  return Math.floor(d / 365) + "y";
}

/* ---- recency grouping (Claude's "Today / Previous 7 days / Older") -----------
   Buckets runs by created_at when timestamps exist; runs WITHOUT a usable
   timestamp fall into a quiet "Recents" bucket. If NO run has a timestamp, the
   whole list collapses to a single "Recents" section (no false day boundaries). */
function railGroup(ts) {
  if (!ts) return { key: "recents", label: "Recents", order: 5 };
  const t = Date.parse(ts);
  if (isNaN(t)) return { key: "recents", label: "Recents", order: 5 };
  const now = Date.now();
  const day = 86400000;
  const startOfToday = new Date(); startOfToday.setHours(0, 0, 0, 0);
  if (t >= startOfToday.getTime()) return { key: "today", label: "Today", order: 0 };
  if (t >= now - 7 * day) return { key: "week", label: "Previous 7 days", order: 1 };
  return { key: "older", label: "Older", order: 2 };
}

function renderRail() {
  const list = $("rail-list");
  const stats = $("rail-stats");
  if (stats) stats.textContent = state.runs.length ? state.runs.length + (state.runs.length === 1 ? " build" : " builds") : "";
  list.innerHTML = "";
  if (!state.runs.length) {
    list.innerHTML = '<div class="rail-empty">No builds yet. Paste a company URL above to start your first one.</div>';
    return;
  }

  // Bucket runs by recency, preserving the index.json order within each bucket.
  const anyTs = state.runs.some((r) => r.created_at && !isNaN(Date.parse(r.created_at)));
  const buckets = {};
  state.runs.forEach((r) => {
    const g = anyTs ? railGroup(r.created_at) : { key: "recents", label: "Recents", order: 5 };
    (buckets[g.key] || (buckets[g.key] = { label: g.label, order: g.order, runs: [] })).runs.push(r);
  });
  const ordered = Object.values(buckets).sort((a, b) => a.order - b.order);

  ordered.forEach((bucket) => {
    const head = document.createElement("div");
    head.className = "rail-group";
    head.textContent = bucket.label;
    list.appendChild(head);
    bucket.runs.forEach((r) => list.appendChild(railRow(r)));
  });
}

/* ONE clean row, Anthropic/Claude-style: a DESCRIPTIVE title ("<Brand> —
   <video descriptor>") plus a faint meta line (date or mode). The MOCK/REAL
   badge, raw run-id, margin % and gross $ have moved OUT of the list (they live
   in the build's detail view). A small status dot is the only extra signal — and
   only for non-delivered builds (running / failed / awaiting). The delete control
   is hover-revealed (CSS). selectRun + the two-step confirm delete are unchanged. */
function railRow(r) {
  const wrap = document.createElement("div");
  wrap.className = "run-wrap" + (r.run_id === state.selected ? " active" : "");
  wrap.setAttribute("data-run", r.run_id);
  const status = (r.status || "").toLowerCase();
  const dot = status && status !== "delivered"
    ? '<span class="rc-dot ' + esc(status) + '" title="' + esc(status) + '" aria-label="' + esc(status) + '"></span>' : "";
  const title = railTitle(r);
  const meta = railMeta(r);
  const metaHtml = meta ? '<span class="rc-meta">' + esc(meta) + "</span>" : "";
  wrap.innerHTML =
    '<button class="run-card" data-run="' + esc(r.run_id) + '" title="' + esc(title) + '">' +
      dot + '<span class="rc-text"><span class="rc-title">' + esc(title) + "</span>" + metaHtml + "</span>" +
    "</button>" +
    '<button class="rc-del" title="Delete this build" aria-label="Delete build ' + esc(title) + '">' +
      icon("i-trash") + "</button>";
  wrap.classList.toggle("has-decline", r.declines > 0);
  wrap.querySelector(".run-card").onclick = () => selectRun(r.run_id);
  wrap.querySelector(".rc-del").onclick = (e) => { e.stopPropagation(); askDelete(wrap, r.run_id); };
  return wrap;
}

/* ---- DELETE a run: a two-step confirm (never a one-click delete) -----------
   Clicking the trash icon swaps the card's footer for an inline "Delete this
   build? [Cancel] [Delete]" confirm bar. Only the explicit Delete button calls
   the server (POST /api/delete). The server sanitizes the id HARD and removes
   exactly runs/<id>/, then returns the regenerated run list. */
function askDelete(wrap, runId) {
  if (wrap.classList.contains("confirming")) return;
  wrap.classList.add("confirming");
  const bar = document.createElement("div");
  bar.className = "rc-confirm";
  bar.innerHTML =
    '<span class="rcc-q">' + icon("i-trash") + "Delete this build?</span>" +
    '<span class="rcc-act">' +
      '<button class="rcc-no">Cancel</button>' +
      '<button class="rcc-yes">Delete</button>' +
    "</span>";
  wrap.appendChild(bar);
  bar.querySelector(".rcc-no").onclick = (e) => { e.stopPropagation(); wrap.classList.remove("confirming"); bar.remove(); };
  bar.querySelector(".rcc-yes").onclick = (e) => { e.stopPropagation(); confirmDelete(wrap, bar, runId); };
}

async function confirmDelete(wrap, bar, runId) {
  const yes = bar.querySelector(".rcc-yes");
  if (yes) { yes.disabled = true; yes.textContent = "deleting…"; }
  try {
    const res = await fetch("/api/delete", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: runId }) });
    const j = await res.json();
    if (!res.ok) throw new Error(j.error || "delete failed");
    // Server returns the regenerated run list — use it directly (no refetch race).
    state.runs = j.runs || [];
    if (state.selected === runId) { state.selected = null; showEmpty(); }
    if (state.building === runId) state.building = null;
    renderRail();
    setConn("ok", state.runs.length + (state.runs.length === 1 ? " build" : " builds"));
  } catch (e) {
    if (yes) { yes.disabled = false; yes.textContent = "Delete"; }
    setConn("err", "delete failed: " + e.message);
  }
}

// Return the stage to the clean idle landing (one clear focus, nothing dense).
function showEmpty(msg) {
  const detail = $("detail"), empty = $("stage-empty");
  if (detail) { detail.hidden = true; detail.innerHTML = ""; }
  if (empty) {
    empty.hidden = false;
    const m = $("stage-empty-msg");
    if (m && msg) m.textContent = msg;
    buildHeroTitle();       // replay the word-by-word hero build when we land back here
    replayLandingMotion();  // replay the how-it-works strip + CTA entrance too
  }
}

// "New build" (sidebar) — return the center to the empty-state composer for a
// fresh run: clear the current selection, stop any live-build poll, deselect every
// rail card, show the landing, and focus the URL field (the single next action).
// Does NOT delete anything; the past builds stay in the sidebar.
function newBuild() {
  if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
  exitAnalytics();          // leaving the operator view (if it was open)
  exitAbout();              // leaving the About view (if it was open)
  state.building = null;
  state.selected = null;
  document.querySelectorAll(".run-wrap").forEach((c) => c.classList.remove("active"));
  showEmpty();
  focusBuildUrl();
}

// Populate the idle hero with the word-by-word build (setup near-ink, accent
// clause lands last in amber). Re-runs the entrance each time it's shown.
function buildHeroTitle() {
  const h = $("hero-title");
  if (!h) return;
  h.innerHTML = heroWords(h.getAttribute("data-setup") || "", h.getAttribute("data-accent") || "");
}

// Replay the landing's staggered entrance (the how-it-works pipeline thread + the
// four beats + the CTA row). The animations are gated behind `.is-live`; removing
// it, forcing a reflow, and re-adding it restarts the CSS animations — so the
// reveal plays on first paint AND on any return to the landing (e.g. after the
// user deletes their last build), not just once on element creation.
function replayLandingMotion() {
  const empty = $("stage-empty");
  if (!empty) return;
  empty.classList.remove("is-live");
  void empty.offsetWidth;
  empty.classList.add("is-live");
}

// Point the user at the single next action: focus the URL input and pulse it once
// so the eye lands there. The pulse is a CSS class removed on the next tick (the
// animation is one-shot, time-based via the stylesheet — no setInterval).
function focusBuildUrl() {
  const u = $("build-url");
  if (!u) return;
  try { u.focus({ preventScroll: false }); } catch (e) { u.focus(); }
  u.classList.remove("nudge");
  // reflow so re-adding the class restarts the one-shot animation
  void u.offsetWidth;
  u.classList.add("nudge");
}

const clip = (s, n) => { s = s || ""; return s.length > n ? s.slice(0, n - 1) + "…" : s; };

/* ---------------- select + detail ---------------- */
async function selectRun(runId, silent) {
  exitAnalytics();          // opening a build leaves the operator analytics view
  exitAbout();              // ...and the About view
  state.selected = runId;
  document.querySelectorAll(".run-wrap").forEach((c) => c.classList.toggle("active", c.getAttribute("data-run") === runId));
  // On narrow viewports, opening a build closes the (overlay) sidebar so the build
  // view isn't hidden behind it — Claude/ChatGPT mobile behaviour.
  if (!silent) {
    const shell = $("shell");
    if (shell && window.matchMedia("(max-width: 940px)").matches) shell.classList.remove("rail-open");
  }
  const detail = $("detail"), empty = $("stage-empty");
  try {
    const res = await fetch("/runs/" + encodeURIComponent(runId) + "/ledger.json", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    state.ledger = await res.json();
    empty.hidden = true; detail.hidden = false;
    renderDetail(detail, state.ledger, runId);
    if (!silent) $("stage").scrollTo({ top: 0 });
  } catch (e) {
    empty.hidden = false; detail.hidden = true;
    empty.querySelector("p").textContent = "Could not load ledger for " + runId + " — " + e.message;
  }
}

function renderDetail(root, l, runId) {
  if (state.typer) { cancelAnimationFrame(state.typer); state.typer = null; }
  const scenes = l.scenes || [];
  const authored = scenes.filter((s) => s.studio && s.studio.kind === "authored");
  const sourceScenes = scenes.filter((s) => s.type === "cinematic" || s.type === "walkthrough");

  // The supporting "proof of craft" sections — title, body, and a one-line hint
  // so each stays meaningful while COLLAPSED. Same content for delivered (folded
  // below the video) and for browsing non-delivered runs (main body).
  // CUSTOMER VIEW: NO economics. The P&L receipt, the budget gate's COGS/margin/
  // declines, and the Stripe money layer (spending limit, auto-decline note) are
  // OPERATOR-only and live in the Analytics tab — never in the customer build view.
  // What the customer sees here = the storyboard, how the agent built it (Studio /
  // source footage), and the delivered video.
  const proof = [];
  if (authored.length) proof.push(["Studio · the agent writes the motion graphics", studio(l, authored, runId),
    authored.length + " authored component" + (authored.length === 1 ? "" : "s")]);
  if (sourceScenes.length) proof.push(["Source media · cinematic & walkthrough footage", sourceMedia(sourceScenes, runId),
    sourceScenes.length + " clip" + (sourceScenes.length === 1 ? "" : "s")]);

  // DELIVERED runs lead with the video: it is the payoff, not a buried section.
  // Everything else COLLAPSES into proof-of-craft disclosures (closed by default)
  // so the default view is just: status + video + actions. One clear focus.
  const delivered = l.status === "delivered" && l.stitch;
  if (delivered) {
    const proofHtml = proof.map((s, i) =>
      disclosure(s[0], s[1], { n: String(i + 1).padStart(2, "0"), hint: s[2], open: false })).join("");
    root.innerHTML = deliveredHero(l, runId) +
      '<div class="proof-fold"><div class="proof-lead">' +
        '<span class="proof-k">The proof of craft</span>' +
        '<span class="proof-sub">how the agent built it — open any section: pricing, the budget gate, the code, the footage</span>' +
      "</div>" + proofHtml +
      disclosure("Run metadata", slate(l), { n: String(proof.length + 1).padStart(2, "0"), hint: l.run_id + " · " + l.mode, open: false }) +
      "</div>";
    // Studio typing only initializes when its disclosure is opened (lazy) so a
    // delivered run lands instantly on the video, not on a code-typing animation.
    wireProofDisclosures(root, l, authored, runId);
    initDeliveredHero(l, runId);
    const hv = root.querySelector(".dh-video"); if (hv) hv.load();
    return;
  }

  // Non-delivered (running-but-rendered / browsing failed): the slate header
  // carries the status (no video hero), then the same collapsed proof sections.
  // A stitched-but-not-delivered run still gets an inline final-cut viewer, open.
  const secs = [];
  if (l.stitch) secs.push(["Final cut", viewer(l, runId), "the assembled video", true]);
  proof.forEach((p) => secs.push([p[0], p[1], p[2], false]));
  const secHtml = secs.map((s, i) =>
    disclosure(s[0], s[1], { n: String(i + 1).padStart(2, "0"), hint: s[2], open: s[3] })).join("");
  root.innerHTML = slate(l) + secHtml;
  wireProofDisclosures(root, l, authored, runId);
  const vid = root.querySelector(".viewer video"); if (vid) vid.load();
}

/* Lazily start the Studio code-typing the first time its disclosure opens (so a
   delivered run doesn't burn a typing animation behind a collapsed section), and
   nudge any <video> inside a freshly-opened section to load its metadata. */
function wireProofDisclosures(root, l, authored, runId) {
  let studioStarted = false;
  root.querySelectorAll(".dsc").forEach((d) => {
    d.addEventListener("toggle", () => {
      if (!d.open) return;
      if (authored.length && !studioStarted && d.querySelector(".studio")) {
        studioStarted = true;
        initStudio(l, authored, runId);
      }
      d.querySelectorAll("video").forEach((v) => { try { v.load(); } catch (e) {} });
    });
  });
}

/* ---- DELIVERED HERO: the video is the payoff -------------------------------
   Leads the delivered view. Large autoplay-muted-with-controls final cut, a
   "Your <brand> promo is ready" headline, a real Download MP4 link (the file is
   web-served), and a Copy-link share affordance. No emoji, amber accent only —
   red is reserved for declines, so it never appears here. */
function deliveredHero(l, runId) {
  const st = l.stitch || {};
  const j = l.job || {};
  const brand = (l.brand_palette && l.brand_palette._brand) ||
    ((j.company_url || "").replace(/^https?:\/\//, "").replace(/^www\./, "").split("/")[0]) || "your";
  const src = "/runs/" + encodeURIComponent(runId) + "/" + esc(st.output_path || "final.mp4");
  const cut = (st.scenes_cut || []).length;
  const meta = "final.mp4 · " + (st.duration_s != null ? st.duration_s + "s" : "—") +
    " · " + (st.clip_count || 0) + " clips · audio " + (st.has_audio ? "on" : "off") +
    (cut ? " · " + cut + " scene" + (cut === 1 ? "" : "s") + " cut by the gate" : "");
  // Hero line builds word-by-word: "Your <brand> promo is" (near-ink, brand bold)
  // then "ready" lands last in amber as the payoff beat. The brand keeps its bold
  // ink emphasis inside the setup; "ready" carries the accent.
  return '<div class="delivered-hero">' +
    '<div class="dh-head">' +
      '<span class="dh-badge">' + icon("i-check") + "DELIVERED</span>" +
      '<span class="dh-title">' + heroWordsBrand("Your", brand, "promo is", "ready") + "</span>" +
    "</div>" +
    '<div class="dh-frame"><video class="dh-video" controls autoplay muted loop playsinline preload="metadata">' +
      '<source src="' + src + '" type="video/mp4"></video></div>' +
    '<div class="dh-bar">' +
      '<div class="dh-meta">' + esc(meta) + "</div>" +
      '<div class="dh-actions">' +
        '<a class="dh-dl" href="' + src + '" download>' + icon("i-down") + "Download MP4</a>" +
        '<button class="dh-share" id="dh-share" data-src="' + src + '">' + icon("i-link") +
          '<span class="dh-share-txt">Copy link</span></button>' +
      "</div>" +
    "</div></div>";
}

function initDeliveredHero(l, runId) {
  if (state.shareTimer) { cancelAnimationFrame(state.shareTimer); state.shareTimer = null; }
  const btn = $("dh-share");
  if (!btn) return;
  btn.onclick = () => {
    const rel = btn.getAttribute("data-src") || "";
    const url = location.origin + rel;
    const done = () => shareConfirmed(btn);
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(done).catch(() => fallbackCopy(url, done));
    } else { fallbackCopy(url, done); }
  };
}

// Tiny no-clipboard-API fallback (older / insecure-context browsers).
function fallbackCopy(text, cb) {
  try {
    const ta = document.createElement("textarea");
    ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "absolute"; ta.style.left = "-9999px";
    document.body.appendChild(ta); ta.select(); document.execCommand("copy"); document.body.removeChild(ta);
  } catch (e) { /* best effort */ }
  cb();
}

// "Copied" state, then revert after ~1.6s — time-based via rAF (setInterval
// throttles in background tabs; same gotcha the typing views already solved).
function shareConfirmed(btn) {
  const label = btn.querySelector(".dh-share-txt");
  btn.classList.add("copied");
  if (label) label.textContent = "Link copied";
  if (state.shareTimer) cancelAnimationFrame(state.shareTimer);
  let start = null;
  const frame = (ts) => {
    if (start == null) start = ts;
    if (ts - start >= 1600) {
      state.shareTimer = null;
      btn.classList.remove("copied");
      if (label) label.textContent = "Copy link";
      return;
    }
    state.shareTimer = requestAnimationFrame(frame);
  };
  state.shareTimer = requestAnimationFrame(frame);
}

function sourceMedia(sceneList, runId) {
  const cards = sceneList.map((s) => {
    const badge = s.real_media
      ? '<span class="sm-badge real">REAL · ' + esc(s.real_media.source) + "</span>"
      : (s.decision === "decline" ? "" : '<span class="sm-badge ph">placeholder</span>');
    if (!s.output_path) {
      return '<div class="sm-card is-cut"><div class="sm-cut">' + icon("i-cut", "cut") +
        "<span>SCENE CUT</span></div><div class=\"sm-foot\"><span class=\"sm-id\">" + esc(s.id) +
        ' · ' + esc(s.type) + '</span><span class="pill decline">decline</span></div></div>';
    }
    const src = "/runs/" + encodeURIComponent(runId) + "/" + s.output_path;
    return '<div class="sm-card"><video controls muted playsinline preload="metadata"><source src="' +
      src + '" type="video/mp4"></video><div class="sm-foot"><span class="sm-id">' + esc(s.id) +
      " · " + esc(s.type) + (s.real_media && s.real_media.model ? " · " + esc(s.real_media.model) : "") +
      "</span>" + badge + "</div></div>";
  }).join("");
  return '<div class="sm-grid">' + cards + "</div>";
}

const sectionLabel = (n, t) => '<div class="sec-label"><span class="n">' + n + "</span>" + esc(t.toUpperCase()) + "</div>";

/* ---- collapsible "details" section — the ONE unified disclosure device ------
   Native <details> so it's keyboard-accessible, needs no JS, and is deterministic
   in headless checks. Used everywhere a dense panel becomes available-on-demand
   instead of rendered open: the delivered proof sections, the live action feed,
   the awaiting-payment script/storyboard. `open` defaults FALSE (collapsed).
   `n` is an optional index badge (matches the old sec-label numbering); `hint`
   is a one-line right-aligned summary so a collapsed section still says what's
   inside. */
function disclosure(title, bodyHtml, opts) {
  opts = opts || {};
  const open = opts.open ? " open" : "";
  const n = opts.n ? '<span class="dsc-n">' + esc(opts.n) + "</span>" : "";
  const hint = opts.hint ? '<span class="dsc-hint">' + esc(opts.hint) + "</span>" : "";
  return '<details class="dsc"' + open + "><summary class=\"dsc-sum\">" + n +
    '<span class="dsc-t">' + esc(title) + "</span>" + hint +
    '<svg class="dsc-chev" aria-hidden="true"><use href="#i-chevron"/></svg></summary>' +
    '<div class="dsc-body">' + bodyHtml + "</div></details>";
}

/* ---- slate ---- */
/* CUSTOMER VIEW: the run-metadata header. No economics — MARGIN and "target
   margin" are operator-only (they live in the Analytics tab), so they're omitted
   here. The customer sees the take/mode/status/client + the goal + the URL. */
function slate(l) {
  const j = l.job || {};
  const brand = (l.brand_palette && l.brand_palette._brand) || "generic";
  const cell = (k, v, amber) => '<div class="slate-cell"><span class="k">' + k + '</span><span class="v ' + (amber ? "amber" : "") + '">' + esc(v) + "</span></div>";
  return '<div class="slate">' +
    '<div class="slate-strip">' +
      cell("TAKE", l.run_id) + cell("MODE", l.mode) + cell("STATUS", l.status) +
      cell("CLIENT", brand, true) + cell("OVERLAYS", l.overlays || "mock") +
    "</div>" +
    '<div class="slate-body">' +
      '<div class="slate-goal">' + esc(j.goal || "") + "</div>" +
      '<div class="slate-url">' + esc(j.company_url || "") + "</div>" +
    "</div></div>";
}

/* ---- P&L receipt ---- */
function pl(l) {
  const pnl = l.pnl || {}, win = pnl.margin != null && pnl.margin >= (l.job.target_margin || 0);
  const lines = (pnl.cost_lines || []).map((c) => {
    const cls = c.decision === "decline" ? "decline" : (c.spent_cents ? "" : "free");
    const tag = c.decision && c.decision !== "free" ? '<span class="tag">' + c.decision + "</span>" : "";
    const amt = c.decision === "decline" ? cents(declineAmt(pnl, c.id)) : cents(c.spent_cents);
    return '<div class="rcpt-row ' + cls + '"><span class="lbl">' + esc(c.id) + tag + '</span><span class="amt">' + amt + "</span></div>";
  }).join("");
  const receipt = '<div class="receipt">' +
    '<div class="rcpt-head"><span class="rcpt-title">PRODUCTION P&amp;L</span><span class="rcpt-take">' + esc(l.run_id) + "</span></div>" +
    '<div class="rcpt-row sum"><span class="lbl">PRICE CHARGED</span><span class="amt">' + cents(pnl.price_cents) + "</span></div>" +
    lines +
    '<div class="rcpt-row sum"><span class="lbl">COGS SPENT</span><span class="amt">' + cents(pnl.cogs_spent_cents) + "</span></div>" +
    '<div class="rcpt-row sum"><span class="lbl">GROSS PROFIT</span><span class="amt">' + cents(pnl.gross_profit_cents) + "</span></div>" +
    "</div>";
  const cogs = pnl.price_cents ? (pnl.cogs_spent_cents / pnl.price_cents) * 100 : 0;
  const side = '<div class="pl-side">' +
    '<div class="margin-card"><div class="margin-k">NET MARGIN</div>' +
      '<div class="margin-fig ' + (win ? "win" : "") + '">' + pct(pnl.margin) + "</div>" +
      '<div class="margin-sub">' + (win ? "above the " + pct(l.job.target_margin) + " target" : "target " + pct(l.job.target_margin)) + "</div>" +
      '<div class="margin-bar"><div class="cogs" style="flex:' + cogs + '"></div><div class="profit" style="flex:' + (100 - cogs) + '"></div></div>' +
      '<div class="bar-legend"><span>COGS ' + cents(pnl.cogs_spent_cents) + "</span><span>PROFIT " + cents(pnl.gross_profit_cents) + "</span></div></div>" +
    (pnl.overage_avoided_cents ? '<div class="saved">' + icon("i-check") +
        '<div class="t">The budget gate auto-declined <b>' + (pnl.declines || []).length + " scene" + ((pnl.declines || []).length === 1 ? "" : "s") +
        "</b> and saved <b>" + cents(pnl.overage_avoided_cents) + "</b> of overage — no human in the loop.</div></div>" : "") +
    "</div>";
  return '<div class="pl-wrap">' + receipt + side + "</div>";
}
const declineAmt = (pnl, id) => { const d = (pnl.declines || []).find((x) => x.id === id); return d ? d.would_have_cost_cents : 0; };

/* ---- gate: filmstrip + list ---- */
function gate(l, scenes) {
  const total = scenes.reduce((a, s) => a + (s.duration_s || 0), 0) || 1;
  const strip = scenes.map((s) => {
    const w = Math.max(0.5, (s.duration_s || 0) / total) * 100;
    if (s.decision === "decline") return '<div class="clip decline" style="flex:' + w + '" title="' + esc(s.id) + ' — CUT">' + icon("i-cut", "cut") + "</div>";
    return '<div class="clip ' + (s.decision || "free") + '" style="flex:' + w + '"><span class="cl-type">' + esc(s.type) + "</span></div>";
  }).join("");
  const rows = scenes.map((s, i) => gateRow(s, i)).join("") + (l.voiceover ? voRow(l.voiceover, scenes.length) : "");
  return '<div class="strip"><div class="strip-ruler"><span>00:00</span><span>TIMELINE · ' + total + 's</span><span>00:' + String(total).padStart(2, "0") + "</span></div>" +
    '<div class="strip-track">' + strip + "</div></div>" +
    '<div class="gate">' + rows + "</div>";
}

function gateRow(s, i) {
  const dec = s.decision || "free";
  const model = s.decision === "downgrade"
    ? esc(s.downgraded_from) + ' <span class="arrow">→</span> ' + esc(s.final_model)
    : esc(s.final_model || s.model || s.tool || "");
  const cost = s.decision === "decline"
    ? '<span style="color:var(--neg)">' + cents(s.would_have_cost_cents) + '</span><span class="sub">would cost · cut</span>'
    : cents(s.spent_cents) + '<span class="sub">' + (s.spent_cents ? "spent" : "free") + "</span>";
  const auth = s.stripe_authorization && !s.stripe_authorization.approved
    ? '<div class="row-auth">' + icon("i-card") + 'Stripe authorization <b>DECLINED</b> · <span class="obj">' + esc(s.stripe_authorization.id || "issuing.authorization") + " · approved=false</span></div>"
    : "";
  return '<div class="row ' + (dec === "free" ? "is-free" : "") + (dec === "decline" ? " is-decline" : "") + '">' +
    '<div class="row-n">' + String(i + 1).padStart(2, "0") + "</div>" +
    '<div class="row-main"><div class="id">' + esc(s.id) + "</div><div class=\"brief\">" + esc(clip(s.brief, 84)) + "</div>" + auth + "</div>" +
    '<div class="row-model">' + model + "</div>" +
    '<div class="row-cost">' + cost + "</div>" +
    '<span class="pill ' + dec + '">' + dec + "</span></div>";
}

function voRow(v, i) {
  const dec = v.decision || "approve";
  const cost = dec === "decline"
    ? '<span style="color:var(--neg)">' + cents(v.would_have_cost_cents) + '</span><span class="sub">would cost · cut</span>'
    : cents(v.spent_cents) + '<span class="sub">' + (v.provider || "edge-tts") + "</span>";
  return '<div class="row ' + (dec === "decline" ? "is-decline" : "") + '">' +
    '<div class="row-n">' + String(i + 1).padStart(2, "0") + "</div>" +
    '<div class="row-main"><div class="id">voiceover</div><div class="brief">' + (v.chars || 0) + " chars · " + esc(v.voice || "") + "</div></div>" +
    '<div class="row-model">elevenlabs · edge-tts (test)</div>' +
    '<div class="row-cost">' + cost + "</div>" +
    '<span class="pill ' + dec + '">' + dec + "</span></div>";
}

/* ---- STUDIO: agent writes Remotion ---- */
function studio(l, authored, runId) {
  const tabs = authored.map((s, i) =>
    '<button class="studio-tab' + (i === 0 ? " active" : "") + '" data-i="' + i + '">' + icon("i-code") +
      esc(s.id) + '.tsx <span class="dot-arch">' + esc(s.studio.archetype) + "</span></button>").join("");
  return '<div class="studio"><div class="studio-tabs">' + tabs + "</div>" +
    '<div class="studio-grid">' +
      '<div class="editor"><div class="editor-bar"><span class="fname">' + icon("i-code") + '<span id="st-fname"></span></span>' +
        '<span class="right"><span id="st-arch"></span></span></div>' +
        '<div class="editor-scroll" id="st-scroll"><div class="code"><div class="gutter" id="st-gutter"></div><pre><code id="st-code"></code></pre></div></div></div>' +
      '<div class="preview"><div class="preview-head"><span>PREVIEW · Remotion</span><span id="st-comp">Scene</span></div>' +
        '<div class="preview-stage"><video id="st-video" muted playsinline loop></video></div>' +
        '<div class="preview-foot"><span class="render-state"><span class="render-dot" id="st-dot"></span><span id="st-status">writing…</span></span>' +
          '<button class="replay" id="st-replay">REPLAY</button></div></div>' +
    "</div></div>";
}

function initStudio(l, authored, runId) {
  let cur = 0;
  const tabs = document.querySelectorAll(".studio-tab");
  const play = (i) => {
    cur = i;
    tabs.forEach((t, k) => t.classList.toggle("active", k === i));
    const s = authored[i];
    $("st-fname").textContent = s.id + ".tsx";
    $("st-arch").textContent = s.studio.code_lines + " lines · " + s.studio.archetype;
    $("st-comp").textContent = s.studio.composition || "Scene";
    typeCode(s, runId);
  };
  tabs.forEach((t) => t.onclick = () => play(+t.getAttribute("data-i")));
  $("st-replay").onclick = () => play(cur);
  play(0);
}

function typeCode(scene, runId) {
  if (state.typer) { cancelAnimationFrame(state.typer); state.typer = null; }
  const code = scene.studio.generated_code || "";
  const toks = tokenizeTSX(code);
  const codeEl = $("st-code"), gut = $("st-gutter"), scroll = $("st-scroll");
  const dot = $("st-dot"), status = $("st-status"), video = $("st-video");
  dot.className = "render-dot"; status.textContent = "writing…";
  video.removeAttribute("src"); video.style.opacity = ".25";
  const total = code.length;
  // time-based reveal: a fixed ~2.6s type regardless of frame throttling, and a
  // guaranteed completion so it can never stick on "writing…".
  const DURATION = Math.min(3200, Math.max(1600, total * 1.25));
  let start = null;
  const finish = () => {
    state.typer = null;
    status.textContent = "rendered · " + (scene.studio.render_ms || 0) + "ms";
    dot.className = "render-dot done";
    video.src = "/runs/" + encodeURIComponent(runId) + "/" + scene.output_path;
    video.style.opacity = "1"; video.load(); video.play().catch(() => {});
  };
  const frame = (ts) => {
    if (start == null) start = ts;
    const shown = Math.min(total, Math.round(total * (ts - start) / DURATION));
    codeEl.innerHTML = renderPrefix(toks, shown) + '<span class="cursor"></span>';
    const lines = code.slice(0, shown).split("\n").length;
    gut.innerHTML = Array.from({ length: lines }, (_, k) => "<span>" + String(k + 1).padStart(2, "0") + "</span>").join("");
    scroll.scrollTop = scroll.scrollHeight;
    if (shown >= total) { finish(); return; }
    state.typer = requestAnimationFrame(frame);
  };
  state.typer = requestAnimationFrame(frame);
}

function renderPrefix(toks, n) {
  let out = "", len = 0;
  for (const t of toks) {
    if (len >= n) break;
    const take = Math.min(t.t.length, n - len);
    const slice = esc(t.t.slice(0, take));
    out += t.c ? '<span class="' + t.c + '">' + slice + "</span>" : slice;
    len += t.t.length;
  }
  return out;
}

/* a small TSX tokenizer good enough for our generated components */
function tokenizeTSX(src) {
  const toks = []; const KW = new Set(["import", "from", "export", "const", "return", "interpolate", "spring", "number", "React"]);
  let i = 0; const push = (t, c) => toks.push({ t, c });
  while (i < src.length) {
    const c = src[i];
    if (c === "/" && src[i + 1] === "/") { let j = src.indexOf("\n", i); if (j < 0) j = src.length; push(src.slice(i, j), "tok-com"); i = j; continue; }
    if (c === '"' || c === "'" || c === "`") { let j = i + 1; while (j < src.length && src[j] !== c) { if (src[j] === "\\") j++; j++; } j++; push(src.slice(i, j), "tok-str"); i = j; continue; }
    if (/[0-9]/.test(c)) { let j = i; while (j < src.length && /[0-9.]/.test(src[j])) j++; push(src.slice(i, j), "tok-num"); i = j; continue; }
    if (/[A-Za-z_$]/.test(c)) { let j = i; while (j < src.length && /[A-Za-z0-9_$]/.test(src[j])) j++; const w = src.slice(i, j);
      push(w, KW.has(w) ? "tok-kw" : (/^[A-Z]/.test(w) && src[j] !== "(" ? "tok-tag" : "tok-fn")); i = j; continue; }
    if (/[{}()<>[\];:,.=+\-*/]/.test(c)) { push(c, "tok-punct"); i++; continue; }
    push(c, null); i++;
  }
  return toks;
}

/* ---- final cut ---- */
function viewer(l, runId) {
  const st = l.stitch;
  return '<div class="viewer"><video controls playsinline preload="metadata" poster="">' +
    '<source src="/runs/' + encodeURIComponent(runId) + "/" + esc(st.output_path) + '" type="video/mp4"></video>' +
    '<div class="viewer-cap"><span>final.mp4 · ' + st.duration_s + "s · " + st.clip_count + " clips · audio " + (st.has_audio ? "on" : "off") + "</span>" +
    ((st.scenes_cut || []).length ? '<span class="cut">' + (st.scenes_cut || []).length + " scene cut by the gate</span>" : "<span>delivered</span>") + "</div></div>";
}

/* ---- stripe + events ---- */
function bottom(l) {
  const earn = l.earn || {}, card = l.card || {};
  const key = earn.key || {};
  const stripe = '<div class="panel"><h4>' + icon("i-card") + "STRIPE MONEY LAYER</h4>" +
    kv("Earn", earn.status === "dev_mode" ? "DEV MODE (no charge)" : (earn.status || "—"), earn.status === "awaiting_payment" ? "amber" : "") +
    kv("Test key", key.present ? key.kind + " key present" : "none", key.present ? "pos" : "") +
    kv("Issuing card", card.provider === "stripe" ? "live · " + (card.card_id || "") : "simulated", "") +
    kv("Spending limit", cents(card.spending_limit_cents), "amber") +
    declineAuthNote(l) + "</div>";
  const log = '<div class="panel"><h4>RUN LOG</h4><div class="log">' +
    (l.events || []).map((e) => '<div class="log-row ' + esc(e.level) + '"><span class="log-seq">' + e.seq +
      '</span><span class="log-tag">' + esc(e.level) + '</span><span class="log-msg">' + esc(e.msg) + "</span></div>").join("") +
    "</div></div>";
  return '<div class="cols">' + stripe + log + "</div>";
}
function declineAuthNote(l) {
  const d = (l.scenes || []).find((s) => s.stripe_authorization && !s.stripe_authorization.approved);
  if (!d) return '<div class="auth-note sim">No over-budget spend on this run — every authorization cleared.</div>';
  const a = d.stripe_authorization;
  return '<div class="auth-note">Scene <b>' + esc(d.id) + "</b> hit a Stripe " + (a.simulated ? "(simulated) " : "") +
    "authorization with <b>approved=false</b> — the budget gate's physical decline. The studio shipped without it.</div>";
}
const kv = (k, v, cls) => '<div class="kv"><span class="k">' + esc(k) + '</span><span class="v ' + (cls || "") + '">' + esc(v) + "</span></div>";

/* ---------------- live build ---------------- */
const PHASES = ["planning", "pricing", "awaiting_payment", "producing", "voiceover", "stitching", "delivered"];
const PHASE_LABEL = { awaiting_payment: "payment" };

async function startBuild() {
  const url = ($("build-url").value || "").trim();
  if (!url) { $("build-url").focus(); return; }
  const goal = ($("build-goal").value || "").trim();
  // "Always real ($)": the live console produces real by default — a real customer
  // payment triggers real production. The mock box is a $0 dev/test escape hatch.
  const mock = $("build-mock");
  const mode = mock && mock.checked ? "mock" : "real";
  // COST-PLUS: the agent scours the site, decides the video, and prices it
  // cost-plus during planning. The ONE upfront choice is QUALITY (standard |
  // premium), chosen on the composer — it changes WHAT the agent produces, so it
  // ships with the build and the plan is priced for it.
  const selection = buildSelectionPayload();
  const btn = $("build-go"); btn.disabled = true; btn.textContent = "starting…";
  try {
    // `pace` is a named pacing (D6) sent as an extra field; the backend may map
    // it to duration/pace or ignore it harmlessly — purely additive here.
    // `selection` is the cost-plus quality choice ({ quality }); the producer
    // prices the plan cost-plus for that quality (standard floors at $5; premium
    // includes Higgsfield + ElevenLabs COGS, ~$6-9) and the produce stack follows.
    const res = await fetch("/api/build", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url, goal, mode, pace: state.pace, selection: selection, quality: selection.quality }) });
    const j = await res.json();
    if (!res.ok || !j.run_id) throw new Error(j.error || "could not start");
    beginPoll(j.run_id);
  } catch (e) {
    btn.disabled = false; btn.textContent = "Build";
    setConn("err", "build failed: " + e.message);
  }
}

/* Resolve the cost-plus `selection` object to POST with the build flow. The ONLY
   field is `quality` ("standard" | "premium") — the upfront video-quality choice.
   Read live from state.selection so it reflects the composer toggle. */
function buildSelectionPayload() {
  const q = (state.selection && state.selection.quality) === "premium" ? "premium" : "standard";
  return { quality: q };
}

function beginPoll(runId) {
  state.building = runId;
  state.selected = null;
  state.liveSig = "";
  state.scriptShown = null;  // let the new build's narration type out fresh
  state.liveGoalShown = null; // let the new build's hero goal build word-by-word once
  state.payForShown = null;   // let the pay-gate "for <brand>" line build once
  if (state.pollTimer) clearInterval(state.pollTimer);
  if (state.typer) { cancelAnimationFrame(state.typer); state.typer = null; }
  if (state.scriptTyper) { cancelAnimationFrame(state.scriptTyper); state.scriptTyper = null; }
  const empty = $("stage-empty"), detail = $("detail");
  empty.hidden = true; detail.hidden = false;
  document.querySelectorAll(".run-wrap").forEach((c) => c.classList.remove("active"));
  const tick = async () => {
    try {
      const r = await fetch("/runs/" + encodeURIComponent(runId) + "/ledger.json?_=" + Date.now(), { cache: "no-store" });
      if (!r.ok) { detail.innerHTML = liveStarting(); return; }
      const l = await r.json();
      if (l.status === "delivered") { finishBuild(runId, true); return; }
      if (l.status === "failed") { finishBuild(runId, false, l); return; }
      // include earn.payment_status in the signature so the pay-gate status line
      // updates the instant the ledger poll flips unpaid -> paid.
      const sig = l.phase + "|" + ((l.earn || {}).payment_status || "") +
        "|" + (l.scenes || []).map((s) => s.id + s.status).join(",") + "|" + (l.events || []).length;
      if (sig !== state.liveSig) { state.liveSig = sig; renderLive(detail, l, runId); }
    } catch (e) { /* transient — keep polling */ }
  };
  tick();
  state.pollTimer = setInterval(tick, 1000);
}

function finishBuild(runId, ok, l) {
  if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
  state.building = null;
  const btn = $("build-go"); btn.disabled = false; btn.textContent = "Build";
  // pin the selection to this run BEFORE refreshing the rail, so loadIndex keeps
  // it instead of auto-selecting a finished decline-run and racing us. (This also
  // matters on the FAILED path: when we land here from a ?paid return on an already-
  // failed run, an unpinned selection let loadIndex auto-select another run and the
  // failure view never stuck.)
  state.selected = runId;
  if (ok) {
    loadIndex(true).then(() => selectRun(runId));
  } else {
    // Show the real failure (the run's actual ledger state), and refresh the rail so
    // the failed run is selectable there — never a bare page or a wrong auto-select.
    const detail = $("detail"), empty = $("stage-empty");
    if (empty) empty.hidden = true;
    if (detail) { detail.hidden = false; detail.innerHTML = liveFailed(l); }
    loadIndex(true);
  }
}

function renderLive(root, l, runId) {
  // Pre-production PAYMENT GATE: the agent has planned + priced the storyboard;
  // production is held until the customer pays the (real, test-mode) Checkout.
  // PRIMARY FOCUS = the pay decision. The customer sees the PRICE they pay (in the
  // pay-gate) — NOT the agent's COGS / budget / margin / auto-decline internals
  // (those are operator economics; they live in the Analytics tab). The script +
  // storyboard collapse into "what you're paying for" disclosures.
  if (l.phase === "awaiting_payment") {
    const scenes = l.scenes || [];
    root.innerHTML = liveHeader(l) +
      sectionLabel("·", "Payment · pay to start production") + payGate(l) +
      disclosure("The script — what the agent wrote before shooting", liveScript(l),
        { n: "·", hint: ((l.plan || {}).scenes || []).length + " scenes", open: false }) +
      disclosure("The storyboard — queued, awaiting payment", liveStoryboard(scenes, runId),
        { n: "·", hint: scenes.length + " scenes queued", open: false });
    initLiveScript(l);
    initPayGate(l);
    return;
  }
  // PRODUCTION. PRIMARY FOCUS = "what's happening now": phase track (in the
  // header) + the storyboard scene-card progress. The customer sees the build
  // PROGRESS, not the running economics (price/spent/budget-left/margin are
  // operator-only — they live in the Analytics tab). The verbose agent browser/
  // action-feed and the full script collapse into disclosures so the build's
  // progress isn't drowned in a wall of log lines.
  const scenes = l.scenes || [];
  const done = scenes.filter((s) => s.status === "produced" || s.status === "declined").length;
  root.innerHTML = liveHeader(l) +
    storyboardLead(done, scenes.length) +
    liveStoryboard(scenes, runId) +
    disclosure("The script — what the agent wrote before shooting", liveScript(l),
      { n: "·", hint: ((l.plan || {}).scenes || []).length + " scenes", open: false }) +
    disclosure("Agent activity — live browser & action feed", liveAgent(l, runId),
      { n: "·", hint: (l.events || []).length + " events", open: false });
  initLiveScript(l);
}

/* ---- QUOTE / PAY GATE: the cost-plus proposal + Stripe TEST-mode Checkout ---
   Shown while phase=="awaiting_payment". This is the QUOTE the customer sees
   before paying: a short "here's the video the agent will make" line, the per-
   video PRICE (cost-plus, from the priced ledger), ONE optional upgrade — a
   premium natural voiceover (+$X) that bumps the displayed TOTAL live — an
   itemized breakdown, then the "Pay $TOTAL to produce" button. On 'paid' the
   next poll re-renders into the production view. */

// The brand label for the proposal line, derived from the ledger/job.
function gateBrand(l) {
  const j = l.job || {};
  return (l.brand_palette && l.brand_palette._brand) ||
    ((j.company_url || "").replace(/^https?:\/\//, "").replace(/^www\./, "").split("/")[0]) || "the product";
}

// The quality the agent priced for THIS run (chosen upfront on the composer).
// Read from the priced ledger (the backend records the resolved quality on the
// premium/selection block), falling back to the live composer choice.
function gateQuality(l) {
  const prem = l.premium || {};
  if (prem.quality) return prem.quality;
  const sel = prem.selection || l.selection || (state.selection || {});
  if (sel.quality) return sel.quality;
  return "standard";
}

function payGate(l) {
  const earn = l.earn || {};
  const j = l.job || {};
  const status = earn.payment_status || "unpaid";
  const paid = status === "paid" || status === "no_payment_required";
  const brand = gateBrand(l);
  const url = earn.checkout_url || "";
  const total = ledgerPriceCents(l);          // the single per-video price (cost-plus)
  const quality = gateQuality(l);

  // status line — amber pulse while waiting, pos check once paid (no red here:
  // red is reserved for declines).
  const statusLine = paid
    ? '<div class="pg-status paid">' + icon("i-check") + "<span>payment received — starting production…</span></div>"
    : '<div class="pg-status wait"><span class="pg-wait-dot"></span><span id="pg-status-text">waiting for payment…</span></div>';
  const payBtn = url && !paid
    ? '<button class="pg-pay" id="pg-pay" data-url="' + esc(url) + '">' + icon("i-card") +
        ' Pay <span id="pg-pay-amt">' + cents(total) + "</span> to produce</button>"
    : (paid ? "" : '<div class="pg-nourl">' + icon("i-loader", "ic spin") + " creating Checkout session…</div>");

  return '<div class="paygate">' +
    '<div class="pg-main">' +
      '<div class="pg-head"><span class="pg-badge">' + icon("i-card") + "TEST MODE · sandbox Stripe</span>" +
        '<span class="pg-sub">no real charge · test card 4242 4242 4242 4242</span></div>' +
      // the proposal: a short "here's the video the agent will make" line
      '<div class="pg-proposal">Here&rsquo;s the video the agent will make for ' +
        '<span class="hw-accent-static">' + esc(brand) + "</span>" +
        (j.goal ? ' &mdash; <span class="pg-prop-goal">' + esc(clip(j.goal, 80)) + "</span>" : "") + ".</div>" +
      // the big price + the cost-plus subtitle
      '<div class="pg-price-row"><div class="pg-price" id="pg-price">' + cents(total) + "</div>" +
        '<div class="pg-for"><div class="pg-for-k">per video · priced cost&#8209;plus</div>' +
          '<div class="pg-for-v">' + payForLine(brand) + "</div></div></div>" +
      // the chosen quality (set upfront on the composer) + its one-line meaning
      qualityNote(quality) +
      // itemized breakdown — one line (Video production) = total
      quoteItems(l) +
      payBtn + statusLine +
    "</div>" +
    '<div class="pg-side">' +
      '<div class="pg-line"><span class="k">Job</span><span class="v">' + esc(clip(j.goal, 60)) + "</span></div>" +
      '<div class="pg-line"><span class="k">Quality</span><span class="v">' + esc(qualityLabel(quality)) + "</span></div>" +
      '<div class="pg-line"><span class="k">Session</span><span class="v mono">' + esc(clip(earn.session_id || "—", 22)) + "</span></div>" +
      '<div class="pg-line"><span class="k">Mode</span><span class="v amber">test · livemode ' + (earn.livemode ? "true" : "false") + "</span></div>" +
      '<div class="pg-line"><span class="k">Detection</span><span class="v">poll · status: ' + esc(status) + "</span></div>" +
      '<div class="pg-note">Payment is detected by polling the session status (the webhook is pending <code>stripe login</code>). On payment, real production begins automatically.</div>' +
    "</div></div>";
}

// A quiet pill naming the chosen quality + its one-line meaning. The quality was
// picked upfront on the composer (it changed what the agent produced), so the
// pay-gate just confirms it — there is no longer an add-on toggle here.
function qualityNote(quality) {
  const def = qualityDef(quality);
  const blurb = def.blurb || (quality === "premium"
    ? "Cinematic AI footage (Higgsfield) + a natural studio voice (ElevenLabs). Richer and more lifelike."
    : "Designed motion graphics + a clean synthetic voice. Fast and free to make.");
  return '<div class="pg-quality pg-q-' + esc(quality) + '">' +
    '<span class="pg-quality-name">' + esc(qualityLabel(quality)) + " quality</span>" +
    '<span class="pg-quality-desc">' + esc(blurb) + "</span></div>";
}

// The itemized breakdown: one Video production line = total (no add-ons).
function quoteItems(l) {
  const total = ledgerPriceCents(l);
  const rows = '<div class="pg-q-row"><span class="pg-q-lbl">Video production</span>' +
    '<span class="pg-q-amt">' + cents(total) + "</span></div>";
  return '<div class="pg-quote" id="pg-quote">' + rows +
    '<div class="pg-q-row pg-q-total"><span class="pg-q-lbl">Total</span>' +
      '<span class="pg-q-amt" id="pg-q-total">' + cents(total) + "</span></div></div>";
}

// The "<brand> video" caption under the price builds word-by-word with the BRAND
// as the amber payload that lands last. Builds once per run; re-renders on
// payment_status flip keep it fully shown so it doesn't rewind under the price.
function payForLine(brand) {
  const firstBuild = state.payForShown !== state.building;
  if (!firstBuild) return '<span class="hw-accent-static">' + esc(brand) + "</span> video";
  state.payForShown = state.building;
  // "video" builds first; the brand resolves last in amber.
  const rest = ["video"];
  const words = rest.map((w, k) =>
    '<span class="hw" style="animation-delay:' + (k * HERO_STEP).toFixed(3) + 's">' + esc(w) + "</span>");
  const brandDelay = rest.length * HERO_STEP + HERO_ACCENT_GAP;
  const brandSpan = '<span class="hw hw-accent" style="animation-delay:' + brandDelay.toFixed(3) + 's">' + esc(brand) + "</span>";
  // brand sits first in reading order but lands last in motion
  return '<span class="hero-build">' + [brandSpan].concat(words).join(" ") + "</span>";
}

function initPayGate(l) {
  // Quality is chosen UPFRONT on the composer (it changes what the agent produced),
  // so the pay-gate has no add-on toggle anymore — it just shows the single quote
  // the backend priced for the chosen quality. Only the pay button is wired here.
  const btn = $("pg-pay");
  if (btn) {
    btn.onclick = () => {
      const u = btn.getAttribute("data-url");
      if (u) window.open(u, "_blank", "noopener");
      // reflect that the customer was sent to Checkout; the poll confirms 'paid'.
      btn.classList.add("opened");
      const t = $("pg-status-text");
      if (t) t.textContent = "Checkout opened in a new tab — waiting for payment…";
    };
  }
}

/* ---- live SCRIPT: the VO narration + ordered shot list the agent decided ----
   Surfaced the moment planning completes (ledger.plan), so the demo can "watch the
   agent write the script before it shoots it." Stays available through the build. */
function liveScript(l) {
  const plan = l.plan || {};
  const vo = plan.voiceover || {};
  const scenes = plan.scenes || [];
  // VO narration — set in serif as reading copy; typed out on first appearance.
  const script = vo.script || "";
  const voInner = script
    ? '<div class="vo-script" id="vo-script" data-script="' + esc(script) + '"></div>' +
      (vo.voice ? '<div class="vo-voice"><span class="dot"></span>voiceover · ' + esc(vo.voice) + "</div>" : "")
    : '<div class="vo-empty">' + icon("i-loader", "ic spin") + " the agent is still writing the narration…</div>";
  const voCard =
    '<div class="script-card"><div class="script-head"><span class="badge">VO</span>' +
      '<span class="h-title">Voiceover narration</span>' +
      '<span class="h-meta">' + (script ? script.length + " chars" : "") + "</span></div>" +
    '<div class="vo-body">' + voInner + "</div></div>";
  // Ordered scene breakdown — brief + type + producing tool/model + duration.
  let shots;
  if (!scenes.length) {
    shots = '<div class="vo-empty" style="padding:16px 18px">' + icon("i-loader", "ic spin") +
      " deciding the shot list…</div>";
  } else {
    shots = scenes.map((s, i) => {
      const tool = s.model ? esc(s.model) : esc(toolForType(s.type));
      const dur = s.duration_s != null ? esc(s.duration_s) + "s" : "—";
      return '<div class="shot"><span class="shot-n">' + String(i + 1).padStart(2, "0") + "</span>" +
        '<div><div class="shot-brief">' + esc(s.brief || s.id || "") + "</div>" +
        '<div class="shot-meta"><span class="shot-tag type">' + esc(s.type || "") + "</span>" +
        '<span class="shot-tag model">' + tool + "</span>" +
        '<span class="shot-tag dur">' + dur + "</span></div></div></div>";
    }).join("");
  }
  const shotCard =
    '<div class="script-card"><div class="script-head"><span class="badge seq">N</span>' +
      '<span class="h-title">Shot list</span>' +
      '<span class="h-meta">' + (scenes.length ? scenes.length + " scenes" : "") + "</span></div>" +
    '<div class="shot-list">' + shots + "</div></div>";
  return '<div class="script-grid">' + voCard + shotCard + "</div>";
}

// The tool that produces a free (non-model) scene type — matches orchestrator.adapters_tool.
function toolForType(t) {
  return { title: "motion-graphics", motion_graphic: "motion-graphics",
           walkthrough: "walk-agent" }[t] || "—";
}

// Type out the VO narration once, time-based via rAF (setInterval throttles in
// background/headless tabs — same gotcha already solved for the code-typing view).
function initLiveScript(l) {
  if (state.scriptTyper) { cancelAnimationFrame(state.scriptTyper); state.scriptTyper = null; }
  const el = $("vo-script");
  if (!el) return;
  const full = el.getAttribute("data-script") || "";
  // Only animate the first time this script appears; re-renders during the build
  // (new events/scenes) keep it fully shown so it never "rewinds" on the viewer.
  if (state.scriptShown === full) { el.textContent = full; return; }
  const total = full.length;
  const DURATION = Math.min(4200, Math.max(1800, total * 13));
  let start = null;
  const frame = (ts) => {
    if (start == null) start = ts;
    const shown = Math.min(total, Math.round(total * (ts - start) / DURATION));
    el.innerHTML = esc(full.slice(0, shown)) + (shown < total ? '<span class="cursor"></span>' : "");
    if (shown >= total) { state.scriptTyper = null; state.scriptShown = full; return; }
    state.scriptTyper = requestAnimationFrame(frame);
  };
  state.scriptTyper = requestAnimationFrame(frame);
}

function liveHeader(l) {
  const ph = l.phase || "planning";
  const idx = PHASES.indexOf(ph);
  // Phase track: an amber fill sweeps left-to-right as phases advance, so the
  // ~90s planning/production wait never reads as static (D4). The fill width is
  // driven by the phase index; the active chip glows; future chips stay ghosted.
  const fillPct = idx >= 0 ? Math.round(((idx + 0.5) / PHASES.length) * 100) : 0;
  const chips = PHASES.map((p, i) =>
    '<span class="ph-chip ' + (i < idx ? "done" : i === idx ? "now" : "") + (p === "awaiting_payment" ? " pay" : "") + '">' +
      (PHASE_LABEL[p] || p) + "</span>").join("");
  const j = l.job || {};
  const goal = clip(j.goal, 80);
  // Hero goal builds word-by-word (accent clause lands last) only the FIRST time
  // this run renders live; later re-renders during the build keep it fully shown
  // so the focal line never "rewinds" as scenes/events tick (mirrors scriptShown).
  const firstBuild = state.liveGoalShown !== state.building;
  const goalHtml = firstBuild ? heroAuto(goal, 2) : esc(goal);
  if (firstBuild) state.liveGoalShown = state.building;
  return '<div class="live-head"><div class="live-top">' +
    '<span class="live-pill"><span class="live-dot"></span>BUILDING</span>' +
    '<span class="live-goal">' + goalHtml + "</span></div>" +
    '<div class="live-url">' + esc(j.company_url || "") + "</div>" +
    '<div class="ph-track"><div class="ph-fill" style="width:' + fillPct + '%"></div>' + chips + "</div></div>";
}

function liveAgent(l, runId) {
  const events = (l.events || []).slice(-7);
  const walk = (l.scenes || []).find((s) => s.type === "walkthrough" && s.output_path);
  const url = (l.job || {}).company_url || "";
  const last = ((l.events || []).slice(-1)[0] || {}).msg || "working…";
  const body = walk
    ? '<video src="/runs/' + encodeURIComponent(runId) + "/" + walk.output_path + '" muted loop autoplay playsinline style="width:100%;display:block;aspect-ratio:16/9;object-fit:cover"></video>'
    : '<div class="agent-think">' + icon("i-code") + "<span>" + esc(last) + "</span></div>";
  return '<div class="agent-grid">' +
    '<div class="browser"><div class="browser-bar"><span class="bdot"></span><span class="bdot"></span><span class="bdot"></span>' +
    '<span class="burl">' + esc(url) + '</span><span class="blive"><span class="blive-dot"></span>live</span></div>' + body + "</div>" +
    '<div class="feed"><div class="feed-h">action feed</div>' +
    events.map((e) => '<div class="feed-row ' + esc(e.level) + '">' + esc(e.msg) + "</div>").join("") +
    "</div></div>";
}

// Storyboard section lead with a bounded "N of M scenes" counter + a thin amber
// progress bar (D4) — gives the production wait a sense of measured forward
// motion instead of a static label. The bar fills proportionally to done/total.
function storyboardLead(done, total) {
  if (!total) {
    return '<div class="sb-lead"><div class="sb-lead-l"><span class="sb-lead-k">STORYBOARD</span>' +
      '<span class="sb-lead-sub">the agent\'s scenes</span></div></div>';
  }
  const pct = Math.round((done / total) * 100);
  return '<div class="sb-lead"><div class="sb-lead-l"><span class="sb-lead-k">STORYBOARD</span>' +
    '<span class="sb-count"><b>' + done + "</b> of " + total + " scenes</span></div>" +
    '<div class="sb-prog"><div class="sb-prog-fill" style="width:' + pct + '%"></div></div></div>';
}

function liveStoryboard(scenes, runId) {
  if (!scenes.length) return '<div class="sb-empty">' + icon("i-loader", "ic spin") + " deciding the storyboard…</div>";
  const cards = scenes.slice().sort((a, b) => (a.order || 0) - (b.order || 0)).map((s) => {
    const st = s.status || "queued";
    let body, badge;
    if (st === "produced" && s.output_path) {
      body = '<video src="/runs/' + encodeURIComponent(runId) + "/" + s.output_path + '" muted loop autoplay playsinline></video>';
      badge = '<span class="sb-badge done">' + esc(s.decision || "done") + "</span>";
    } else if (s.decision === "decline" || st === "declined") {
      body = '<div class="sb-state cut">' + icon("i-cut", "cut") + "</div>"; badge = '<span class="sb-badge cut">cut</span>';
    } else if (st === "working") {
      body = '<div class="sb-state work">' + icon("i-loader", "ic spin") + "</div>"; badge = '<span class="sb-badge work">working</span>';
    } else {
      body = '<div class="sb-state queue"></div>'; badge = '<span class="sb-badge queue">queued</span>';
    }
    return '<div class="sb-card s-' + st + '">' + body +
      '<div class="sb-foot"><span class="sb-id">' + esc(s.id) + "</span>" + badge + "</div></div>";
  }).join("");
  return '<div class="sb-grid">' + cards + "</div>";
}

function livePnl(l, atGate) {
  const p = l.pricing || {};
  const price = p.suggested_price_cents, budget = p.production_budget_cents;
  if (price == null) return "";
  const spent = (l.scenes || []).reduce((a, s) => a + (s.spent_cents || 0), 0) + ((l.voiceover || {}).spent_cents || 0);
  const margin = l.pnl ? l.pnl.margin : (price ? (price - spent) / price : null);
  const cell = (k, v) => '<div class="pl-cell"><div class="pl-k">' + k + '</div><div class="pl-v">' + v + "</div></div>";
  // At the pay gate the build hasn't spent yet — show what the customer pays, the
  // agent's hard production budget, and the guardrail, so the economics are visible
  // BEFORE the payment decision (not only after, as before).
  if (atGate) {
    return '<div class="live-pnl gate">' + cell("You pay", cents(price)) +
      cell("Agent budget", cents(budget)) +
      cell("Auto-declines over", cents(budget)) + "</div>";
  }
  return '<div class="live-pnl">' + cell("Price", cents(price)) + cell("Spent", cents(spent)) +
    cell("Budget left", cents(Math.max(0, (budget || 0) - spent))) + cell("Margin", pct(margin)) + "</div>";
}

function liveStarting() {
  return '<div class="live-head"><span class="live-pill"><span class="live-dot"></span>STARTING</span>' +
    '<div class="live-url" style="margin-top:12px">spinning up the agent…</div></div>';
}
function liveFailed(l) {
  const msg = l ? (((l.events || []).slice(-1)[0] || {}).msg || "build failed") : "build failed";
  return '<div class="live-head"><span class="live-pill bad">FAILED</span>' +
    '<div class="live-url" style="margin-top:12px;color:var(--neg-2)">' + esc(msg) + "</div></div>";
}

/* ---- post-payment / post-cancel return from Stripe Checkout -----------------
   Stripe redirects the customer back to the dashboard after Checkout with either
   ?paid=<run_id> (success_url) or ?cancelled=<run_id> (cancel_url). Without this
   the browser lands on the default view (or, before the success_url was pointed at
   the dashboard, a bare directory listing) and the just-paid build looks dead.

   On ?paid=<id>: pin that run, show a "payment received — producing your video"
   confirmation, and resume polling it so the landing transitions straight into the
   live production view (or the delivered video / a clear failure if it already
   finished). On ?cancelled=<id>: a graceful "payment cancelled" state, never a dead
   page. Returns true if a return param was handled (so boot skips the default flow). */
function handleCheckoutReturn() {
  let params;
  try { params = new URLSearchParams(location.search); } catch (e) { return false; }
  const paid = params.get("paid");
  const cancelled = params.get("cancelled");
  if (!paid && !cancelled) return false;

  // Drop the query string from the address bar so a manual refresh doesn't replay
  // the banner; the run stays selected via state.
  try { history.replaceState(null, "", location.pathname); } catch (e) { /* best effort */ }

  const empty = $("stage-empty"), detail = $("detail");
  if (empty) empty.hidden = true;
  if (detail) detail.hidden = false;

  if (cancelled) {
    // Paint the cancelled card and pin the run. Keep state.building set to this run
    // for the whole rail refresh so loadIndex's auto-select (and its selectRun of the
    // pinned run) are both suppressed and can't overwrite the card; clear it only once
    // the refresh settles. The "View the build" button is the explicit way back.
    const paint = () => {
      if (detail) { detail.hidden = false; detail.innerHTML = checkoutCancelled(cancelled); }
      const retry = $("pc-retry"); if (retry) retry.onclick = () => selectRun(cancelled);
    };
    state.building = cancelled;  // suppress loadIndex auto-select + re-select
    state.selected = cancelled;
    paint();
    const done = () => { state.building = null; paint(); };
    loadIndex(false).then(done).catch(done);
    return true;
  }

  // paid: confirm, then resume the live view for this run.
  if (detail) detail.innerHTML = checkoutPaid(paid);
  // Pin building+selected to the paid run so any rail refresh keeps focus on it and
  // never auto-selects another (e.g. a finished decline) run. beginPoll owns the flow
  // from here: it shows the live production view for a running run, or hands off to
  // finishBuild (which re-pins + refreshes the rail) when the ledger is delivered/failed.
  state.building = paid;
  state.selected = paid;
  beginPoll(paid);
  // beginPoll nulls state.selected for its fresh-build animation; re-pin it so the
  // deferred rail refresh below keeps this run selected.
  state.selected = paid;
  // Refresh the rail so the paid run appears in the list — safe from auto-select
  // because state.building is set (loadIndex skips auto-select while building).
  loadIndex(false);
  return true;
}

// A confirmation card shown the instant we return from a successful Checkout,
// before the first ledger poll lands. Amber accent only (red is reserved for
// declines). beginPoll() replaces this with the live/delivered view on first tick.
function checkoutPaid(runId) {
  return '<div class="live-head"><div class="live-top">' +
    '<span class="live-pill"><span class="live-dot"></span>PAYMENT RECEIVED</span>' +
    '<span class="live-goal">producing your video…</span></div>' +
    '<div class="live-url" style="margin-top:10px">' + icon("i-check") +
      " Payment confirmed for <b>" + esc(runId) + "</b> — resuming the live production view." +
    "</div></div>";
}

// Shown on return from a cancelled Checkout — a clear state with a way back to the
// run (whose pay-gate is still pollable), never a dead page.
function checkoutCancelled(runId) {
  return '<div class="live-head"><div class="live-top">' +
    '<span class="live-pill bad">PAYMENT CANCELLED</span>' +
    '<span class="live-goal">no charge was made</span></div>' +
    '<div class="live-url" style="margin-top:10px">Checkout for <b>' + esc(runId) +
      "</b> was cancelled. The build is still queued at the payment gate.</div>" +
    '<div style="margin-top:14px"><button class="build-go" id="pc-retry">View the build</button></div>' +
    "</div>";
}

/* ============================================================================
   ANALYTICS — the OPERATOR view (Dennis), NOT the customer.
   ----------------------------------------------------------------------------
   The customer build view shows only the price they pay + progress + the video.
   ALL the economics (revenue, COGS, gross profit, margin, the overage the budget
   gate auto-saved, the per-build P&L) live HERE, behind a quiet sidebar entry and
   ?view=analytics. This is the "P&L on camera" money-shot for the demo.

   Data source: GET /api/analytics -> { builds:[...], totals:{...} } (contract in
   .handoff-analytics-backend.md). The route may 404 until the orchestrator
   restarts the server to activate it — we render a graceful loading/empty state
   in that case (never a broken page).
   ========================================================================== */

// Render the operator Analytics view into #detail (hiding the empty/composer
// state). Shows a loading state, then the totals metric cards + the per-build
// table, or a graceful empty/error state if the fetch fails (e.g. 404 pre-restart).
async function openAnalytics() {
  // stop any live-build poll so it can't overwrite the analytics view
  if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
  exitAbout();              // opening Analytics leaves the About view
  state.building = null;
  state.selected = null;
  state.view = "analytics";
  document.querySelectorAll(".run-wrap").forEach((c) => c.classList.remove("active"));
  const a = $("rail-analytics"); if (a) a.classList.add("is-on");
  // on narrow viewports, close the overlay sidebar so the view isn't hidden
  const shell = $("shell");
  if (shell && window.matchMedia("(max-width: 940px)").matches) shell.classList.remove("rail-open");
  const detail = $("detail"), empty = $("stage-empty");
  if (empty) empty.hidden = true;
  if (detail) { detail.hidden = false; detail.innerHTML = analyticsLoading(); }
  if ($("stage")) $("stage").scrollTo({ top: 0 });
  try {
    const res = await fetch("/api/analytics", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (state.view !== "analytics") return;  // user navigated away while fetching
    if (detail) detail.innerHTML = analyticsView(data || {});
  } catch (e) {
    if (state.view !== "analytics") return;
    if (detail) detail.innerHTML = analyticsUnavailable(e.message);
    const r = $("an-retry"); if (r) r.onclick = openAnalytics;
  }
}

// Leave the analytics view (clears the active state on the sidebar entry).
function exitAnalytics() {
  state.view = null;
  const a = $("rail-analytics"); if (a) a.classList.remove("is-on");
}

function analyticsHead() {
  return '<div class="an-head"><div class="an-head-l">' +
    '<span class="an-eyebrow">OPERATOR</span>' +
    '<h2 class="an-title">' + heroWords("Studio", "P&L") + "</h2>" +
    '<p class="an-sub">Revenue, cost of goods, and the margin across every build. Customers never see this.</p>' +
    "</div></div>";
}

function analyticsLoading() {
  return '<div class="analytics">' + analyticsHead() +
    '<div class="an-state">' + icon("i-loader", "ic spin") + "<span>Loading analytics…</span></div></div>";
}

// Graceful state when /api/analytics isn't reachable yet (commonly a 404 until the
// orchestrator restarts the server to activate the route). Clear, not broken.
function analyticsUnavailable(msg) {
  return '<div class="analytics">' + analyticsHead() +
    '<div class="an-state empty">' + icon("i-coin") +
      "<div class=\"an-state-t\">Analytics aren’t available yet.</div>" +
      '<div class="an-state-d">The <code>/api/analytics</code> endpoint isn’t responding' +
        (msg ? " (" + esc(msg) + ")" : "") +
        ". It activates when the server restarts — then this view fills in.</div>" +
      '<button class="an-retry" id="an-retry" type="button">' + icon("i-refresh") + "Retry</button>" +
    "</div></div>";
}

// The full analytics view: the totals as metric cards + the per-build table.
function analyticsView(data) {
  const t = data.totals || {};
  const builds = Array.isArray(data.builds) ? data.builds : [];
  if (!builds.length && !t.builds) {
    return '<div class="analytics">' + analyticsHead() +
      '<div class="an-state empty">' + icon("i-coin") +
        '<div class="an-state-t">No builds yet.</div>' +
        '<div class="an-state-d">Once videos are priced and produced, the P&amp;L shows up here.</div>' +
      "</div></div>";
  }
  return '<div class="analytics">' + analyticsHead() +
    analyticsCards(t) +
    analyticsTable(builds) +
    "</div>";
}

// TOTALS as metric cards. Revenue / COGS / margin = real (priced, terminal)
// builds only — honest money. Overage auto-saved + declines = across ALL builds.
// Gross profit is the hero card (the money-shot). Numbers in mono.
function analyticsCards(t) {
  const realN = t.real_builds != null ? t.real_builds : 0;
  const allN = t.builds != null ? t.builds : 0;
  const card = (k, v, sub, hero) =>
    '<div class="an-card' + (hero ? " hero" : "") + '">' +
      '<div class="an-card-k">' + esc(k) + "</div>" +
      '<div class="an-card-v mono">' + v + "</div>" +
      (sub ? '<div class="an-card-sub">' + esc(sub) + "</div>" : "") +
    "</div>";
  return '<div class="an-cards">' +
    card("Gross profit", cents(t.total_gross_profit_cents), realN + (realN === 1 ? " real build" : " real builds"), true) +
    card("Revenue", cents(t.total_revenue_cents), "real builds only") +
    card("Cost of goods", cents(t.total_cogs_cents), "what production spent") +
    card("Avg margin", pct(t.avg_margin), "mean across real builds") +
    card("Overage auto-saved", cents(t.total_overage_saved_cents), "the budget gate, all builds") +
    card("Builds", String(allN), realN + " priced · real") +
    card("Declines", String(t.total_declines != null ? t.total_declines : 0), "scenes the gate cut") +
    "</div>";
}

// The PER-BUILD table: brand, price, COGS, margin, declines/overage, status.
// One row per build (newest-first, server-sorted). Numbers right-aligned + mono.
// Unpriced/in-flight builds show "—" for price/margin (they're excluded from the
// revenue/margin totals server-side).
function analyticsTable(builds) {
  const head = '<thead><tr>' +
    '<th class="an-th-brand">Build</th>' +
    '<th>Quality</th>' +
    '<th class="num">Price</th>' +
    '<th class="num">COGS</th>' +
    '<th class="num">Margin</th>' +
    '<th class="num">Gate</th>' +
    '<th>Status</th>' +
    "</tr></thead>";
  const rows = builds.map((b) => {
    const brand = anBrandLabel(b);
    const mode = (b.mode || "").toLowerCase();
    const modeTag = mode ? '<span class="an-mode an-mode-' + esc(mode) + '">' + esc(mode) + "</span>" : "";
    const decN = Array.isArray(b.declines) ? b.declines.length : 0;
    const gate = decN
      ? '<span class="an-gate cut">' + decN + (decN === 1 ? " cut" : " cuts") +
        (b.overage_saved_cents ? " · saved " + cents(b.overage_saved_cents) : "") + "</span>"
      : '<span class="an-gate clear">—</span>';
    const st = (b.status || "—");
    const stCls = anStatusClass(st);
    const marginCls = b.margin == null ? "" : (b.margin >= 0.5 ? "pos" : "");
    return '<tr>' +
      '<td class="an-td-brand"><span class="an-brand">' + esc(brand) + "</span>" + modeTag +
        '<span class="an-runid mono">' + esc(clip(b.run_id || "", 28)) + "</span></td>" +
      '<td>' + esc(anQuality(b)) + "</td>" +
      '<td class="num mono">' + (b.price_charged_cents == null ? "—" : cents(b.price_charged_cents)) + "</td>" +
      '<td class="num mono">' + cents(b.cogs_spent_cents) + "</td>" +
      '<td class="num mono ' + marginCls + '">' + (b.margin == null ? "—" : pct(b.margin)) + "</td>" +
      '<td class="num">' + gate + "</td>" +
      '<td><span class="an-status ' + stCls + '">' + esc(st) + "</span></td>" +
    "</tr>";
  }).join("");
  return '<div class="an-table-wrap"><table class="an-table">' + head + "<tbody>" + rows + "</tbody></table></div>";
}

// The brand/label for an analytics row, derived from the build's brand (a company
// URL) the same way the sidebar does — falling back to the run id.
function anBrandLabel(b) {
  const url = (b.brand || "").trim();
  if (url) {
    const host = url.replace(/^https?:\/\//i, "").replace(/^www\./i, "").split("/")[0];
    if (host) {
      const base = brandFromHost(host).replace(/[-_.]+/g, " ").trim();
      if (base) return base.split(/\s+/).map((w) => w ? w.charAt(0).toUpperCase() + w.slice(1) : w).join(" ");
    }
  }
  return railBrand({ run_id: b.run_id });
}
// Quality isn't in the analytics contract directly; the contract carries mode, so
// show that as the build "kind" column heading value when no quality is present.
function anQuality(b) {
  if (b.quality) return qualityLabel(b.quality);
  return b.mode === "real" ? "Real" : (b.mode === "mock" ? "Mock" : "—");
}
function anStatusClass(st) {
  const s = String(st || "").toLowerCase();
  if (s === "delivered" || s === "complete" || s === "completed_with_warnings") return "ok";
  if (s === "failed") return "bad";
  if (s === "running") return "live";
  return "";
}

/* ============================================================================
   ABOUT — the CUSTOMER-facing story: how the agent works, and why our videos are
   better. Two sections:
     (a) ARCHITECTURE — an honest, readable end-to-end of the pipeline, with a
         native-SVG diagram (no raster). URL + goal -> brand_extract -> the planner
         brain (Nemotron) -> align_vo -> build_timeline (picture FROM the voice) ->
         style_fill (designed on-brand motion graphics) -> Remotion render ->
         cost-plus priced + paid on Stripe -> the finished video ships.
     (b) WHY OUR VIDEOS ARE BETTER — the curation thesis: every video is held to the
         bar of a small set of films HAND-PICKED by Dennis. Curation is the moat;
         taste is what separates this from generic AI slop. The curated lookbook
         (moved off the front page) lives here as the proof.

   Routing MIRRORS the Analytics view exactly: a quiet sidebar entry (#rail-about)
   opens it into #detail; state.view = "about"; deep-linkable via ?view=about; it
   exits when the user starts a new build / opens a build / opens Analytics.
   Static content — no fetch, so it never has a loading/error state.
   ========================================================================== */

// Open the About view into #detail (hiding the empty/composer state). Static, so
// it renders synchronously — no loading/error path.
function openAbout() {
  if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
  exitAnalytics();          // opening About leaves the operator analytics view
  state.building = null;
  state.selected = null;
  state.view = "about";
  document.querySelectorAll(".run-wrap").forEach((c) => c.classList.remove("active"));
  const a = $("rail-about"); if (a) a.classList.add("is-on");
  // on narrow viewports, close the overlay sidebar so the view isn't hidden
  const shell = $("shell");
  if (shell && window.matchMedia("(max-width: 940px)").matches) shell.classList.remove("rail-open");
  const detail = $("detail"), empty = $("stage-empty");
  if (empty) empty.hidden = true;
  if (detail) { detail.hidden = false; detail.innerHTML = aboutView(); }
  if ($("stage")) $("stage").scrollTo({ top: 0 });
}

// Leave the About view (clears the active state on the sidebar entry).
function exitAbout() {
  if (state.view === "about") state.view = null;
  const a = $("rail-about"); if (a) a.classList.remove("is-on");
}

// The curated lookbook — the SAME films that used to sit on the front page, moved
// here as the "bar every video is held to." Posters live under
// /dashboard/assets/styles/. Each is a poster + brand + Watch (no style-family tag).
const ABOUT_LOOKBOOK = [
  { name: "Orinovate",    poster: "orinovate.jpg", yt: "https://www.youtube.com/watch?v=FNXrDx8v42I", alt: "Orinovate promo — material filter dashboard" },
  { name: "Hotcake",      poster: "hotcake.jpg",   yt: "https://www.youtube.com/watch?v=BL8IVJ-f14Y", alt: "Hotcake promo — salon CRM member card" },
  { name: "Kuli",         poster: "kuli.jpg",      yt: "https://www.youtube.com/watch?v=nxFYamrhC5o", alt: "Kuli promo — video analysis grid" },
  { name: "Trayd",        poster: "trayd.jpg",     yt: "https://www.youtube.com/watch?v=w-YUqHcC9vU", alt: "Trayd promo — navy and lime payroll dashboard" },
  { name: "JGB Property", poster: "jgb.jpg",       yt: "https://www.youtube.com/watch?v=OKW6xlPMrpo", alt: "JGB Property promo — smart-contract reveal" },
];

function aboutLookbookCards() {
  return ABOUT_LOOKBOOK.map((f) => {
    const src = "/dashboard/assets/styles/" + f.poster;
    return '<article class="style-card">' +
      '<a class="sc-frame" href="' + f.yt + '" target="_blank" rel="noopener" aria-label="Watch ' + esc(f.name) + ' on YouTube">' +
        '<img class="sc-poster" src="' + src + '" width="800" height="450" loading="lazy" decoding="async" alt="' + esc(f.alt) + '" />' +
        '<span class="sc-play" aria-hidden="true">' + icon("i-play") + "</span>" +
      "</a>" +
      '<div class="sc-foot"><span class="sc-name">' + esc(f.name) + "</span>" +
        '<a class="sc-watch" href="' + f.yt + '" target="_blank" rel="noopener"><span>Watch</span>' + icon("i-link") + "</a>" +
      "</div></article>";
  }).join("");
}

// The pipeline diagram, drawn as native inline SVG (no raster). Seven labelled
// stages flow left-to-right with coral connectors; the input (URL + goal) feeds in
// and the finished, paid-for video ships out. Stage glyphs come from the icon
// sprite (#i-*). Deterministic — pure markup, no script. The viewBox scales to fit.
function aboutPipelineSVG() {
  // 7 stages: brand_extract, plan (Nemotron), align_vo, build_timeline, style_fill,
  // render (Remotion), price+pay (Stripe). Laid out on a single horizontal rail.
  const stages = [
    { ic: "i-brand",  k: "brand_extract", t: "Read the brand",  d: "Pull palette, fonts, wordmark and real copy from the URL." },
    { ic: "i-plan",   k: "planner · Nemotron", t: "Plan the story", d: "The brain breaks the goal into a scene-by-scene storyboard." },
    { ic: "i-mic",    k: "align_vo",      t: "Find the voice",  d: "Generate the voiceover with word-level timing." },
    { ic: "i-wave",   k: "build_timeline", t: "Build from voice", d: "Anchor every scene to the words it speaks." },
    { ic: "i-layers", k: "style_fill",    t: "Design each scene", d: "Fill the timeline with on-brand motion graphics." },
    { ic: "i-film",   k: "Remotion",      t: "Render",          d: "Frame-exact render to a real MP4." },
    { ic: "i-card",   k: "Stripe",        t: "Price & ship",    d: "Cost-plus price, paid on Stripe, then the video ships." },
  ];
  const W = 1180, H = 232;
  const padX = 70, top = 64, boxW = 132, boxH = 104, gap = (W - padX * 2 - boxW) / (stages.length - 1);
  let defs = "", rail = "", nodes = "";
  // the connecting rail under the boxes
  const railY = top + boxH / 2;
  rail += '<line x1="' + (padX + boxW / 2) + '" y1="' + railY + '" x2="' + (padX + boxW / 2 + gap * (stages.length - 1)) + '" y2="' + railY + '" stroke="var(--ws-rail)" stroke-width="2"/>';
  stages.forEach((s, i) => {
    const x = padX + i * gap;
    const cx = x + boxW / 2;
    // a small connector arrowhead between boxes (coral), drawn on the rail
    if (i < stages.length - 1) {
      const ax = cx + gap / 2;
      nodes += '<path d="M' + (ax - 5) + ' ' + (railY - 5) + ' L' + (ax + 5) + ' ' + railY + ' L' + (ax - 5) + ' ' + (railY + 5) + '" fill="none" stroke="var(--ws-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>';
    }
    nodes +=
      '<g class="ab-node" style="--i:' + i + '">' +
        '<rect x="' + x + '" y="' + top + '" width="' + boxW + '" height="' + boxH + '" rx="12" fill="var(--ws-card)" stroke="var(--ws-line)"/>' +
        '<circle cx="' + cx + '" cy="' + (top + 26) + '" r="15" fill="var(--ws-chip)" stroke="var(--ws-line)"/>' +
        '<use href="#' + s.ic + '" x="' + (cx - 9) + '" y="' + (top + 26 - 9) + '" width="18" height="18" color="var(--ws-accent)"/>' +
        '<text x="' + cx + '" y="' + (top + 58) + '" text-anchor="middle" class="ab-t">' + esc(s.t) + "</text>" +
        '<text x="' + cx + '" y="' + (top + 76) + '" text-anchor="middle" class="ab-k">' + esc(s.k) + "</text>" +
      "</g>";
  });
  // input chip (URL + goal) feeding the first box from the top-left
  const inX = padX + boxW / 2;
  defs +=
    '<g class="ab-in">' +
      '<rect x="' + (inX - 92) + '" y="14" width="184" height="34" rx="17" fill="var(--ws-accent-soft)" stroke="var(--ws-accent-line)"/>' +
      '<text x="' + inX + '" y="36" text-anchor="middle" class="ab-in-t">a URL  +  a goal</text>' +
      '<path d="M' + inX + ' 48 L' + inX + ' ' + top + '" stroke="var(--ws-accent)" stroke-width="2"/>' +
    "</g>";
  // output chip (finished video) leaving the last box at the bottom-right
  const outX = padX + (stages.length - 1) * gap + boxW / 2;
  defs +=
    '<g class="ab-out">' +
      '<path d="M' + outX + ' ' + (top + boxH) + ' L' + outX + ' ' + (top + boxH + 16) + '" stroke="var(--ws-accent)" stroke-width="2"/>' +
      '<rect x="' + (outX - 96) + '" y="' + (top + boxH + 16) + '" width="192" height="34" rx="17" fill="var(--ws-accent)" stroke="none"/>' +
      '<text x="' + outX + '" y="' + (top + boxH + 38) + '" text-anchor="middle" class="ab-out-t">a finished, paid-for video</text>' +
    "</g>";
  return '<svg class="ab-svg" viewBox="0 0 ' + W + " " + H + '" role="img" ' +
    'aria-label="Pipeline: a URL and a goal flow through brand_extract, the planner brain, align_vo, build_timeline, style_fill, Remotion render, and Stripe pricing, producing a finished paid-for video.">' +
    rail + nodes + defs + "</svg>";
}

// One step in the readable, numbered walkthrough beneath the diagram. A lettered/
// numbered badge (no emoji), a title, and a plain-language line.
function aboutStep(n, icId, title, body) {
  return '<li class="ab-step">' +
    '<span class="ab-step-n">' + esc(n) + "</span>" +
    '<span class="ab-step-ic">' + icon(icId) + "</span>" +
    '<span class="ab-step-main"><span class="ab-step-t">' + esc(title) + "</span>" +
      '<span class="ab-step-d">' + body + "</span></span>" +
  "</li>";
}

// The full About view markup. Section A = architecture (diagram + numbered steps);
// Section B = the curation thesis + the relocated curated lookbook.
function aboutView() {
  const head =
    '<div class="an-head about-head"><div class="an-head-l">' +
      '<span class="an-eyebrow">ABOUT</span>' +
      '<h2 class="an-title">' + heroWords("How Walk Studio", "makes a film") + "</h2>" +
      '<p class="an-sub">A URL and a goal go in. A finished, on-brand promo — written, designed, ' +
        "rendered, priced and paid for — comes out. Here is exactly how, and why we think " +
        "ours are better.</p>" +
    "</div></div>";

  // ---- Section A: ARCHITECTURE ----
  const steps =
    aboutStep("1", "i-brand", "Read the brand",
      "The agent visits the URL and pulls the real brand — palette, fonts, wordmark, and actual copy. " +
      "Nothing is invented; the video looks like the company, not like a template.") +
    aboutStep("2", "i-plan", "Plan the story",
      "The planner brain (<span class=\"ab-em\">Nemotron</span>) reads the goal and decomposes it into a " +
      "scene-by-scene storyboard — what each beat says and shows.") +
    aboutStep("3", "i-mic", "Find the voice",
      "<span class=\"ab-em\">align_vo</span> generates the voiceover and captures word-level timing — it " +
      "knows exactly when every word is spoken.") +
    aboutStep("4", "i-wave", "Build the picture from the voice",
      "<span class=\"ab-em\">build_timeline</span> builds the timeline <span class=\"ab-em\">from</span> the " +
      "voice: each scene is anchored to the words it narrates, so picture and audio are locked together by " +
      "design — not edited to fit afterward.") +
    aboutStep("5", "i-layers", "Design every scene",
      "<span class=\"ab-em\">style_fill</span> fills each scene with designed, on-brand motion graphics in a " +
      "curated style — real layout, type and motion, not stock b-roll.") +
    aboutStep("6", "i-film", "Render it",
      "Remotion renders the timeline to a real, frame-exact MP4.") +
    aboutStep("7", "i-card", "Price it, get paid, ship it",
      "The video is priced <span class=\"ab-em\">cost-plus</span> from its own plan, paid for on " +
      "<span class=\"ab-em\">Stripe</span>, and the finished file ships.");

  const arch =
    '<section class="about-sec" aria-labelledby="about-arch-h">' +
      '<div class="about-sec-head">' +
        '<span class="about-kicker">' + icon("i-layers") + "Architecture</span>" +
        '<h3 class="about-h" id="about-arch-h">One pipeline, end to end</h3>' +
        '<p class="about-lead">The agent runs the whole chain itself — read the brand, plan the ' +
          "story, find the voice, build the picture from that voice, design every scene, render, " +
          "and settle up. The picture is built from the voice, so it always lands on the words.</p>" +
      "</div>" +
      '<div class="ab-diagram">' + aboutPipelineSVG() + "</div>" +
      '<ol class="ab-steps">' + steps + "</ol>" +
    "</section>";

  // ---- Section B: WHY OUR VIDEOS ARE BETTER (curation thesis + lookbook) ----
  const why =
    '<section class="about-sec about-why" aria-labelledby="about-why-h">' +
      '<div class="about-sec-head">' +
        '<span class="about-kicker">' + icon("i-star") + "Why ours are better</span>" +
        '<h3 class="about-h" id="about-why-h">Curation is the moat</h3>' +
        '<p class="about-lead">Most AI video is slop because nothing holds it to a standard. ' +
          "Every video Walk Studio makes is held to the bar of a small set of films " +
          "<span class=\"ab-em\">hand-picked by Dennis</span>. The agent supplies the speed; a " +
          "human's taste supplies the standard. That pairing — an agent plus a curated eye — is " +
          "what separates this from generic AI output.</p>" +
      "</div>" +
      '<div class="about-thesis">' +
        '<div class="about-thesis-card"><span class="att-n">A</span><div class="att-main">' +
          '<span class="att-t">A fixed bar, not a vibe</span>' +
          '<span class="att-d">The reference films below are the explicit standard. New videos are ' +
            "measured against them, not against whatever a model felt like producing.</span></div></div>" +
        '<div class="about-thesis-card"><span class="att-n">B</span><div class="att-main">' +
          '<span class="att-t">Taste, then speed</span>' +
          '<span class="att-d">The styles are chosen by a person first; the agent then applies that ' +
            "judgement at scale. Curation comes before automation, never after.</span></div></div>" +
        '<div class="about-thesis-card"><span class="att-n">C</span><div class="att-main">' +
          '<span class="att-t">On-brand, not on-template</span>' +
          '<span class="att-d">Because the brand is read from the real site, the bar is applied to ' +
            "<span class=\"ab-em\">your</span> brand — same craft, your colours, type and voice.</span></div></div>" +
      "</div>" +
      '<div class="about-lookbook">' +
        '<div class="about-lookbook-head">' +
          '<h4 class="about-lb-h">The bar every video is held to</h4>' +
          '<p class="about-lb-note">A few we are proud of — hand-picked.</p>' +
        "</div>" +
        '<div class="styles-grid">' + aboutLookbookCards() + "</div>" +
      "</div>" +
    "</section>";

  return '<div class="about">' + head + arch + why + "</div>";
}

/* ---------------- boot ---------------- */
function init() {
  buildHeroTitle();       // the idle hero builds word-by-word on first paint
  replayLandingMotion();  // the how-it-works strip + CTAs reveal on first paint
  loadPricing();          // fetch the canonical pricing.json + render the premium menu
  const btn = $("refresh"); if (btn) btn.addEventListener("click", () => loadIndex(true));
  const go = $("build-go"); if (go) go.addEventListener("click", startBuild);
  const u = $("build-url"); if (u) u.addEventListener("keydown", (e) => { if (e.key === "Enter") startBuild(); });
  // First-run landing actions: the ONE next step (focus the URL input) and a
  // one-click "see a finished example" that opens a real delivered run so a
  // newcomer can see the payoff before committing.
  const hs = $("hero-start"); if (hs) hs.addEventListener("click", focusBuildUrl);
  const hx = $("hero-sample"); if (hx) hx.addEventListener("click", () => {
    const id = hx.getAttribute("data-run");
    if (id) selectRun(id);
  });
  // Example chips (Hiro-style use-case starters) — clicking one FILLS the goal
  // prompt with a concise starter, focuses it (caret at end), and pulses the field
  // so the next step (Build) is obvious. Pure DOM; no build/plan/pay logic touched.
  const ex = $("ex-chips");
  if (ex) ex.querySelectorAll(".ex-chip").forEach((c) => c.addEventListener("click", () => {
    const goal = $("build-goal");
    if (!goal) return;
    goal.value = c.getAttribute("data-fill") || "";
    try { goal.focus({ preventScroll: true }); } catch (e) { goal.focus(); }
    try { goal.setSelectionRange(goal.value.length, goal.value.length); } catch (e) {}
    goal.classList.remove("nudge"); void goal.offsetWidth; goal.classList.add("nudge");
  }));
  // Sidebar "New build" — returns the center to the empty-state composer for a
  // fresh run (like Claude's "New chat"). Each past build is a sidebar item that
  // opens its view via the existing renderRail()->selectRun wiring.
  const nb = $("rail-new"); if (nb) nb.addEventListener("click", newBuild);
  // OPERATOR Analytics entry (sidebar footer) — opens the P&L-across-all-builds
  // view. Quiet on purpose: this is Dennis's view, not the customer's.
  const ra = $("rail-analytics"); if (ra) ra.addEventListener("click", openAnalytics);
  // ABOUT entry (sidebar footer, customer-facing) — opens the how-it-works +
  // curation-thesis view (where the curated lookbook now lives).
  const rb = $("rail-about"); if (rb) rb.addEventListener("click", openAbout);
  // Sidebar collapse / reopen. On wide layouts we toggle .rail-collapsed (slides
  // the grid column to 0). On narrow layouts the rail is collapsed by default and
  // .rail-open slides it in (see the <=940px @media). One toggle handles both.
  const shell = $("shell");
  const setRail = (collapsed) => {
    if (!shell) return;
    const narrow = window.matchMedia("(max-width: 940px)").matches;
    if (narrow) { shell.classList.toggle("rail-open", !collapsed); shell.classList.remove("rail-collapsed"); }
    else { shell.classList.toggle("rail-collapsed", collapsed); shell.classList.remove("rail-open"); }
  };
  const rc = $("rail-collapse"); if (rc) rc.addEventListener("click", () => setRail(true));
  const rr = $("rail-reopen"); if (rr) rr.addEventListener("click", () => setRail(false));
  // Pace segmented pill (D6): one selection at a time, stored on state.pace and
  // sent with the build request. Named tiers, not a hidden env var.
  const pace = $("build-pace");
  if (pace) pace.querySelectorAll(".pace-opt").forEach((b) => b.addEventListener("click", () => {
    pace.querySelectorAll(".pace-opt").forEach((o) => o.classList.toggle("is-on", o === b));
    state.pace = b.getAttribute("data-pace") || "standard";
  }));
  // QUALITY toggle (Standard | Premium): the ONE upfront choice that changes what
  // the agent makes. One selection at a time, stored on state.selection.quality and
  // sent with the build request. Each option carries a small explanation (in HTML);
  // here we just track the choice + the selected look.
  const qual = $("cmp-quality");
  if (qual) qual.querySelectorAll(".q-opt").forEach((b) => b.addEventListener("click", () => {
    qual.querySelectorAll(".q-opt").forEach((o) => o.classList.toggle("is-on", o === b));
    state.selection.quality = b.getAttribute("data-quality") === "premium" ? "premium" : "standard";
  }));
  // A return from Stripe Checkout (?paid / ?cancelled) takes priority over both the
  // in-flight-build resume and the default auto-select — it pins + shows the user's
  // own run. If handled, skip the default boot flow.
  if (handleCheckoutReturn()) return;
  // Deep-link to the operator Analytics view (?view=analytics). Loads the rail so
  // the sidebar populates, then opens the P&L view; skips the default build flow.
  let _params;
  try { _params = new URLSearchParams(location.search); } catch (e) { _params = null; }
  if (_params && _params.get("view") === "analytics") {
    loadIndex(false);
    openAnalytics();
    return;
  }
  // Deep-link to the customer About view (?view=about). Same shape as analytics:
  // load the rail so the sidebar populates, then open the About view.
  if (_params && _params.get("view") === "about") {
    loadIndex(false);
    openAbout();
    return;
  }
  // Resume an in-flight build FIRST so a live run takes priority over auto-selecting
  // a finished one; loadIndex then skips its auto-select because state.building is set.
  fetch("/api/active").then((r) => r.json()).then((d) => {
    if (d.active && d.active.length) beginPoll(d.active[0].run_id);
    loadIndex(false);
  }).catch(() => loadIndex(false));
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
