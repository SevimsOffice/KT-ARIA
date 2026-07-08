# ARIA — Automated Revenue Intelligence Agent
### Built for Sevim Durmuş / aiandtech.cloud

MEET ARIA
<img width="1080" height="1456" alt="Aria Sales Agent AIANDTECH TURKEY" src="https://github.com/user-attachments/assets/ff5f8b64-fcfb-4019-a0e3-25f24aa3fb34" />


ARIA runs every morning at 7 AM Turkey time, finds new Bursa OSB companies,
researches them, writes personalized Turkish outreach emails, and adds them
to your Instantly.ai campaign — automatically. You only get a Telegram
message when someone says yes.

---

## What ARIA Does Daily

```
07:00 AM Turkey  →  Scrape NOSAB + DOSAB + KAYAPA for new companies
                 →  Enrich with emails (Apollo → Hunter → smart guess)
                 →  Research each company website (Claude AI)
                 →  Write personalized Turkish opening line (Claude AI)
                 →  Add to Instantly.ai campaign (sends Email 1 + follow-ups)
                 →  Update Google Sheets master tracker
                 →  Telegram: "Today: X new companies, Y emails sent"

Every 2 hours   →  Check Instantly.ai for new replies
                 →  Claude classifies: HOT / WARM / COLD / UNSUBSCRIBE
                 →  HOT: Instant Telegram alert + suggested response
                 →  WARM: Telegram notice + auto follow-up queued

Every Sunday    →  Weekly intelligence report to Telegram
                    (what worked, what didn't, which sector to focus on)
```

---

## One-Time Setup (Do This Before First Run)

### 1. Google Sheets API
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project: "ARIA"
3. Enable **Google Sheets API** and **Google Drive API**
4. Go to **Credentials → Service Account** → Create service account
5. Download the JSON key file
6. Create a new Google Sheet → copy its ID from the URL
7. Share that sheet with the service account email (from the JSON file) as **Editor**
8. Paste the full JSON content into `GOOGLE_SERVICE_ACCOUNT_JSON` in your `.env`

### 2. Instantly.ai
1. Sign up at [app.instantly.ai](https://app.instantly.ai)
2. Add your email: `sevim@aiandtech-info.com`
3. Start the **warm-up** process (takes 2 weeks — start today!)
4. Create a campaign with 3-step sequence:
   - Email 1: Use `{{personalized_line}}` and `{{sector}}` variables
   - Email 2: Day +4 (follow-up with ROI formula)
   - Email 3: Day +8 (final, sector-specific example)
   - Turn ON: "Stop sending when lead replies"
5. Go to **Settings → API** → copy your API key
6. Copy the campaign ID from the campaign URL

### 3. Telegram Bot
1. Open Telegram → search `@BotFather`
2. Send `/newbot` → follow prompts → copy the bot token
3. Send any message to your new bot
4. Visit: `https://api.telegram.org/bot{YOUR_TOKEN}/getUpdates`
5. Find `"chat":{"id": 123456789}` — that's your chat ID

### 4. Apollo.io
1. Sign up at [app.apollo.io](https://app.apollo.io) (free tier: 50 credits/month)
2. Go to **Settings → Integrations → API Keys** → create a key

### 5. GitHub
1. Create a **private** repo: `aria-outreach`
2. Go to **Settings → Secrets and variables → Actions**
3. Add all secrets from `.env.example` as repository secrets
4. Push this code to the repo
5. Go to **Actions** tab → enable workflows

---

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill in your secrets
cp .env.example .env
# Edit .env with your actual keys

# Test without sending anything
python scripts/run_daily_pipeline.py --dry-run

# Process only 3 companies for testing
python scripts/run_daily_pipeline.py --limit 3

# Check replies
python scripts/run_reply_handler.py --dry-run

# Weekly report
python scripts/run_weekly_report.py
```

---

## Project Structure

```
ARIA/
├── .github/workflows/     # GitHub Actions cron jobs
├── src/
│   ├── config.py          # Environment variable loader
│   ├── database/          # Google Sheets read/write
│   ├── scraper/           # NOSAB, DOSAB, KAYAPA website scrapers
│   ├── enrichment/        # Apollo, Hunter, email pattern guesser
│   ├── research/          # Company website research (Claude)
│   ├── outreach/          # Email composer (Claude) + Instantly.ai client
│   ├── replies/           # Reply fetcher + classifier (Claude)
│   └── notifications/     # Telegram alerts
├── scripts/               # Orchestrators — what GitHub Actions runs
├── templates/             # Email templates + Claude prompts
├── .env.example           # Template for your secrets
└── requirements.txt
```

---

## Monthly Cost

| Tool | Cost |
|------|------|
| GitHub Actions | Free |
| Google Sheets API | Free |
| Instantly.ai | $37/month |
| Claude API (Haiku, 50/day) | ~$3–5/month |
| Apollo.io free tier | Free (50/month) |
| Hunter.io free tier | Free (25/month) |
| **Total** | **~$40–42/month** |

One paid workshop (8,000 TL ≈ $240) covers 6 months of ARIA.

---

## Troubleshooting

**GitHub Actions failing?**
- Check that all secrets are added in repo Settings → Secrets → Actions
- Run `workflow_dispatch` manually from the Actions tab to see live logs

**No emails being found?**
- Check Apollo API key is valid
- Make sure campaign is in "active" state in Instantly dashboard
- Run with `--dry-run` to see what ARIA finds without sending

**Telegram not receiving messages?**
- Verify bot token is correct
- Make sure you've sent at least one message to the bot first
- Check chat ID is your personal ID (not a group)

---

*Built with Claude Code · aiandtech.cloud*
