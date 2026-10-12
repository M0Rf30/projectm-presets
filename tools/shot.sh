#!/bin/sh
# shot.sh preset.{milk,milk2} out_dir frame [frame...]
# Renders the preset in lactea (MilkDrop 3 mode, deterministic 60 fps clock, synthetic 128 bpm audio)
# and saves out_dir/<name>_f<frame>.png for each frame (frame 60 = 1 s of music; renders in real time).
# Shader compile problems show up on stderr as "WARN ... replaced by default ... shader".
# All lactea runs are serialised through one lock so parallel authors do not fight over the GPU.
set -e
P="$1"; O="$2"; shift 2
D=$(cd "$(dirname "$0")" && pwd)
WAV=${SHOT_WAV:-/tmp/lactea-synth.wav}
[ -s "$WAV" ] || python3 "$D/synth.py" "$WAV" 40
N=$(basename "$P"); N=${N%.milk2}; N=${N%.milk}
mkdir -p "$O"
for F in "$@"; do
  flock /tmp/lactea-shot.lock timeout 120 lactea --preset "$P" --compat milkdrop3 \
    --audio-wav "$WAV" --deterministic --no-vsync --transition-duration 0 \
    --size "${SHOT_SIZE:-960x540}" --screenshot "$O/${N}_f$F.png" --screenshot-frame "$F" 2>&1 \
    | grep -E 'WARN|ERROR|Error|error' || true
  echo "$O/${N}_f$F.png"
done
