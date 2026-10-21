#!/usr/bin/env bash
# Record and edit the web demo video. Copy to <project>/demo/make-video.sh and fill in CONFIGURE.
#   demo/make-video.sh              start an isolated app stack, record, render
#   demo/make-video.sh --record     record only (check the journey without waiting for the render)
#   demo/make-video.sh --edit-only  re-render the last recording (after changing video.json)
set -euo pipefail
cd "$(dirname "$0")"
DEMO="$PWD"; ROOT="$(cd .. && pwd)"
# This example uses the skill shipped in this repository; set APP_DEMO_SKILL to use another copy.
SKILL="${APP_DEMO_SKILL:-$(cd "$DEMO/../../../skills/app-demo-video" && pwd)}"
export APP_DEMO_SKILL="$SKILL"

# ---- CONFIGURE ----------------------------------------------------------------
PORT=3099                                   # not the dev port: the demo stack must not touch real data
URL="http://localhost:$PORT"
HEALTH="$URL"                               # any URL that answers once the app is up
BUILD=()                                    # static HTML/CSS: nothing to build
START=(python3 -m http.server "$PORT" --bind 127.0.0.1)
# Static mockup: no data or side effects. Kept non-empty because bash 3.2 + set -u rejects empty arrays.
APP_ENV=(DEMO=1)
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
