"""
GetAJob — Cybersecurity Internship & Entry-Level Job Alert Bot
-----------------------------------------------------
Searches Internshala, LinkedIn (guest job search), and Adzuna for
cybersecurity internships (priority) and 0-1 year experience jobs
around Delhi NCR / India, then sends new results to Telegram.

Designed to run every hour via GitHub Actions (see .github/workflows/hourly.yml).
State (which jobs have already been alerted) is kept in seen_jobs.json,
which the workflow commits back to the repo after each run.
"""

import os
import re
import json
import time
import requests

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------

SEEN_FILE = "seen_jobs.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Adzuna is optional but recommended - free signup at https://developer.adzuna.com/
ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "")

# Keywords used across all sources. Internships are searched first/flagged as priority.
SEARCH_TERMS = [
    "cyber security",
    "cybersecurity",
    "penetration testing",
    "SOC analyst",
    "VAPT",
    "information security",
]

# Words that suggest a listing is NOT entry-level (used to filter out senior roles
# from sources that don't support an experience filter, e.g. LinkedIn/Internshala titles)
SENIOR_EXCLUDE = [
    "senior", "sr.", "sr ", "lead", "manager", "principal", "architect",
    "5+ years", "7+ years", "10+ years", "director", "head of",
]

LOCATIONS = ["New Delhi", "Noida", "Greater Noida", "Ghaziabad", "Gurgaon", "Remote"]

LOCATION_KEYWORDS = ["delhi", "ncr", "gurugram", "gurgaon", "noida", "greater noida", "ghaziabad", "india", "remote", "work from home"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}


# ----------------------------------------------------------------------
# STATE (dedupe across runs)
# ----------------------------------------------------------------------

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            try:
                return set(json.load(f))
            except json.JSONDecodeError:
                return set()
    return set()


def save_seen(seen_ids):
    # keep the file from growing forever - cap at the most recent 3000 ids
    trimmed = list(seen_ids)[-3000:]
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f)


# ----------------------------------------------------------------------
# SOURCE 1: Internshala (internships - priority source)
# ----------------------------------------------------------------------

def fetch_internshala():
    """
    Scrapes Internshala's cyber-security internship listing page.
    Internshala doesn't offer a public API, so this parses the public HTML.
    NOTE: page structure can change over time; selectors may need updates.
    """
    results = []
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return results

    url = "https://internshala.com/internships/cyber-security-internship/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        return results

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select("div.individual_internship")

    for card in cards:
        try:
            id_ = card.get("internshipid") or card.get("data-id")
            title_el = card.select_one("h3.job-internship-name a, .job-title-href")
            company_el = card.select_one(".company-name")
            location_el = card.select_one(".locations")
            link = None
            if title_el and title_el.get("href"):
                link = "https://internshala.com" + title_el["href"]

            title = title_el.get_text(strip=True) if title_el else None
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            location_text = location_el.get_text(strip=True).lower() if location_el else ""

            if not title or not link:
                continue

            # location filter: Delhi NCR, India, or remote/WFH
            if location_text and not any(loc in location_text for loc in LOCATION_KEYWORDS):
                continue

            results.append({
                "id": f"internshala:{id_ or link}",
                "title": title,
                "company": company,
                "location": location_el.get_text(strip=True) if location_el else "India",
                "link": link,
                "source": "Internshala",
                "priority": True,  # internships are priority
            })
        except Exception:
            continue

    return results


# ----------------------------------------------------------------------
# SOURCE 2: LinkedIn guest job search (internship + entry level jobs)
# ----------------------------------------------------------------------

