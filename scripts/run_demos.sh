#!/bin/bash
# Runs every demo scenario against a real portal process and appends each run to logs/runs.csv.
# The broken-login and missing-report runs are recorded on video and converted to GIFs in docs/demo/.
# Each scenario uses its own month so the bot really downloads (instead of skipping) every time.
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
URL=http://127.0.0.1:5050
mkdir -p logs/videos docs/demo

scenario() {  # scenario <name> <month> [PORTAL_ENV=VALUE ...]   (bot env overrides: $BOT_ENV)
  local name=$1 month=$2; shift 2
  echo; echo "=== $name ($month) ==="
  rm -rf "output/$month"  # start clean so this run downloads for real
  env "$@" $PY -m portal >/dev/null 2>&1 &
  local pid=$!
  until curl -s -o /dev/null "$URL/login"; do sleep 0.2; done
  env ${BOT_ENV:-} $PY -m bot --month "$month" --video logs/videos
  echo "exit code: $?"
  kill $pid; wait $pid 2>/dev/null
  if [ "$name" = broken-login ] || [ "$name" = missing-report ]; then
    ffmpeg -loglevel error -y -i "$(ls -t logs/videos/*.webm | head -1)" \
      -vf "fps=8,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" "docs/demo/$name.gif"
    echo "GIF: docs/demo/$name.gif"
  fi
}

scenario normal         2026-07
scenario broken-login   2026-08 FAIL_FIRST_LOGIN=1
scenario missing-report 2026-09 MISSING_REPORT=vendor-payments:2026-09
BOT_ENV=PORTAL_PASSWORD=wrong-password scenario wrong-password 2026-05
scenario popup-slow-session-timeout 2026-06 SHOW_POPUP=1 SLOW_MODE=1.5 SESSION_TIMEOUT=6
