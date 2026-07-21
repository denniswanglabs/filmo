"""Run event bus (walkrec prototype) — the agent's visible activity stream.

ARCHITECTURAL CONTRACT (Dennis 2026-07-18: "the agent always gives updates"):
1. ONE BUS — every user-visible progress line flows through emit(). emit()
   both appends a structured JSON event to runs/<id>/events.jsonl AND prints
   the human log line, so narration and telemetry are the same act and can
   never drift apart.
2. NO SILENT ENDINGS — the run wrapper emits a terminal event ("run.done" /
   "run.error") from a finally block; a watcher always learns how a run ended.
3. ARTIFACTS BY REFERENCE — events carry repo-relative paths to the real
   files the agent produced (page shots, recordings, the film). The viewer
   shows what the agent actually saw, never a reconstruction.

Events are append-only JSONL: {"seq", "ts", "kind", "title", "detail",
"artifact"}. kind is dot-namespaced: run.*, read.*, decide.*, film.*,
assemble.*. Never raises — a broken event stream must not break a build.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# HOSTED SINK (walkrec beta): when the worker env carries InsForge access,
# every event ALSO lands in public.agent_events and artifacts upload to
# storage — same bus, second sink, best-effort and non-blocking so a network
# blip can never break a build.
_IF_BASE = (os.environ.get("INSFORGE_BASE_URL")
            or os.environ.get("INSFORGE_URL", "")).rstrip("/")
_IF_KEY = os.environ.get("INSFORGE_API_KEY", "")
_IF_BUCKET = os.environ.get("INSFORGE_BUCKET", "walk-videos")


def _hosted_run_id(run_dir: str) -> str:
    """The InsForge runs.id for this run dir ('' when not a hosted run).
    The worker writes runs/<dir>/insforge-run-id at claim time."""
    try:
        with open(os.path.join(run_dir, "insforge-run-id")) as f:
            return f.read().strip()
    except Exception:
        return ""


def _if_req(method: str, path: str, body, ctype: str):
    headers = {"Authorization": f"Bearer {_IF_KEY}"}
    if body is not None:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(
        _IF_BASE + path, data=body, method=method, headers=headers)
    return urllib.request.urlopen(req, timeout=15)


def _if_req_retry(method: str, path: str, body, ctype: str, attempts: int = 3):
    """BROWNOUT CONTRACT: InsForge intermittently stalls for tens of seconds
    (observed 2026-07-19: timeout, then ~1s responses). A single-shot call
    turns a brownout into LOST events; bounded retries turn it into LATE
    events. 4xx (real rejections, e.g. seq 409) never retry."""
    delay = 4.0
    for i in range(attempts):
        try:
            return _if_req(method, path, body, ctype)
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                raise
            if i == attempts - 1:
                raise
        except Exception:
            if i == attempts - 1:
                raise
        time.sleep(delay)
        delay *= 2
    raise RuntimeError("unreachable")


def _multipart(fields: dict, file_field: str, filename: str,
               ctype: str, data: bytes):
    """Encode a multipart/form-data body (stdlib only)."""
    boundary = "----filmo%d" % int(time.time() * 1000)
    out = []
    for k, v in fields.items():
        out.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                   f"name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    out.append(f"--{boundary}\r\nContent-Disposition: form-data; "
               f"name=\"{file_field}\"; filename=\"{filename}\"\r\n"
               f"Content-Type: {ctype}\r\n\r\n".encode())
    out.append(data)
    out.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


def upload_object(key: str, path: str, overwrite: bool = False) -> str:
    """Upload a file via the documented strategy flow (S3 presigned POST or
    local direct PUT). Returns the object URL, '' on failure. Never raises."""
    try:
        ext = os.path.splitext(path)[1].lower()
        # The content-type the object is STORED with. .json/.mp3/.svg used to
        # fall through to image/png (cosmetic — downloads are unaffected, but
        # the metadata lied). Map the extensions this helper actually uploads;
        # anything else is honest binary, not a wrong image type.
        ctype = {
            ".mp4": "video/mp4", ".mp3": "audio/mpeg",
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml", ".json": "application/json",
        }.get(ext, "application/octet-stream")
        with open(path, "rb") as f:
            data = f.read()
        if overwrite:
            try:
                req = urllib.request.Request(
                    f"{_IF_BASE}/api/storage/buckets/{_IF_BUCKET}/objects/{key}",
                    method="DELETE",
                    headers={"Authorization": f"Bearer {_IF_KEY}"})
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                pass
        strat = json.loads(_if_req(
            "POST", f"/api/storage/buckets/{_IF_BUCKET}/upload-strategy",
            json.dumps({"filename": key, "contentType": ctype,
                        "size": len(data)}).encode(),
            "application/json").read())
        if strat.get("method") == "presigned":
            fields = dict(strat.get("fields") or {})
            body, mp_ctype = _multipart(fields, "file", key, ctype, data)
            req = urllib.request.Request(strat["uploadUrl"], data=body,
                                         method="POST",
                                         headers={"Content-Type": mp_ctype})
            urllib.request.urlopen(req, timeout=60)
            _if_req("POST",
                    f"/api/storage/buckets/{_IF_BUCKET}/objects/"
                    f"{urllib.parse.quote(key, safe='')}/confirm-upload",
                    json.dumps({"size": len(data)}).encode(),
                    "application/json")
        else:
            body, mp_ctype = _multipart({}, "file", key, ctype, data)
            req = urllib.request.Request(strat.get("uploadUrl", ""), data=body,
                                         method="PUT",
                                         headers={
                                             "Authorization": f"Bearer {_IF_KEY}",
                                             "Content-Type": mp_ctype})
            urllib.request.urlopen(req, timeout=60)
        return (f"{_IF_BASE}/api/storage/buckets/{_IF_BUCKET}/objects/"
                f"{urllib.parse.quote(key, safe='')}")
    except Exception:
        return ""


def charge_credits(run_dir: str, amount: int, reason: str) -> bool:
    """Charge the RUN'S OWNER for work the pipeline actually performed.
    The worker owns this because only it knows whether the taste gates
    accepted an edit — a declined edit must never cost anything. The
    ledger's (run_id, reason) unique index makes a retry idempotent, so
    `reason` must identify the unit of work (e.g. the director job id).
    Returns True when a charge row landed. Never raises."""
    rid = _hosted_run_id(run_dir)
    if not (rid and _IF_BASE and _IF_KEY and amount > 0):
        return False
    try:
        resp = _if_req("GET",
                       f"/api/database/records/runs?id=eq.{rid}&select=user_id",
                       None, "application/json")
        rows = json.loads(resp.read())
        uid = rows[0]["user_id"] if rows else ""
        if not uid:
            return False
        _if_req_retry("POST", "/api/database/records/credit_ledger",
                      json.dumps([{"user_id": uid, "delta": -abs(amount),
                                   "reason": reason, "run_id": rid}]).encode(),
                      "application/json")
        return True
    except Exception as e:
        print(f"[credits!] charge {reason}: {e}", file=sys.stderr)
        return False


def _walkrec_plan_patch(run_dir: str) -> dict:
    """The forensic write-through (2026-07-20 audit): walkrec runs used to
    deliver with runs.plan / props / selection ALL NULL — the claimer's walkrec
    verdict sets only {status, phase}, and this shipper only PATCHed final_url —
    which left a delivered film unexplainable from the DB (the overnight film
    forensics were blind). The tour plan (stops + brand ctx, ~4KB, written by
    proto_walkrec next to the render) IS the film's plan, so it ships WITH the
    delivery, in the same PATCH.

    props / selection stay untouched on purpose: runs.props gates the CLASSIC
    editor and the rerender enqueue in the web app (truthy props would unlock a
    classic editor on a walkrec film), and walkrec records no planner_usage for
    selection. Best-effort: a missing/oversized/unreadable plan ships final_url
    alone, exactly as before."""
    p = os.path.join(run_dir, "stops.json")
    try:
        if os.path.exists(p) and os.path.getsize(p) <= 256 * 1024:
            with open(p) as f:
                plan = json.load(f)
            if isinstance(plan, dict) and plan:
                return {"plan": plan}
    except Exception as e:
        print(f"[ship] plan write-through skipped: {e}", file=sys.stderr)
    return {}


def ship_final(run_dir: str, run_key: str, film_path: str) -> str:
    """Deliver a walkrec film: copy to runs/<key>/final.mp4, upload via the
    strategy flow (no gateway cap), PATCH runs.final_url with a fresh ?v=
    cache-buster (+ the tour plan — see _walkrec_plan_patch). ONE contract for
    both the build and director paths — the director's re-render used to update
    only the canvas artifact, leaving final_url serving the pre-edit cut.
    Returns the URL ('' off-hosted)."""
    rid = _hosted_run_id(run_dir)
    if not rid:
        return ""
    final = os.path.join(run_dir, "final.mp4")
    try:
        if os.path.abspath(film_path) != os.path.abspath(final):
            import shutil
            shutil.copyfile(film_path, final)
    except Exception:
        return ""
    url = upload_object(f"{run_key}/final.mp4", final, overwrite=True)
    if not url:
        print("[ship!] final upload failed (strategy flow)", file=sys.stderr)
        return ""
    url = f"{url}?v={int(time.time())}"
    try:
        patch = {"final_url": url}
        patch.update(_walkrec_plan_patch(run_dir))
        _if_req_retry("PATCH", f"/api/database/records/runs?id=eq.{rid}",
                      json.dumps(patch).encode(),
                      "application/json")
    except Exception as e:
        print(f"[ship!] final_url patch failed: {e}", file=sys.stderr)
    # FIRST DELIVERY -> "your film is ready" email to the run's OWNER. Idempotent
    # (runs.notified_at): a director re-render lands here too but finds the marker
    # set and sends nothing, so only the initial delivery notifies. Gated dry-run/
    # allowlist by default. Best-effort by the same contract as the rest of ship:
    # it NEVER raises and NEVER delays — final_url is already persisted above.
    notify_video_ready(run_dir, run_key, url)
    return url


# ── Ready-email (AgentMail) ──────────────────────────────────────────────────
# OUTWARD-ACTION SAFETY: this sends real email to real people, so it is OFF for
# everyone but an allowlist until Dennis flips ONE env flag.
#   * FILMO_EMAIL_LIVE unset/false (DEFAULT) -> DRY-RUN: the email is composed and
#     LOGGED (recipient, subject, links) and actually SENT only when the recipient
#     is on FILMO_EMAIL_ALLOWLIST (default: exactly denniswanglabs@gmail.com).
#   * FILMO_EMAIL_LIVE truthy -> sends to every run owner.
# NO BACKFILL: fires only inside ship_final, i.e. on deliveries that happen AFTER
# this ships; already-delivered runs are never revisited. The owner is looked up
# worker-side from the run's user_id — never CC, never another user's data.
_EMAIL_ALLOWLIST_DEFAULT = "denniswanglabs@gmail.com"
_AGENTMAIL_INBOX = os.environ.get("AGENTMAIL_INBOX", "filmo@agentmail.to")


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _email_allowlist() -> set:
    raw = os.environ.get("FILMO_EMAIL_ALLOWLIST", _EMAIL_ALLOWLIST_DEFAULT)
    return {a.strip().lower() for a in raw.split(",") if a.strip()}


def _looks_like_email(addr) -> bool:
    return bool(addr) and isinstance(addr, str) and bool(
        re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", addr.strip()))


def _lookup_owner_email(user_id):
    """Resolve the run owner's email from user_id via the InsForge admin auth
    API (GET /api/auth/users/<uid> -> {email, ...}; VERIFIED read-only path).
    Returns a trimmed address or None. Never raises."""
    if not (user_id and _IF_BASE and _IF_KEY):
        return None
    try:
        resp = _if_req("GET",
                       f"/api/auth/users/{urllib.parse.quote(str(user_id), safe='')}",
                       None, "application/json")
        j = json.loads(resp.read())
        email = j.get("email") if isinstance(j, dict) else None
        return email.strip() if isinstance(email, str) and email.strip() else None
    except Exception as e:
        print(f"[notify] owner-email lookup failed for {user_id}: {e}",
              file=sys.stderr)
        return None


def _clean_brand(brand) -> str:
    """A human subject fragment from runs.brand (which may be a bare domain)."""
    b = (brand or "").strip()
    b = re.sub(r"^https?://", "", b, flags=re.I).rstrip("/")
    b = re.sub(r"^www\.", "", b, flags=re.I)
    return b or "your brand"


def _compose_ready_email(run_id, brand, final_url):
    """Compose the (subject, text, html, watch_url, download_url) for a ready
    film. No emoji, no operator internals — a plain, branded, deliverable note
    with a WATCH link (run page) and a DOWNLOAD link."""
    base = (os.environ.get("FILMO_SITE_BASE")
            or os.environ.get("FILMO_PUBLIC_BASE")
            or "https://filmo.dev").rstrip("/")
    rid = urllib.parse.quote(str(run_id), safe="")
    watch = f"{base}/runs/{rid}"
    download = f"{base}/api/runs/{rid}/download"
    subject = f"Your Filmo for {brand} is ready"
    text = "\n".join([
        f"Your Filmo for {brand} is ready.",
        "",
        "We've finished producing your launch video. You can watch it, "
        "fine-tune it in the editor, or download the final cut.",
        "",
        f"Watch: {watch}",
        f"Download: {download}",
        "",
        "— Filmo",
    ])
    html = (
        '<!doctype html><html><body style="margin:0;padding:0;background:#f6f7f9;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f6f7f9;padding:32px 0;font-family:-apple-system,'
        "BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;\">"
        '<tr><td align="center">'
        '<table role="presentation" width="480" cellpadding="0" cellspacing="0" '
        'style="max-width:480px;width:100%;background:#ffffff;border:1px solid '
        '#eceef1;border-radius:16px;overflow:hidden;">'
        '<tr><td style="padding:32px 36px 0;">'
        '<div style="font-size:20px;font-weight:700;letter-spacing:-0.01em;'
        'color:#0b0f1a;">Filmo</div></td></tr>'
        '<tr><td style="padding:20px 36px 0;">'
        '<div style="font-size:22px;line-height:1.3;font-weight:700;'
        f'letter-spacing:-0.01em;color:#0b0f1a;">Your Filmo for {brand} is ready</div>'
        '<p style="margin:12px 0 0;font-size:15px;line-height:1.55;color:#475067;">'
        "We&rsquo;ve finished producing your launch video. Watch it, fine-tune it "
        'in the editor, or download the final cut.</p></td></tr>'
        '<tr><td style="padding:24px 36px 4px;">'
        f'<a href="{watch}" style="display:inline-block;background:#3B82F6;'
        'color:#ffffff;text-decoration:none;font-size:15px;font-weight:600;'
        'padding:12px 22px;border-radius:10px;">Watch your video</a></td></tr>'
        '<tr><td style="padding:12px 36px 4px;">'
        f'<a href="{download}" style="font-size:14px;color:#3B82F6;'
        'text-decoration:none;font-weight:600;">Download the final cut</a></td></tr>'
        '<tr><td style="padding:14px 36px 32px;">'
        '<p style="margin:0;font-size:12px;line-height:1.5;color:#8a93a6;">'
        "Or paste this link into your browser:<br>"
        f'<a href="{watch}" style="color:#3B82F6;text-decoration:none;'
        f'word-break:break-all;">{watch}</a></p></td></tr></table>'
        '<div style="font-size:11px;color:#aab2c0;padding:18px 0 0;">'
        "Filmo &mdash; AI launch videos</div></td></tr></table></body></html>"
    )
    return subject, text, html, watch, download


def _agentmail_send(to_email, subject, text, html):
    """POST one message via AgentMail. Returns (ok, message_id_or_error).
    Never raises. Reads AGENTMAIL_API_KEY from env (worker/Railway); the key is
    used, never logged."""
    key = os.environ.get("AGENTMAIL_API_KEY", "")
    if not key:
        return False, "AGENTMAIL_API_KEY not set"
    endpoint = ("https://api.agentmail.to/v0/inboxes/"
                f"{urllib.parse.quote(_AGENTMAIL_INBOX, safe='')}/messages/send")
    body = json.dumps({"to": [to_email], "subject": subject,
                       "text": text, "html": html}).encode()
    try:
        req = urllib.request.Request(
            endpoint, data=body, method="POST",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        raw = resp.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {}
        mid = (parsed.get("message_id") or parsed.get("id")
               or "(200, no message_id)")
        return True, str(mid)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        return False, f"HTTP {e.code} {detail}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _mark_notified(run_id) -> None:
    """Stamp runs.notified_at, but only when still null (the filter makes a race
    set it once). Best-effort; never raises."""
    try:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _if_req("PATCH",
                f"/api/database/records/runs?id=eq."
                f"{urllib.parse.quote(str(run_id), safe='')}&notified_at=is.null",
                json.dumps({"notified_at": now}).encode(),
                "application/json")
    except Exception as e:
        print(f"[notify] mark notified_at failed for {run_id}: {e}",
              file=sys.stderr)


def notify_video_ready(run_dir: str, run_key: str, final_url: str) -> None:
    """Email the run OWNER once, on first delivery, that their film is ready.
    Idempotent via runs.notified_at (re-renders skip). Dry-run/allowlist gated.
    NEVER raises, NEVER blocks the delivery."""
    try:
        rid = _hosted_run_id(run_dir)
        if not (rid and _IF_BASE and _IF_KEY):
            return
        # Read the marker + owner + brand in one shot.
        try:
            resp = _if_req(
                "GET",
                f"/api/database/records/runs?id=eq.{rid}"
                "&select=notified_at,user_id,brand", None, "application/json")
            rows = json.loads(resp.read())
        except Exception as e:
            print(f"[notify] run {rid}: read failed ({e}); skipping ready-email",
                  file=sys.stderr)
            return
        if not rows:
            return
        row = rows[0]
        if row.get("notified_at"):
            # Re-render (director) or a prior send: the durable marker is set.
            print(f"[notify] run {rid}: already notified at "
                  f"{row.get('notified_at')}; re-render sends no email")
            return
        brand = _clean_brand(row.get("brand"))
        email = _lookup_owner_email(row.get("user_id"))
        subject, text, html, watch, download = _compose_ready_email(
            rid, brand, final_url)
        live = _env_truthy("FILMO_EMAIL_LIVE")
        if not _looks_like_email(email):
            # No deliverable owner email (or a transient lookup failure): compose
            # + log only, and do NOT mark, so a later delivery can still notify.
            print(f"[notify] run {rid}: no deliverable owner email; composed "
                  f"only [live={live}] subject={subject!r}", file=sys.stderr)
            return
        allow = email.strip().lower() in _email_allowlist()
        if live or allow:
            ok, info = _agentmail_send(email, subject, text, html)
            if ok:
                _mark_notified(rid)
                gate = "live" if live else "allowlist"
                print(f"[notify] ready-email SENT run {rid} brand={brand} -> "
                      f"{email} [gate={gate}, message_id={info}] watch={watch}")
            else:
                # Attempted but failed: do NOT mark, so the next delivery retries.
                print(f"[notify] ready-email SEND FAILED run {rid} -> {email}: "
                      f"{info} (not marked; retriable)", file=sys.stderr)
        else:
            # DRY-RUN for a non-allowlisted recipient: compose + log, do NOT send.
            # MARK it handled so the flag flipping to live never backfills this run.
            _mark_notified(rid)
            print(f"[notify][DRY-RUN] run {rid} brand={brand} WOULD email "
                  f"{email} (set FILMO_EMAIL_LIVE=1 to send). subject={subject!r} "
                  f"watch={watch} download={download}")
    except Exception as e:
        print(f"[notify] ready-email errored run {run_key}: "
              f"{type(e).__name__}: {e}", file=sys.stderr)


def _upload_artifact(run_id: str, seq: int, path: str) -> str:
    ext = os.path.splitext(path)[1] or ".bin"
    return upload_object(f"agent/{run_id}/{seq}{ext}", path)


_SINK_THREADS: list = []
_SEQ_OFFSET: dict = {}
_SEQ_LOCK = threading.Lock()


def _seq_offset(rid: str, first_local_seq: int) -> int:
    """RETRY CONTRACT: a re-run of the same hosted run starts its local seq
    at 0 on a fresh disk, colliding with rows the previous attempt already
    inserted (UNIQUE(run_id, seq) -> every event 409s). On the first sink
    call of this process, read the DB's max seq and offset all rows past it."""
    with _SEQ_LOCK:
        if rid in _SEQ_OFFSET:
            return _SEQ_OFFSET[rid]
        off = 0
        try:
            resp = _if_req(
                "GET",
                f"/api/database/records/agent_events?run_id=eq.{rid}"
                "&select=seq&order=seq.desc&limit=1", None, "application/json")
            rows = json.loads(resp.read())
            if rows:
                off = max(0, int(rows[0]["seq"]) + 1 - first_local_seq)
        except Exception:
            off = 0
        _SEQ_OFFSET[rid] = off
        return off


