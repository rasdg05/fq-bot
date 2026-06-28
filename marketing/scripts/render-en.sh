#!/usr/bin/env bash
set -e
cd /home/user/fq-bot/marketing
FFMPEG=$(node -e "process.stdout.write(require('ffmpeg-static'))")
COMPS="g1-en-banda g1-en-cover g1-en-web-banda g1-en-web-cover"
for c in $COMPS; do
  echo ">>> render $c"
  npx remotion render "$c" "out/$c.mp4" --log=error
  echo ">>> master $c"
  node scripts/master.mjs "$c" >/dev/null 2>&1 || true
  echo ">>> light $c"
  "$FFMPEG" -y -i "out/$c-master.mp4" -vf scale=-2:1280 -c:v libx264 -crf 30 -preset veryfast -c:a aac -b:a 128k "out/$c-LIGHT.mp4" >/dev/null 2>&1
done
echo "ALL DONE"
ls -la out/g1-en*-LIGHT.mp4
