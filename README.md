# 🏠 House Hunting Agent

An autonomous pipeline that fetches rental listings, scores them against your
personal preferences using Google Gemini AI, and delivers a curated weekly
digest to your inbox.

Built by [Curro Casas](https://currocasas.com) — same architecture as the
[Job Hunter Agent](https://github.com/currocasas88/job-agent), applied to real estate.

---

## What It Does

1. **Fetches** rental listings from Zillow (via RapidAPI) for configured locations
2. **Scores** each listing against your stated preferences using Gemini AI
3. **Emails** a curated digest with top matches highlighted + full reports attached

Runs automatically every Monday via GitHub Actions.

---

## Architecture

```
GitHub Actions (cron)
        │
        ▼
  fetch_listings()      ← Zillow API via RapidAPI
        │
        ▼
  normalize_listing()   ← Consistent schema
        │
        ▼
  evaluate_listings()   ← Gemini 2.0 Flash (free tier)
        │
        ▼
  generate_report()     ← raw_listings.txt + scored_listings.txt
        │
        ▼
  send_email()          ← Gmail SMTP with HTML digest + attachments
```

---

## APIs Used

| API | Purpose | Cost |
|-----|---------|------|
| [Zillow API via RapidAPI](https://rapidapi.com/apimaker/api/zillow-com1) | Property listings | Free tier available |
| [Google Gemini 2.0 Flash](https://ai.google.dev/) | AI scoring | Free tier |
| Gmail SMTP | Email delivery | Free |

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/currocasas88/house-hunting.git
cd house-hunting
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env with your actual keys
```

### 3. Customize your preferences

Edit the config block at the top of `main.py`:

```python
SEARCH_LOCATIONS = [
    "New York, NY",
    "Brooklyn, NY",
]

PREFERENCES = """
Looking for a 2-bed rental, $3,500–$5,500/month.
Must-haves: in-unit laundry, elevator, pet-friendly.
Preferred neighborhoods: Lower Manhattan, Midtown East.
"""

SCORE_THRESHOLD = 7.5
```

### 4. Run locally

```bash
python main.py
```

### 5. Deploy to GitHub Actions

Add secrets in **Settings → Secrets → Actions**:

| Secret | Value |
|--------|-------|
| `RAPIDAPI_KEY` | Your RapidAPI key |
| `GEMINI_API_KEY` | Your Google AI Studio key |
| `GMAIL_APP_PASSWORD` | [Gmail App Password](https://support.google.com/accounts/answer/185833) |
| `GMAIL_ADDRESS` | Your Gmail address |

---

## Output Example

```
[9.1/10] 420 E 64th St, New York, NY — $4,200/month
  2 beds · Doorman building, in-unit W/D, gym
  Rationale: Strong match on all must-haves, prime UES location.
  Flags: Pet policy — confirm breed restrictions
  View Listing →
```

---

## Related Projects

- [Job Hunter Agent](https://github.com/currocasas88/job-agent) — Same pattern for job search
- [Portfolio](https://currocasas.com)

---

## License

MIT — adapt freely to your own search criteria.
