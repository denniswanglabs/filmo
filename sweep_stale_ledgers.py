#!/usr/bin/env python3
"""One-off SAFE sweep of orphaned-"running" ledgers (stale-fix).

Scans runs/*/ledger.json. A run is an orphaned corpse if status=="running" AND its
liveness (freshest mtime of build.log / ledger.json) is older than FRESHNESS_SECS
(same window the dashboard's _api_active guard uses). For each corpse:
  * back up the ledger to ledger.json.pre-stalefix.bak (never overwrites an existing bak)
  * flip status to a TERMINAL value, preserving every OTHER field:
      - final.mp4 exists AND ledger carries a usable stitch block -> "delivered"
      - otherwise -> "failed" + failure_reason (auto-swept)
Deletes NOTHING. Prints exactly which runs changed and to what.
"""
import json
import os
import time

FRESHNESS_SECS = 180
ROOT = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR = os.path.join(ROOT, "runs")
REASON = "abandoned — build process died before finalizing (auto-swept)"


def liveness_mtime(run_dir):
    newest = 0.0
    for fname in ("build.log", "ledger.json"):
        fp = os.path.join(run_dir, fname)
        try:
            newest = max(newest, os.path.getmtime(fp))
        except OSError:
            continue
    return newest


def main():
    now = time.time()
    changed = []
    try:
        names = sorted(os.listdir(RUNS_DIR))
    except OSError:
        names = []
    for name in names:
        run_dir = os.path.join(RUNS_DIR, name)
        ledger_path = os.path.join(run_dir, "ledger.json")
        if not os.path.isfile(ledger_path):
            continue
        try:
            with open(ledger_path) as fh:
                d = json.load(fh)
        except (OSError, ValueError) as e:
            print("  SKIP %s (unreadable ledger: %s)" % (name, e))
            continue
        if d.get("status") != "running":
            continue
        age = now - liveness_mtime(run_dir)
        if age <= FRESHNESS_SECS:
            print("  LIVE %s (age %.0fs <= %ds) — left untouched" % (name, age, FRESHNESS_SECS))
            continue

        has_final = os.path.isfile(os.path.join(run_dir, "final.mp4"))
        has_stitch = bool(d.get("stitch"))
        if has_final and has_stitch:
            new_status = "delivered"
        else:
            new_status = "failed"

        # Back up before any write; never clobber an existing backup.
        bak = ledger_path + ".pre-stalefix.bak"
        if not os.path.exists(bak):
            with open(bak, "w") as bf:
                json.dump(d, bf, indent=2)

        old_status = d.get("status")
        d["status"] = new_status
        if new_status == "failed":
            d["failure_reason"] = REASON
        with open(ledger_path, "w") as fh:
            json.dump(d, fh, indent=2)

        changed.append((name, old_status, new_status, has_final, has_stitch, age))
        print("  SWEPT %s: %s -> %s (final.mp4=%s stitch=%s age=%.0fs)"
              % (name, old_status, new_status, has_final, has_stitch, age))

    print("\nSwept %d run(s)." % len(changed))


if __name__ == "__main__":
    main()
