"""
fetch/ — Job listing fetchers.

Each module exposes a fetch(config: dict) -> list[dict] function
returning normalized job records:

    {
        "title":             str,
        "company":           str,
        "location":          str,
        "url":               str,
        "posted_date":       str,   # ISO 8601, e.g. "2024-01-15T12:00:00"
        "source":            str,   # e.g. "RemoteOK", "WeWorkRemotely"
        "comp_if_available": str | None,
    }
"""

from .remoteok import fetch as fetch_remoteok
from .weworkremotely import fetch as fetch_weworkremotely
from .wellfound import fetch as fetch_wellfound
from .naukri import fetch as fetch_naukri
from .company_careers import fetch as fetch_company_careers
from .linkedin_email import fetch as fetch_linkedin_email

__all__ = [
    "fetch_remoteok",
    "fetch_weworkremotely",
    "fetch_wellfound",
    "fetch_naukri",
    "fetch_company_careers",
    "fetch_linkedin_email",
]
