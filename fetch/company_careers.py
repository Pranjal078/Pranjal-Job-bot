"""
fetch/company_careers.py — Fetcher for target company career pages.

Strategy per company:
  - Use public JSON search APIs where available (no auth, no scraping)
  - Fall back gracefully with a log message if an endpoint fails
  - Never scrape authenticated or JS-rendered pages

Companies: HSBC, Wells Fargo, American Express, JPMC, Mastercard, Walmart Global Tech
"""

import logging
import requests
from datetime import datetime, timezone
from dateutil import parser as dateparser
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html",
}

TIMEOUT = 30


def _iso(date_str: str) -> str:
    """Parse various date string formats into ISO 8601."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        return dateparser.parse(date_str).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# Per-company fetchers
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_hsbc() -> list[dict]:
    """
    HSBC uses Workday. Public search endpoint (unauthenticated):
    https://mycareer.hsbc.com/wday/cxs/hsbc/External/jobs
    """
    url = "https://mycareer.hsbc.com/wday/cxs/hsbc/External/jobs"
    payload = {
        "searchText": "",
        "limit": 50,
        "offset": 0,
        "searchLocation": "",
        "locations": [],
        "categories": ["Finance", "Analytics", "Technology"],
    }
    jobs = []
    try:
        resp = requests.post(url, json=payload, headers={**HEADERS, "Accept": "application/json"}, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("jobPostings", []):
            title = item.get("title", "").strip()
            external_path = item.get("externalPath", "")
            job_url = f"https://mycareer.hsbc.com{external_path}" if external_path else ""
            posted = _iso(item.get("postedOn", ""))
            location = item.get("locationsText", "Various")
            if title:
                jobs.append({
                    "title": title,
                    "company": "HSBC",
                    "location": location,
                    "url": job_url,
                    "posted_date": posted,
                    "source": "HSBC Careers",
                    "comp_if_available": None,
                })
    except Exception as e:
        logger.warning("HSBC: failed to fetch — %s", e)
    return jobs


def _fetch_wells_fargo() -> list[dict]:
    """
    Wells Fargo uses Workday. Public search endpoint.
    """
    url = "https://wd1.myworkdaysite.com/wday/cxs/wellsfargo/External_Careers_-_Wells_Fargo_Careers/jobs"
    payload = {
        "searchText": "analyst",
        "limit": 50,
        "offset": 0,
    }
    jobs = []
    try:
        resp = requests.post(url, json=payload, headers={**HEADERS, "Accept": "application/json"}, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("jobPostings", []):
            title = item.get("title", "").strip()
            external_path = item.get("externalPath", "")
            job_url = f"https://www.wellsfargojobs.com{external_path}" if external_path else ""
            posted = _iso(item.get("postedOn", ""))
            location = item.get("locationsText", "Various")
            if title:
                jobs.append({
                    "title": title,
                    "company": "Wells Fargo",
                    "location": location,
                    "url": job_url,
                    "posted_date": posted,
                    "source": "Wells Fargo Careers",
                    "comp_if_available": None,
                })
    except Exception as e:
        logger.warning("Wells Fargo: failed to fetch — %s", e)
    return jobs


def _fetch_amex() -> list[dict]:
    """
    American Express uses Eightfold AI. Public search endpoint.
    """
    url = "https://aexp.eightfold.ai/api/apply/v2/jobs"
    params = {
        "domain": "aexp.com",
        "query": "analyst",
        "num_rec": 50,
        "location": "",
        "pid": "",
        "domain": "aexp.com",
    }
    jobs = []
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("positions", []):
            title = item.get("name", "").strip()
            job_id = item.get("id", "")
            job_url = f"https://aexp.eightfold.ai/careers?pid={job_id}" if job_id else ""
            posted = _iso(item.get("t_create", ""))
            location = item.get("location", "Various")
            if isinstance(location, list):
                location = ", ".join(location)
            if title:
                jobs.append({
                    "title": title,
                    "company": "American Express",
                    "location": location,
                    "url": job_url,
                    "posted_date": posted,
                    "source": "American Express Careers",
                    "comp_if_available": None,
                })
    except Exception as e:
        logger.warning("American Express: failed to fetch — %s", e)
    return jobs


def _fetch_jpmc() -> list[dict]:
    """
    JPMorgan Chase uses a public job search API.
    """
    url = "https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    params = {
        "onlyData": "true",
        "expand": "requisitionList.secondaryLocations,flexFieldsFacet.values",
        "finder": "findReqs;siteNumber=CX_1,facetsList=LOCATIONS%3BWORK_LOCATIONS%3BWORKPLACE_TYPES%3BTITLES%3BCATEGORIES%3BORGANIZATIONS%3BPOSTING_DATES%3BFLEX_FIELDS,limit=25,offset=0,sortBy=POSTING_DATE_RECENT,keyword=analyst",
    }
    jobs = []
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("items", []):
            req_list = item.get("requisitionList", [])
            for req in req_list:
                title = req.get("Title", "").strip()
                req_id = req.get("Id", "")
                job_url = f"https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/requisitions/preview/{req_id}" if req_id else ""
                posted = _iso(req.get("PostedDate", ""))
                locations = req.get("PrimaryLocation", "Various")
                if title:
                    jobs.append({
                        "title": title,
                        "company": "JPMorgan Chase",
                        "location": locations,
                        "url": job_url,
                        "posted_date": posted,
                        "source": "JPMC Careers",
                        "comp_if_available": None,
                    })
    except Exception as e:
        logger.warning("JPMC: failed to fetch — %s", e)
    return jobs


def _fetch_mastercard() -> list[dict]:
    """
    Mastercard uses an Oracle HCM public API.
    """
    url = "https://mastercard.wd1.myworkdayjobs.com/wday/cxs/mastercard/CorporateCareers/jobs"
    payload = {
        "searchText": "analyst",
        "limit": 50,
        "offset": 0,
    }
    jobs = []
    try:
        resp = requests.post(url, json=payload, headers={**HEADERS, "Accept": "application/json"}, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("jobPostings", []):
            title = item.get("title", "").strip()
            external_path = item.get("externalPath", "")
            job_url = f"https://mastercard.wd1.myworkdayjobs.com{external_path}" if external_path else ""
            posted = _iso(item.get("postedOn", ""))
            location = item.get("locationsText", "Various")
            if title:
                jobs.append({
                    "title": title,
                    "company": "Mastercard",
                    "location": location,
                    "url": job_url,
                    "posted_date": posted,
                    "source": "Mastercard Careers",
                    "comp_if_available": None,
                })
    except Exception as e:
        logger.warning("Mastercard: failed to fetch — %s", e)
    return jobs


def _fetch_walmart() -> list[dict]:
    """
    Walmart Global Tech uses a public job search API.
    """
    url = "https://careers.walmart.com/api/jobs"
    params = {
        "q": "analyst",
        "page": 0,
        "sort": "date",
        "expand": "department,brand,type,rate",
        "limit": 50,
    }
    jobs = []
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("jobs", data.get("data", {}).get("jobs", [])):
            title = item.get("title", item.get("jobTitle", "")).strip()
            req_id = item.get("requisitionId", item.get("jobId", ""))
            job_url = item.get("jobHref", f"https://careers.walmart.com/us/jobs/{req_id}")
            posted = _iso(item.get("postedDate", item.get("datePosted", "")))
            location = item.get("location", item.get("locationText", "Various"))
            if isinstance(location, dict):
                location = location.get("displayName", "Various")
            if title:
                jobs.append({
                    "title": title,
                    "company": "Walmart Global Tech",
                    "location": location,
                    "url": job_url,
                    "posted_date": posted,
                    "source": "Walmart Careers",
                    "comp_if_available": None,
                })
    except Exception as e:
        logger.warning("Walmart: failed to fetch — %s", e)
    return jobs


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

_FETCHERS = {
    "hsbc": _fetch_hsbc,
    "wells_fargo": _fetch_wells_fargo,
    "amex": _fetch_amex,
    "jpmc": _fetch_jpmc,
    "mastercard": _fetch_mastercard,
    "walmart": _fetch_walmart,
}


def fetch(config: dict) -> list[dict]:
    """
    Fetch job listings from all enabled company career pages.

    Args:
        config: Full parsed config.yaml dict.

    Returns:
        Combined list of normalized job dicts from all companies.
    """
    companies = config.get("company_targets", [])
    all_jobs = []

    for company in companies:
        if not company.get("enabled", True):
            continue
        company_type = company.get("type", "")
        fetcher = _FETCHERS.get(company_type)
        if not fetcher:
            logger.warning("No fetcher for company type '%s' — skipping", company_type)
            continue
        logger.info("Fetching careers: %s...", company.get("name", company_type))
        jobs = fetcher()
        logger.info("  %s: %d listings", company.get("name"), len(jobs))
        all_jobs.extend(jobs)

    logger.info("Company careers: fetched %d total listings", len(all_jobs))
    return all_jobs
