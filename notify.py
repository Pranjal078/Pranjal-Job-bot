"""
notify.py — Send the job digest via Telegram (primary) or SMTP email (fallback).

Telegram limits:
  - Max message length: 4096 characters
  - HTML parse mode supported
  - Rate limit: ~30 messages/second to same chat (well within our needs)

Format:
  🔔 Job Alert Digest — <date>
  Found <N> new listings

  [Source Group]
  • <Title> @ <Company>
    📍 <Location>  💰 <Comp or —>  📅 <date>
    🔗 <URL>
"""

import asyncio
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

MAX_TG_MSG_LEN = 4000  # Conservative limit (4096 minus header overhead)


# ─────────────────────────────────────────────────────────────────────────────
# Formatting
# ─────────────────────────────────────────────────────────────────────────────

def _escape_html(text: str) -> str:
    """Escape characters that are special in Telegram HTML mode."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _format_job_html(job: dict) -> str:
    """Format a single job as an HTML snippet for Telegram."""
    title = _escape_html(job.get("title", "Untitled"))
    company = _escape_html(job.get("company", "Unknown"))
    location = _escape_html(job.get("location", "—"))
    url = job.get("url", "#")
    source = _escape_html(job.get("source", ""))
    comp = job.get("comp_if_available")
    comp_str = _escape_html(comp) if comp else "—"
    flagged = "💰✅ " if job.get("comp_flagged") else ""
    visa_badge = "✈️ <b>[Visa/Relocation]</b> " if job.get("visa_flagged") else ""
    posted = job.get("posted_date", "")
    if posted:
        try:
            posted = datetime.fromisoformat(posted).strftime("%b %d")
        except Exception:
            posted = posted[:10]

    return (
        f'• {visa_badge}<b><a href="{url}">{title}</a></b> @ {company}\n'
        f'  📍 {location}  {flagged}💰 {comp_str}  📅 {posted}\n'
    )


def _format_job_plain(job: dict) -> str:
    """Plain-text format for email fallback."""
    title = job.get("title", "Untitled")
    company = job.get("company", "Unknown")
    location = job.get("location", "—")
    url = job.get("url", "#")
    comp = job.get("comp_if_available") or "—"
    flagged = " ✅ COMP≥FLOOR" if job.get("comp_flagged") else ""
    visa_badge = " ✈️ [VISA/RELOCATION]" if job.get("visa_flagged") else ""
    posted = job.get("posted_date", "")[:10]
    return (
        f"• {title} @ {company}{visa_badge}\n"
        f"  📍 {location}  💰 {comp}{flagged}  📅 {posted}\n"
        f"  {url}\n"
    )


def _build_messages(jobs: list[dict], max_per_msg: int = 10) -> list[str]:
    """
    Split jobs into paginated Telegram-safe HTML message strings.

    Groups jobs by source for readability. Ensures each message is
    within Telegram's 4096-char limit.
    """
    if not jobs:
        return []

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = (
        f"🔔 <b>Job Alert Digest</b> — {now_str}\n"
        f"📋 {len(jobs)} new listing(s) found\n\n"
    )

    # Group by source
    by_source: dict[str, list[dict]] = {}
    for job in jobs:
        src = job.get("source", "Other")
        by_source.setdefault(src, []).append(job)

    messages = []
    current_msg = header
    chunk_count = 0

    for source, source_jobs in by_source.items():
        section_header = f"<b>── {_escape_html(source)} ──</b>\n"
        if len(current_msg) + len(section_header) > MAX_TG_MSG_LEN:
            messages.append(current_msg.strip())
            current_msg = section_header
        else:
            current_msg += section_header

        for job in source_jobs:
            job_text = _format_job_html(job)
            if len(current_msg) + len(job_text) > MAX_TG_MSG_LEN:
                messages.append(current_msg.strip())
                current_msg = job_text
            else:
                current_msg += job_text
            chunk_count += 1

        current_msg += "\n"

    if current_msg.strip():
        messages.append(current_msg.strip())

    # Add page numbers if multiple messages
    if len(messages) > 1:
        messages = [
            f"({i+1}/{len(messages)}) {msg}" for i, msg in enumerate(messages)
        ]

    return messages


# ─────────────────────────────────────────────────────────────────────────────
# Telegram sender
# ─────────────────────────────────────────────────────────────────────────────

def _send_telegram(token: str, chat_id: str, messages: list[str]) -> bool:
    """Send paginated messages via Telegram Bot HTTP API."""
    import requests
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    success = True
    for i, msg in enumerate(messages):
        logger.debug("Sending Telegram message %d/%d...", i + 1, len(messages))
        try:
            payload = {
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error("Telegram send failed: %s", e)
            success = False
    return success


def send_telegram(jobs: list[dict], config: dict) -> bool:
    """
    Send the job digest via Telegram.

    Args:
        jobs:   Filtered list of new job dicts.
        config: Full parsed config.yaml dict.

    Returns:
        True if all messages sent successfully.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set. Skipping Telegram notification.")
        return False

    tg_config = config.get("notification", {}).get("telegram", {})
    max_per_msg = tg_config.get("max_jobs_per_message", 10)

    messages = _build_messages(jobs, max_per_msg=max_per_msg)
    if not messages:
        logger.info("No new jobs to notify about.")
        return True

    logger.info("Sending %d Telegram message(s) for %d jobs...", len(messages), len(jobs))
    return _send_telegram(token, chat_id, messages)


