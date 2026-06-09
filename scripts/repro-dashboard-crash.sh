#!/usr/bin/env bash
set -euo pipefail
SERIAL="${ANDROID_SERIAL:-emulator-5554}"
PKG="com.azemon.santanderclone"
APK="$(cd "$(dirname "$0")/.." && pwd)/SantanderClone-signed.apk"

adb() { command adb -s "$SERIAL" "$@"; }

adb install -r --no-incremental "$APK" 2>&1 | tail -1 || true
adb shell pm clear "$PKG"
adb logcat -c
adb shell am start -n "${PKG}/es.bancosantander.apps.mobile.android.activities.PublicActivity"
sleep 12

python3 <<'PY'
import xml.etree.ElementTree as ET, re, subprocess, time
subprocess.run(["adb", "-s", "emulator-5554", "shell", "uiautomator", "dump", "/sdcard/ui.xml"], capture_output=True)
xml = subprocess.check_output(["adb", "-s", "emulator-5554", "shell", "cat", "/sdcard/ui.xml"]).decode()
root = ET.fromstring(xml)
edits = []
for n in root.iter("node"):
    if "EditText" not in n.attrib.get("class", ""):
        continue
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.attrib.get("bounds", ""))
    if m:
        x1, y1, x2, y2 = map(int, m.groups())
        edits.append(((x1 + x2) // 2, (y1 + y2) // 2))
ux, uy = edits[0]
px, py = edits[1]
for cmd in [
    ["adb", "-s", "emulator-5554", "shell", "input", "tap", str(ux), str(uy)],
    ["adb", "-s", "emulator-5554", "shell", "input", "text", "demo"],
    ["adb", "-s", "emulator-5554", "shell", "input", "tap", str(px), str(py)],
    ["adb", "-s", "emulator-5554", "shell", "input", "text", "demo123"],
    ["adb", "-s", "emulator-5554", "shell", "input", "tap", "540", "1392"],
]:
    subprocess.run(cmd)
    time.sleep(0.8)
PY

sleep 10
for i in $(seq 1 15); do
  adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1 || true
  OUT=$(python3 <<'PY'
import xml.etree.ElementTree as ET, re, subprocess
xml = subprocess.check_output(["adb", "-s", "emulator-5554", "shell", "cat", "/sdcard/ui.xml"]).decode()
root = ET.fromstring(xml)
texts = []
for n in root.iter("node"):
    t = (n.attrib.get("text") or n.attrib.get("content-desc") or "").strip()
    if t:
        texts.append(t)
joined = " | ".join(texts).lower()
if "home" in joined and "transfer" in joined:
    print("DASHBOARD")
    raise SystemExit(0)
for label in ("yes, i'm sure", "yes, i", "skip configuration", "get started"):
    for n in root.iter("node"):
        t = (n.attrib.get("text") or n.attrib.get("content-desc") or "").strip().lower()
        if label in t:
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.attrib.get("bounds", ""))
            if m:
                x1, y1, x2, y2 = map(int, m.groups())
                print(f"TAP {(x1+x2)//2} {(y1+y2)//2}")
                raise SystemExit(0)
print("TAP 540 1250")
PY
)
  echo "round $i: $OUT"
  if [ "$OUT" = "DASHBOARD" ]; then break; fi
  read _ x y <<< "$OUT"
  adb shell input tap "$x" "$y"
  sleep 2
done

sleep 8
echo "=== FATAL ==="
adb logcat -d | awk '/FATAL EXCEPTION/,/^$/' | head -100
