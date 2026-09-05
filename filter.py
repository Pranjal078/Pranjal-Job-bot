"""
filter.py — Filter and deduplicate job listings based on config.yaml rules.

Filtering pipeline (in order):
  1. Title keyword match     — must contain at least one keyword
  2. Exclude title check     — discard if contains any excluded keyword
  3. Location filter         — must match at least one target location
  4. Age filter              — must be posted within max_age_days
  5. Dedup check             — skip if URL hash is already in the DB
  6. Comp flag               — mark (not exclude) if comp meets floor
"""

import hashlib
import logging
from datetime import datetime, timezone, timedelta
from dateutil import parser as dateparser

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def url_hash(url: str) -> str:
    """SHA-256 hash of a URL (first 16 bytes as hex = 32 chars). Used as dedup key."""
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()[:32]


def _parse_posted_date(date_str: str) -> datetime | None:
    """Parse an ISO 8601 or other date string into a timezone-aware datetime."""
    if not date_str:
        return None
    try:
        dt = dateparser.parse(date_str)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _matches_keyword(title: str, keywords: list[str]) -> bool:
    """Case-insensitive substring check — title must contain at least one keyword."""
    title_lower = title.lower()
    return any(kw.lower() in title_lower for kw in keywords)


def _matches_excluded(title: str, excluded: list[str]) -> bool:
    """Return True if title contains any excluded keyword."""
    title_lower = title.lower()
    return any(exc.lower() in title_lower for exc in excluded)


def _matches_location(location: str, target_locations: list[str]) -> bool:
    """
    Case-insensitive substring match against any target location term.
    'Remote' in location OR location matches an India/Germany term.
    """
    loc_lower = location.lower()
    return any(tl.lower() in loc_lower for tl in target_locations)


def _parse_comp_inr_lpa(comp_str: str | None) -> float | None:
    """
    Attempt to parse a compensation string into approximate INR LPA value.
    Supports: USD/yr annual figures (converts at 1 USD ≈ 83 INR).
    Returns None if unparseable or unknown currency.
    """
    if not comp_str:
        return None
    import re
    # Extract numbers from the string
    numbers = re.findall(r"[\d,]+", comp_str.replace(",", ""))
    if not numbers:
        return None
    # Take the first number as base
    try:
        amount = float(numbers[0])
    except ValueError:
        return None

    comp_lower = comp_str.lower()

    # USD annual
    if "usd" in comp_lower or "$" in comp_str:
        # Convert: 1 USD/yr = 83 INR / 100,000 LPA ≈ 0.000830 LPA
        return (amount * 83) / 100_000

    # INR (already in rupees — assume annual)
    if "inr" in comp_lower or "₹" in comp_str or "lpa" in comp_lower:
        if "lpa" in comp_lower or "lakh" in comp_lower:
            return amount  # already in LPA
        # Assume raw INR annual
        return amount / 100_000

    # EUR annual (1 EUR ≈ 90 INR)
    if "eur" in comp_lower or "€" in comp_str:
        return (amount * 90) / 100_000

    return None


def _check_experience(title: str, text: str, min_years: int = 2) -> bool:
    """
    Check if role satisfies experience requirement (default 2+ years).
    Excludes explicit 0-1 yr / intern / graduate trainee roles.
    """
    import re
    combined = f"{title} {text}".lower()

    # Reject 0-1 year or intern/fresher explicit statements
    reject_patterns = [
        r"\b0\s*-\s*1\s*(?:year|yr)",
        r"\b0\s*to\s*1\s*(?:year|yr)",
        r"\bno\s+experience\b",
        r"\bentry\s+level\b",
        r"\b0\s*(?:year|yr)s?\s+exp",
        r"\bintern\b",
        r"\binternship\b",
        r"\bfresher\b",
        r"\bstudent\b",
        r"\bgraduate\s+program\b",
        r"\btraining\s+program\b",
    ]
    for pat in reject_patterns:
        if re.search(pat, combined):
            return False

    return True


def tag_visa_sponsorship(job: dict, visa_keywords: list[str], body_text: str = "") -> tuple[bool, str | None]:
    """
    Check if title, location, description, or page body text mentions visa sponsorship or relocation.
    Returns (is_flagged, matched_term).
    """
    if not visa_keywords:
        return False, None

    combined_text = (
        f"{job.get('title', '')} {job.get('location', '')} {job.get('description', '')} {body_text}"
    ).lower()

    for kw in visa_keywords:
        if kw.lower() in combined_text:
            return True, kw

    return False, None


