# Deploy free forever (GitHub + Supabase + Vercel)

No Fly.io. No credit card traps. All three services have **permanent free tiers**.

| Service | Free forever | Role |
|---------|--------------|------|
| [GitHub](https://github.com) | Yes | Your code |
| [Supabase](https://supabase.com) | Yes | Database (PostgreSQL) |
| [Vercel](https://vercel.com) | Yes (Hobby) | Hosts API + Admin UI |

---

## Step 1 — Code is on GitHub

Repo: **https://github.com/azemon444/red_clone**

---

## Step 2 — Create free Supabase database

1. Go to [supabase.com](https://supabase.com) → **Start your project** (free)
2. Create a project (save the database password)
3. Open **Project Settings → Database**
4. Copy the **URI** connection string (mode: **Transaction** pooler, port **6543**)
   - Looks like: `postgresql://postgres.xxxx:YOUR_PASSWORD@aws-0-eu-central-1.pooler.supabase.com:6543/postgres`
5. Replace `[YOUR-PASSWORD]` with your real password

> The app auto-creates the table and seeds Shuaib demo data on first start.  
> Optional: run `supabase/schema.sql` in **SQL Editor** if you prefer.

---

## Step 3 — Deploy on Vercel (connects to GitHub)

1. Go to [vercel.com](https://vercel.com) → **Sign up with GitHub**
2. **Add New Project** → import **azemon444/red_clone**
3. Leave settings as default (Vercel reads `vercel.json` automatically)
4. Add **Environment Variables**:

| Name | Value |
|------|--------|
| `DATABASE_URL` | Your Supabase connection string (step 2) |
| `ADMIN_PASSWORD` | A password you choose (for `/admin`) |
| `NODE_ENV` | `production` |

5. Click **Deploy**
6. Copy your URL, e.g. `https://red-clone.vercel.app`
7. Add one more variable → **Redeploy**:

| Name | Value |
|------|--------|
| `PUBLIC_URL` | `https://red-clone.vercel.app` (your real URL, no trailing slash) |

---

## Step 4 — Open Admin from any browser

```
https://YOUR-PROJECT.vercel.app/admin
```

- Paste **ADMIN_PASSWORD** in the sidebar token field
- Edit customer name, balance, transactions, etc.
- Data saves to **Supabase** permanently

Health check:

```
https://YOUR-PROJECT.vercel.app/health
```

---

## Step 5 — Rebuild APK for cloud URL

On your Mac:

```bash
cd /Users/azemon/Desktop/clone_santander
python3 scripts/patch-apk.py --mock-host https://YOUR-PROJECT.vercel.app
adb install -r SantanderClone-signed.apk
adb shell pm clear com.azemon.santanderclone
```

Login: **demo** / **demo123** (change in Admin).

---

## Local development (no Supabase needed)

```bash
cd mock-server
npm install
npm start
```

Open http://localhost:9090/admin — uses JSON files in `mock-server/data/`.

To test with Supabase locally, create `mock-server/.env`:

```
DATABASE_URL=postgresql://...
ADMIN_PASSWORD=test
PUBLIC_URL=http://localhost:9090
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Admin 401 | Enter `ADMIN_PASSWORD` in sidebar |
| Deploy fails | Check `DATABASE_URL` uses port **6543** (pooler) |
| App errors | Rebuild APK with correct Vercel URL |
| Supabase paused | Open Supabase dashboard → Resume project (still free) |
| Slow first request | Vercel cold start — wait ~5s, retry |

---

## Cost summary

- **GitHub**: free
- **Supabase**: free (500 MB, pauses after 1 week idle — click resume)
- **Vercel Hobby**: free for personal projects
- **Total**: $0
