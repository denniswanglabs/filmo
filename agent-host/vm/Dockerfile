FROM ghcr.io/nvidia/nemoclaw/sandbox-base:v0.0.50
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-pip && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /sandbox/hermes-venv \
 && /sandbox/hermes-venv/bin/pip install --no-cache-dir --upgrade pip \
 && /sandbox/hermes-venv/bin/pip install --no-cache-dir 'hermes-agent[cli]' \
 && chown -R 998:998 /sandbox/hermes-venv \
 && ln -sf /sandbox/hermes-venv/bin/hermes /usr/local/bin/hermes
USER sandbox
