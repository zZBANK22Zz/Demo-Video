#!/bin/zsh
# Regenerates the app demo video end to end. Copy to <project>/demo/make-video.sh
# and fill in the CONFIGURE section.
#
#   demo/make-video.sh                    prepare → run all flows while recording → edit
#   demo/make-video.sh --dry-run          prepare → run all flows, no recording, no edit
#   demo/make-video.sh --edit-only [cfg]  re-edit the last recording (after caption tweaks)
set -euo pipefail

DEMO="${0:A:h}"
OUT="$DEMO/out"
# Where this skill is installed. When copying this template, replace the default with the skill's base directory.
SKILL="${APP_DEMO_SKILL:-$HOME/.claude/skills/app-demo-video}"
export APP_DEMO_SKILL="$SKILL"            # record.py and other helpers read it

# ---- CONFIGURE ----------------------------------------------------------------
APP_ID="com.example.app"          # default app id; a device line may override it (5th column)
CONFIG="${CONFIG:-video.json}"     # edit config in demo/ (see the skill's references/config.md)
# One line per device: key platform id flow-file [app-id]
#   platform: ios (simulator UDID) | android (adb serial, e.g. emulator-5554)
#   key must match "devices[].key" in the config; recordings go to out/<key>-raw.mp4
#   and the recording-start mark is rec_<key>. app-id defaults to APP_ID (set it when
#   devices run different apps, e.g. customer and rider builds).
DEVICES=(
  "p ios     00000000-0000-0000-0000-000000000000 demo-flow.yaml"
  # "d android emulator-5554 driver-flow.yaml"
)
START_STAGGER=4        # seconds between starting flows (lets a "waiting" flow attach first: list it first)
PREPARE="$DEMO/scripts/prepare.py"   # optional: puts test accounts/data into a known state
MARK_PORT="${MARK_PORT:-8787}"
# --------------------------------------------------------------------------------

export PATH="$PATH:$HOME/.maestro/bin"
export MAESTRO_CLI_NO_ANALYTICS=1 MAESTRO_CLI_ANALYSIS_NOTIFICATION_DISABLED=true
MODE="${1:-full}"
[[ "$MODE" == "--edit-only" && -n "${2:-}" ]] && CONFIG="$2"
mkdir -p "$OUT"

log() { print -P "%F{green}▸%f $*"; }
die() { print -P "%F{red}✗%f $*" >&2; exit 1; }
now() { python3 -c 'import time; print(f"{time.time():.3f}")'; }
pause() { python3 -c "import time; time.sleep($1)"; }

if [[ "$MODE" == "--edit-only" ]]; then
  exec python3 "$SKILL/scripts/edit.py" "$DEMO/$CONFIG"
fi

# ---- preflight ------------------------------------------------------------------
for tool in maestro ffmpeg ffprobe python3 swift; do
  command -v $tool >/dev/null || die "$tool not found"
done
for line in $DEVICES; do
  read -r key platform id flow app <<< "$line"; app="${app:-$APP_ID}"
  case $platform in
    ios) xcrun simctl list devices booted | grep -q "$id" || die "simulator $id ($key) is not booted" ;;
    android) adb -s "$id" get-state 2>/dev/null | grep -q device || die "android $id ($key) not connected" ;;
  esac
  [[ -f "$DEMO/$flow" ]] || die "missing flow demo/$flow"
done

# Maestro runners left by an interrupted run stay attached to the device; a second
# runner on the same device makes every wait flaky.
stop_stale_maestro() {
  pkill -f "maestro.cli.AppKt" 2>/dev/null || true
  pkill -f "maestro-driver-ios" 2>/dev/null || true
  pkill -f "mark-server.py" 2>/dev/null || true
}
stop_stale_maestro
pause 2

# ---- known state ------------------------------------------------------------------
[[ -f "$PREPARE" ]] && { log "Preparing test data"; python3 "$PREPARE"; }

