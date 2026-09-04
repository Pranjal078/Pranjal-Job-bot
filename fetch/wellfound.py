"""
fetch/wellfound.py — Stub for Wellfound (AngelList) job listings.

STATUS: SKIPPED IN V1
Reason: Wellfound shut down its public API in 2023. Their current Terms of
Service explicitly prohibit scraping. This stub exists as a placeholder so
the rest of the pipeline doesn't break when this source is toggled on in
config.yaml.

To implement when/if a public API becomes available:
  1. Check https://wellfound.com/developers for any new API endpoints.
  2. Implement fetch() below following the normalized schema.
  3. Set `sources.wellfound: true` in config.yaml.
"""

import logging

logger = logging.getLogger(__name__)


def fetch(config: dict) -> list[dict]:
    """
    Wellfound fetcher — currently a no-op stub.

    Returns:
        Empty list with an informational log message.
    """
    logger.info(
        "Wellfound: SKIPPED — no public API available (ToS prohibits scraping). "
        "See fetch/wellfound.py for details on when/how to implement."
    )
    return []
