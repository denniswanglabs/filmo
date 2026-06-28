#!/usr/bin/env bash
# provision-vm.sh — one-shot bootstrap for the Filmo Agent-Host VM (Hetzner Ampere ARM,
# Ubuntu 24.04). Installs Docker Engine + Node + NemoClaw + Hermes, then provisions the
# NemoClaw sandbox. Run as a sudo-capable user.
#
#   NVIDIA_API_KEY=... OPENROUTER_API_KEY=... bash provision-vm.sh
#
# ⚠ SPIKE MARKERS (★0b): steps tagged ★ were proven on Dennis's macOS + Docker Desktop;
# they need confirming on Linux/Docker-Engine/arm64. Do NOT assume — the 0b spike verifies
# each ★ on the real VM and we pin the exact commands here afterward.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SANDBOX="${SANDBOX:-filmo}"
say() { printf "\n\033[1;32m[provision-vm] %s\033[0m\n" "$1"; }
need() { command -v "$1" >/dev/null 2>&1; }

[ -n "${NVIDIA_API_KEY:-}" ] || { echo "ERROR: NVIDIA_API_KEY not set"; exit 1; }

say "1/6 system deps (Docker Engine, build tools, ffmpeg)"
if ! need docker; then
  curl -fsSL https://get.docker.com | sh                      # Docker ENGINE (not Desktop)
  sudo usermod -aG docker "$USER" || true                     # re-login or `newgrp docker`
fi
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends git curl ca-certificates ffmpeg python3 python3-venv python3-pip unzip

say "2/6 Node 22 (NemoClaw + Hermes + Remotion need it)"
if ! need node || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 22 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi

say "3/6 NemoClaw (★0b: verify the Linux install path + that privileged Docker works here)"
# ★ On macOS this is `curl https://www.nvidia.com/nemoclaw.sh | bash`. Confirm the Linux
#   installer + that NemoClaw can create a privileged sandbox container on this host
#   (Hetzner raw VM should allow it; Railway/Fargate do not — that's why we're on a VM).
if ! need nemoclaw; then
  curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash         # ★ verify on Linux
  export PATH="$HOME/.local/bin:$PATH"
fi
nemoclaw --version || { echo "ERROR: nemoclaw not installed"; exit 1; }

say "4/6 Hermes runtime (the orchestrator; brain = Nemotron Ultra)"
# ★ Install Hermes Agent on Linux + point it at Nemotron via OpenRouter (paid Ultra) or NIM.
#   Mirrors ~/.hermes/config.yaml on Dennis's Mac. Register the filmo-producer skill + the
#   walk-studio MCP server (see steps below).
if ! need hermes; then
  : # ★0b: pin the Linux Hermes install command here after the spike
fi
mkdir -p "$HOME/.hermes/skills"
cp -r "$HERE/skills/filmo-producer" "$HOME/.hermes/skills/" 2>/dev/null || true
# hermes mcp add walk-studio --command "python3 $HERE/mcp_studio_server.py"   # ★ after MCP lands

say "5/6 NemoClaw sandbox (chrome-baked image + policies + chromium)"
bash "$HERE/sandbox/provision-sandbox.sh" "$SANDBOX"

say "6/6 Filmo pipeline + claimer"
# The host runs the pipeline (Remotion render + ffmpeg) and the claimer that pulls jobs from
# InsForge and invokes Hermes. ★ The pipeline checkout is rsync'd/cloned here by deploy; the
# in-sandbox READ is driven via `nemoclaw $SANDBOX exec`.
echo "  (deploy step: sync the Filmo repo here, npm/pip install, start the claimer)"

echo
echo "[provision-vm] base bootstrap done. Next: Phase-0 spikes 0b (sandbox capture) + 0c"
echo "(Hermes drives the filmo-producer skill end to end) + 0d (Ultra latency in the loop)."
