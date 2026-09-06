import csv
import time
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import date
from logger import get_logger
from config import CONFIG, project_path

logger = get_logger(__name__)

#BASE_URL="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

#PARAMS= {
#        "keywords": "Software OR Data OR AI OR Machine Learning OR Functional Analyst OR Business Analyst",
#        "location": "Ghent OR Amsterdam",
#        "geoId" :  "105077224",
#        "distance": "50",
#        "f_E"     : "2",
#        "f_TPR"  :"r604800",
#        "start": 0,
#}
#LOCATIONS = ["Ghent, Belgium", "Amsterdam, Netherlands"]

#PARAMS = {
#    "keywords": "Software OR Data OR AI OR Machine Learning OR Functional Analyst OR Business Analyst",
#    "distance": "50",
#    "f_E": "2",
#    "f_TPR": "r604800",
#    "start": 0,
#}

LINKEDIN_CONFIG = CONFIG["linkedin"]

BASE_URL = LINKEDIN_CONFIG["base_url"]
LOCATIONS = LINKEDIN_CONFIG["locations"]
PARAMS = LINKEDIN_CONFIG["params"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}


#RAW_DIR = Path("raw")
#PROJECT_ROOT = Path(__file__).resolve().parent.parent
#RAW_DIR = PROJECT_ROOT / "data" / "raw" / "linkedin"
RAW_DIR = project_path(CONFIG["paths"]["linkedin_raw"])

RAW_DIR.mkdir(parents=True, exist_ok=True)



def parse_job_card(card):
    title_el = card.select_one("h3")
    company_el=card.select_one("h4")
    location_el=card.select_one(".job-search-card__location")
    date_el    =card.select_one("time")

    return {
            "job_title": title_el.get_text(strip=True) if title_el else None,
            "company" : company_el.get_text(strip=True) if company_el else None,
            "location": location_el.get_text(strip=True) if location_el else None,
            "date_posted":(
                date_el.get("datetime") or date_el.get_text(strip=True) if date_el else None),
    }

def fetch_jobs(limit=None):
    if limit is None:
        limit = LINKEDIN_CONFIG["job_limit"]
    jobs = []
    #start = 0

    for location in LOCATIONS:
        start = 0
        location_jobs = 0
        #print(f"\n Fetching Jobs around {location}...")
        logger.info("Fetching jobs around %s", location)

        while location_jobs < limit:
            params = PARAMS.copy()
            params["location"] = location
            params["start"] = start 

            resp = requests.get(BASE_URL, params= params, headers=HEADERS, timeout=LINKEDIN_CONFIG["timeout_seconds"])
            
            if resp.status_code !=200:
                #print(f"STOPPING {location}: HTTP {resp.status_code} at start={start}")
                logger.error(
                "Stopping %s: HTTP %s at start=%s",
                location,
                resp.status_code,
                start,
            )
                break

            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, 'html.parser')
            cards = soup.select('li')

            if not cards:
                break
            
            for card in cards:
                job = parse_job_card(card)
                if job['job_title'] and job['company']:
                    jobs.append(job)
                    location_jobs += 1
                    #if len(jobs) >= limit:
                    #    break
                    if location_jobs >= limit:
                        break
            #print(f"GOT {len(jobs)} out of max={limit} in {location}")
            logger.info(
                "Fetched %s jobs so far for %s",
                location_jobs,
                location,
            )
            start += 25

            time.sleep(LINKEDIN_CONFIG["request_delay_seconds"])
    return jobs

def save_to_csv(jobs):
    today_str = date.today().isoformat()
    dated_file = RAW_DIR / f"jobs_{today_str}.csv"
    latest_file = RAW_DIR / "jobs_latest.csv"

    fieldnames=["job_title", "company", "location", "date_posted"]
    for filename in [dated_file, latest_file]:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(jobs)
    return dated_file, latest_file

#if __name__ == "__main__":
#    jobs = fetch_jobs(limit=500)
#    #save_to_csv(jobs)
#    if not jobs:
#        raise ValueError("No Jobs were extracted!")
#
#    dated_file, latest_file = save_to_csv(jobs)
#
#    print(f"DONE: saved {len(jobs)} !")
#    print(f"Dated raw file: {dated_file}")
#    print(f"Latest RAW file: {latest_file}")
def run_linkedin_ingestion():
    #print("Starting LinkedIn ingestion...")
    logger.info("Starting LinkedIn ingestion")

    jobs = fetch_jobs()

    if not jobs:
        logger.error("No LinkedIn jobs were extracted")
        raise ValueError("No LinkedIn jobs were extracted!")

    dated_file, latest_file = save_to_csv(jobs)

    #print(f"LinkedIn ingestion complete: {len(jobs)} jobs")
    #print(f"Dated raw file: {dated_file}")
    #print(f"Latest raw file: {latest_file}")
    logger.info(
        "LinkedIn ingestion complete: %s jobs",
        len(jobs),
    )

    logger.info(
        "Latest raw file: %s",
        latest_file,
    )

    return latest_file


if __name__ == "__main__":
    run_linkedin_ingestion()

            


