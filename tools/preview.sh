#!/bin/sh
# preview.sh preset.milk -> renders/<name>.png (3x3 contact sheet) + <name>.mp4
set -e
D=$(dirname "$0")/..; P="$1"; N=$(basename "$P" .milk); W=640; H=360; F=${FRAMES:-600}
mkdir -p "$D/renders"
"$D/tools/render" "$P" $W $H $F 2>"$D/renders/$N.log" | ffmpeg -loglevel error -y \
  -f rawvideo -pix_fmt rgb24 -s ${W}x$H -r 60 -i - \
  -c:v libx264 -pix_fmt yuv420p -crf 20 "$D/renders/$N.mp4"
ffmpeg -loglevel error -y -i "$D/renders/$N.mp4" \
  -vf "select='not(mod(n\,$((F/9))))',scale=320:180,tile=3x3" -frames:v 1 "$D/renders/$N.png"
echo "$D/renders/$N.png"