def flush_sinks(timeout: float = 120.0) -> None:
    """Join pending sink threads. The bus contract's exit clause: daemon
    threads die with the process, so a run's TAIL events (terminal events,
    the film artifact) were lost when the pipeline exited right after its
    last emit. Callers that end a run MUST flush."""
    deadline = time.time() + timeout
    for t in list(_SINK_THREADS):
        t.join(max(0.0, deadline - time.time()))
    _SINK_THREADS.clear()


def _hosted_sink(run_dir: str, evt: dict, artifact_path: str) -> None:
    rid = _hosted_run_id(run_dir)
    if not (rid and _IF_BASE and _IF_KEY):
        return

    def work():
        # ROW FIRST, PIXELS AFTER: the text event must reach the UI in
        # seconds; artifact uploads (cross-region, uplink shared with the
        # live-frame stream) can take a minute — serializing insert behind
        # upload made the whole thread lag minutes behind the live canvas.
        # The artifact attaches to the already-visible row via PATCH.
        try:
            seq = evt["seq"] + _seq_offset(rid, evt["seq"])
            row = {"run_id": rid, "seq": seq, "ts": evt["ts"],
                   "kind": evt["kind"], "title": evt["title"],
                   "detail": evt["detail"], "artifact_url": ""}
            _if_req_retry("POST", "/api/database/records/agent_events",
                          json.dumps([row]).encode(), "application/json")
        except Exception as e:
            print(f"[sink!] insert {evt['kind']} seq {row['seq']}: {e}",
                  file=sys.stderr)
            return
        if not (artifact_path and os.path.exists(artifact_path)):
            return
        try:
            url = _upload_artifact(rid, seq, artifact_path)
            if url:
                _if_req_retry("PATCH",
                              "/api/database/records/agent_events"
                              f"?run_id=eq.{rid}&seq=eq.{seq}",
                              json.dumps({"artifact_url": url}).encode(),
                              "application/json")
        except Exception as e:
            print(f"[sink!] artifact {evt['kind']} seq {seq}: {e}",
                  file=sys.stderr)
    t = threading.Thread(target=work, daemon=True)
    _SINK_THREADS.append(t)
    t.start()


