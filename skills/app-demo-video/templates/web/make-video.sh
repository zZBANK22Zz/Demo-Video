#!/usr/bin/env bash
# Record and edit the web demo video. Copy to <project>/demo/make-video.sh and fill in CONFIGURE.
#   demo/make-video.sh              start an isolated app stack, record, render
#   demo/make-video.sh --record     record only (check the journey without waiting for the render)
#   demo/make-video.sh --edit-only  re-render the last recording (after changing video.json)
set -euo pipefail
cd "$(dirname "$0")"
DEMO="$PWD"; ROOT="$(cd .. && pwd)"
# Where this skill is installed. When copying this template, replace the default with the skill's base directory.
SKILL="${APP_DEMO_SKILL:-$HOME/.claude/skills/app-demo-video}"
export APP_DEMO_SKILL="$SKILL"            # record.py and other helpers read it

# ---- CONFIGURE ----------------------------------------------------------------
PORT=3099                                   # not the dev port: the demo stack must not touch real data
URL="http://localhost:$PORT"
HEALTH="$URL"                               # any URL that answers once the app is up
BUILD=(npm run build)                       # empty () to skip
START=(npx next start -p "$PORT")           # the app's production start command, run from $ROOT
# Point the app at throwaway data and dry-run side effects (mail, payments, webhooks) here:
APP_ENV=(DATA_DIR="$DEMO/out/data" MAIL_MODE=dry_run)
# --------------------------------------------------------------------------------

MODE="${1:-all}"
render() { python3 "$SKILL/scripts/web/render_web.py" "$DEMO/video.json"; }
[[ "$MODE" == "--edit-only" ]] && { render; exit 0; }

cleanup() { [[ -n "${APP_PID:-}" ]] && kill "$APP_PID" 2>/dev/null || true; }
trap cleanup EXIT
lsof -ti ":$PORT" | xargs kill 2>/dev/null || true

if (( ${#BUILD[@]} )); then echo "==> build"; (cd "$ROOT" && "${BUILD[@]}" >/dev/null); fi
rm -rf "$DEMO/out/frames" "$DEMO/out/data"; mkdir -p "$DEMO/out/data"
echo "==> start demo stack on :$PORT"
(cd "$ROOT" && env "${APP_ENV[@]}" "${START[@]}" > "$DEMO/out/app.log" 2>&1) & APP_PID=$!
for _ in $(seq 120); do curl -sf "$HEALTH" >/dev/null && break; sleep 0.5; done
curl -sf "$HEALTH" >/dev/null || { echo "app did not start (see out/app.log)"; exit 1; }

echo "==> record"
python3 "$DEMO/record.py" --url "$URL"
[[ "$MODE" == "--record" ]] && exit 0
echo "==> render"
render