def check_url_live_and_body(url: str, timeout: int = 5) -> tuple[bool, str]:
    """
    Perform a lightweight HEAD/GET request to verify if listing is still active.
    Returns (is_live, body_sample_text).
    """
    import requests
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    closed_indicators = [
        "no longer accepting applications",
        "position filled",
        "job expired",
        "job is no longer available",
        "this position has been closed",
        "job listing has expired",
    ]
    try:
        resp = requests.head(url, headers=headers, allow_redirects=True, timeout=timeout)
        if resp.status_code in (404, 410):
            return False, ""

        body_sample = ""
        if resp.status_code not in (404, 410):
            resp = requests.get(url, headers=headers, allow_redirects=True, timeout=timeout)
            if resp.status_code in (404, 410):
                return False, ""

        if resp.status_code == 200 and "html" in resp.headers.get("content-type", "").lower():
            body_sample = resp.text[:30000].lower()
            if any(indicator in body_sample for indicator in closed_indicators):
                return False, ""

        return True, body_sample
    except Exception as e:
        logger.debug("Live URL check for %s: %s (failing open)", url, e)
        return True, ""


def is_url_live(url: str, timeout: int = 5) -> bool:
    """Convenience wrapper for backward compatibility in tests."""
    is_live, _ = check_url_live_and_body(url, timeout=timeout)
    return is_live


# ─────────────────────────────────────────────────────────────────────────────
# Main filter function
# ─────────────────────────────────────────────────────────────────────────────

def apply_filters(jobs: list[dict], config: dict, seen_hashes: set[str], check_live_urls: bool = False) -> list[dict]:
    """
    Filter a list of normalized job dicts according to config.yaml rules.

    Args:
        jobs:            Raw list of job dicts from fetch modules.
        config:          Full parsed config.yaml dict.
        seen_hashes:     Set of URL hashes already stored in the DB (for dedup).
        check_live_urls: Whether to verify live URL availability right before return.

    Returns:
        Filtered list of job dicts, annotated with:
        - `comp_flagged: True` if comp >= floor.
        - `visa_flagged: True` if visa/relocation keywords matched.
    """
    filters = config.get("filters", {})
    title_keywords = filters.get("title_keywords", [])
    exclude_keywords = filters.get("exclude_title_keywords", [])
    target_locations = filters.get("locations", [])
    visa_keywords = filters.get("visa_keywords", [])
    max_age_days = filters.get("max_age_days", 7)
    min_exp_years = filters.get("min_experience_years", 2)
    comp_floor_lpa = filters.get("comp_floor_lpa")

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    passed = []
    stats = {
        "total": len(jobs),
        "no_title": 0,
        "no_url": 0,
        "keyword_miss": 0,
        "excluded_title": 0,
        "location_miss": 0,
        "experience_miss": 0,
        "too_old": 0,
        "duplicate": 0,
        "expired_url": 0,
        "passed": 0,
    }

    for job in jobs:
        title = (job.get("title") or "").strip()
        url = (job.get("url") or "").strip()

        # Must have title and URL
        if not title:
            stats["no_title"] += 1
            continue
        if not url:
            stats["no_url"] += 1
            continue

        # 1. Title keyword match
        if title_keywords and not _matches_keyword(title, title_keywords):
            stats["keyword_miss"] += 1
            continue

        # 2. Excluded title check
        if exclude_keywords and _matches_excluded(title, exclude_keywords):
            stats["excluded_title"] += 1
            continue

        # 3. Experience filter (2+ years)
        desc = job.get("description", "")
        if not _check_experience(title, desc, min_years=min_exp_years):
            stats["experience_miss"] += 1
            continue

        # 4. Location filter (if configured)
        location = (job.get("location") or "").strip()
        if target_locations and not _matches_location(location, target_locations):
            stats["location_miss"] += 1
            continue

        # 5. Age filter
        posted_str = job.get("posted_date", "")
        posted_dt = _parse_posted_date(posted_str)
        if posted_dt and posted_dt < cutoff:
            stats["too_old"] += 1
            continue

        # 6. Dedup check
        h = url_hash(url)
        if h in seen_hashes:
            stats["duplicate"] += 1
            continue

        # 7. Freshness / Live URL Availability Check & Body Text Fetch
        body_text = ""
        if check_live_urls:
            is_live, body_text = check_url_live_and_body(url)
            if not is_live:
                stats["expired_url"] += 1
                continue

        # 8. Annotations (comp flagging & visa sponsorship tagging)
        comp_str = job.get("comp_if_available")
        comp_lpa = _parse_comp_inr_lpa(comp_str)
        job = dict(job)  # shallow copy to avoid mutating original
        job["url_hash"] = h
        job["comp_flagged"] = bool(
            comp_floor_lpa and comp_lpa is not None and comp_lpa >= comp_floor_lpa
        )

        is_visa, visa_term = tag_visa_sponsorship(job, visa_keywords, body_text=body_text)
        job["visa_flagged"] = is_visa
        if is_visa:
            job["visa_matched_term"] = visa_term

        stats["passed"] += 1
        passed.append(job)

    logger.info(
        "Filter results: %d total → %d passed | "
        "keyword_miss=%d, excluded=%d, location_miss=%d, exp_miss=%d, too_old=%d, duplicate=%d, expired_url=%d, no_title=%d, no_url=%d",
        stats["total"], stats["passed"],
        stats["keyword_miss"], stats["excluded_title"], stats["location_miss"], stats["experience_miss"],
        stats["too_old"], stats["duplicate"], stats["expired_url"], stats["no_title"], stats["no_url"],
    )
    return passed