def fetch_linkedin(keywords="cyber security", location="Delhi NCR, India", remote=False):
    """
    Uses LinkedIn's public "guest" job search endpoint (no login required).
    f_E=1,2 restricts to Internship (1) and Entry level (2) experience.
    f_WT=2 restricts to remote workplace type (used when remote=True).
    This is an unofficial endpoint and may break or rate-limit; treated as best-effort.
    """
    results = []
    url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    params = {
        "keywords": keywords,
        "location": "India" if remote else location,
        "f_E": "1,2",       # internship, entry level
        "f_TPR": "r86400",  # posted in the last 24 hours (seen_jobs.json dedupes repeats)
        "start": 0,
    }
    if remote:
        params["f_WT"] = "2"  # remote workplace type
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
        if resp.status_code != 200:
            return results
    except requests.RequestException:
        return results

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return results

    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select("li")

    for card in cards:
        try:
            title_el = card.select_one(".base-search-card__title")
            company_el = card.select_one(".base-search-card__subtitle")
            location_el = card.select_one(".job-search-card__location")
            link_el = card.select_one("a.base-card__full-link")

            if not title_el or not link_el:
                continue

            title = title_el.get_text(strip=True)
            link = link_el["href"].split("?")[0]
            job_id = link.rstrip("/").split("-")[-1]

            title_lower = title.lower()
            if any(bad in title_lower for bad in SENIOR_EXCLUDE):
                continue

            results.append({
                "id": f"linkedin:{job_id}",
                "title": title,
                "company": company_el.get_text(strip=True) if company_el else "Unknown",
                "location": location_el.get_text(strip=True) if location_el else location,
                "link": link,
                "source": "LinkedIn",
                "priority": "intern" in title_lower,
            })
        except Exception:
            continue

    return results


# ----------------------------------------------------------------------
# SOURCE 3: Adzuna API (structured, free tier - optional but more reliable)
# ----------------------------------------------------------------------

def fetch_adzuna(keywords="cyber security", where="Delhi NCR"):
    results = []
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        print("Adzuna: skipped (no app_id/app_key configured)")
        return results  # skipped if not configured

    url = "https://api.adzuna.com/v1/api/jobs/in/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "what": keywords,
        "where": where,
        "results_per_page": 20,
        "max_days_old": 3,
        "content-type": "application/json",
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"Adzuna: request failed - {e}")
        return results
    except ValueError:
        print(f"Adzuna: bad response (status {resp.status_code}) - {resp.text[:200]}")
        return results

    for job in data.get("results", []):
        title = job.get("title", "")
        title_lower = title.lower()
        if any(bad in title_lower for bad in SENIOR_EXCLUDE):
            continue

        results.append({
            "id": f"adzuna:{job.get('id')}",
            "title": title,
            "company": job.get("company", {}).get("display_name", "Unknown"),
            "location": job.get("location", {}).get("display_name", where),
            "link": job.get("redirect_url", ""),
            "source": "Adzuna",
            "priority": "intern" in title_lower,
        })

    return results


# ----------------------------------------------------------------------
# TELEGRAM
# ----------------------------------------------------------------------

def send_telegram(job):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured - skipping send.")
        return

    tag = "🎯 INTERNSHIP" if job["priority"] else "💼 JOB (0-1 yr)"
    text = (
        f"{tag}\n"
        f"*{job['title']}*\n"
        f"{job['company']} — {job['location']}\n"
        f"Source: {job['source']}\n"
        f"{job['link']}"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }, timeout=15)
    except requests.RequestException as e:
        print(f"Telegram send failed: {e}")


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------

def main():
    seen = load_seen()
    all_jobs = []

    print("Fetching Internshala...")
    internshala_jobs = fetch_internshala()
    print(f"Internshala: {len(internshala_jobs)} results")
    all_jobs += internshala_jobs

    for loc in LOCATIONS:
        print(f"Fetching LinkedIn for '{loc}'...")
        if loc == "Remote":
            linkedin_jobs = fetch_linkedin(keywords="cyber security", remote=True)
        else:
            linkedin_jobs = fetch_linkedin(keywords="cyber security", location=f"{loc}, India")
        print(f"LinkedIn ('{loc}'): {len(linkedin_jobs)} results")
        all_jobs += linkedin_jobs
        time.sleep(2)  # be polite between requests

    for loc in LOCATIONS:
        if loc == "Remote":
            continue  # Adzuna's "where" needs a real place; remote roles surface via keyword/location filters elsewhere
        print(f"Fetching Adzuna for '{loc}'...")
        adzuna_jobs = fetch_adzuna(where=loc)
        print(f"Adzuna ('{loc}'): {len(adzuna_jobs)} results")
        all_jobs += adzuna_jobs
        time.sleep(1)

    # dedupe within this run
    unique = {}
    for job in all_jobs:
        unique[job["id"]] = job

    new_jobs = [job for job in unique.values() if job["id"] not in seen]

    # priority (internships) first
    new_jobs.sort(key=lambda j: not j["priority"])

    print(f"Found {len(unique)} total, {len(new_jobs)} new.")

    for job in new_jobs:
        send_telegram(job)
        seen.add(job["id"])
        time.sleep(1)  # avoid Telegram rate limits

    save_seen(seen)


if __name__ == "__main__":
    main()
