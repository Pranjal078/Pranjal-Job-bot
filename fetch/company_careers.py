"""
fetch/company_careers.py — Fetcher for target company career pages.

Strategy per company:
  - Use public JSON search APIs where available (no auth, no scraping)
  - Workday endpoints: POST to /wday/cxs/{tenant}/{site}/jobs with {"appliedFacets": {}}
  - SmartRecruiters: GET to https://api.smartrecruiters.com/v1/companies/{id}/postings
  - Greenhouse: GET to https://boards-api.greenhouse.io/v1/boards/{token}/jobs
  - Workable: GET to https://apply.workable.com/api/v1/widget/accounts/{slug}
  - Oracle Cloud HCM: GET to {hcm_host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
  - Fall back gracefully with a log message if an endpoint fails
  - Never scrape authenticated or JS-rendered pages

Companies supported (19 live API integrations):
  Wells Fargo, American Express, JPMorgan Chase, Mastercard, Walmart Global Tech,
  Citi, Barclays, Deutsche Bank, PayPal, Fractal Analytics, Genpact, Target,
  Visa, Freshworks, WNS, Swiggy, PhonePe, Razorpay, Tiger Analytics.

Companies skipped (no unauthenticated public API):
  HSBC, Standard Chartered, Goldman Sachs, LatentView Analytics, ZS Associates,
  Mu Sigma, EXL Service, Flipkart, Myntra, Meesho, CRED, Zomato.
"""

