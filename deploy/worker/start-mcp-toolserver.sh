#!/usr/bin/env bash
# Launch the Filmo HOST tool-server (M2 Phase A) detached on port 8770.
# Separate process/port from the live filmo-claimer — does NOT touch it.
# (/root/start-mcp-toolserver.sh on the VM; run by mcp-toolserver.service.)
set -a
[ -f /root/.orkey ] && . /root/.orkey            # OPENROUTER_API_KEY=<REDACTED>
[ -f /root/.el-key ] && . /root/.el-key          # ELEVENLABS_API_KEY=<REDACTED>
[ -f /root/.insforge-key ] && . /root/.insforge-key   # INSFORGE_API_KEY=<REDACTED>
set +a
export MCP_PORT="${MCP_PORT:-8770}"
export WS_PREMIUM_MENU=1
export ANALYZE_BRAIN="${ANALYZE_BRAIN:-ultra-paid}"
export INSFORGE_URL="${INSFORGE_URL:-https://jd3mdkqr.ap-southeast.insforge.app}"
export INSFORGE_UPLOADER=/root/filmo-worker/insforge_upload.mjs
export WORKER_DIR=/root/filmo-worker
# In-sandbox STILL capture (NemoClaw). Capture runs inside the `filmo` sandbox;
# RENDER STAYS ON HOST. Default-OFF (native); flip by writing CAPTURE_BACKEND
# into /root/.capture-backend (the `filmo fallback` revert empties that file).
# Any nemoclaw failure auto-falls-back to native per-job, so the pipeline never
# breaks. NEMOCLAW_SANDBOX MUST be `filmo` (the live registered sandbox).
[ -f /root/.capture-backend ] && . /root/.capture-backend
export CAPTURE_BACKEND="${CAPTURE_BACKEND:-native}"
export NEMOCLAW_SANDBOX="${NEMOCLAW_SANDBOX:-filmo}"
cd /root/filmo-pipeline
exec /root/filmo-venv/bin/python /root/filmo-pipeline/mcp_toolserver.py
