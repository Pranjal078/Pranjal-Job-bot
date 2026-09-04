# 🔔 Job Search Alert Bot

A daily-run bot that pulls fresh job listings from public APIs and feeds, deduplicates them, filters by your criteria, and delivers a digest to your Telegram (or email inbox).

**No LinkedIn login automation. No scraping of authenticated pages. No auto-apply.**

---

## What It Does

Every day (configurable cron), the bot:
1. **Fetches** listings from RemoteOK, We Work Remotely, six company career pages, and LinkedIn job-alert emails you already receive
2. **Filters** by title keywords, location, posting age (7 days), and compensation floor
3. **Deduplicates** using a local SQLite database — you only see each listing once
4. **Sends** a grouped, formatted Telegram digest (or email fallback)

---

## Project Structure

```
Job_search_bot/
├── config.yaml              ← Edit this to change your criteria
├── main.py                  ← Orchestrator (fetch → filter → store → notify)
├── filter.py                ← Keyword / location / age / dedup logic
├── store.py                 ← SQLite dedup store
├── notify.py                ← Telegram + email sender
├── setup_gmail.py           ← One-time Gmail OAuth2 setup
├── requirements.txt
├── .env.example             ← Copy to .env and fill in credentials
├── fetch/
│   ├── remoteok.py          ← RemoteOK public JSON API
│   ├── weworkremotely.py    ← We Work Remotely RSS
│   ├── company_careers.py   ← HSBC, Wells Fargo, Amex, JPMC, Mastercard, Walmart
│   ├── linkedin_email.py    ← Parse LinkedIn job-alert emails (Gmail API / IMAP)
│   ├── wellfound.py         ← Stub (API unavailable)
│   └── naukri.py            ← Stub (no public API)
├── tests/
│   ├── test_filter.py
│   ├── test_store.py
│   └── test_fetch_remoteok.py
└── .github/workflows/
    └── daily_job_alert.yml  ← GitHub Actions cron
```

---

## Quick Start (Local)

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/job-search-bot.git
cd job-search-bot

python3.11 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
# Open .env and fill in your keys (see "API Keys" section below)
```

### 3. Edit your criteria

Open `config.yaml` and adjust:
- `filters.title_keywords` — job titles you're looking for
- `filters.locations` — locations to include
- `filters.comp_floor_lpa` — compensation floor (INR LPA)
- `sources.*` — enable/disable individual sources
- `notification.channel` — `telegram` or `email`

### 4. Dry run (no notifications)

```bash
python main.py --dry-run
```

This fetches real data, applies filters, and prints the digest to your terminal. Nothing is written to the database. Perfect for testing.

### 5. Test a single source

```bash
python main.py --source remoteok --dry-run
python main.py --source weworkremotely --dry-run
python main.py --source company_careers --dry-run
python main.py --source linkedin_email --dry-run
```

### 6. Full run

```bash
python main.py
```

### 7. Check stats

```bash
python main.py --stats
```

---

## API Keys Needed

### Telegram Bot (required for Telegram notifications)

1. Open Telegram and message [@BotFather](https://t.me/botfather)
2. Send `/newbot`, follow the prompts → get your **Bot Token**
3. Message your new bot once to activate the chat
4. Get your **Chat ID** by messaging [@userinfobot](https://t.me/userinfobot)
5. Add to `.env`:
   ```
   TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNO...
   TELEGRAM_CHAT_ID=123456789
   ```

### Gmail API — for LinkedIn email parsing

You only need this if `sources.linkedin_email: true` in `config.yaml`.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use an existing one)
3. **Enable the Gmail API**: APIs & Services → Enable APIs → search "Gmail API" → Enable
4. **Create OAuth2 credentials**:
   - APIs & Services → Credentials → Create Credentials → OAuth client ID
   - Application type: **Desktop app**
   - Download the JSON → save as `credentials.json` in project root
5. Run the setup script:
   ```bash
   python setup_gmail.py
   ```
   This opens a browser, asks you to sign in with Google, and saves `token.json`.

> **Privacy**: The bot only requests `gmail.readonly` scope (read-only). It searches only for emails from `jobalerts-noreply@linkedin.com`. It never reads, modifies, or deletes your email.

### SMTP Email (optional fallback)

If you prefer email over Telegram, or as a fallback:

```
SMTP_USER=yourname@gmail.com
SMTP_PASSWORD=your_app_password   # Gmail: 16-char App Password (not your main password)
SMTP_TO=yourname@gmail.com
```

For Gmail App Passwords: [Google Account → Security → 2-Step Verification → App passwords](https://myaccount.google.com/apppasswords)

---

## GitHub Actions Setup (Free, No Server)

The bot runs for free on GitHub Actions — no server needed.

### Step 1: Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/job-search-bot.git
git push -u origin main
```

