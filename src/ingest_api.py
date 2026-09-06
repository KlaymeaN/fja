import json 
import requests 
import os
import time
from pathlib import Path
from config import CONFIG, project_path

from logger import get_logger

logger = get_logger(__name__)

#API_URL = "https://www.arbeitnow.com/api/job-board-api"
#API_URL = "http://localhost:9999"

#OUTPUT_DIR = "../data/raw/api"
#os.makedirs(OUTPUT_DIR, exist_ok=True)
#PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_CONFIG = CONFIG["api"]

API_URL = API_CONFIG["url"]

OUTPUT_DIR = project_path(
    CONFIG["paths"]["api_raw"]
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RETRYABLE_STATUS_CODES = set(
    API_CONFIG["retryable_status_codes"]
)
#OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "api"

#RETRYABLE_STATUS_CODES = {429, 500, 502, 503}

def fetch_page(page, max_retries=None):
    if max_retries is None:
        max_retries = API_CONFIG["max_retries"]
    for attempt in range(1, max_retries+1):
        try:
            response = requests.get(API_URL, params={"page": page}, timeout = API_CONFIG["timeout_seconds"])
            #print(f"Page {page} STATUS:", response.status_code)
            logger.info(
                "Page %s returned status %s",
                page,
                response.status_code,
            )

            if response.status_code in RETRYABLE_STATUS_CODES:
                raise requests.HTTPError(f"Retrable HTTP error: {response.status_code}",
                                         response=response)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            #print(f"Page {page} FAILED on attempt {attempt}: {error}")
            logger.warning(
                "Page %s failed on attempt %s: %s",
                page,
                attempt,
                error,
            )

            status_code = None

            if error.response is not None:
                status_code = error.response.status_code
            if (status_code is not None and status_code not in RETRYABLE_STATUS_CODES):
                raise

            if attempt < max_retries:
                wait_time = 2 ** (attempt - 1)

                if status_code == 429: # too many reqs 
                    retry_after = error.response.headers.get("Retry-After")
                    if retry_after is not None:
                        wait_time = int(retry_after)
                #print(f"Waiting {wait_time} seconds before retrying...")
                logger.warning(
                    "Waiting %s seconds before retrying page %s",
                    wait_time,
                    page,
                )
                time.sleep(wait_time)

    logger.error(
    "Failed to fetch page %s after %s attempts",
    page,
    max_retries,
)
    raise RuntimeError(f"FAILED to fetch page {page} after {max_retries} attempts")




    #return response.json()

def save_page(data, page):
    #os.makedirs(OUTPUT_DIR, exist_ok=True)

    #output_path = f"{OUTPUT_DIR}/jobs_page_{page}.json"
    output_path = OUTPUT_DIR / f"jobs_page_{page}.json"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )
    #print(f"Saved: {output_path}")
    logger.info(
            "Saved API page %s to %s",
            page,
            output_path,
        )

def run_api_ingestion(max_pages=None):
    if max_pages is None:
        max_pages = API_CONFIG["max_pages"]
    logger.info("Starting API ingestion")

    total_jobs = 0

    for page in range(1, max_pages + 1):
        data = fetch_page(page)

        jobs_on_page = len(data["data"])
        total_jobs += jobs_on_page

        logger.info(
            "Page %s contained %s jobs",
            page,
            jobs_on_page,
        )

        save_page(data, page)

    logger.info(
        "API ingestion complete: %s jobs",
        total_jobs,
    )

    return total_jobs
#def run_api_ingestion(max_pages=1):
#    print("Starting API ingestion...")
#
#    total_jobs = 0
#
#    for page in range(1, max_pages + 1):
#        data = fetch_page(page)
#
#        jobs_on_page = len(data["data"])
#        total_jobs += jobs_on_page
#
#        print(f"Page {page}: {jobs_on_page} jobs")
#
#        save_page(data, page)
#
#    print(f"API ingestion complete: {total_jobs} jobs")
#
#    return total_jobs


if __name__ == "__main__":
    run_api_ingestion()
#def ingest_api():
#    for page in range(1, 2):
#        data = fetch_page(page)
#    
#        print(f"Page {page}: {len(data['data'])} jobs")
#        save_page(data, page)
#
#if __name__ == "__main__":
#    ingest_api()




#response = requests.get(API_URL, params={"page":2}, timeout=10)

#print("Status Code:", response.status_code)

#response.raise_for_status()
# 200 => Ok
# 429 => Too many reqeusts ( masalan rate limit mizanim)
# 500 => Server Error 
# 502 => Bad gateway 


#data= response.json()

#print("Current page:", data["meta"]["current_page"])
#print("Jobs on page:", len(data["data"]))
#print("Next page:", data["links"]["next"])

#for page in range(1, 4):
#    response = requests.get(
#            API_URL,
#            params={"page": page},
#            timeout = 10,
#            )
#    print(f"Page {page} status:", response.status_code)
#
#    response.raise_for_status()
#
#    data = response.json()
#
#    print(
#        f"Page {page}: {len(data['data'])} jobs"
#    )
#
#    output_path = f"../data/raw/api/jobs_page_{page}.json"
#
#    with open(output_path, "w", encoding="utf-8") as file:
#        json.dump(
#            data,
#            file,
#            indent=2,
#            ensure_ascii=False,
#        )
#    print(f"Saved: {output_path}")



#os.makedirs("../data/raw/api", exist_ok=True)
#output_path = "../data/raw/api/jobs_page_1.json"
#with open(output_path, "w", encoding="utf-8") as file:
#    json.dump(data, file, indent=2, ensure_ascii=False)
#print(f"\nRaw API response saved to: {output_path}")
#
#
#
#print("Top Level Keys:", data.keys())
#
#print("Number of Jobs:", len(data["data"]))
#
#print("\nFirst Job:")
#
##print(data["data"][0])
#first_job = data["data"][0]
#
#print("Title:", first_job["title"])
#print("Company:", first_job["company_name"])
#print("Location:", first_job["location"])
#print("Remote:", first_job["remote"])
#print("Created:", first_job["created_at"])

