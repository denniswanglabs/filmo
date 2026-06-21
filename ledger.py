#!/usr/bin/env python3
"""Run ledger for the producer-brain orchestrator.

The ledger is the single source of truth for a production run: the priced plan,
the earn/payment state, every per-scene gate VERDICT (approve / downgrade /
decline), the actual spend, the P&L, and a timeline of events. Both the test
assertions and the dashboard read this JSON. Schema is documented in LEDGER.md.

Stdlib only. No timestamps from the wall clock are required for correctness; an
optional monotonic counter orders events so the dashboard can render a timeline
even though the orchestrator may pass a fixed `now` for reproducible runs.
"""

import json
import os


class Ledger:
    def __init__(self, run_id, job, mode, now=None):
        self.run_id = run_id
        self._seq = 0
        self.data = {
            "run_id": run_id,
            "schema_version": 1,
            "mode": mode,                      # "mock" | "real"
            "created_at": now,                 # ISO string or None (set by caller)
            "job": job,
            "status": "running",               # running | delivered | failed
            "phase": "init",                   # init|planning|pricing|earning|producing|voiceover|stitching|delivered
            "pricing": None,                   # filled by set_pricing()
            "earn": None,                      # filled by set_earn()
            "card": None,                      # filled by set_card()
            "scenes": [],                      # per-scene production records
            "voiceover": None,                 # VO production record
            "stitch": None,                    # final assembly record
            "pnl": None,                       # profit & loss summary
            "events": [],                      # ordered timeline
        }

    # -- timeline -----------------------------------------------------------
    def event(self, level, msg, **extra):
        """Append a timeline event. level: info | gate | spend | decline | money | error."""
        self._seq += 1
        ev = {"seq": self._seq, "level": level, "msg": msg}
        if extra:
            ev.update(extra)
        self.data["events"].append(ev)
        return ev

    # -- structured sections ------------------------------------------------
    def set_pricing(self, pricing):
        self.data["pricing"] = pricing

    def set_earn(self, earn):
        self.data["earn"] = earn

    def set_card(self, card):
        self.data["card"] = card

    def add_scene(self, record):
        self.data["scenes"].append(record)

    def upsert_scene(self, record):
        """Replace the scene record with the same id, else append. Lets the live
        console pre-list scenes as 'queued' then fill each in as it is produced."""
        for i, s in enumerate(self.data["scenes"]):
            if s.get("id") == record.get("id"):
                self.data["scenes"][i] = record
                return
        self.data["scenes"].append(record)

    def set_phase(self, phase):
        self.data["phase"] = phase

    def set_voiceover(self, record):
        self.data["voiceover"] = record

    def set_stitch(self, record):
        self.data["stitch"] = record

    def set_pnl(self, pnl):
        self.data["pnl"] = pnl

    def set_status(self, status):
        self.data["status"] = status

    # -- persistence --------------------------------------------------------
    def to_dict(self):
        return self.data

    def write(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, path)  # atomic: a concurrent poller never sees a torn file
        return path

    @classmethod
    def load(cls, path):
        """Reconstruct a Ledger from an existing ledger.json on disk.

        Preserves every block already written (earn/pricing/plan/scenes/pnl/…) and
        restores the event sequence counter so a subsequent event() continues the
        timeline instead of colliding with existing seq numbers. Used by the build
        runner to flip a run to 'failed' WITHOUT wiping the paid record (a
        post-payment failure must keep its earn/pricing/plan/scenes). Raises OSError
        if the file is missing, ValueError if it is unreadable/torn.
        """
        with open(path) as f:
            data = json.load(f)
        led = cls(data.get("run_id"), data.get("job"), data.get("mode"),
                  now=data.get("created_at"))
        # Stored values win; any keys new to the current schema keep their defaults.
        merged = led.data
        merged.update(data)
        led.data = merged
        led._seq = max((e.get("seq", 0) for e in data.get("events", [])), default=0)
        return led


def compute_pnl(price_cents, scenes, voiceover):
    """Build the P&L summary block from the produced scene + VO records.

    cogs_spent_cents = sum of actual spend across produced scenes + VO.
    overage_avoided_cents = sum of what declined scenes WOULD have cost (the
        money the budget gate saved). This is the headline of the money-shot.
    margin = (price - cogs_spent) / price  (None if price is 0/None).
    """
    cogs = 0
    overage_avoided = 0
    declines = []
    cost_lines = []

    rows = list(scenes)
    if voiceover:
        rows = rows + [voiceover]

    for r in rows:
        spent = int(r.get("spent_cents") or 0)
        cogs += spent
        if r.get("decision") == "decline":
            would = int(r.get("would_have_cost_cents") or 0)
            overage_avoided += would
            declines.append({"id": r.get("id"), "would_have_cost_cents": would})
        cost_lines.append({
            "id": r.get("id"),
            "type": r.get("type"),
            "decision": r.get("decision"),
            "spent_cents": spent,
        })

    margin = None
    if price_cents:
        margin = round((price_cents - cogs) / price_cents, 4)

    return {
        "price_cents": price_cents,
        "cogs_spent_cents": cogs,
        "overage_avoided_cents": overage_avoided,
        "gross_profit_cents": (price_cents - cogs) if price_cents is not None else None,
        "margin": margin,
        "declines": declines,
        "cost_lines": cost_lines,
    }
