#!/usr/bin/env bash
# Walk through Santander clone on emulator: launch, login, capture screens, check logcat.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="com.azemon.santanderclone"
APK="${ROOT}/SantanderClone-signed.apk"
OUT="${ROOT}/screenshots/emulator-run-$(date +%Y%m%d-%H%M%S)"
ADB="adb"
SERIAL="${ANDROID_SERIAL:-}"

mkdir -p "$OUT"

log() { echo "[walkthrough] $*"; }

wait_device() {
  log "Waiting for emulator..."
  "$ADB" wait-for-device
  for i in $(seq 1 90); do
    boot=$("$ADB" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r') || boot=""
    if [[ "$boot" == "1" ]]; then
      log "Boot complete"
      sleep 5
      return 0
    fi
    sleep 2
  done
  log "WARN: boot timeout — continuing anyway"
}

shot() {
  local name="$1"
  local path="${OUT}/${name}.png"
  "$ADB" exec-out screencap -p > "$path" 2>/dev/null || "$ADB" shell screencap -p "/sdcard/${name}.png" && "$ADB" pull "/sdcard/${name}.png" "$path" >/dev/null
  log "Screenshot: $path"
}

tap() {
  log "Tap $1 $2"
  "$ADB" shell input tap "$1" "$2"
  sleep 2
}

text() {
  log "Type: $1"
  "$ADB" shell input text "$1"
  sleep 0.5
}

key() {
  "$ADB" shell input keyevent "$1"
  sleep 0.5
}

launch_app() {
  "$ADB" shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || \
  "$ADB" shell am start -n "${PKG}/pt.santander.oneappparticulares.ui.splash.SplashActivity" 2>/dev/null || \
  "$ADB" shell am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER "$PKG" 2>/dev/null || true
}

dump_ui() {
  local name="$1"
  "$ADB" shell uiautomator dump "/sdcard/${name}.xml" >/dev/null 2>&1 || true
  "$ADB" pull "/sdcard/${name}.xml" "${OUT}/${name}.xml" >/dev/null 2>&1 || true
}

find_and_tap_text() {
  local label="$1"
  local xml="${OUT}/_ui.xml"
  "$ADB" shell uiautomator dump /sdcard/_ui.xml >/dev/null 2>&1 || return 1
  "$ADB" pull /sdcard/_ui.xml "$xml" >/dev/null 2>&1 || return 1
  python3 - "$label" "$xml" <<'PY'
import re, sys
label, path = sys.argv[1], sys.argv[2]
try:
    xml = open(path, encoding='utf-8', errors='ignore').read()
except FileNotFoundError:
    sys.exit(1)
pat = re.compile(rf'text="{re.escape(label)}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', re.I)
m = pat.search(xml)
if not m:
    pat2 = re.compile(rf'content-desc="{re.escape(label)}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', re.I)
    m = pat2.search(xml)
if not m:
    sys.exit(2)
x1,y1,x2,y2 = map(int, m.groups())
print((x1+x2)//2, (y1+y2)//2)
PY
  read -r x y < <(python3 - "$label" "$xml" <<'PY'
import re, sys
label, path = sys.argv[1], sys.argv[2]
xml = open(path, encoding='utf-8', errors='ignore').read()
for attr in ('text', 'content-desc'):
    pat = re.compile(rf'{attr}="[^"]*{re.escape(label)}[^"]*"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', re.I)
    m = pat.search(xml)
    if m:
        x1,y1,x2,y2 = map(int, m.groups())
        print((x1+x2)//2, (y1+y2)//2)
        break
PY
) 2>/dev/null && tap "$x" "$y"
}

if [[ -n "$SERIAL" ]]; then ADB="adb -s $SERIAL"; fi

log "Output dir: $OUT"
wait_device

log "Installing APK..."
"$ADB" install -r --no-incremental "$APK" || "$ADB" install -r "$APK"

log "Clearing app data for clean run..."
"$ADB" shell pm clear "$PKG" >/dev/null

log "Warming API..."
/usr/bin/curl -sf "https://project-efnt2.vercel.app/health" >/dev/null || true
/usr/bin/curl -sf "https://project-efnt2.vercel.app/santander/eeic/global_position_app?active_only=true" >/dev/null || true

log "Starting logcat capture..."
"$ADB" logcat -c
"$ADB" logcat -v time > "${OUT}/logcat.txt" 2>&1 &
LOGCAT_PID=$!
trap 'kill $LOGCAT_PID 2>/dev/null || true' EXIT

launch_app
sleep 8
shot "01-launch"

# Dismiss possible dialogs / scroll public screen
tap 540 1800
sleep 2
shot "02-public-home"

# Try Access / Login — common positions on 1080x2400
tap 540 2100
sleep 3
shot "03-after-access-tap"

dump_ui "03-ui"

# Login flow: try tapping center-bottom login area
tap 540 1200
sleep 2
shot "04-login-screen"

# Enter username demo
tap 540 900
sleep 1
key 67; key 67; key 67; key 67
text "demo"
key 61
sleep 1
text "demo123"
sleep 1
shot "05-credentials-filled"

# Submit / Continue
tap 540 1500
sleep 2
tap 540 1700
sleep 8
shot "06-after-login"

# Bottom nav tabs (typical 5-tab bar on 1080x2400)
for i in 1 2 3 4 5; do
  x=$((216 * i))
  tap "$x" 2280
  sleep 5
  shot "07-tab-${i}"
  dump_ui "07-tab-${i}-ui"
done

# Pull recent errors from logcat
kill $LOGCAT_PID 2>/dev/null || true
sleep 1
{
  echo "=== FATAL EXCEPTIONS ==="
  grep -A 20 "FATAL EXCEPTION" "${OUT}/logcat.txt" || echo "(none)"
  echo ""
  echo "=== Global position / network ==="
  grep -iE "global.position|Load global|JsonParse|PortugalError|global-position|ServiceException|NetworkException" "${OUT}/logcat.txt" | tail -40 || true
} > "${OUT}/errors-summary.txt"

log "Done. Screenshots in $OUT"
ls -la "$OUT"
