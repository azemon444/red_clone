#!/usr/bin/env bash
set -euo pipefail
SERIAL="${ANDROID_SERIAL:-emulator-5554}"
PKG="com.azemon.santanderclone"
APK="$(cd "$(dirname "$0")/.." && pwd)/SantanderClone-signed.apk"

adb() { command adb -s "$SERIAL" "$@"; }

tap_label() {
  local label="$1"
  python3 - "$SERIAL" "$label" <<'PY'
import sys, xml.etree.ElementTree as ET, re, subprocess
serial, label = sys.argv[1], sys.argv[2].lower()
subprocess.run(["adb", "-s", serial, "shell", "uiautomator", "dump", "/sdcard/ui.xml"], capture_output=True)
xml = subprocess.check_output(["adb", "-s", serial, "shell", "cat", "/sdcard/ui.xml"]).decode()
root = ET.fromstring(xml)
for n in root.iter("node"):
    t = (n.attrib.get("text") or n.attrib.get("content-desc") or n.attrib.get("resource-id") or "").strip().lower()
    if label in t:
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.attrib.get("bounds", ""))
        if m:
            x1, y1, x2, y2 = map(int, m.groups())
            x, y = (x1 + x2) // 2, (y1 + y2) // 2
            subprocess.run(["adb", "-s", serial, "shell", "input", "tap", str(x), str(y)])
            print(f"TAPPED {label} at {x},{y}")
            raise SystemExit(0)
print(f"MISS {label}")
raise SystemExit(1)
PY
}

adb install -r --no-incremental "$APK" 2>&1 | tail -1 || true
adb shell pm clear "$PKG"
adb logcat -c
adb shell am start -n "${PKG}/es.bancosantander.apps.mobile.android.activities.PublicActivity"
sleep 12

python3 <<PY
import xml.etree.ElementTree as ET, re, subprocess, time, os
serial = os.environ.get("ANDROID_SERIAL", "emulator-5554")
subprocess.run(["adb", "-s", serial, "shell", "uiautomator", "dump", "/sdcard/ui.xml"], capture_output=True)
xml = subprocess.check_output(["adb", "-s", serial, "shell", "cat", "/sdcard/ui.xml"]).decode()
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
    ["adb", "-s", serial, "shell", "input", "tap", str(ux), str(uy)],
    ["adb", "-s", serial, "shell", "input", "text", "demo"],
    ["adb", "-s", serial, "shell", "input", "tap", str(px), str(py)],
    ["adb", "-s", serial, "shell", "input", "text", "demo123"],
    ["adb", "-s", serial, "shell", "input", "tap", "540", "1392"],
]:
    subprocess.run(cmd)
    time.sleep(0.8)
PY

sleep 8
tap_label "skipconfiguration" || tap_label "skip configuration" || true
sleep 2
tap_label "yes" || tap_label "sure" || true
sleep 2
tap_label "don" || tap_label "allow" || true
sleep 12

adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1 || true
python3 - "$SERIAL" <<'PY'
import sys, xml.etree.ElementTree as ET, subprocess
serial = sys.argv[1]
xml = subprocess.check_output(["adb", "-s", serial, "shell", "cat", "/sdcard/ui.xml"]).decode()
root = ET.fromstring(xml)
texts, ids = [], []
for n in root.iter("node"):
    t = (n.attrib.get("text") or n.attrib.get("content-desc") or "").strip()
    rid = n.attrib.get("resource-id", "")
    if t:
        texts.append(t)
    if rid:
        ids.append(rid)
print("TEXTS:", " | ".join(texts[:25]))
print("HAS_FAKE_PG:", any("fake_pg" in i for i in ids))
print("HAS_HOME:", any("home" in (t or "").lower() for t in texts))
print("HAS_BALANCE:", any("65" in t or "6079" in t or "Shuaib" in t for t in texts))
PY

echo "=== FATAL ==="
adb logcat -d | awk '/FATAL EXCEPTION/,/^$/' | head -60
