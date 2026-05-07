"""
House Hunting Agent
-------------------
Fetches property listings from a real estate API on a schedule,
scores each against a configurable preferences profile using Google Gemini AI,
and delivers a curated digest by email.

Runs on a schedule via GitHub Actions. All credentials are injected as
environment variables — no secrets are ever hardcoded.

Setup:
    1. Copy .env.example to .env for local runs (never commit .env)
    2. Add RAPIDAPI_KEY, GEMINI_API_KEY, GMAIL_APP_PASSWORD, GMAIL_ADDRESS
       as GitHub Actions secrets for automated runs.

Author: Curro Casas (github.com/currocasas88)
"""

import os
import json
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from google import genai

# ---------------------------------------------------------------------------
# CONFIGURATION — edit this block to match your search criteria
# ---------------------------------------------------------------------------

# Locations to search. Each entry is passed as a city/zip query.
SEARCH_LOCATIONS = [
    "New York, NY",
    # "Brooklyn, NY",
    # "Jersey City, NJ",
]

# Property preferences — used by the AI to score fit.
PREFERENCES = """
Looking for a rental apartment with the following priorities:
- Budget: $3,500–$5,500/month
- Size: 2+ bedrooms
- Must-haves: in-unit laundry, elevator building, pet-friendly
- Nice-to-have: doorman, gym, outdoor space, home office space
- Neighborhoods: Lower Manhattan, Midtown East, Upper East Side, Long Island City
- Avoid: ground floor, no-elevator walkups above 4th floor, studios
"""

# Score threshold — only listings at or above this score are highlighted.
SCORE_THRESHOLD = 7.5

# Max listings to fetch per location (keep low to stay within free tier).
MAX_LISTINGS = 10

# ---------------------------------------------------------------------------
# GLOBALS
# ---------------------------------------------------------------------------

status_messages = []


# ---------------------------------------------------------------------------
# PROPERTY FETCHING — Zillow API via RapidAPI (free tier available)
# ---------------------------------------------------------------------------

