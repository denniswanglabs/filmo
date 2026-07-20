"""Film workspace persistence — a re-cut survives a redeploy.

THE CLASS THIS KILLS (Dennis 2026-07-20, live): a delivered walkrec film's
working files (stops.json, the kept clips, the staged logo/music) live only on
the ONE Railway replica's ephemeral disk that built it. A deploy — three a day —
wipes every container disk, so a later director edit finds no local files and
the edit is impossible. The old code papered over this with a replica-affinity
bounce (hope the sibling still holds them); a deploy beats that every time.

THE FIX: persist a MANIFEST of exactly what a re-cut needs to storage on
delivery, re-persist after every edit, and rehydrate on demand. Any replica,
after any deploy, can pull the manifest and re-cut the film.

WHAT A RE-CUT NEEDS (read from the render code, not guessed):
  - runs/<key>/stops.json       the cut state {stops, ctx}; the re-cut's input
  - runs/<key>/<seg>            every kept clip a stop's `seg` references
                                (e.g. shot-1-60.mp4 — the 60fps-smoothed take,
                                NOT the raw shot-1.mp4 the plan discarded)
  - studio/public/<logo_rel>   the staged brand mark (ctx.logo_rel); the re-cut
                                path (_plan_beats) reads it by name, never
                                re-stages it
  - studio/public/<music>      the staged track (ctx.theme.music); same
  - runs/<key>/chat.jsonl      conversation continuity, when present

DELIBERATELY NOT PERSISTED (derivable or transient): page captures /
screenshots-read (read-pass scratch), events.jsonl (seq continuity comes from
_seq_offset reading the DB), the rendered film-tour.mp4 / final.mp4 (final.mp4
already ships to runs.final_url), and the per-scene public copies
walkrec-<id>-shotN.mp4 (_plan_beats re-derives them from the seg sources).

STORAGE LAYOUT: flat prefix per run in the walk-videos bucket —
  workspace/<run_key>/workspace.json   the manifest (the TRUTH of "latest")
  workspace/<run_key>/<name>           each persisted file
Overwrite in place; the manifest's `revision` counter is for debuggability.

Never raises out of persist()/rehydrate(): a storage blip must never break a
delivered film, and a missing manifest is the HONEST fallback (films delivered
before this shipped), not a crash.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from run_events import upload_object  # the strategy-flow upload (no gateway cap)

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = 1
_WARN_BYTES = 200 * 1024 * 1024  # log loudly past ~200MB; never a silent cap


def _base() -> str:
    return (os.environ.get("INSFORGE_BASE_URL")
            or os.environ.get("INSFORGE_URL", "")).rstrip("/")


def _key() -> str:
    return os.environ.get("INSFORGE_API_KEY", "")


def _bucket() -> str:
    return os.environ.get("INSFORGE_BUCKET", "walk-videos")


def _log(msg: str) -> None:
    print(f"[workspace] {msg}", file=sys.stderr)


def _prefix(run_key: str) -> str:
    return f"workspace/{run_key}"


def _manifest_key(run_key: str) -> str:
    return f"{_prefix(run_key)}/workspace.json"


def _pub() -> str:
    return os.path.join(HERE, "studio", "public")


def _mb(n: int) -> str:
    return f"{n / 1_048_576:.1f}MB"


# ── storage GET (bytes) — mirror of the claimer's downloadRunAssets, in python.
# upload_object owns the write half; this is the read half the director needs.
def _object_url(run_key: str, name: str) -> str:
    key = f"{_prefix(run_key)}/{name}"
    return (f"{_base()}/api/storage/buckets/{_bucket()}/objects/"
            f"{urllib.parse.quote(key, safe='')}")


def _get_bytes(url: str, attempts: int = 3) -> bytes:
    """GET an object's bytes (follows the CDN redirect). Bounded retries for the
    same InsForge brownout _if_req_retry guards against; 404 never retries."""
    delay = 3.0
    for i in range(attempts):
        try:
            req = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {_key()}"})
            return urllib.request.urlopen(req, timeout=120).read()
        except urllib.error.HTTPError as e:
            if e.code == 404 or i == attempts - 1:
                raise
        except Exception:
            if i == attempts - 1:
                raise
        time.sleep(delay)
        delay *= 2
    raise RuntimeError("unreachable")


def _read_manifest(run_key: str) -> dict | None:
    """The persisted manifest, or None when absent (a pre-persist film) or
    unreadable. Never raises."""
    try:
        body = _get_bytes(_object_url(run_key, "workspace.json"))
        obj = json.loads(body)
        return obj if isinstance(obj, dict) else None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        _log(f"manifest read failed ({e.code})")
        return None
    except Exception as e:
        _log(f"manifest read failed: {type(e).__name__}")
        return None


def _collect(run_dir: str, run_key: str):
    """The manifest's file list, read from stops.json (the render's own truth).
    Returns (entries, ok) where each entry is {name, path, dest, role, bytes};
    ok is False when there is nothing to persist (no stops.json)."""
    stops_path = os.path.join(run_dir, "stops.json")
    if not os.path.exists(stops_path):
        return [], False
    try:
        state = json.load(open(stops_path))
    except Exception as e:
        _log(f"stops.json unreadable, skipping persist: {type(e).__name__}")
        return [], False
    stops = state.get("stops") or []
    ctx = state.get("ctx") or {}

    entries = [{"name": "stops.json", "path": stops_path, "dest": "run",
                "role": "essential"}]
    # Every kept clip a stop references — by its ACTUAL seg path (the smoothed
    # take carries a -60 suffix), with a basename fallback for a rehydrated dir.
    seen = set()
    for s in stops:
        seg = s.get("seg")
        if not seg:
            continue
        p = seg if os.path.exists(seg) else os.path.join(
            run_dir, os.path.basename(seg))
        name = os.path.basename(p)
        if os.path.exists(p) and name not in seen:
            seen.add(name)
            entries.append({"name": name, "path": p, "dest": "run",
                            "role": "essential"})
    # Staged assets the re-cut reads by name and never re-stages.
    logo_rel = ctx.get("logo_rel")
    if logo_rel:
        lp = os.path.join(_pub(), logo_rel)
        if os.path.exists(lp):
            entries.append({"name": logo_rel, "path": lp, "dest": "public",
                            "role": "asset"})
    music = (ctx.get("theme") or {}).get("music")
    if music:
        mp = os.path.join(_pub(), music)
        if os.path.exists(mp):
            entries.append({"name": music, "path": mp, "dest": "public",
                            "role": "asset"})
    chat = os.path.join(run_dir, "chat.jsonl")
    if os.path.exists(chat):
        entries.append({"name": "chat.jsonl", "path": chat, "dest": "run",
                        "role": "asset"})
    for e in entries:
        try:
            e["bytes"] = os.path.getsize(e["path"])
        except OSError:
            e["bytes"] = 0
    return entries, True


def persist(run_dir: str, run_key: str, reason: str = "build") -> dict | None:
    """Persist the run's workspace after delivery. Uploads only what CHANGED
    since the last manifest (clips are immutable; stops.json and the manifest
    always re-upload), so an edit's re-persist tail is a few KB. Returns the
    written manifest, or None when there is nothing/no storage to persist to.

    The manifest is written LAST — it is the commit point, so a partial upload
    never advertises a workspace that cannot be rehydrated. An essential upload
    failure leaves the PRIOR manifest intact (a stale-but-whole workspace beats
    a fresh-but-broken one)."""
    if not (_base() and _key()):
        return None
    entries, ok = _collect(run_dir, run_key)
    if not ok:
        return None

    prior = _read_manifest(run_key) or {}
    prior_bytes = {f["name"]: f.get("bytes") for f in (prior.get("files") or [])}
    revision = int(prior.get("revision") or 0) + 1

    total = sum(e["bytes"] for e in entries)
    _log(f"persist rev{revision} ({reason}) {run_key}: {len(entries)} files, "
         f"{_mb(total)}")
    if total > _WARN_BYTES:
        _log(f"WARNING workspace {_mb(total)} exceeds {_mb(_WARN_BYTES)} — "
             "persisting anyway (no silent cap)")

    t0 = time.time()
    files, essential_ok, uploaded, skipped = [], True, 0, 0
    for e in entries:
        key = f"{_prefix(run_key)}/{e['name']}"
        # stops.json always re-uploads (it changed); an immutable file already
        # in storage at the same size is skipped — it is still listed.
        unchanged = (e["name"] != "stops.json"
                     and prior_bytes.get(e["name"]) == e["bytes"])
        if unchanged:
            skipped += 1
        else:
            tu = time.time()
            url = upload_object(key, e["path"], overwrite=True)
            if not url:
                _log(f"upload FAILED {e['name']} ({e['role']}, {_mb(e['bytes'])})")
                if e["role"] == "essential":
                    essential_ok = False
                continue
            uploaded += 1
            _log(f"  up {e['name']} {_mb(e['bytes'])} {time.time() - tu:.1f}s")
        files.append({"key": key, "name": e["name"], "dest": e["dest"],
                      "role": e["role"], "bytes": e["bytes"]})

    if not essential_ok:
        _log("essential upload failed — leaving prior manifest intact "
             "(rehydrate stays honest)")
        return None

    manifest = {"schema": SCHEMA, "run_key": run_key, "revision": revision,
                "reason": reason, "created_ts": prior.get("created_ts") or t0,
                "updated_ts": round(time.time(), 3),
                "total_bytes": sum(f["bytes"] for f in files), "files": files}
    mpath = os.path.join(run_dir, "workspace.json")
    try:
        with open(mpath, "w") as f:
            json.dump(manifest, f, indent=2)
        if not upload_object(_manifest_key(run_key), mpath, overwrite=True):
            _log("manifest upload FAILED — workspace not committed")
            return None
    except Exception as e:
        _log(f"manifest write FAILED: {type(e).__name__}: {e}")
        return None
    _log(f"persist rev{revision} committed: {uploaded} uploaded, {skipped} "
         f"unchanged, {_mb(manifest['total_bytes'])} total, "
         f"{time.time() - t0:.1f}s")
    return manifest


def _dest_dir(run_dir: str, dest: str) -> str:
    return _pub() if dest == "public" else run_dir


def _normalize_segs(run_dir: str) -> None:
    """Point every stop's `seg` at the rehydrated file in THIS run_dir. The path
    was baked absolute at build time; if the builder ran under a different root
    (or on another machine), the bare abs path would miss the file we just
    pulled. Rewriting to run_dir/<basename> makes the re-cut robust to where it
    was built. Best-effort."""
    p = os.path.join(run_dir, "stops.json")
    try:
        state = json.load(open(p))
    except Exception:
        return
    changed = False
    for s in state.get("stops") or []:
        seg = s.get("seg")
        if not seg:
            continue
        local = os.path.join(os.path.abspath(run_dir), os.path.basename(seg))
        if seg != local and os.path.exists(local):
            s["seg"] = local
            changed = True
    if changed:
        try:
            with open(p, "w") as f:
                json.dump(state, f, indent=2, default=str)
        except Exception:
            pass


def rehydrate(run_dir: str, run_key: str) -> bool:
    """Pull the workspace from storage into runs/<key>/ and studio/public/.
    True when the essentials landed (a re-cut can proceed); False when the
    manifest is absent or an essential file could not be pulled — the caller's
    honest 'recycled by a redeploy' reply is the fallback."""
    if not (_base() and _key()):
        return False
    manifest = _read_manifest(run_key)
    if not manifest:
        _log(f"no manifest for {run_key} — cannot rehydrate (honest fallback)")
        return False
    files = manifest.get("files") or []
    total = manifest.get("total_bytes") or sum(f.get("bytes", 0) for f in files)
    _log(f"rehydrate rev{manifest.get('revision')} {run_key}: {len(files)} "
         f"files, {_mb(total)}")
    if total > _WARN_BYTES:
        _log(f"WARNING rehydrating {_mb(total)} (large workspace)")

    os.makedirs(run_dir, exist_ok=True)
    os.makedirs(_pub(), exist_ok=True)
    t0, got = time.time(), 0
    for f in files:
        name, role = f.get("name"), f.get("role", "asset")
        dest = os.path.join(_dest_dir(run_dir, f.get("dest", "run")), name)
        try:
            tf = time.time()
            body = _get_bytes(_object_url(run_key, name))
            with open(dest, "wb") as fh:
                fh.write(body)
            got += 1
            _log(f"  down {name} {_mb(len(body))} {time.time() - tf:.1f}s")
        except Exception as e:
            _log(f"download FAILED {name} ({role}): {type(e).__name__}")
            if role == "essential":
                _log("essential file missing — rehydrate failed (honest "
                     "fallback)")
                return False
    _normalize_segs(run_dir)
    _log(f"rehydrate rev{manifest.get('revision')} done: {got}/{len(files)} "
         f"files, {_mb(total)}, {time.time() - t0:.1f}s")
    return os.path.exists(os.path.join(run_dir, "stops.json"))


def has_local_workspace(run_dir: str) -> bool:
    return os.path.exists(os.path.join(run_dir, "stops.json"))
