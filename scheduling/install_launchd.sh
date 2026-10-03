#!/bin/bash
# Install the launchd job.
#   ./scheduling/install_launchd.sh          -> monthly: 07:00 on the 1st
#   ./scheduling/install_launchd.sh 3        -> demo: fires 3 minutes from now (then daily at that time,
#                                               so re-run without a number afterwards to go back to monthly)
#   ./scheduling/install_launchd.sh remove   -> uninstall
set -euo pipefail
LABEL=com.legacyportalbot.monthly
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ "${1:-}" = "remove" ]; then rm -f "$DEST"; echo "Removed $LABEL"; exit 0; fi

mkdir -p "$REPO/logs" "$(dirname "$DEST")"
sed "s#REPO_DIR#$REPO#g" "$REPO/scheduling/$LABEL.plist" > "$DEST"
if [ -n "${1:-}" ]; then
  read -r H M <<<"$(date -v+"${1}"M '+%H %M')"
  plutil -replace StartCalendarInterval -json "{\"Hour\": $((10#$H)), \"Minute\": $((10#$M))}" "$DEST"
  echo "Demo schedule: bot runs at $H:$M (keep the portal running: python -m portal)"
else
  echo "Monthly schedule: 07:00 on the 1st"
fi
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "Installed $DEST. Output goes to logs/launchd.out.log and logs/launchd.err.log"
