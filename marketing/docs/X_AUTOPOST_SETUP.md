# FQ X auto-poster — setup ($0)

Posts one tweet per run from `content/tweets.csv` via the **X API Free tier**
(write). Rotates deterministically by time slot → cycles the whole bank before
repeating (evergreen). No paid API, no server required.

Files: `scripts/x-autopost.py` · `content/tweets.csv` · `.github/workflows/x-autopost.yml`.

---

## 1. Get the keys (free) — ~5 min
1. Go to **developer.x.com** → sign up for the **Free** plan → create a Project + App.
2. In the App's **User authentication settings**: enable OAuth 1.0a, set app
   permissions to **Read and write** (required to post).
3. Generate/copy these 4 values:
   - **API Key** and **API Key Secret** (consumer key/secret)
   - **Access Token** and **Access Token Secret** (for *your* account)
   - ⚠️ Regenerate the Access Token AFTER setting "Read and write", or it stays read-only.

## 2. Choose where it runs

### Option A — GitHub Actions (free, no server) ✅ recommended
1. In the repo: **Settings → Secrets and variables → Actions → New repository secret**.
   Add: `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`.
2. The workflow `.github/workflows/x-autopost.yml` runs 3×/day (06/14/22 UTC).
   **Scheduled runs only fire from the DEFAULT branch** — merge the workflow +
   script + CSV to your default branch to activate the cron.
3. Test anytime without waiting: **Actions tab → "FQ X auto-post" → Run workflow**
   (leave "Dry run" checked first to see what it would post; uncheck to post live).

### Option B — any cron (Railway / VPS / your laptop)
```bash
pip install tweepy
export X_API_KEY=... X_API_SECRET=... X_ACCESS_TOKEN=... X_ACCESS_SECRET=...
export POST_INTERVAL_HOURS=8
python3 marketing/scripts/x-autopost.py     # add to crontab every 8h
```
Crontab example (every 8h): `0 */8 * * * cd /path/fq-bot && python3 marketing/scripts/x-autopost.py`

## 3. Test safely
```bash
AUTOPOST_DRYRUN=1 python3 marketing/scripts/x-autopost.py     # prints, never posts
AUTOPOST_INDEX=5 AUTOPOST_DRYRUN=1 python3 marketing/scripts/x-autopost.py  # preview a row
```

## 4. Cadence & rotation
- `POST_INTERVAL_HOURS` **must match** your cron spacing (default 8h = 3/day).
  The script maps each time slot to the next tweet, so spacing the cron 8h apart
  advances exactly one tweet per run.
- 28 tweets at 3/day ≈ a fresh tweet for ~9 days before it loops. Refill / reorder
  `content/tweets.csv` anytime (keep pillars alternating; CTA every ~5 rows).

## 5. Rules
- Free tier write cap ≈ 1,500/month — way above this cadence.
- Keep `tweets.csv` compliant: no profit promises, no %, no guarantees.
- Don't bolt on auto-DM / auto-follow / auto-reply — that's what gets accounts
  banned. This poster only **publishes**; keep replies human.
