# How to open the Santander clone app

## Install

| Device | Command |
|--------|---------|
| Physical phone (Samsung, etc.) | `adb -s <SERIAL> install -r --no-incremental SantanderClone-signed.apk` |
| Emulator | `adb -s emulator-5554 install -r --no-incremental SantanderClone-signed.apk` |

Package: `com.azemon.santanderclone`

## Login

1. Open the app — splash / public home appears.
2. Tap **Login**.
3. Username: **`demo`**
4. Password: **`demo123`**
5. Tap **Enter** / confirm.

## PIN & biometrics (first login)

After username/password login the app asks you to **create a 6-digit PIN**:

1. Enter any **6 digits** (e.g. `123456`).
2. Confirm the same PIN on the next screen.
3. Optionally tap **Use biometrics** to enable fingerprint/face unlock (requires device biometrics enrolled in Android Settings).

On later launches, unlock with your PIN or biometrics — the mock API accepts any valid PIN locally and returns the correct `pinValidationId` / `userDeviceId` responses.

If PIN setup fails with a generic error, pull-to-refresh is not enough — force-stop the app, clear app data once, and login again after the mock API is updated (see `/health`).

## Onboarding (first launch after install)

Tap through in this order:

1. **Skip configuration** (or “Skip configuration” link).
2. **Yes, I'm sure** — confirm you want to skip setup.
3. **Notifications** → **Don't allow** (or “Not now”). The clone works without push.
4. **Location** → **Don't allow** (or deny on the system dialog). Not required for demo data.

You should land on the **Home** tab with bottom navigation: Home · Transfer · Pay · Rewards · Profile.

## Permissions — what to allow

| Permission | Recommendation | Why |
|------------|----------------|-----|
| Notifications | **Deny** | Mock server does not send real push; denying avoids extra prompts. |
| Location | **Deny** | Dashboard balance and cards come from the API, not GPS. |
| Contacts | **Deny** if asked | Pay/MB WAY favourites use mock data. |
| Camera / Photos | **Deny** if asked | Not needed for the demo walkthrough. |
| Phone / SMS | **Deny** if asked | Not used in this clone. |

If you already allowed something, you can revoke it in Android **Settings → Apps → Santander Clone → Permissions**.

## Expected demo data (match `target/02-dashboard.png`)

| Field | Value |
|-------|--------|
| Name | Shuaib |
| Balance | **-65,72 €** |
| Account | `000365542813020` |
| Debit card | `*6079` |

## API / network

| Where you run the app | Mock API |
|-----------------------|----------|
| Real phone | `https://project-efnt2.vercel.app` (baked into phone APK build) |
| Emulator + local mock | `http://10.0.2.2:9090` (rebuild with `python3 scripts/patch-apk.py` without `--mock-host`) |

Check API health: open `https://project-efnt2.vercel.app/health` in a browser.

## Dynamic cards & offers

- Pull-to-refresh on Home re-fetches global position (`Cache-Control: no-store`).
- Promo / RTO slots rotate about every minute on `/santander/eeic/rto_crm/*`.
- Microsite assets (`offersV4.xml`, images) are served with **no-cache** so a refresh can pick up changes.
- Edit live JSON (balance, payees, mailbox) via **Admin UI**: `https://project-efnt2.vercel.app/admin`

## Tabs (reference screenshots)

| Tab | Reference image |
|-----|-----------------|
| Home | `reference/target/02-dashboard.png` |
| Transfer | `reference/target/04-transfer.png` |
| Pay | `reference/target/05-pay.png` |
| Rewards | `reference/target/06-rewards.png` |
| Menu | `reference/target/07-menu-more-options.png` |

Full walkthrough video: `reference/video/santander_video.mp4`

## Rebuild APK (after code changes)

```bash
# Phone / Vercel
python3 scripts/patch-apk.py --mock-host https://project-efnt2.vercel.app

# Emulator + local mock on port 9090
python3 scripts/patch-apk.py
```

Output: `SantanderClone-signed.apk` in the repo root.

## Troubleshooting

- **Black emulator screenshots** — UI may still be fine; use `adb shell uiautomator dump /sdcard/ui.xml` for text.
- **“We are sorry” dialog** — should be suppressed; reinstall the latest signed APK.
- **Empty dashboard** — confirm `/health` shows balance -65.72; force-stop app and login again.
- **Transfer tab crash** — reinstall APK built after drawable patches (`icn_transfer_red`, `icn_send_programmed`).