def _events_path(run_dir: str) -> str:
    return os.path.join(run_dir, "events.jsonl")


def emit(run_dir: str, kind: str, title: str, detail: str = "",
         artifact: str = "") -> None:
    """Append one event and mirror it to stderr. Best-effort, never raises."""
    try:
        os.makedirs(run_dir, exist_ok=True)
        path = _events_path(run_dir)
        seq = 0
        if os.path.exists(path):
            with open(path, "rb") as f:
                seq = sum(1 for _ in f)
        if artifact:
            # Store repo-relative so the viewer server can serve it.
            ap = os.path.abspath(artifact)
            if ap.startswith(HERE):
                artifact = os.path.relpath(ap, HERE)
        evt = {"seq": seq, "ts": round(time.time(), 3), "kind": kind,
               "title": title, "detail": detail, "artifact": artifact}
        with open(path, "a") as f:
            f.write(json.dumps(evt, ensure_ascii=False) + "\n")
        print(f"[{kind}] {title}" + (f" — {detail}" if detail else ""),
              file=sys.stderr)
        _hosted_sink(run_dir, evt,
                     os.path.join(HERE, artifact) if artifact else "")
    except Exception:
        pass


def read_events(run_dir: str, after: int = -1):
    """Events with seq > after. Never raises."""
    try:
        out = []
        with open(_events_path(run_dir)) as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if e.get("seq", -1) > after:
                        out.append(e)
                except Exception:
                    continue
        return out
    except Exception:
        return []
