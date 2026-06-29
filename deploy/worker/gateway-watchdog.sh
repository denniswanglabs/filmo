#!/usr/bin/env bash
# Filmo gateway self-heal watchdog (Added 2026-06-29; hardened same day).
#
# WHY: the OpenShell/NemoClaw Docker-driver gateway on 127.0.0.1:8080 is the L7
# relay the hermes conduct (curated-claimer.js -> `nemoclaw filmo exec`) needs.
# It FLAPS during operation: a transient h2 relay error / health blip makes the
# recovery path send the running host gateway a SHUTDOWN signal, and its restart
# sub-step aborts on "Error: HOME is not set" -> the gateway is left DOWN. The
# boot-only ExecStartPre prewarm doesn't cover a mid-operation flap, so a conduct
# that hits the dead gateway cold-fails into the deterministic build_runner
# (producer=hetzner-curated) instead of hetzner-hermes.
#
# WHAT: poll :8080 LISTEN; only act when it is confirmed DOWN. Recovery = the
# FULL `nemoclaw filmo connect` path (re-establishes the host gateway + relay),
# NOT `recover`/`--probe-only` -- probe-only TEARS the host gateway DOWN when the
# in-sandbox probe fails (it does not relaunch anything), which can churn. HOME +
# XDG set so recovery does not itself abort on "HOME is not set".
#
# SAFETY (do not make the flap worse):
#   * flock: only ONE recovery runs at a time; never stack recoveries.
#   * debounce + settle: require :8080 DOWN twice and respect a post-recovery
#     settle window, so a single mid-conduct blip never triggers a destructive
#     restart that would kill an in-flight conduct.
#   * NO-OP when up -> never disrupts a warm gateway or an in-flight conduct.
#
# Driven by gateway-watchdog.timer (~every 12s). Revert: `systemctl disable --now
# gateway-watchdog.timer` then rm the two unit files + this script.
set -u
export HOME=/root
export XDG_CONFIG_HOME=/root/.config
export XDG_STATE_HOME=/root/.local/state
export XDG_DATA_HOME=/root/.local/share
export XDG_CACHE_HOME=/root/.cache

PORT=8080
LOCK=/run/filmo-gateway-watchdog.lock
SETTLE_STAMP=/run/filmo-gateway-watchdog.settle

is_up() { /usr/bin/ss -ltn 2>/dev/null | grep -q ":${PORT}"; }

# Fast path: gateway up -> nothing to do.
is_up && exit 0

# Post-recovery settle: if a recovery finished < 90s ago, give the stack time to
# bind before judging it down again (a recovery takes ~10-20s to relisten).
if [ -f "$SETTLE_STAMP" ]; then
  now=$(date +%s)
  then_ts=$(stat -c %Y "$SETTLE_STAMP" 2>/dev/null || echo 0)
  age=$(( now - then_ts ))
  if [ "$age" -lt 90 ]; then
    echo "watchdog: in settle window (${age}s) -- skip"
    exit 0
  fi
fi

# Debounce: confirm DOWN with a second look 3s later (ignore a momentary blip).
sleep 3
is_up && exit 0

# Single-flight: take the lock; if a recovery is already running, bail.
exec 9>"$LOCK"
if ! /usr/bin/flock -n 9; then
  echo "watchdog: recovery already in progress -- skip"
  exit 0
fi

echo "watchdog: gateway confirmed DOWN on :${PORT} -- running full 'nemoclaw filmo connect' recovery"
# Full connect re-establishes the host gateway + relay. Pipe an immediate exit so
# the interactive SSH session opened by connect closes right after recovery.
printf 'exit\n' | /usr/bin/timeout 180 /usr/bin/nemoclaw filmo connect >/tmp/filmo-watchdog-connect.out 2>&1
rc=$?
date +%s > "$SETTLE_STAMP" 2>/dev/null || true
if is_up; then
  echo "watchdog: recovery OK -- :${PORT} listening again (connect rc=${rc})"
else
  tail3=$(tail -3 /tmp/filmo-watchdog-connect.out 2>/dev/null | tr '\n' '|')
  echo "watchdog: connect rc=${rc}; :${PORT} not yet up -- will retry next tick (tail: ${tail3})"
fi
exit 0
