#!/usr/bin/env python3
"""Live-DOM harvests for the walkrec pipeline — partner marks and quotes.

WHY THIS MODULE EXISTS (the defect class it kills): these harvests need
Playwright, but the hosted worker's MAIN interpreter has none — only
.venv-capture does. Both harvests used to import playwright inline and
swallow the ImportError, so on every hosted run they silently returned
nothing: quotes vanished ("Harvested 0 real quotes") and the partner wall
fell through to a text-window guess that scraped the NEXT section's
headings — an integration wall listing the site's own features.

So: the JS lives here, and `run()` executes it in-process when Playwright
is importable, else subprocesses THIS FILE under the capture interpreter.
Callers get real data or a loud, attributable failure — never a silent [].

CLI: page_harvest.py <url> <kind>   # kind: logos | quotes -> JSON on stdout
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# ── Partner marks ────────────────────────────────────────────────────────
# PROVENANCE CONTRACT: names AND images come from the marker's OWN
# container. A partner is only a partner if the site put it inside the
# "works with" block — anything found by walking the text after the marker
# belongs to whatever section came next, which is exactly how a features
# grid ended up under "Works perfectly with".
_LOGO_JS = r"""
() => {
  const MARKERS = ["works perfectly with", "works with", "compatible with",
                   "integrated with", "integrations", "supported tools"];
  const clean = (s) => (s || "").trim().replace(/[-_]/g, " ")
    .replace(/\.(svg|png|webp|jpg|jpeg|ico)$/i, "")
    .replace(/\s+logo$/i, "").replace(/\s+color$/i, "").trim();

  // The host is the SMALLEST element whose own text is the marker line and
  // that contains the mark images — smallest wins, so we never swallow a
  // neighbouring section.
  let host = null, hostLen = Infinity;
  for (const el of document.querySelectorAll("section,div,aside,footer")) {
    const t = (el.textContent || "").trim().toLowerCase();
    if (t.length > 400) continue;
    if (!MARKERS.some((m) => t.startsWith(m) || t === m)) continue;
    if (el.querySelectorAll("img,svg").length < 3) continue;
    if (t.length < hostLen) { host = el; hostLen = t.length; }
  }
  if (!host) return { names: [], marks: [] };

  const seen = new Set();
  const marks = [];
  for (const img of host.querySelectorAll("img")) {
    let n = clean(img.getAttribute("alt") || img.getAttribute("aria-label")
                  || img.getAttribute("title"));
    const src = img.currentSrc || img.getAttribute("src") || "";
    if (!n) n = clean((src.split("/").pop() || "").split("?")[0]);
    if (!n || n.length > 24) continue;
    const key = n.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    marks.push({ name: n, src: src ? new URL(src, location.href).href : "" });
  }
  // Inline <svg> marks carry their name in aria-label/title only; keep the
  // name (an honest initial badge) with no src rather than dropping it.
  for (const sv of host.querySelectorAll("svg")) {
    const n = clean(sv.getAttribute("aria-label")
                    || (sv.querySelector("title") || {}).textContent);
    if (!n || n.length > 24) continue;
    const key = n.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    marks.push({ name: n, src: "" });
  }
  // Text-node partners (rare: a wall rendered as words) — ONLY from inside
  // the host, never from the corpus after it.
  if (marks.length < 3) {
    for (const el of host.querySelectorAll("li,span,p,a")) {
      if (el.children.length) continue;
      const n = (el.textContent || "").trim();
      if (!(2 <= n.length && n.length <= 24)) continue;
      if (MARKERS.some((m) => n.toLowerCase().startsWith(m))) continue;
      if (!/^[A-Za-z0-9]/.test(n) || !/[A-Z]/.test(n)) continue;
      const key = n.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      marks.push({ name: n, src: "" });
    }
  }
  return { marker: (host.textContent || "").trim().slice(0, 60),
           names: marks.map((m) => m.name), marks: marks.slice(0, 14) };
}
"""

_QUOTES_JS = r"""
() => {
  let host = null;
  for (const el of document.querySelectorAll("*")) {
    const t = (el.textContent || "").trim().toLowerCase();
    if ((t.includes("testimonial") || t.includes("from founders") ||
         t.includes("wall of love") || t.includes("what people say")) &&
        (!host || t.length < (host.textContent || "").length))
      host = el;
  }
  if (!host) return [];
  let sec = host;
  for (let i = 0; i < 6 && sec.parentElement; i++) {
    sec = sec.parentElement;
    if ((sec.innerText || "").length > 300) break;
  }
  const lines = (sec.innerText || "").split("\n").map(s => s.trim()).filter(Boolean);
  const attrRe = /@|^(founder|co-founder|ceo|cto|head of|director)\b/i;
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    const isQ = /^[“”"']/.test(l) || (l.length >= 40 && !attrRe.test(l));
    if (!isQ || l.length < 25 || l.length > 300) continue;
    let name = "", attr = "";
    for (let j = i + 1; j <= i + 2 && j < lines.length; j++) {
      if (attrRe.test(lines[j])) attr = lines[j];
      else if (!name && lines[j].length <= 40 && /^[A-Z]/.test(lines[j])) name = lines[j];
    }
    if (attr) out.push({ q: l.replace(/^[“”"']+|[“”"']+$/g, ""), name, a: attr });
    if (out.length >= 3) break;
  }
  return out;
}
"""

_JS = {"logos": _LOGO_JS, "quotes": _QUOTES_JS}


def _in_process(url: str, kind: str):
    """Run the harvest here. Raises if Playwright isn't importable."""
    import walk_native as wn
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = wn._launch_browser(p)
        try:
            ctx = browser.new_context(viewport=wn.VIEWPORT,
                                      user_agent=wn._DESKTOP_UA,
                                      extra_http_headers=wn._EXTRA_HEADERS)
            ctx.add_init_script(wn._STEALTH_INIT_JS)
            page = ctx.new_page()
            page.goto(wn._norm_url(url), wait_until="domcontentloaded",
                      timeout=45000)
            wn._wait_for_spa_hydration(page)
            page.wait_for_timeout(1500)
            return page.evaluate(_JS[kind])
        finally:
            try:
                browser.close()
            except Exception:
                pass


def run(url: str, kind: str, run_dir: str = ""):
    """Harvest `kind` from `url`. In-process when possible, else under the
    capture interpreter. Returns the JS result (or None on failure) and
    reports WHY on failure — a silent empty result is what let a fabricated
    wall ship."""
    err = ""
    try:
        return _in_process(url, kind)
    except ImportError:
        err = "no playwright in this interpreter"
    except Exception as e:
        err = f"{type(e).__name__}: {e}"

    try:
        import capture_screenshots as _cs
        cap = _cs.CAPTURE_PY
        if os.path.exists(cap) and os.path.abspath(cap) != os.path.abspath(sys.executable):
            r = subprocess.run([cap, os.path.abspath(__file__), url, kind],
                               capture_output=True, text=True, timeout=180)
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout)
            err = ((r.stderr or "") + " " + (r.stdout or "")).strip()[-300:]
        else:
            err = err or "no capture interpreter available"
    except Exception as e:
        err = f"{type(e).__name__}: {e}"

    print(f"[harvest!] {kind} from {url}: {err}", file=sys.stderr)
    if run_dir:
        try:
            from run_events import emit
            emit(run_dir, "read.harvest_failed",
                 f"Couldn't read the {kind} section", err)
        except Exception:
            pass
    return None


def _prefer(a: dict, b: dict) -> dict:
    """Between two spellings of one partner, keep the better mark: a real
    <img src> beats none, then the longer name ('Google Antigravity' beats
    the filename-derived 'antigravity')."""
    if bool(a.get("src")) != bool(b.get("src")):
        return a if a.get("src") else b
    return a if len(a.get("name", "")) >= len(b.get("name", "")) else b


def marks(url: str, run_dir: str = ""):
    """Deduped partner marks: [{name, src}]. Theme/hover variants of one
    partner collapse to a single entry (a wall listing 'Google Antigravity'
    AND 'antigravity' reads as two products)."""
    res = run(url, "logos", run_dir) or {}
    out: list = []
    for m in (res.get("marks") or []):
        name = (m.get("name") or "").strip()
        if not name:
            continue
        nl = name.lower()
        hit = None
        for i, o in enumerate(out):
            ol = o["name"].lower()
            if nl == ol or nl in ol.split() or ol in nl.split() \
                    or nl.startswith(ol + " ") or ol.startswith(nl + " ") \
                    or nl.replace(" ", "") == ol.replace(" ", ""):
                hit = i
                break
        if hit is None:
            out.append({"name": name, "src": m.get("src") or ""})
        else:
            out[hit] = _prefer(out[hit], {"name": name, "src": m.get("src") or ""})
    return out[:10]


def mark_data_uri(src: str) -> str:
    """The partner's OWN mark as a data URI (the film renders offline).
    Only same-run http(s) fetches, size-capped. '' when unavailable — the
    caller then shows an honest initial badge."""
    if not src.startswith(("http://", "https://")):
        return ""
    try:
        import base64
        import urllib.request
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip()
            data = r.read(400_000)
        if not data or not ctype.startswith("image/"):
            return ""
        return f"data:{ctype};base64," + base64.b64encode(data).decode()
    except Exception:
        return ""


def main(argv):
    if len(argv) < 3:
        print("usage: page_harvest.py <url> <logos|quotes>", file=sys.stderr)
        return 2
    print(json.dumps(_in_process(argv[1], argv[2])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
