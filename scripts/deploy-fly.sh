#!/usr/bin/env bash
# One-time Fly.io deploy helper (free tier). Run from repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v flyctl &>/dev/null && ! command -v fly &>/dev/null; then
  echo "Install Fly CLI first:"
  echo "  curl -L https://fly.io/install.sh | sh"
  echo "Then restart your terminal and run this script again."
  exit 1
fi
FLY="$(command -v flyctl || command -v fly)"

read -r -p "Fly app name [santander-clone-mock]: " APP_NAME
APP_NAME="${APP_NAME:-santander-clone-mock}"
read -r -s -p "Admin password (ADMIN_PASSWORD): " ADMIN_PW
echo ""
read -r -p "Region [ams]: " REGION
REGION="${REGION:-ams}"

# Patch fly.toml app name if custom
if [[ "$APP_NAME" != "santander-clone-mock" ]]; then
  sed -i.bak "s/^app = .*/app = \"$APP_NAME\"/" fly.toml
  sed -i.bak "s/^primary_region = .*/primary_region = \"$REGION\"/" fly.toml
  rm -f fly.toml.bak
fi

echo "→ Launching app (first time creates the Fly app + volume)..."
$FLY launch --no-deploy --copy-config --name "$APP_NAME" --region "$REGION" --yes 2>/dev/null || true

echo "→ Creating persistent volume (if missing)..."
$FLY volumes create santander_data --region "$REGION" --size 1 -a "$APP_NAME" 2>/dev/null || true

HOST="https://${APP_NAME}.fly.dev"
echo "→ Setting secrets..."
$FLY secrets set \
  ADMIN_PASSWORD="$ADMIN_PW" \
  PUBLIC_URL="$HOST" \
  -a "$APP_NAME"

echo "→ Deploying..."
$FLY deploy -a "$APP_NAME"

echo ""
echo "════════════════════════════════════════"
echo "  Deployed: $HOST"
echo "  Admin:    $HOST/admin"
echo "  Health:   $HOST/health"
echo ""
echo "Next — rebuild APK:"
echo "  ./scripts/rebuild-apk-cloud.sh $HOST"
echo "════════════════════════════════════════"