log "Clean status bars, fresh app launches"
for line in $DEVICES; do
  read -r key platform id flow app <<< "$line"; app="${app:-$APP_ID}"
  case $platform in
    ios)
      xcrun simctl status_bar "$id" override --time "9:41" --batteryState charged --batteryLevel 100 \
        --cellularMode active --cellularBars 4 --wifiBars 3 --dataNetwork wifi
      xcrun simctl terminate "$id" $app 2>/dev/null || true ;;
    android)
      adb -s "$id" shell settings put global sysui_demo_allowed 1
      adb -s "$id" shell am broadcast -a com.android.systemui.demo -e command enter >/dev/null
      adb -s "$id" shell am broadcast -a com.android.systemui.demo -e command clock -e hhmm 0941 >/dev/null
      adb -s "$id" shell am broadcast -a com.android.systemui.demo -e command battery -e level 100 -e plugged false >/dev/null
      adb -s "$id" shell am broadcast -a com.android.systemui.demo -e command notifications -e visible false >/dev/null
      adb -s "$id" shell am force-stop $app ;;
  esac
done
pause 2
for line in $DEVICES; do
  read -r key platform id flow app <<< "$line"; app="${app:-$APP_ID}"
  case $platform in
    ios) xcrun simctl launch "$id" $app >/dev/null ;;
    android) adb -s "$id" shell monkey -p $app -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 ;;
  esac
done
pause 10

# ---- run (and record) ---------------------------------------------------------------
MARKS="$OUT/marks.txt"
[[ "$MODE" == "--dry-run" ]] && MARKS="$OUT/marks-dry.txt"
: > "$MARKS"
python3 "$SKILL/scripts/mark-server.py" "$MARKS" "$MARK_PORT" &
MARK_PID=$!
REC_PIDS=()
cleanup() {
  for pid in $REC_PIDS; do kill -INT $pid 2>/dev/null || true; done
  kill $MARK_PID 2>/dev/null || true
  stop_stale_maestro
}
trap cleanup EXIT

start_recording() {  # <key> <platform> <id>
  local file="$OUT/$1-raw.mp4" errlog="$OUT/$1-rec.log"
  rm -f "$file"
  case $2 in
    ios)
      xcrun simctl io "$3" recordVideo --codec=h264 --force "$file" 2> "$errlog" &
      REC_PIDS+=($!)
      # The clip's 0 s is when simctl says recording started, not when it was launched.
      for _ in {1..50}; do grep -q "Recording started" "$errlog" 2>/dev/null && break; pause 0.1; done ;;
    android)
      # scrcpy has no 3-minute cap (adb screenrecord does); see references/android.md.
      command -v scrcpy >/dev/null || die "android recording needs scrcpy (brew install scrcpy)"
      scrcpy -s "$3" --no-playback --no-audio --record="$file" --max-fps=60 > "$errlog" 2>&1 &
      REC_PIDS+=($!)
      for _ in {1..80}; do grep -qi "recording started" "$errlog" 2>/dev/null && break; pause 0.1; done ;;
  esac
  print "rec_$1 $(now)" >> "$MARKS"
}

if [[ "$MODE" != "--dry-run" ]]; then
  log "Recording"
  for line in $DEVICES; do read -r key platform id flow app <<< "$line"; app="${app:-$APP_ID}"; start_recording $key $platform $id; done
  pause 1
fi

log "Running flows"
cd "$DEMO"
FLOW_PIDS=()
first=1
for line in $DEVICES; do
  read -r key platform id flow app <<< "$line"; app="${app:-$APP_ID}"
  (( first )) || pause $START_STAGGER
  first=0
  maestro test --udid "$id" -e MARK_PORT=$MARK_PORT "$flow" > "$OUT/$key-flow.log" 2>&1 &
  FLOW_PIDS+=($!)
done
FAILED=0
for pid in $FLOW_PIDS; do wait $pid || FAILED=1; done

if [[ "$MODE" != "--dry-run" ]]; then
  pause 1
  for pid in $REC_PIDS; do kill -INT $pid 2>/dev/null || true; done
  for pid in $REC_PIDS; do wait $pid 2>/dev/null || true; done
  REC_PIDS=()
fi
kill $MARK_PID 2>/dev/null || true

(( FAILED )) && die "a flow failed — see $OUT/*-flow.log and ~/.maestro/tests/<latest>/ screenshots"
log "Flows passed. Marks: $MARKS"
[[ "$MODE" == "--dry-run" ]] && exit 0

log "Editing"
python3 "$SKILL/scripts/edit.py" "$DEMO/$CONFIG"
