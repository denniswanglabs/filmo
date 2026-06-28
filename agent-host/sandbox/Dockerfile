# Filmo NemoClaw sandbox image — bake the Chromium runtime deps onto the NVIDIA base.
# The base sandbox image ships WITHOUT Chrome's system libs, so the in-sandbox browser
# fails to launch (`libglib-2.0.so.0: cannot open shared object file`). Baking them via
# `nemoclaw onboard --from <Dockerfile>` is the ONLY thing that survives a rebuild
# (runtime `dpkg-deb -x` extraction does not). See HERMES-NEMOCLAW-PLAN landmines.
#
# ★0b: this is the standard Playwright-chromium dep set; on the base's distro the names
# may be the Trixie `t64` variants (e.g. libasound2t64). The 0b spike pins the exact set.
FROM ghcr.io/nvidia/nemoclaw/sandbox-base:v0.0.50
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
      libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
      libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
      libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
