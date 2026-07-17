#!/usr/bin/env bash
# Push the worker's runtime env to the linked Railway service without ever printing
# a secret. Values are sourced from the Hetzner key files (over ssh) and the local
# web/.env.local. Run AFTER `railway login` + `railway link`, from the repo root.
set -euo pipefail

VM=root@204.168.128.193
LOCAL_ENV="$(dirname "$0")/../web/.env.local"

get_local() { grep "^$1=" "$LOCAL_ENV" | head -1 | cut -d= -f2-; }
get_vm() { ssh -o BatchMode=yes "$VM" "grep '^$1=' $2 | head -1 | cut -d= -f2-"; }

INSFORGE_URL=$(get_local INSFORGE_URL)
INSFORGE_API_KEY=$(get_local INSFORGE_API_KEY)
OPENROUTER_API_KEY=$(get_vm OPENROUTER_API_KEY /root/.orkey)
ELEVENLABS_API_KEY=$(get_vm ELEVENLABS_API_KEY /root/.el-key)
AGENTMAIL_API_KEY=$(get_vm AGENTMAIL_API_KEY /root/.agentmail-key)
# NVIDIA key lives in the local shell rc on this Mac (memory: zshrc), fall back to VM.
NVIDIA_API_KEY=$(source ~/.zshrc >/dev/null 2>&1; printf '%s' "${NVIDIA_API_KEY:-}")

for v in INSFORGE_URL INSFORGE_API_KEY OPENROUTER_API_KEY ELEVENLABS_API_KEY AGENTMAIL_API_KEY; do
  [ -n "${!v}" ] || { echo "MISSING $v — aborting before touching Railway"; exit 1; }
done
[ -n "$NVIDIA_API_KEY" ] || echo "WARN: NVIDIA_API_KEY empty (super-free brain unavailable until set)"

railway variables \
  --set "INSFORGE_URL=$INSFORGE_URL" \
  --set "INSFORGE_API_KEY=$INSFORGE_API_KEY" \
  --set "OPENROUTER_API_KEY=$OPENROUTER_API_KEY" \
  --set "ELEVENLABS_API_KEY=$ELEVENLABS_API_KEY" \
  --set "AGENTMAIL_API_KEY=$AGENTMAIL_API_KEY" \
  --set "NVIDIA_API_KEY=$NVIDIA_API_KEY" \
  --set "FILMO_PUBLIC_BASE=https://filmo.dev" \
  --set "WALK_BUCKET=walk-videos" \
  --set "PAYMENTS_REQUIRED=true" \
  --set "PAYMENT_TIMEOUT_MS=900000" \
  --service walk-studio-hosted >/dev/null

echo "Railway env pushed (values not shown). Verify names with: railway variables --service walk-studio-hosted --kv | cut -d= -f1"
