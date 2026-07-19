#!/usr/bin/env python3
"""Hosted director turn — spawned by the claimer for jobs.type='director'.

    python3 director_job.py --run-key <key> --run-id <uuid> --message <text>

Replies and applies through the event bus (chat.director / review.* /
run.done), which dual-sinks into agent_events so the web workspace narrates
the change live. Exit 0 = handled (including graceful declines), 1 = the
apply failed after the reply.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import director  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-key", required=True)
    ap.add_argument("--run-id", default="")
    ap.add_argument("--job-id", default="",
                    help="the claimer's job id — the idempotency key for the "
                         "edit's credit charge")
    ap.add_argument("--message", required=True)
    a = ap.parse_args()
    return director.handle_job(a.run_key, a.run_id, a.message, a.job_id)


if __name__ == "__main__":
    sys.exit(main())