def fetch_listings(location: str) -> list[dict]:
    """
    Fetches rental listings for a given location using the Zillow API.
    Returns a list of listing dicts, or an empty list on error.

    Note: API field names may vary — check the RapidAPI docs for the
    current Zillow API response schema and update normalize_listing() if needed.
    """
    url = "https://zillow-com1.p.rapidapi.com/propertyExtendedSearch"
    params = {
        "location":   location,
        "home_type":  "Apartments",
        "rentMinPrice": "3500",
        "rentMaxPrice": "5500",
        "bedsMin":    "2",
        "status_type": "ForRent",
    }

    headers = {
        "X-RapidAPI-Key":  os.environ["RAPIDAPI_KEY"],
        "X-RapidAPI-Host": "zillow-com1.p.rapidapi.com",
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        listings = data.get("props", [])[:MAX_LISTINGS]
        status_messages.append(f"✅ Zillow API: {len(listings)} listings for '{location}'.")
        return listings
    except requests.exceptions.HTTPError as e:
        status_messages.append(f"❌ Zillow API HTTP error ({location}): {e}")
    except requests.exceptions.RequestException as e:
        status_messages.append(f"❌ Zillow API request failed ({location}): {e}")
    except (KeyError, ValueError) as e:
        status_messages.append(f"❌ Zillow API parse error ({location}): {e}")
    return []


def normalize_listing(raw: dict) -> dict:
    """
    Maps raw Zillow API fields to a consistent internal schema.
    Update field names here if the API response shape changes.
    """
    return {
        "address":   raw.get("address", "Unknown Address"),
        "price":     raw.get("price", "Unknown Price"),
        "beds":      raw.get("bedrooms", "?"),
        "baths":     raw.get("bathrooms", "?"),
        "sqft":      raw.get("livingArea", "?"),
        "url":       raw.get("detailUrl", "#"),
        "img":       raw.get("imgSrc", ""),
        "status":    raw.get("statusText", ""),
        "days_on":   raw.get("daysOnZillow", "?"),
        "latitude":  raw.get("latitude"),
        "longitude": raw.get("longitude"),
    }


# ---------------------------------------------------------------------------
# AI SCORING — Google Gemini (free tier)
# ---------------------------------------------------------------------------

SCORING_PROMPT_TEMPLATE = """
You are a real estate concierge helping a busy professional find an apartment.
Score the following listings against their stated preferences.

PREFERENCES:
{preferences}

SCORING GUIDE:
- 9-10: Exceptional match. Hits all must-haves, right neighborhood, great value.
- 7-8:  Strong match. Most criteria met, minor tradeoffs.
- 5-6:  Partial match. Some criteria met but notable gaps.
- 1-4:  Poor match. Multiple dealbreakers.

Return ONLY a valid JSON array. Each element must have exactly these keys:
  address, price, beds, url, numeric_score (float), rationale (1-2 sentences max), flags (list of strings — dealbreakers or highlights)

No markdown. No preamble. No trailing text. Valid JSON only.

LISTINGS:
{listings_json}
"""


def evaluate_listings(listings: list[dict]) -> list[dict]:
    """
    Sends a batch of normalized listings to Gemini for preference scoring.
    Returns a list of scored listing dicts.
    """
    if not listings:
        return []

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    prompt = SCORING_PROMPT_TEMPLATE.format(
        preferences=PREFERENCES.strip(),
        listings_json=json.dumps(listings, ensure_ascii=False, indent=2),
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        scored = json.loads(response.text.strip())
        status_messages.append(f"✅ Gemini AI: scored {len(scored)} listings.")
        return scored
    except json.JSONDecodeError as e:
        status_messages.append(f"❌ Gemini JSON parse error: {e}")
    except Exception as e:
        status_messages.append(f"❌ Gemini error: {e}")
    return []


# ---------------------------------------------------------------------------
# REPORTING
# ---------------------------------------------------------------------------

def generate_report(all_raw: dict, all_scored: list[dict]) -> list[str]:
    """
    Writes two plain-text report files.
    Returns a list of file paths.
    """
    with open("raw_listings.txt", "w", encoding="utf-8") as f:
        f.write("=== RAW LISTINGS ===\n")
        for loc, listings in all_raw.items():
            f.write(f"\nLocation: {loc} ({len(listings)} listings)\n")
            f.write("-" * 40 + "\n")
            for l in listings:
                f.write(f"  {l['address']} — {l['price']} — {l['beds']}bd/{l['baths']}ba\n")
                f.write(f"  {l['url']}\n\n")

    sorted_scored = sorted(all_scored, key=lambda x: x.get("numeric_score", 0), reverse=True)

    with open("scored_listings.txt", "w", encoding="utf-8") as f:
        f.write("=== SYSTEM DIAGNOSTICS ===\n")
        for msg in status_messages:
            f.write(f"  {msg}\n")

        f.write("\n=== AI-SCORED LISTINGS ===\n")
        for l in sorted_scored:
            score = l.get("numeric_score", "?")
            flags = ", ".join(l.get("flags", []))
            f.write(f"\n[{score}/10] {l.get('address')} — {l.get('price')}\n")
            f.write(f"  {l.get('beds')} beds\n")
            f.write(f"  Rationale: {l.get('rationale')}\n")
            if flags:
                f.write(f"  Flags: {flags}\n")
            f.write(f"  URL: {l.get('url')}\n")

    return ["raw_listings.txt", "scored_listings.txt"]


# ---------------------------------------------------------------------------
# EMAIL DELIVERY
# ---------------------------------------------------------------------------

def build_email_html(high_matches: list[dict], all_scored: list[dict]) -> str:
    """Builds a clean HTML email body."""
    lines = ["<html><body style='font-family:sans-serif;max-width:600px;margin:auto;color:#1a1916;'>"]
    lines.append("<h2 style='border-bottom:2px solid #2a5c45;padding-bottom:8px;'>🏠 Property Digest</h2>")

    if high_matches:
        lines.append(f"<p><b>{len(high_matches)} listing(s)</b> above match score {SCORE_THRESHOLD}:</p>")
        for m in sorted(high_matches, key=lambda x: x.get("numeric_score", 0), reverse=True):
            flags_html = ""
            if m.get("flags"):
                flags_html = "<br><small style='color:#6b6860;'>⚑ " + " · ".join(m["flags"]) + "</small>"
            lines.append(f"""
            <div style='border:1px solid #e0dbd2;padding:16px;margin:12px 0;border-radius:4px;'>
              <b style='font-size:15px;'>{m.get('address')}</b>
              <span style='float:right;background:#2a5c45;color:#fff;padding:2px 8px;
                           border-radius:12px;font-size:13px;'>{m.get('numeric_score')}/10</span><br>
              <span style='color:#2a5c45;font-weight:bold;'>{m.get('price')}</span>
              · {m.get('beds')} beds
              <p style='margin:8px 0;font-size:14px;color:#6b6860;'>{m.get('rationale','')}{flags_html}</p>
              <a href='{m.get('url','#')}' style='color:#2a5c45;font-weight:bold;'>View Listing →</a>
            </div>""")
    else:
        lines.append("<p>No listings exceeded the score threshold this run. See attached report for full results.</p>")

    lines.append(f"<hr style='margin:24px 0;border-color:#e0dbd2;'>")
    lines.append(f"<p style='font-size:12px;color:#c8c5be;'>")
    lines.append(f"{len(all_scored)} total listings scored · Threshold: {SCORE_THRESHOLD}/10<br>")
    lines.append("Full details in attached reports.</p>")
    lines.append("</body></html>")
    return "\n".join(lines)


def send_email(html_body: str, attachments: list[str]) -> None:
    """Sends the digest email with report attachments via Gmail SMTP."""
    gmail_address  = os.environ["GMAIL_ADDRESS"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEMultipart("mixed")
    msg["Subject"] = "🏠 Property Digest — Top Listings This Week"
    msg["From"]    = gmail_address
    msg["To"]      = gmail_address
    msg.attach(MIMEText(html_body, "html"))

    for path in attachments:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(path)}"')
        msg.attach(part)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(gmail_address, gmail_password)
            server.send_message(msg)
        status_messages.append("✅ Email delivered.")
    except smtplib.SMTPException as e:
        status_messages.append(f"❌ Email error: {e}")
        raise


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    all_raw: dict[str, list[dict]] = {}
    all_scored: list[dict] = []

    for location in SEARCH_LOCATIONS:
        raw       = fetch_listings(location)
        norm      = [normalize_listing(l) for l in raw]
        all_raw[location] = norm

        if norm:
            scored = evaluate_listings(norm)
            all_scored.extend(scored)

    report_files = generate_report(all_raw, all_scored)
    high_matches = [l for l in all_scored if l.get("numeric_score", 0) >= SCORE_THRESHOLD]
    html_body    = build_email_html(high_matches, all_scored)

    send_email(html_body, report_files)
    print("\n".join(status_messages))


if __name__ == "__main__":
    main()
