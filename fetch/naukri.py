"""
fetch/naukri.py — Stub for Naukri.com job listings.

STATUS: SKIPPED IN V1
Reason: Naukri does not expose a public RSS feed or authenticated API for
third-party use. Their Terms of Service prohibit automated scraping.

Alternatives to consider for future v2:
  - If Naukri launches a partner API, implement here.
  - Consider iimjobs.com RSS if targeting premium analytics roles in India.
  - AmbitionBox RSS (sister site, more open) — worth checking.

To implement when a public API becomes available:
  1. Obtain API credentials from Naukri's developer program (if launched).
  2. Implement fetch() below following the normalized schema.
  3. Set `sources.naukri: true` in config.yaml.
"""

import logging

logger = logging.getLogger(__name__)


def fetch(config: dict) -> list[dict]:
    """
    Naukri fetcher — currently a no-op stub.

    Returns:
        Empty list with an informational log message.
    """
    logger.info(
        "Naukri: SKIPPED — no public API or RSS available (ToS prohibits scraping). "
        "See fetch/naukri.py for details on when/how to implement."
    )
    return []
