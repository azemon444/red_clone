#!/usr/bin/env bash
# Rebuild the signed APK to point at your hosted mock API.
# Usage: ./scripts/rebuild-apk-cloud.sh https://your-app.fly.dev
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${1:-}"
if [[ -z "$URL" ]]; then
  echo "Usage: $0 https://YOUR-HOSTED-URL"
  echo "Example: $0 https://santander-clone-mock.fly.dev"
  exit 1
fi
URL="${URL%/}"
echo "Patching APK → $URL"
cd "$ROOT"
python3 scripts/patch-apk.py --mock-host "$URL"
echo ""
echo "Done. Install:"
echo "  adb install -r SantanderClone-signed.apk"
echo "  adb shell pm clear com.azemon.santanderclone"
