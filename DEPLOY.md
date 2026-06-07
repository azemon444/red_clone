# Hosted mock API + Admin (free)

Edit demo data from **any browser** and use the clone app on your phone **without your Mac running**.

**Cost: $0** on [Fly.io](https://fly.io) free allowance (machine sleeps when idle).

| URL | Purpose |
|-----|---------|
| `https://YOUR-APP.fly.dev/health` | API health |
| `https://YOUR-APP.fly.dev/admin` | Admin UI |
| `https://YOUR-APP.fly.dev/santander/eeic/...` | API the patched app calls |

App login: **demo** / **demo123** (change in Admin → Customer profile).

---

## Step 1 — Deploy to Fly.io (free)

### Install Fly CLI

```bash
curl -L https://fly.io/install.sh | sh
```

Restart the terminal, then:

```bash
fly auth login
```

### Deploy (automated script)

```bash
cd /Users/azemon/Desktop/clone_santander
chmod +x scripts/deploy-fly.sh scripts/rebuild-apk-cloud.sh
./scripts/deploy-fly.sh
```

It will ask for:
- **App name** (default `santander-clone-mock` → URL `https://santander-clone-mock.fly.dev`)
- **Admin password** (for `/admin` sidebar token)
- **Region** (`ams` = Amsterdam, good for Portugal)

### Deploy (manual)

```bash
cd /Users/azemon/Desktop/clone_santander
fly launch --no-deploy --copy-config
fly volumes create santander_data --region ams --size 1
fly secrets set ADMIN_PASSWORD="your-strong-password" PUBLIC_URL="https://YOUR-APP.fly.dev"
fly deploy
```

Open `https://YOUR-APP.fly.dev/admin` → paste **ADMIN_PASSWORD** in the sidebar.

> **Note:** First request after idle may take ~10s (machine wakes up). Admin edits persist in the `/data` volume.

---

## Step 2 — Rebuild APK for cloud URL

```bash
./scripts/rebuild-apk-cloud.sh https://YOUR-APP.fly.dev
```

Install on phone:

```bash
adb install -r SantanderClone-signed.apk
adb shell pm clear com.azemon.santanderclone
```

One APK works on **emulator + physical phone** anywhere.

---

## Step 3 — Later: PostgreSQL (Supabase, still free)

When JSON files feel limiting:

1. Create free project at [supabase.com](https://supabase.com)
2. Add `DATABASE_URL` to Fly secrets
3. Migrate `mock-server/src/data-store.js` from JSON → Postgres

The clone app and admin UI stay the same — only the server storage changes.

---

## Other hosts (paid or limited free)

- **Railway** — `railway.toml` included; hobby plan may cost after trial
- **Render** — `render.yaml` included; disk on paid plans

---

## Local test (optional)

```bash
docker build -f mock-server/Dockerfile -t santander-mock .
docker run --rm -p 9090:9090 \
  -e PUBLIC_URL=http://localhost:9090 \
  -e ADMIN_PASSWORD=test \
  -v santander-data:/data \
  santander-mock
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Admin shows 401 | Enter `ADMIN_PASSWORD` in sidebar token field |
| App shows errors | Rebuild APK with correct `--mock-host` URL |
| Old data in app | Force-close app or `adb shell pm clear com.azemon.santanderclone` |
| Slow first load | Fly machine was sleeping — wait a few seconds |
