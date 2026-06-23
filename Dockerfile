# Walk Studio cloud worker image.
# Bundles the python pipeline (build_runner.py + deps) and the Node worker (run.js)
# into one container for Railway. Standard quality only for v1: Remotion render +
# Playwright capture + edge-tts VO + whisper word-timing (no NemoClaw, no Higgsfield).
FROM node:22-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PIPELINE_DIR=/app \
    HOME=/root \
    PYTHONUNBUFFERED=1

# ── system deps: python, ffmpeg, and the toolchain to build whisper.cpp ──
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip \
      ffmpeg git cmake build-essential ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# ── whisper.cpp (align_vo hardcodes /opt/homebrew/bin/whisper-cli + the model path) ──
# GGML_NATIVE/CPU_AARCH64 OFF → skip the ARM repack codegen that mis-compiles under
# this GCC (the -Wstringop-overflow build failure); a portable build is plenty fast
# for base.en word-timing.
RUN git clone --depth 1 https://github.com/ggml-org/whisper.cpp /tmp/whisper \
    && cmake -S /tmp/whisper -B /tmp/whisper/build -DCMAKE_BUILD_TYPE=Release \
       -DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=OFF -DGGML_CPU_AARCH64=OFF \
       -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_SERVER=OFF \
    && cmake --build /tmp/whisper/build -j --target whisper-cli \
    && mkdir -p /opt/homebrew/bin \
    && cp /tmp/whisper/build/bin/whisper-cli /opt/homebrew/bin/whisper-cli \
    && mkdir -p /root/.cache/whisper \
    && curl -fsSL -o /root/.cache/whisper/ggml-base.en.bin \
       https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin \
    && rm -rf /tmp/whisper

# ── edge-tts (free VO) on PATH ──
RUN pip3 install --no-cache-dir --break-system-packages edge-tts

WORKDIR /app

# the pipeline + worker (the worktree root = the hermes-video-agent repo + worker/)
COPY . /app

# ── Playwright capture venv (.venv-capture/bin/python is what capture_screenshots.py calls) ──
RUN python3 -m venv /app/.venv-capture \
    && /app/.venv-capture/bin/pip install --no-cache-dir playwright \
    && /app/.venv-capture/bin/playwright install --with-deps chromium

# ── Remotion studio: drop the macOS node_modules symlink, install fresh, fetch its chromium ──
RUN rm -f /app/studio/node_modules \
    && cd /app/studio && npm install --no-audit --no-fund \
    && npx remotion browser ensure \
    && npm i -g @remotion/cli@$(node -p "require('/app/studio/node_modules/remotion/package.json').version")

# ── music bed: the pipeline points at sibling-repo mp3s that aren't here; provide a
#    silent placeholder at both paths so the VO-ducked <Audio> mount never crashes ──
RUN mkdir -p "/Users/dennis/Desktop/Projects/Demos/tappay-promo/public" \
            "/Users/dennis/Desktop/Projects/Demos/kuli-promo/public" \
    && ffmpeg -f lavfi -i anullsrc=r=44100:cl=stereo -t 60 -q:a 9 \
       "/Users/dennis/Desktop/Projects/Demos/tappay-promo/public/music.mp3" \
    && cp "/Users/dennis/Desktop/Projects/Demos/tappay-promo/public/music.mp3" \
          "/Users/dennis/Desktop/Projects/Demos/kuli-promo/public/music.mp3"

# ── Node worker deps ──
RUN cd /app/worker && npm install --no-audit --no-fund

CMD ["node", "/app/worker/run.js"]
