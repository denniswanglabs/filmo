#!/usr/bin/env bash
# Smoke render of the <Timeline> composition against the APPLE-STYLE fixture
# (apple.fixture.json — exercises apple-hero + apple-registry + apple-statement),
# then a tiled montage of stills to confirm scenes land at the right frames and
# reveals fire on cue frames. SHORT by construction (300f / 10s @30fps).
#
# The fixture is passed via --props so it OVERRIDES the composition's default
# (Orinovate kinetic-light) fixture without touching Root.tsx.
set -uo pipefail
cd "$(dirname "$0")"
export PATH="$PWD/node_modules/.bin:$PATH"

OUT_DIR="out/apple-smoke"
mkdir -p "$OUT_DIR"
MP4="$OUT_DIR/apple.mp4"
PROPS="src/timeline/fixtures/apple.fixture.json"

echo "== rendering Timeline (apple fixture) =="
remotion render src/index.ts Timeline "$MP4" --codec=h264 --concurrency=8 --props="$PROPS"

echo "== extracting stills (1 fps) =="
rm -f "$OUT_DIR"/still-*.png
ffmpeg -y -i "$MP4" -vf "fps=1" "$OUT_DIR/still-%02d.png" >/dev/null 2>&1

echo "== building tiled montage (4x3) =="
ffmpeg -y -i "$MP4" -vf "fps=1,scale=480:-1,tile=4x3" -frames:v 1 \
  "$OUT_DIR/montage.png" >/dev/null 2>&1

echo "DONE"
echo "  mp4:     $PWD/$MP4"
echo "  stills:  $PWD/$OUT_DIR/still-*.png"
echo "  montage: $PWD/$OUT_DIR/montage.png"