> ⚠️ Make sure `.gitignore` is committed first so `.env`, `token.json`, and `credentials.json` are **never pushed**.

### Step 2: Add GitHub Secrets

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |
| `GMAIL_TOKEN_JSON` | Full contents of `token.json` (see below) |
| `GMAIL_CREDENTIALS_JSON` | Full contents of `credentials.json` |
| `SMTP_USER` | Your email (if using email fallback) |
| `SMTP_PASSWORD` | Your App Password |
| `SMTP_TO` | Destination email |

**To get `GMAIL_TOKEN_JSON`:**
```bash
cat token.json   # Copy the entire JSON output and paste as the secret value
```

### Step 3: Enable the workflow

The workflow is in `.github/workflows/daily_job_alert.yml`.
It runs at **06:00 UTC daily (11:30 AM IST)**.

To trigger it manually:
1. Go to your repo → **Actions** → **Daily Job Alert**
2. Click **Run workflow** → optionally enable dry run or select a source

### Step 4: Adjust the cron time

Edit `.github/workflows/daily_job_alert.yml`:
```yaml
- cron: '0 6 * * *'   # Change to your preferred UTC time
```
Use [crontab.guru](https://crontab.guru) to calculate your time.

---

## Digest Format (Telegram)

```
🔔 Job Alert Digest — 2024-01-15 06:00 UTC
📋 8 new listing(s) found

── RemoteOK ──
• Data Analyst @ Stripe
  📍 Remote  💰 $90,000 – $120,000 USD/yr ✅  📅 Jan 14

• Product Analyst @ Notion
  📍 Remote  💰 —  📅 Jan 15

── WeWorkRemotely ──
• Business Analyst @ Acme Corp
  📍 WORLDWIDE  💰 —  📅 Jan 14

── JPMC Careers ──
• Data Analyst, Consumer Banking @ JPMorgan Chase
  📍 Gurgaon, India  💰 —  📅 Jan 13
```

**`✅`** next to compensation means it meets your `comp_floor_lpa` threshold.

If more than 10 jobs are found, they're split across multiple paginated messages.

---

## Customizing Sources

### Add a new company career page

In `fetch/company_careers.py`:
1. Write a `_fetch_yourcompany()` function
2. Add it to `_FETCHERS = { "yourcompany": _fetch_yourcompany }`
3. Add an entry to `company_targets` in `config.yaml`:
   ```yaml
   - name: Your Company
     type: yourcompany
     enabled: true
   ```

### Disable a source

In `config.yaml`, set it to `false`:
```yaml
sources:
  company_careers: false   # Skip all company career pages
```

---

## Running Tests

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

Expected output:
```
tests/test_filter.py::TestUrlHash::test_same_url_same_hash PASSED
tests/test_filter.py::TestKeywordMatching::test_exact_match PASSED
... (all tests)
tests/test_store.py::TestJobStoreConnect::test_creates_db_file PASSED
tests/test_fetch_remoteok.py::TestRemoteOKFetch::test_returns_normalized_jobs PASSED
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No jobs found | Run `--dry-run` and check logs for filter stats. Broaden keywords or locations in `config.yaml`. |
| Telegram not sending | Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`. Make sure you've messaged your bot first. |
| Gmail auth error | Re-run `python setup_gmail.py`. Token may have been revoked. |
| Company career page returning 0 jobs | That company's public API endpoint may have changed. Check logs for warnings. |
| `ImportError` | Make sure your virtualenv is active and `pip install -r requirements.txt` completed. |
| GitHub Actions: "token.json not found" | Ensure `GMAIL_TOKEN_JSON` secret is set in GitHub repo settings. |

---

## What's Explicitly Out of Scope

- ❌ Auto-apply to any job listing
- ❌ Resume tailoring or cover letter generation
- ❌ LinkedIn login or any LinkedIn write actions
- ❌ Scraping of authenticated/JS-rendered pages
- ❌ Wellfound / Naukri (no public API — stubs exist for future use)

---

## License

MIT — do whatever you want, just don't auto-apply to jobs with it.