import logging
import requests
from datetime import datetime, timezone
from dateutil import parser as dateparser

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
# Generic ATS Fetcher Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_workday(company_name: str, cxs_url: str, web_prefix: str, search_text: str = "analyst", limit: int = 20) -> list[dict]:
    """
    Fetch jobs from a Workday CXS search endpoint.
    Workday requires {"appliedFacets": {}} in the payload and enforces a hard maximum of limit <= 20.
    """
    payload = {
        "appliedFacets": {},
        "limit": min(limit, 20),
        "offset": 0,
        "searchText": search_text,
    }
    jobs = []
    try:
        resp = requests.post(
            cxs_url,
            json=payload,
            headers={**HEADERS, "Content-Type": "application/json", "Accept": "application/json"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("jobPostings", []):
            title = item.get("title", "").strip()
            external_path = item.get("externalPath", "")
            job_url = f"{web_prefix}{external_path}" if external_path else ""
            posted = _iso(item.get("postedOn", ""))
            location = item.get("locationsText", "Various")
            if title:
                jobs.append({
                    "title": title,
                    "company": company_name,
                    "location": location,
                    "url": job_url,
                    "posted_date": posted,
                    "source": f"{company_name} Careers",
                    "comp_if_available": None,
                })
    except Exception as e:
        logger.warning("%s: failed to fetch via Workday (%s)", company_name, e)
    return jobs


def _fetch_smartrecruiters(company_name: str, company_id: str, query: str = "analyst", limit: int = 50) -> list[dict]:
    """
    Fetch jobs from SmartRecruiters public postings API.
    """
    url = f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings"
    params = {"q": query, "limit": limit, "offset": 0}
    jobs = []
    try:
        resp = requests.get(url, params=params, headers={**HEADERS, "Accept": "application/json"}, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("content", []):
            title = item.get("name", "").strip()
            job_id = item.get("id", "")
            job_url = f"https://jobs.smartrecruiters.com/{company_id}/{job_id}" if job_id else ""
            posted = _iso(item.get("releasedDate", ""))
            loc_data = item.get("location", {})
            city = loc_data.get("city", "")
            country = loc_data.get("country", "")
            location = f"{city}, {country}".strip(", ") or "Various"
            if title:
                jobs.append({
                    "title": title,
                    "company": company_name,
                    "location": location,
                    "url": job_url,
                    "posted_date": posted,
                    "source": f"{company_name} Careers",
                    "comp_if_available": None,
                })
    except Exception as e:
        logger.warning("%s: failed to fetch via SmartRecruiters (%s)", company_name, e)
    return jobs


def _fetch_greenhouse(company_name: str, board_token: str, filter_keyword: str = "analyst") -> list[dict]:
    """
    Fetch jobs from Greenhouse public board API.
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    jobs = []
    try:
        resp = requests.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        kw = filter_keyword.lower()
        for item in data.get("jobs", []):
            title = item.get("title", "").strip()
            if kw and kw not in title.lower():
                continue
            job_url = item.get("absolute_url", "")
            posted = _iso(item.get("updated_at", ""))
            location = item.get("location", {}).get("name", "Various")
            if title:
                jobs.append({
                    "title": title,
                    "company": company_name,
                    "location": location,
                    "url": job_url,
                    "posted_date": posted,
                    "source": f"{company_name} Careers",
                    "comp_if_available": None,
                })
    except Exception as e:
        logger.warning("%s: failed to fetch via Greenhouse (%s)", company_name, e)
    return jobs


def _fetch_workable(company_name: str, account_slug: str, filter_keyword: str = "analyst") -> list[dict]:
    """
    Fetch jobs from Workable public widget API.
    """
    url = f"https://apply.workable.com/api/v1/widget/accounts/{account_slug}"
    jobs = []
    try:
        resp = requests.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        kw = filter_keyword.lower()
        for item in data.get("jobs", []):
            title = item.get("title", "").strip()
            if kw and kw not in title.lower():
                continue
            job_url = item.get("url", "")
            posted = _iso(item.get("published", ""))
            city = item.get("city", "")
            country = item.get("country", "")
            location = f"{city}, {country}".strip(", ") or "Various"
            if title:
                jobs.append({
                    "title": title,
                    "company": company_name,
                    "location": location,
                    "url": job_url,
                    "posted_date": posted,
                    "source": f"{company_name} Careers",
                    "comp_if_available": None,
                })
    except Exception as e:
        logger.warning("%s: failed to fetch via Workable (%s)", company_name, e)
    return jobs


def _fetch_oracle_hcm(company_name: str, api_url: str, preview_base_url: str, site_number: str = "CX_1", keyword: str = "analyst", limit: int = 25) -> list[dict]:
    """
    Fetch jobs from Oracle Cloud HCM recruiting CE API.
    """
    params = {
        "onlyData": "true",
        "expand": "requisitionList.secondaryLocations,flexFieldsFacet.values",
        "finder": f"findReqs;siteNumber={site_number},facetsList=LOCATIONS%3BWORK_LOCATIONS%3BWORKPLACE_TYPES%3BTITLES%3BCATEGORIES%3BORGANIZATIONS%3BPOSTING_DATES%3BFLEX_FIELDS,limit={limit},offset=0,sortBy=POSTING_DATE_RECENT,keyword={keyword}",
    }
    jobs = []
    try:
        resp = requests.get(api_url, params=params, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("items", []):
            req_list = item.get("requisitionList", [])
            for req in req_list:
                title = req.get("Title", "").strip()
                req_id = req.get("Id", "")
                job_url = f"{preview_base_url}{req_id}" if req_id and preview_base_url else ""
                posted = _iso(req.get("PostedDate", ""))
                locations = req.get("PrimaryLocation", "Various")
                if title:
                    jobs.append({
                        "title": title,
                        "company": company_name,
                        "location": locations,
                        "url": job_url,
                        "posted_date": posted,
                        "source": f"{company_name} Careers",
                        "comp_if_available": None,
                    })
    except Exception as e:
        logger.warning("%s: failed to fetch via Oracle HCM (%s)", company_name, e)
    return jobs


# ─────────────────────────────────────────────────────────────────────────────
# Individual Company Fetchers
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_hsbc() -> list[dict]:
    """HSBC: Migrated from Workday to Eightfold/SuccessFactors behind active sessions."""
    logger.info("HSBC: Skipped — migrated to Eightfold/SuccessFactors requiring authenticated candidate session.")
    return []


def _fetch_wells_fargo() -> list[dict]:
    return _fetch_workday(
        company_name="Wells Fargo",
        cxs_url="https://wd1.myworkdaysite.com/wday/cxs/wf/WellsFargoJobs/jobs",
        web_prefix="https://www.wellsfargojobs.com",
    )


def _fetch_amex() -> list[dict]:
    return _fetch_oracle_hcm(
        company_name="American Express",
        api_url="https://egug.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        preview_base_url="https://careers.americanexpress.com/hcmUI/CandidateExperience/en/sites/CX_1/requisitions/preview/",
    )


def _fetch_jpmc() -> list[dict]:
    return _fetch_oracle_hcm(
        company_name="JPMorgan Chase",
        api_url="https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        preview_base_url="https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/requisitions/preview/",
    )


def _fetch_mastercard() -> list[dict]:
    return _fetch_workday(
        company_name="Mastercard",
        cxs_url="https://mastercard.wd1.myworkdayjobs.com/wday/cxs/mastercard/CorporateCareers/jobs",
        web_prefix="https://mastercard.wd1.myworkdayjobs.com/en-US/CorporateCareers",
    )


def _fetch_walmart() -> list[dict]:
    return _fetch_workday(
        company_name="Walmart Global Tech",
        cxs_url="https://walmart.wd504.myworkdayjobs.com/wday/cxs/walmart/WalmartExternal/jobs",
        web_prefix="https://walmart.wd504.myworkdayjobs.com/en-US/WalmartExternal",
    )


def _fetch_citi() -> list[dict]:
    return _fetch_workday(
        company_name="Citi",
        cxs_url="https://citi.wd5.myworkdayjobs.com/wday/cxs/citi/2/jobs",
        web_prefix="https://citi.wd5.myworkdayjobs.com/en-US/2",
    )


def _fetch_barclays() -> list[dict]:
    return _fetch_workday(
        company_name="Barclays",
        cxs_url="https://barclays.wd3.myworkdayjobs.com/wday/cxs/barclays/External_Career_Site_Barclays/jobs",
        web_prefix="https://barclays.wd3.myworkdayjobs.com/en-US/External_Career_Site_Barclays",
    )


def _fetch_deutsche_bank() -> list[dict]:
    return _fetch_workday(
        company_name="Deutsche Bank",
        cxs_url="https://db.wd3.myworkdayjobs.com/wday/cxs/db/DBWebsite/jobs",
        web_prefix="https://db.wd3.myworkdayjobs.com/en-US/DBWebsite",
    )


def _fetch_paypal() -> list[dict]:
    return _fetch_workday(
        company_name="PayPal",
        cxs_url="https://paypal.wd1.myworkdayjobs.com/wday/cxs/paypal/jobs/jobs",
        web_prefix="https://paypal.wd1.myworkdayjobs.com/en-US/jobs",
    )


def _fetch_fractal() -> list[dict]:
    return _fetch_workday(
        company_name="Fractal Analytics",
        cxs_url="https://fractal.wd1.myworkdayjobs.com/wday/cxs/fractal/Careers/jobs",
        web_prefix="https://fractal.wd1.myworkdayjobs.com/en-US/Careers",
    )


def _fetch_genpact() -> list[dict]:
    return _fetch_workday(
        company_name="Genpact",
        cxs_url="https://genpact.wd108.myworkdayjobs.com/wday/cxs/genpact/External_Careers/jobs",
        web_prefix="https://genpact.wd108.myworkdayjobs.com/en-US/External_Careers",
    )


def _fetch_target() -> list[dict]:
    return _fetch_workday(
        company_name="Target",
        cxs_url="https://target.wd5.myworkdayjobs.com/wday/cxs/target/targetcareers/jobs",
        web_prefix="https://target.wd5.myworkdayjobs.com/en-US/targetcareers",
    )


def _fetch_visa() -> list[dict]:
    return _fetch_workday(
        company_name="Visa",
        cxs_url="https://visa.wd5.myworkdayjobs.com/wday/cxs/visa/Visa/jobs",
        web_prefix="https://visa.wd5.myworkdayjobs.com/en-US/Visa",
    )


def _fetch_freshworks() -> list[dict]:
    return _fetch_smartrecruiters(company_name="Freshworks", company_id="Freshworks")


def _fetch_wns() -> list[dict]:
    return _fetch_smartrecruiters(company_name="WNS", company_id="WNSGlobalServices")


def _fetch_swiggy() -> list[dict]:
    return _fetch_smartrecruiters(company_name="Swiggy", company_id="Swiggy")


def _fetch_phonepe() -> list[dict]:
    return _fetch_smartrecruiters(company_name="PhonePe", company_id="PhonePeLimited")


def _fetch_razorpay() -> list[dict]:
    return _fetch_greenhouse(company_name="Razorpay", board_token="razorpaysoftwareprivatelimited")


def _fetch_tiger() -> list[dict]:
    return _fetch_workable(company_name="Tiger Analytics", account_slug="tiger-analytics")


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

_FETCHERS = {
    # Priority 1: Fixed / Existing
    "hsbc": _fetch_hsbc,
    "wells_fargo": _fetch_wells_fargo,
    "amex": _fetch_amex,
    "jpmc": _fetch_jpmc,
    "mastercard": _fetch_mastercard,
    "walmart": _fetch_walmart,

    # Priority 2: New Workday targets
    "citi": _fetch_citi,
    "barclays": _fetch_barclays,
    "deutsche_bank": _fetch_deutsche_bank,
    "paypal": _fetch_paypal,
    "fractal": _fetch_fractal,
    "genpact": _fetch_genpact,
    "target": _fetch_target,

    # Priority 2: New SmartRecruiters targets
    "visa": _fetch_visa,
    "freshworks": _fetch_freshworks,
    "wns": _fetch_wns,
    "swiggy": _fetch_swiggy,
    "phonepe": _fetch_phonepe,

    # Priority 2: Greenhouse & Workable targets
    "razorpay": _fetch_razorpay,
    "tiger": _fetch_tiger,
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
