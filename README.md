# GetAJob — Cybersecurity Internship & Job Alert Bot

Checks Internshala, LinkedIn, and Adzuna every hour for cybersecurity
internships (priority) and 0-1 year jobs, and pings you on Telegram
when it finds something new. Runs entirely on GitHub Actions' free tier
— no server, no hosting cost.

## Setup (10 minutes)

### 1. Create a Telegram bot
1. Open Telegram, message **@BotFather**, send `/newbot`, follow the prompts.
2. Copy the **bot token** it gives you.
3. Message your new bot anything (e.g. "hi") so it can reply to you.
4. Get your **chat ID**: visit
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser
   right after messaging the bot, and find the `"chat":{"id":...}` value.

### 2. (Optional but recommended) Get a free Adzuna API key
1. Sign up free at https://developer.adzuna.com/
2. Copy your `app_id` and `app_key`.
   This adds a second, more reliable job source alongside the scrapers.

### 3. Push this folder to a new GitHub repo
```bash
cd getajob
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/getajob.git
git push -u origin main
```
Repo can be public or private — GitHub Actions free tier covers both
(private repos get 2,000 free minutes/month, which this easily fits in;
public repos are unlimited).

### 4. Add your secrets
In the repo: **Settings → Secrets and variables → Actions → New repository secret**
Add:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `ADZUNA_APP_ID` (optional)
- `ADZUNA_APP_KEY` (optional)

### 5. Done
The workflow (`.github/workflows/hourly.yml`) runs automatically every
hour. To test it immediately: go to the **Actions** tab → **GetAJob - Hourly
Cybersecurity Job Alert** → **Run workflow**.

## How it works
- `job_alert.py` searches Internshala (scrape), LinkedIn's public guest
  job search, and Adzuna (API) for cybersecurity roles filtered to
  internship/entry-level and Delhi NCR / India / remote.
- `seen_jobs.json` tracks which job IDs have already been sent, so you
  only get pinged once per listing. GitHub Actions commits this file
  back to the repo after each run so state persists between runs.
- Internships are tagged 🎯 and sorted first; 0-1 yr jobs are tagged 💼.

## Notes & limitations
- Internshala and LinkedIn don't have official public APIs — this uses
  their public search pages/endpoints, which can change structure or
  rate-limit occasionally. If alerts stop coming through, check the
  Actions tab for a failed run and re-check the CSS selectors in
  `fetch_internshala()` / `fetch_linkedin()`.
- Adzuna's free tier (up to 250 calls/day) comfortably covers 24 hourly
  runs/day and is the most stable source — worth setting up even though
  it's optional.
- Add more search terms or tweak `SENIOR_EXCLUDE` / `LOCATION_KEYWORDS`
  in `job_alert.py` to fine-tune matches.
