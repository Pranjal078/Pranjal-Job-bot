"""
fetch/remoteok.py — Fetcher for RemoteOK public JSON API.

Endpoint: https://remoteok.com/api
Docs:     https://remoteok.com/api (public, no auth needed)
Rate limit: Be polite — one request per run, add User-Agent header.
"""

import logging
import requests
from datetime import datetime, timezone
from dateutil import parser as dateparser

logger = logging.getLogger(__name__)

REMOTEOK_API = "https://remoteok.com/api"
HEADERS = {
    "User-Agent": "JobSearchBot/1.0 (personal job alert aggregator; contact via GitHub)",
    "Accept": "application/json",
}


def _parse_date(epoch_or_str) -> str:
    """Convert RemoteOK's epoch timestamp to ISO 8601 string."""
    if not epoch_or_str:
        return datetime.now(timezone.utc).isoformat()
    try:
        ts = int(epoch_or_str)
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (ValueError, TypeError):
        try:
            return dateparser.parse(str(epoch_or_str)).isoformat()
        except Exception:
            return datetime.now(timezone.utc).isoformat()


def fetch(config: dict) -> list[dict]:
    """
    Fetch job listings from RemoteOK's public JSON API.

    Args:
        config: The full parsed config.yaml dict (used for future extensions).

    Returns:
        List of normalized job dicts.
    """
    logger.info("Fetching from RemoteOK...")
    jobs = []

    try:
        resp = requests.get(REMOTEOK_API, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error("RemoteOK request failed: %s", e)
        return []
    except ValueError as e:
        logger.error("RemoteOK JSON parse failed: %s", e)
        return []

    # RemoteOK returns a list where the first element is a legal/meta notice
    # actual job objects have an "id" field
    for item in data:
        if not isinstance(item, dict) or "id" not in item:
            continue

        title = item.get("position", "").strip()
        company = item.get("company", "").strip()
        url = item.get("url", "").strip()
        if not url:
            url = f"https://remoteok.com/remote-jobs/{item.get('id', '')}"

        # Location: RemoteOK jobs are all remote; some specify extra regions
        location_tags = item.get("location", "") or ""
        if isinstance(location_tags, list):
            location_tags = ", ".join(location_tags)
        location = location_tags.strip() or "Remote"

        # Compensation
        salary_min = item.get("salary_min")
        salary_max = item.get("salary_max")
        comp = None
        if salary_min or salary_max:
            parts = []
            if salary_min:
                parts.append(f"${salary_min:,}")
            if salary_max:
                parts.append(f"${salary_max:,}")
            comp = " – ".join(parts) + " USD/yr"

        posted_date = _parse_date(item.get("date") or item.get("epoch"))

        if not title or not company:
            continue

        jobs.append({
            "title": title,
            "company": company,
            "location": location,
            "url": url,
            "posted_date": posted_date,
            "source": "RemoteOK",
            "comp_if_available": comp,
        })

    logger.info("RemoteOK: fetched %d listings", len(jobs))
    return jobs
