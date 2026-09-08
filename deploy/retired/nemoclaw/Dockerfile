# Filmo NemoClaw sandbox image (/root/filmo-sandbox/Dockerfile on the VM).
# Built from the NVIDIA NemoClaw sandbox base; adds a venv with the Hermes CLI so
# `hermes chat -s filmo-producer` runs INSIDE the sandbox as the unprivileged
# `sandbox` user (uid 998). The agent only conducts the 5 filmo-host MCP tools;
# the heavy/trusted work (Nemotron read+plan, capture, Remotion render) stays on
# the host tool-server (:8770).
FROM ghcr.io/nvidia/nemoclaw/sandbox-base:v0.0.50
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-pip && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /sandbox/hermes-venv \
 && /sandbox/hermes-venv/bin/pip install --no-cache-dir --upgrade pip \
 && /sandbox/hermes-venv/bin/pip install --no-cache-dir 'hermes-agent[cli]' \
 && chown -R 998:998 /sandbox/hermes-venv \
 && ln -sf /sandbox/hermes-venv/bin/hermes /usr/local/bin/hermes
USER sandbox
