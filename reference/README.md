# UI reference — Santander Portugal clone

**→ [How to install, login, and permissions](GETTING_STARTED.md)**

Target UI captured from the real app (iPhone screenshots + screen recording). Use these when fixing layout, copy, and tab flows.

## Quick targets (`target/`)

| File | Screen |
|------|--------|
| `01-login.png` | Pre-login home — Hello Shuaib, Login, MB WAY shortcuts |
| `02-dashboard.png` | **Home** — balance **-65,72€**, account `000365542813020`, debit `*6079`, insurance |
| `03-account-detail.png` | Account drill-down + transactions |
| `04-transfer.png` | **Transfer** tab — Send money |
| `05-pay.png` | **Pay** tab |
| `06-rewards.png` | **Rewards** tab |
| `07-menu-more-options.png` | Menu → More options grid |

## Full set (`screenshots/`)

All frames from `~/Downloads/SantanderSS/` (IMG_7665–IMG_7712). Filename order ≈ app walkthrough order.

## Video (`video/santander_video.mp4`)

Full screen recording of the real app flow. Source: `~/Downloads/santander_video.mp4`.

## Demo data (must match `02-dashboard.png`)

| Field | Value |
|-------|--------|
| User | Shuaib |
| Balance | **-65,72€** |
| Account | `000365542813020` |
| IBAN | `PT50 0018 0003 6554 2813 0205 8` |
| Card | Debit `*6079` |
| Login | `demo` / `demo123` |

API seed: `mock-server/data/global-position.json` → bundled as `global_position_seed.json`.

## Clone status vs reference (Jun 2026)

| Screen | Reference | Clone today |
|--------|-----------|-------------|
| Login | ✅ `01-login.png` | ✅ Works (`demo` / `demo123`) |
| Dashboard | ✅ `02-dashboard.png` | ⚠️ **Partial** — skeleton gone, "Your balance" shows; **missing** amount, account card, debit card, quick actions row |
| Transfer | ✅ `04-transfer.png` | ⚠️ Opens (no drawable crash after latest build); may show activation prompts instead of full Send money UI |
| Pay | ✅ `05-pay.png` | ⚠️ Structure similar; favourites/scheduling empty states |
| Rewards | ✅ `06-rewards.png` | ❓ Not fully verified on device |
| Profile / Menu | screenshots | ❓ Partial |

**Next engineering focus:** finish `SimplePGPresenter.fillView` / GP wrapper so dashboard renders cards and **-65,72€** like `02-dashboard.png`.

## For agents

- Compare emulator captures under `screenshots/emulator-*` against `reference/target/`.
- Prefer `reference/target/02-dashboard.png` as the acceptance image for home tab.
- Mock API: `https://project-efnt2.vercel.app` (physical phone) or `http://10.0.2.2:9090` (emulator + local mock-server).
