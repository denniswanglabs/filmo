#!/usr/bin/env bash
# Smoke render of the <Timeline> composition against the bundled fixture, then a
# tiled montage of stills to confirm scenes land at the right frames and reveals
# fire on cue frames. SHORT by construction (300f / 10s @30fps fixture).
#
# Usage:  ./render-timeline-smoke.sh [PROPS_JSON_FILE]
#   no arg  -> uses the bundled defaultProps fixture
#   arg     -> passes --props=<file> (e.g. a real build_timeline.py timeline.json)
set -uo pipefail
cd "$(dirname "$0")"
export PATH="$PWD/node_modules/.bin:$PATH"

OUT_DIR="out/timeline-smoke"
mkdir -p "$OUT_DIR"
MP4="$OUT_DIR/timeline.mp4"
PROPS="${1:-}"

echo "== rendering Timeline =="
if [ -n "$PROPS" ]; then
  remotion render src/index.ts Timeline "$MP4" --codec=h264 --concurrency=8 --props="$PROPS"
else
  remotion render src/index.ts Timeline "$MP4" --codec=h264 --concurrency=8
fi

echo "== extracting stills =="
# 10 evenly-spaced stills across the clip; fps derived to ~1 frame/sec of fixture.
rm -f "$OUT_DIR"/still-*.png
ffmpeg -y -i "$MP4" -vf "fps=1" "$OUT_DIR/still-%02d.png" >/dev/null 2>&1

echo "== building tiled montage =="
ffmpeg -y -i "$MP4" -vf "fps=1,scale=480:-1,tile=5x2" -frames:v 1 \
  "$OUT_DIR/montage.png" >/dev/null 2>&1

echo "DONE"
echo "  mp4:     $PWD/$MP4"
echo "  stills:  $PWD/$OUT_DIR/still-*.png"
echo "  montage: $PWD/$OUT_DIR/montage.png"