# ─────────────────────────────────────────────────────────────────────────────
# Email fallback
# ─────────────────────────────────────────────────────────────────────────────

def send_email(jobs: list[dict], config: dict) -> bool:
    """
    Send the job digest via SMTP email (fallback).

    Args:
        jobs:   Filtered list of new job dicts.
        config: Full parsed config.yaml dict.

    Returns:
        True if email sent successfully.
    """
    email_config = config.get("notification", {}).get("email", {})
    smtp_host = email_config.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(email_config.get("smtp_port", 587))
    from_addr = email_config.get("from_addr") or os.environ.get("SMTP_USER", "")
    to_addr = email_config.get("to_addr") or os.environ.get("SMTP_TO", from_addr)
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASSWORD", "")

    if not smtp_user or not smtp_pass:
        logger.warning("SMTP credentials not set. Skipping email notification.")
        return False

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = f"Job Alert Digest — {now_str} ({len(jobs)} new listings)"

    # Plain text body
    plain = f"Job Alert Digest — {now_str}\n{len(jobs)} new listing(s)\n\n"
    by_source: dict[str, list] = {}
    for job in jobs:
        by_source.setdefault(job.get("source", "Other"), []).append(job)

    for source, source_jobs in by_source.items():
        plain += f"── {source} ──\n"
        for job in source_jobs:
            plain += _format_job_plain(job) + "\n"
        plain += "\n"

    # HTML body
    html_parts = [
        "<html><body>",
        f"<h2>🔔 Job Alert Digest — {now_str}</h2>",
        f"<p><strong>{len(jobs)} new listing(s)</strong></p>",
    ]
    for source, source_jobs in by_source.items():
        html_parts.append(f"<h3>{_escape_html(source)}</h3><ul>")
        for job in source_jobs:
            title = _escape_html(job.get("title", ""))
            company = _escape_html(job.get("company", ""))
            location = _escape_html(job.get("location", "—"))
            url = job.get("url", "#")
            comp = _escape_html(job.get("comp_if_available") or "—")
            flagged = " ✅" if job.get("comp_flagged") else ""
            posted = job.get("posted_date", "")[:10]
            html_parts.append(
                f'<li><a href="{url}"><strong>{title}</strong></a> @ {company}<br>'
                f'📍 {location} &nbsp; 💰 {comp}{flagged} &nbsp; 📅 {posted}</li>'
            )
        html_parts.append("</ul>")
    html_parts.append("</body></html>")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText("\n".join(html_parts), "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, to_addr, msg.as_string())
        logger.info("Email digest sent to %s", to_addr)
        return True
    except Exception as e:
        logger.error("Email send failed: %s", e)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Public dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def notify(jobs: list[dict], config: dict, dry_run: bool = False) -> bool:
    """
    Send the digest via the configured channel.

    Args:
        jobs:    Filtered new job dicts.
        config:  Full parsed config.yaml dict.
        dry_run: If True, print to stdout only — no actual notifications sent.

    Returns:
        True if notification succeeded (or dry_run).
    """
    if not jobs:
        logger.info("No new jobs — nothing to notify.")
        return True

    if dry_run:
        _print_dry_run(jobs)
        return True

    channel = config.get("notification", {}).get("channel", "telegram")

    if channel == "telegram":
        success = send_telegram(jobs, config)
        if not success:
            logger.info("Telegram failed or unconfigured — trying email fallback...")
            return send_email(jobs, config)
        return success
    elif channel == "email":
        return send_email(jobs, config)
    else:
        logger.error("Unknown notification channel: '%s'. Use 'telegram' or 'email'.", channel)
        return False


def _print_dry_run(jobs: list[dict]):
    """Print a formatted digest to stdout (for --dry-run mode)."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*60}")
    print(f"🔔 DRY RUN — Job Alert Digest — {now_str}")
    print(f"   {len(jobs)} new listing(s) found")
    print(f"{'='*60}")

    by_source: dict[str, list] = {}
    for job in jobs:
        by_source.setdefault(job.get("source", "Other"), []).append(job)

    for source, source_jobs in by_source.items():
        print(f"\n── {source} ({len(source_jobs)} jobs) ──")
        for job in source_jobs:
            title = job.get("title", "Untitled")
            company = job.get("company", "Unknown")
            location = job.get("location", "—")
            url = job.get("url", "#")
            comp = job.get("comp_if_available") or "—"
            flagged = " ✅ COMP≥FLOOR" if job.get("comp_flagged") else ""
            posted = job.get("posted_date", "")[:10]
            print(f"  • {title} @ {company}")
            print(f"    📍 {location}  💰 {comp}{flagged}  📅 {posted}")
            print(f"    🔗 {url}")

    print(f"\n{'='*60}\n")
