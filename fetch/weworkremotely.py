"""
fetch/weworkremotely.py — Fetcher for We Work Remotely RSS feeds.

WWR publishes category-specific RSS feeds. We pull the most relevant ones
for analyst/data roles. No auth required.

Feed index: https://weworkremotely.com/categories/remote-programming-jobs#job-listings
"""

import logging
import feedparser
from datetime import datetime, timezone
from dateutil import parser as dateparser
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

# We Work Remotely RSS feeds — grab all and filter by keyword in filter.py
WWR_FEEDS = [
    ("All Remote Jobs", "https://weworkremotely.com/remote-jobs.rss"),
    ("Business/Management", "https://weworkremotely.com/categories/remote-business-exec-management-jobs.rss"),
    ("Finance/Legal", "https://weworkremotely.com/categories/remote-finance-legal-jobs.rss"),
    ("Data Science", "https://weworkremotely.com/categories/remote-data-science-jobs.rss"),
    ("Product", "https://weworkremotely.com/categories/remote-product-jobs.rss"),
]


def _parse_date(entry) -> str:
    """Extract publication date from a feedparser entry."""
    # Try published_parsed first (struct_time)
    if entry.get("published_parsed"):
        try:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            pass

    # Try published as raw string
    if entry.get("published"):
        try:
            return parsedate_to_datetime(entry["published"]).isoformat()
        except Exception:
            try:
                return dateparser.parse(entry["published"]).isoformat()
            except Exception:
                pass

    return datetime.now(timezone.utc).isoformat()


def _extract_location(entry) -> str:
    """
    WWR encodes location in the title like: '[ANYWHERE] Data Analyst at Acme'.
    Extract the bracket region tag if present; else return 'Remote'.
    """
    title = entry.get("title", "")
    if title.startswith("[") and "]" in title:
        bracket_content = title[1: title.index("]")]
        return bracket_content.strip()
    return "Remote"


def _clean_title(raw_title: str) -> str:
    """Remove the '[LOCATION]' prefix and 'at Company' suffix from WWR titles."""
    title = raw_title
    if title.startswith("[") and "]" in title:
        title = title[title.index("]") + 1:].strip()
    # Remove trailing " at Company Name" — it's in a separate field anyway
    if " at " in title:
        title = title[: title.rfind(" at ")].strip()
    return title


def fetch(config: dict) -> list[dict]:
    """
    Fetch job listings from We Work Remotely RSS feeds.

    Args:
        config: Full parsed config.yaml dict.

    Returns:
        List of normalized job dicts.
    """
    logger.info("Fetching from We Work Remotely...")
    seen_urls: set[str] = set()
    jobs = []

    for feed_name, feed_url in WWR_FEEDS:
        logger.debug("  Parsing feed: %s", feed_name)
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as e:
            logger.warning("Failed to parse WWR feed '%s': %s", feed_name, e)
            continue

        if parsed.bozo and parsed.bozo_exception:
            # bozo = feed has errors; log but try to continue
            logger.warning("WWR feed '%s' has parse errors: %s", feed_name, parsed.bozo_exception)

        for entry in parsed.entries:
            url = entry.get("link", "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            raw_title = entry.get("title", "").strip()
            title = _clean_title(raw_title)
            location = _extract_location(entry)

            # Company is usually in the 'author' field or embedded in title
            company = ""
            if entry.get("author"):
                company = entry["author"].strip()
            elif " at " in raw_title:
                company = raw_title.split(" at ")[-1].strip()

            posted_date = _parse_date(entry)

            if not title:
                continue

            jobs.append({
                "title": title,
                "company": company or "Unknown",
                "location": location,
                "url": url,
                "posted_date": posted_date,
                "source": "WeWorkRemotely",
                "comp_if_available": None,  # WWR doesn't publish comp in RSS
            })

    logger.info("WeWorkRemotely: fetched %d listings", len(jobs))
    return jobs
