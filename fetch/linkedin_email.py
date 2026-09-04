"""
fetch/linkedin_email.py — Parse LinkedIn job-alert emails from Gmail.

Strategy:
  1. Connect to Gmail via Gmail API (OAuth2) — preferred
  2. Fall back to IMAP + App Password if Gmail API creds not present

LinkedIn sends HTML emails with job listings when you have saved job alerts.
We parse those emails to extract: title, company, location, URL.

Setup: Run `python setup_gmail.py` once to authenticate and save token.json.
"""

import logging
import os
import re
import base64
import json
from datetime import datetime, timezone
from email import message_from_bytes
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Gmail API path
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_via_gmail_api(max_emails: int = 20) -> list[dict]:
    """Fetch LinkedIn job-alert emails using Gmail API."""
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        logger.error("google-api-python-client not installed. Run: pip install -r requirements.txt")
        return []

    token_path = os.environ.get("GMAIL_TOKEN_PATH", "token.json")
    creds_path = os.environ.get("GMAIL_CREDENTIALS_PATH", "credentials.json")

    if not os.path.exists(token_path):
        logger.warning(
            "Gmail token not found at '%s'. "
            "Run `python setup_gmail.py` to authenticate. Skipping LinkedIn email parsing.",
            token_path,
        )
        return []

    try:
        creds = Credentials.from_authorized_user_file(
            token_path,
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed token
            with open(token_path, "w") as f:
                f.write(creds.to_json())

        service = build("gmail", "v1", credentials=creds)

        # Search for LinkedIn job alert emails (last 8 days to overlap with 7-day filter)
        query = "from:jobalerts-noreply@linkedin.com newer_than:8d"
        result = service.users().messages().list(userId="me", q=query, maxResults=max_emails).execute()
        messages = result.get("messages", [])

        if not messages:
            logger.info("LinkedIn email: no job-alert emails found in Gmail.")
            return []

        logger.info("LinkedIn email: found %d job-alert email(s)", len(messages))
        all_jobs = []
        for msg_meta in messages:
            msg_id = msg_meta["id"]
            msg = service.users().messages().get(userId="me", id=msg_id, format="raw").execute()
            raw = base64.urlsafe_b64decode(msg["raw"].encode("UTF-8"))
            jobs = _parse_linkedin_email(raw)
            all_jobs.extend(jobs)

        return all_jobs

    except Exception as e:
        logger.error("Gmail API error: %s", e)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# IMAP fallback path
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_via_imap() -> list[dict]:
    """Fetch LinkedIn job-alert emails using IMAP (Gmail App Password fallback)."""
    import imaplib
    import email as email_lib

    imap_host = os.environ.get("IMAP_HOST", "imap.gmail.com")
    imap_user = os.environ.get("SMTP_USER", "")
    imap_pass = os.environ.get("SMTP_PASSWORD", "")

    if not imap_user or not imap_pass:
        logger.warning("IMAP credentials not set (SMTP_USER / SMTP_PASSWORD). Skipping LinkedIn email parsing.")
        return []

    try:
        mail = imaplib.IMAP4_SSL(imap_host)
        mail.login(imap_user, imap_pass)
        mail.select("inbox")

        # Search for LinkedIn job alert sender
        status, data = mail.search(None, '(FROM "jobalerts-noreply@linkedin.com" SINCE "7-days-ago")')
        if status != "OK":
            logger.warning("IMAP search failed: %s", status)
            return []

        email_ids = data[0].split()
        logger.info("LinkedIn email (IMAP): found %d email(s)", len(email_ids))
        all_jobs = []
        for eid in email_ids[-20:]:  # Process last 20 at most
            status, msg_data = mail.fetch(eid, "(RFC822)")
            if status == "OK":
                raw = msg_data[0][1]
                jobs = _parse_linkedin_email(raw)
                all_jobs.extend(jobs)

        mail.logout()
        return all_jobs

    except Exception as e:
        logger.error("IMAP error: %s", e)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Email HTML parser
# ─────────────────────────────────────────────────────────────────────────────

# LinkedIn job URL pattern in emails
_LI_JOB_URL_RE = re.compile(
    r"https://www\.linkedin\.com/jobs/view/(\d+)",
    re.IGNORECASE,
)

# LinkedIn tracking redirect — extract the real URL
_LI_REDIRECT_RE = re.compile(
    r"https://www\.linkedin\.com/comm/jobs/view/(\d+)",
    re.IGNORECASE,
)


def _extract_html_body(raw_bytes: bytes) -> str:
    """Extract HTML body from a raw RFC822 email."""
    msg = message_from_bytes(raw_bytes)
    html_part = None
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                charset = part.get_content_charset() or "utf-8"
                html_part = part.get_payload(decode=True).decode(charset, errors="replace")
                break
    else:
        if msg.get_content_type() == "text/html":
            charset = msg.get_content_charset() or "utf-8"
            html_part = msg.get_payload(decode=True).decode(charset, errors="replace")
    return html_part or ""


def _get_email_date(raw_bytes: bytes) -> str:
    """Extract the Date header from a raw email."""
    msg = message_from_bytes(raw_bytes)
    date_str = msg.get("Date", "")
    if date_str:
        try:
            return parsedate_to_datetime(date_str).isoformat()
        except Exception:
            pass
    return datetime.now(timezone.utc).isoformat()


def _parse_linkedin_email(raw_bytes: bytes) -> list[dict]:
    """
    Parse a single LinkedIn job-alert HTML email and extract job listings.

    LinkedIn email structure (as of 2024):
    - Each job card is a <table> or <div> with job title as an <a> link
    - Company name and location follow the title
    - The link href contains the LinkedIn job ID

    Returns a list of normalized job dicts.
    """
    html = _extract_html_body(raw_bytes)
    if not html:
        return []

    email_date = _get_email_date(raw_bytes)
    soup = BeautifulSoup(html, "lxml")
    jobs = []

    # LinkedIn job alert emails contain job links with /jobs/view/<ID>
    # Find all anchor tags with LinkedIn job URLs
    seen_job_ids: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]

        # Match direct job URLs or redirect URLs
        match = _LI_JOB_URL_RE.search(href) or _LI_REDIRECT_RE.search(href)
        if not match:
            continue

        job_id = match.group(1)
        if job_id in seen_job_ids:
            continue
        seen_job_ids.add(job_id)

        # Canonical job URL (no tracking params)
        job_url = f"https://www.linkedin.com/jobs/view/{job_id}"

        # Job title: text of the anchor or nearest heading
        title = anchor.get_text(strip=True)
        if not title or len(title) < 3:
            # Try parent elements
            parent = anchor.find_parent(["td", "div", "li"])
            if parent:
                title_tag = parent.find(["h2", "h3", "h4", "strong", "b"])
                title = title_tag.get_text(strip=True) if title_tag else ""

        if not title or len(title) < 3:
            continue

        # Company and location: look for sibling/child text elements
        company = ""
        location = ""
        container = anchor.find_parent(["td", "div", "li", "tr"])
        if container:
            # LinkedIn usually puts company then location as separate spans/divs
            text_nodes = [
                t.get_text(strip=True)
                for t in container.find_all(["span", "p", "div"])
                if t.get_text(strip=True) and t.get_text(strip=True) != title
            ]
            # Heuristic: first distinct text = company, second = location
            if len(text_nodes) >= 1:
                company = text_nodes[0][:100]
            if len(text_nodes) >= 2:
                location = text_nodes[1][:100]

        jobs.append({
            "title": title[:200],
            "company": company or "Unknown",
            "location": location or "Not specified",
            "url": job_url,
            "posted_date": email_date,  # Use email receipt date as proxy
            "source": "LinkedIn (Email Alert)",
            "comp_if_available": None,
        })

    logger.debug("Parsed %d jobs from LinkedIn email", len(jobs))
    return jobs


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def fetch(config: dict) -> list[dict]:
    """
    Fetch LinkedIn job listings by parsing job-alert emails.

    Tries Gmail API first; falls back to IMAP if token not present.

    Args:
        config: Full parsed config.yaml dict.

    Returns:
        List of normalized job dicts extracted from LinkedIn emails.
    """
    logger.info("Fetching from LinkedIn job-alert emails...")

    token_path = os.environ.get("GMAIL_TOKEN_PATH", "token.json")
    creds_path = os.environ.get("GMAIL_CREDENTIALS_PATH", "credentials.json")

    if os.path.exists(token_path):
        jobs = _fetch_via_gmail_api()
    else:
        logger.info("Gmail API token not found — trying IMAP fallback...")
        jobs = _fetch_via_imap()

    logger.info("LinkedIn email: %d job listings extracted", len(jobs))
    return jobs
