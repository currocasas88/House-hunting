import os
import json
import requests
import smtplib
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from google import genai

# 1. Configuration
SEARCH_CONFIG = [
    #{"location": "New York, United States", "region_code": "US"},
    {"location": "Spain", "region_code": "ES"}
]

api_status_messages = []

def fetch_linkedin_jobs(location):
    base_url = "https://linkedin-job-search-api.p.rapidapi.com/active-jb-7d"
    query = '"VP Product Management" OR "Director Product Management" OR "Head of Product" OR "Country Manager" OR "Product Executive" OR "VP Product" OR "Director Product"'
    
    params = {
        "limit": "15",
        "title_filter": query,
        "location_filter": location,
        "description_type": "text"
    }
    
    query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    full_url = f"{base_url}?{query_string}"
    
    headers = {
        "X-RapidAPI-Key": os.environ.get("RAPIDAPI_KEY"),
        "X-RapidAPI-Host": "linkedin-job-search-api.p.rapidapi.com"
    }

    try:
        response = requests.get(full_url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            jobs = data.get("data", []) if isinstance(data, dict) else data
            api_status_messages.append(f"✅ RapidAPI: Found {len(jobs)} jobs for {location}.")
            return jobs
        api_status_messages.append(f"❌ RapidAPI Status {response.status_code} for {location}.")
        return []
    except Exception as e:
        api_status_messages.append(f"❌ RapidAPI Error: {e}")
        return []

def evaluate_jobs_in_batch(job_list, region_code):
    if not job_list: return []
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    
    batch_data = [{"title": j.get("title"), "company": j.get("organization"), "url": j.get("url"), "description": j.get("description_text", "")[:1500]} for j in job_list]

    prompt = f"Evaluate these executive jobs for {region_code}. Focus: AI, Growth. Return a JSON array: title, company, url, numeric_score, rationale."

    try:
        # UPDATED TO GEMINI 2.0 FLASH
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt + "\n\nJobs JSON:\n" + json.dumps(batch_data),
            config={'response_mime_type': 'application/json'}
        )
        
        parsed_data = json.loads(response.text.strip())
        api_status_messages.append(f"✅ Gemini AI: Evaluated {len(parsed_data)} jobs.")
        return parsed_data
    except Exception as e:
        api_status_messages.append(f"❌ Gemini AI Error: {str(e)}")
        return []

def generate_reports(all_raw_jobs, all_evaluated):
    with open("API_Raw_Discovery.txt", "w") as f:
        f.write("=== RAW DISCOVERY ===\n")
        for loc, jobs in all_raw_jobs.items():
            f.write(f"\nLocation: {loc}\n")
            for j in jobs: f.write(f"- {j.get('title')} @ {j.get('organization')}\n")
    
    with open("All_Evaluated_Jobs.txt", "w") as f:
        f.write("=== SYSTEM DIAGNOSTICS ===\n")
        for msg in api_status_messages: f.write(f"{msg}\n")
        f.write("\n=== AI SCORES ===\n")
        for j in all_evaluated:
            f.write(f"[{j.get('numeric_score')}/10] {j.get('title')} @ {j.get('company')}\n")
            f.write(f"Rationale: {j.get('rationale')}\n\n")
    
    return ["API_Raw_Discovery.txt", "All_Evaluated_Jobs.txt"]

def send_email(content, files):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = "🚀 Executive Job Matches"
    msg['From'] = os.environ.get("GMAIL_ADDRESS")
    msg['To'] = "casascurro@gmail.com"
    msg.attach(MIMEText(content, 'html'))
    
    for path in files:
        if os.path.exists(path):
            with open(path, "rb") as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read()); encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{path}"')
                msg.attach(part)
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.starttls(); s.login(os.environ.get("GMAIL_ADDRESS"), os.environ.get("GMAIL_APP_PASSWORD"))
            s.send_message(msg)
    except: pass

def main():
    all_raw = {}; all_eval = []
    for s in SEARCH_CONFIG:
        jobs = fetch_linkedin_jobs(s["location"])
        all_raw[s["location"]] = jobs
        if jobs:
            evaluated = evaluate_jobs_in_batch(jobs, s["region_code"])
            if evaluated: all_eval.extend(evaluated)
    
    files = generate_reports(all_raw, all_eval)
    high_scores = [j for j in all_eval if j.get('numeric_score', 0) >= 7.5]
    
    body = "<h2>Matches Found</h2>" if high_scores else "<h3>No matches. Check reports.</h3>"
    for m in high_scores:
        body += f"<p><b>{m.get('title')}</b> @ {m.get('company')} ({m.get('numeric_score')})<br><a href='{m.get('url')}'>Link</a></p>"
    
    send_email(body, files)

if __name__ == "__main__":
    main()
