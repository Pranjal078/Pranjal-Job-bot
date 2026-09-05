"""
fetch/gulf.py — Fetcher for Middle East / Gulf job boards (Bayt, GulfTalent, etc.).

Features:
  - Pulls public RSS/search endpoints (unauthenticated, read-only)
  - Normalizes jobs into standard schema:
    {title, company, location, url, posted_date, source, comp_if_available, description}
"""

import logging
import requests
import feedparser
from datetime import datetime, timezone
from dateutil import parser as dateparser
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, application/json, text/html",
}

TIMEOUT = 30


def _iso(date_str: str) -> str:
    """Parse date string into ISO 8601 format."""
    if not date_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        return dateparser.parse(date_str).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def fetch_bayt() -> list[dict]:
    """
    Fetch public RSS feed from Bayt (Middle East job board).
    """
    url = "https://www.bayt.com/en/international/jobs/rss/"
    jobs = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            feed = feedparser.parse(resp.content)
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", "") or entry.get("description", "")
                published = _iso(entry.get("published", entry.get("updated", "")))
                
                # Extract company/location from summary or title if present
                company = "Bayt Employer"
                location = "Middle East"
                if " in " in title:
                    parts = title.split(" in ")
                    title = parts[0].strip()
                    location = parts[1].strip()

                if title and link:
                    jobs.append({
                        "title": title,
                        "company": company,
                        "location": location,
                        "url": link,
                        "posted_date": published,
                        "source": "Bayt",
                        "comp_if_available": None,
                        "description": summary,
                    })
    except Exception as e:
        logger.warning("Bayt RSS fetch failed: %s", e)
    return jobs


def fetch_gulftalent() -> list[dict]:
    """
    Fetch public RSS feed from GulfTalent.
    """
    url = "https://www.gulftalent.com/rss/jobs.xml"
    jobs = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            feed = feedparser.parse(resp.content)
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", "") or entry.get("description", "")
                published = _iso(entry.get("published", entry.get("updated", "")))
                
                company = "GulfTalent Employer"
                location = "Gulf / Middle East"
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    location = parts[1].strip()

                if title and link:
                    jobs.append({
                        "title": title,
                        "company": company,
                        "location": location,
                        "url": link,
                        "posted_date": published,
                        "source": "GulfTalent",
                        "comp_if_available": None,
                        "description": summary,
                    })
    except Exception as e:
        logger.warning("GulfTalent RSS fetch failed: %s", e)
    return jobs


def fetch(config: dict) -> list[dict]:
    """
    Fetch Middle East / Gulf job listings from all public feeds.
    """
    all_jobs = []
    
    bayt_jobs = fetch_bayt()
    logger.info("Bayt: fetched %d listings", len(bayt_jobs))
    all_jobs.extend(bayt_jobs)
    
    gt_jobs = fetch_gulftalent()
    logger.info("GulfTalent: fetched %d listings", len(gt_jobs))
    all_jobs.extend(gt_jobs)

    return all_jobs
