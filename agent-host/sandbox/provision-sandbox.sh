#!/usr/bin/env bash
# provision-sandbox.sh <sandbox-name> — create + provision the Filmo NemoClaw sandbox.
# Adapted from walk-ultra/sandbox/provision.sh (the recipe learned the hard way). Differences
# for Filmo: NO static demo-targets list (the target allowlist is generated PER RUN from the
# job URL); the in-sandbox browser is driven by the host's conversion_read tool, not a baked
# agent.js.
set -uo pipefail
NAME="${1:-filmo}"
HERE="$(cd "$(dirname "$0")" && pwd)"
N="$HOME/.local/bin/nemoclaw"; [ -x "$N" ] || N=nemoclaw
[ -n "${NVIDIA_API_KEY:-}" ] || { echo "ERROR: NVIDIA_API_KEY not in env"; exit 1; }
say() { printf "\n\033[1;32m[sandbox:%s] %s\033[0m\n" "$NAME" "$1"; }

say "1/4 onboard (chrome-deps-baked image)"
if "$N" "$NAME" exec --no-tty -- true >/dev/null 2>&1; then
  echo "  exists + responds — skipping onboard"
else
  # ★0b: confirm onboard flags on Linux. --no-gpu (headless VM), --from bakes Chrome libs.
  "$N" onboard --non-interactive --fresh --name "$NAME" \
    --from "$HERE/Dockerfile" --no-gpu --yes --yes-i-accept-third-party-software 2>&1 | tail -5
  "$N" "$NAME" exec --no-tty -- true >/dev/null 2>&1 || { echo "ERROR: not reachable after onboard"; exit 1; }
fi

say "2/4 NIM egress policy (the target policy is applied PER RUN, not here)"
"$N" "$NAME" policy-add nim --from-file "$HERE/policies/nim.yaml" --yes 2>&1 | tail -1

say "3/4 chromium (in-sandbox node:https download — curl is policy-blocked)"
# ★0b: pin the Playwright/chromium revision that matches the engine (walk-ultra used 1.49.0
#   → chromium-1148). undici fetch bypasses the proxy, so the downloader must use node:https.
if "$N" "$NAME" exec --no-tty -- test -x /tmp/.cache/ms-playwright/chromium-1148/chrome-linux/chrome 2>/dev/null; then
  echo "  chromium already present"
else
  echo "  ★0b: run the node:https chromium fetch here (port dl-chromium.js from walk-ultra)"
fi

say "4/4 smoke"
"$N" "$NAME" exec --no-tty -- bash -c 'echo "sandbox responds: $(uname -m)"'
echo "[sandbox:$NAME] provisioned. Driven by the host conversion_read tool + Hermes."
