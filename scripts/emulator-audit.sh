#!/usr/bin/env bash
set -euo pipefail

SERIAL="${ANDROID_SERIAL:-emulator-5554}"
PKG="com.azemon.santanderclone"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APK="$ROOT/SantanderClone-signed.apk"
OUT="$ROOT/screenshots/emulator-audit-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"

adb() { command adb -s "$SERIAL" "$@"; }

curl -sf https://project-efnt2.vercel.app/health > "$OUT/api-health.json" || true
curl -sf "https://project-efnt2.vercel.app/santander/eeic/global_position_app?active_only=true" > "$OUT/api-gp.json" || true

adb install -r --no-incremental "$APK" 2>&1 | tail -2 || true
adb shell pm clear "$PKG"
adb logcat -c
adb shell am start -n "${PKG}/es.bancosantander.apps.mobile.android.activities.PublicActivity"
sleep 18

dump_ui() {
  local name=$1
  adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1 || true
  adb pull /sdcard/ui.xml "$OUT/${name}.xml" >/dev/null 2>&1 || true
  adb exec-out screencap -p > "$OUT/${name}.png" 2>/dev/null || true
  python3 - "$OUT/${name}.xml" "$name" <<'PY'
import sys, xml.etree.ElementTree as ET
path, name = sys.argv[1], sys.argv[2]
try:
    root = ET.parse(path).getroot()
except Exception:
    print(f"--- {name}: NO XML ---"); sys.exit(0)
texts, ids, pkg = [], [], ""
for n in root.iter("node"):
    if not pkg:
        pkg = n.attrib.get("package", "")
    for k in ("text", "content-desc"):
        v = (n.attrib.get(k) or "").strip()
        if v and v not in texts:
            texts.append(v)
    rid = n.attrib.get("resource-id", "")
    if rid and any(k in rid for k in ("fake_pg", "bottomBar", "loginRemembered", "simple_pg")):
        ids.append(rid.split("/")[-1])
print(f"--- {name}: pkg={pkg} labels={len(texts)} ---")
if ids:
    print("KEY_IDS:", ", ".join(sorted(set(ids))[:12]))
print("LABELS:", " | ".join(texts[:30]))
PY
}

dump_ui "01-splash-login"

adb shell input tap 540 798; sleep 1
adb shell input text demo; sleep 1
adb shell input tap 540 1055; sleep 1
adb shell input text demo123; sleep 1
adb shell input tap 540 1392
sleep 20
dump_ui "02-after-login"

for round in 1 2 3 4 5 6 7; do
  adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1 || true
  COORDS=$(ANDROID_SERIAL="$SERIAL" python3 <<'PY'
import os, xml.etree.ElementTree as ET, subprocess, re
serial = os.environ.get("ANDROID_SERIAL", "emulator-5554")
xml = subprocess.check_output(["adb", "-s", serial, "shell", "cat", "/sdcard/ui.xml"], stderr=subprocess.DEVNULL).decode()
root = ET.fromstring(xml)
prio = []
for n in root.iter("node"):
    t = (n.attrib.get("text") or n.attrib.get("content-desc") or "").strip()
    tl = t.lower()
    if n.attrib.get("clickable") != "true":
        continue
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.attrib.get("bounds", ""))
    if not m:
        continue
    x1, y1, x2, y2 = map(int, m.groups())
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    rid = n.attrib.get("resource-id") or ""
    if "onboarding_link_skipconfiguration" in rid.lower():
        prio.insert(0, (-1, cx, cy, t or rid))
    elif "skip configuration" in tl or tl == "skip":
        prio.insert(0, (0, cx, cy, t))
    elif "verificationsheet_secondarybutton" in rid.lower() or "yes, i'm sure" in tl:
        prio.insert(0, (1, cx, cy, t))
    elif "don't allow" in tl or tl == "deny" or "not now" in tl:
        prio.insert(0, (2, cx, cy, t))
    elif tl == "allow" or "while using" in tl:
        prio.append((3, cx, cy, t))
    elif tl == "login" and ("loginRemembered" in rid or cy > 1400):
        prio.insert(0, (0, cx, cy, t))
if prio:
    prio.sort(key=lambda x: x[0])
    print(f"{prio[0][1]} {prio[0][2]} # {prio[0][3]}")
PY
)
  if [ -z "$COORDS" ]; then
    echo "Round $round: no dialog"
    break
  fi
  X=$(echo "$COORDS" | awk '{print $1}')
  Y=$(echo "$COORDS" | awk '{print $2}')
  echo "Round $round tap $X $Y ($COORDS)"
  adb shell input tap "$X" "$Y"
  sleep 6
done

sleep 8
dump_ui "03-dashboard"

for spec in "108:home" "324:transfer" "540:pay" "756:rewards" "972:profile"; do
  x=${spec%%:*}
  name=${spec##*:}
  adb shell input tap "$x" 2241
  sleep 8
  dump_ui "04-tab-${name}"
done

adb shell input tap 1006 137; sleep 5; dump_ui "05-menu"
adb shell input keyevent KEYCODE_BACK; sleep 2
adb shell input tap 880 137; sleep 5; dump_ui "06-mailbox"
adb shell input keyevent KEYCODE_BACK; sleep 2

adb shell dumpsys activity activities | grep -E "mResumedActivity|mFocusedApp" | head -3 > "$OUT/activity.txt" || true
adb logcat -d | grep -iE "FATAL EXCEPTION|Load global|global.position|GlobalPosition|fake_pg|ServiceException" | tail -40 > "$OUT/errors.txt" || true

echo ""
echo "=== SUMMARY ==="
cat "$OUT/activity.txt" 2>/dev/null || true
echo "--- errors ---"
cat "$OUT/errors.txt" 2>/dev/null || true
echo "OUT=$OUT"
