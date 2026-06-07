# Santander Clone (Offline Demo)

A **standalone offline clone** of the Santander Portugal retail app UI, running entirely on your own mock API and dummy data. No connections to Santander's real servers, databases, or APIs.

## What's included

| Component | Description |
|-----------|-------------|
| `mock-server/` | Node.js API with login + post-login (Global Position) dummy data |
| `scripts/patch-apk.py` | Patches the APK: new package name, local API, SSL bypass |
| `apktool/` | Decompiled original APK (UI assets, layouts, code) |
| `jadx-out/` | Java source reference from decompilation |

## Package name

- **Original:** `pt.santander.oneappparticulares`
- **Clone:** `com.azemon.santanderclone`
- **App label:** Banco Clone

## Quick start

### 1. Start the mock API server

```bash
cd mock-server
npm install
npm start
```

Server runs at `http://localhost:9090`. From Android emulator use `http://10.0.2.2:9090`.

**Demo login credentials:**
- Username: `demo`
- Password: `demo123`

### 2. Build the patched APK

```bash
python3 scripts/patch-apk.py
```

This produces `SantanderClone-signed.apk` (or `SantanderClone.apk` if signing tools are missing).

### 3. Install on emulator/device

```bash
# Start emulator first, then:
adb install -r SantanderClone-signed.apk
```

### 4. Login and explore

Open **Banco Clone**, log in with `demo` / `demo123`. You should reach the Global Position (home dashboard) with dummy accounts and cards.

## Architecture

```
┌─────────────────────┐      HTTP (local only)      ┌──────────────────────┐
│  Patched Android    │ ──────────────────────────► │  mock-server :9090   │
│  com.azemon.        │   10.0.2.2 (emulator)       │  Express + JSON data │
│  santanderclone     │                             │  No external calls   │
└─────────────────────┘                             └──────────────────────┘
```

### API endpoints implemented

| Endpoint | Purpose |
|----------|---------|
| `POST /santander/eeic/idp-channel/oauth/token` | Login |
| `POST /santander/eeic/oauth-server-channel/oauth/token` | Session token |
| `GET /santander/eeic/global_position_app` | Main dashboard data |
| `GET /santander/eeic/*` | Catch-all stubs (prevents crashes) |

## Customizing dummy data

Edit these files and restart the server:

- `mock-server/data/global-position.json` — accounts, cards, balances
- `mock-server/data/customer-info.json` — user profile
- Environment: `DEMO_USERNAME`, `DEMO_PASSWORD`, `PORT`

## Physical device (not emulator)

Replace `10.0.2.2` with your computer's LAN IP in `scripts/patch-apk.py` (`MOCK_HOST`), re-run the patch script, and ensure phone and PC are on the same Wi-Fi.

## Limitations (honest scope)

This is a **demo/sandbox clone**, not a production banking app:

1. **UI fidelity** — Uses the real app's compiled UI (same screens, fonts, colors). Deep features (transfers, MB Way, investments) return stub data until you add mock endpoints.
2. **100% feature parity** — The original app has 200+ API endpoints. The mock server implements login + Global Position + generic stubs. Add more endpoints in `mock-server/src/server.js` as needed.
3. **Security layers** — Root detection, fraud (Trusteer), device binding, and push notifications are bypassed or stubbed.
4. **Legal** — For personal/educational use only. Do not distribute as a real bank app or phish users.

## Re-decompile from scratch

```bash
apktool d Santander.apk -o apktool -f
jadx -d jadx-out Santander.apk
python3 scripts/patch-apk.py
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Login fails / network error | Ensure mock-server is running; check `adb logcat` |
| SSL/certificate error | Re-run patch script (SSL pinning patch) |
| App won't install | Uninstall old clone first: `adb uninstall com.azemon.santanderclone` |
| Blank after login | Check server logs; extend `global-position.json` structure |
