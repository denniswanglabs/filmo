#!/usr/bin/env bash
# Idempotent OpenShell/NemoClaw gateway prewarm for filmo-claimer (ExecStartPre).
# The hermes conduct (curated-claimer.js -> `nemoclaw filmo exec`) assumes a warm,
# LISTENING gateway. The gateway is a persistent host process, independent of this
# worker, so it survives worker restarts — but after a VM reboot or a gateway crash
# it is DOWN, and the first conduct cold-fails ("Connection refused") and falls back
# to the deterministic build_runner (producer=hetzner-curated). This warms it BEFORE
# the worker claims. No-op (no gateway bounce) when already listening, so a normal
# restart never disrupts a warm gateway or an in-flight conduct.
set -u
PORT=8080
if /usr/bin/ss -ltn 2>/dev/null | grep -q ":${PORT}"; then
  echo "prewarm: gateway already listening on :${PORT} (no-op)"
  exit 0
fi
echo "prewarm: gateway down — running 'nemoclaw filmo recover'"
/usr/bin/timeout 120 /usr/bin/nemoclaw filmo recover || \
  echo "prewarm: recover non-zero (worker still starts; conduct falls back to curated if needed)"
exit 0
