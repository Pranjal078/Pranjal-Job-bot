"""
main.py — Orchestrator for the Job Search Alert Bot.

Pipeline:
    fetch → filter → dedup → store → notify → log run

Usage:
    python main.py                         # Full run (fetch + notify)
    python main.py --dry-run               # Fetch + filter, print digest, no notify
    python main.py --source remoteok       # Test a single source only
    python main.py --stats                 # Show store stats and recent runs
    python main.py --config path/to/config.yaml  # Use custom config file
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Load .env file if present (for local dev)
load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging(level_str: str = "INFO"):
    level = getattr(logging, level_str.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Config loader
# ─────────────────────────────────────────────────────────────────────────────

def load_config(config_path: str = "config.yaml") -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────────────────────────────────────
# Source dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def run_fetchers(config: dict, only_source: str | None = None) -> list[dict]:
    """Run all enabled fetch modules and return combined raw results."""
    from fetch import (
        fetch_remoteok,
        fetch_weworkremotely,
        fetch_wellfound,
        fetch_naukri,
        fetch_company_careers,
        fetch_linkedin_email,
        fetch_gulf,
    )

    sources_config = config.get("sources", {})
    logger = logging.getLogger("main.fetch")

    source_map = {
        "remoteok":       (fetch_remoteok,        sources_config.get("remoteok", True)),
        "weworkremotely": (fetch_weworkremotely,   sources_config.get("weworkremotely", True)),
        "gulf":           (fetch_gulf,             sources_config.get("gulf", True)),
        "wellfound":      (fetch_wellfound,        sources_config.get("wellfound", False)),
        "naukri":         (fetch_naukri,           sources_config.get("naukri", False)),
        "company_careers":(fetch_company_careers,  sources_config.get("company_careers", True)),
        "linkedin_email": (fetch_linkedin_email,   sources_config.get("linkedin_email", True)),
    }

    all_jobs = []
    for source_name, (fetcher_fn, enabled) in source_map.items():
        if only_source and source_name != only_source:
            continue
        if not enabled and not only_source:
            logger.debug("Source '%s' disabled in config — skipping", source_name)
            continue
        try:
            jobs = fetcher_fn(config)
            all_jobs.extend(jobs)
        except Exception as e:
            logger.error("Source '%s' crashed: %s", source_name, e, exc_info=True)

    return all_jobs


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run(config: dict, dry_run: bool = False, only_source: str | None = None):
    """Execute the full fetch → filter → store → notify pipeline."""
    logger = logging.getLogger("main")
    from filter import apply_filters
    from store import JobStore
    from notify import notify

    db_path = config.get("database", {}).get("path", "jobs.db")

    with JobStore(db_path) as store:
        # ── 1. Fetch ────────────────────────────────────────────────────────
        logger.info("=== STEP 1: Fetching job listings ===")
        raw_jobs = run_fetchers(config, only_source=only_source)
        logger.info("Total raw listings fetched: %d", len(raw_jobs))

        # ── 2. Filter + Dedup ───────────────────────────────────────────────
        logger.info("=== STEP 2: Filtering and deduplication ===")
        seen_hashes = store.get_seen_hashes()
        logger.info("Known seen jobs in DB: %d", len(seen_hashes))
        new_jobs = apply_filters(raw_jobs, config, seen_hashes)
        logger.info("New jobs after filtering: %d", len(new_jobs))

        # ── 3. Notify ───────────────────────────────────────────────────────
        logger.info("=== STEP 3: Sending digest ===")
        notified = notify(new_jobs, config, dry_run=dry_run)

        # ── 4. Store ─────────────────────────────────────────────────────────
        if not dry_run and new_jobs:
            logger.info("=== STEP 4: Marking %d jobs as seen ===", len(new_jobs))
            store.mark_seen(new_jobs)
        elif dry_run:
            logger.info("=== STEP 4: DRY RUN — skipping DB write ===")

        # ── 5. Log run ──────────────────────────────────────────────────────
        if not dry_run:
            store.log_run(
                jobs_found=len(raw_jobs),
                jobs_new=len(new_jobs),
                notified=notified,
                status="ok",
            )

    return len(new_jobs)


def show_stats(config: dict):
    """Print store statistics and recent run history."""
    from store import JobStore
    db_path = config.get("database", {}).get("path", "jobs.db")

    with JobStore(db_path) as store:
        total = store.total_seen()
        runs = store.recent_runs(10)

    print(f"\n📊 Job Store Stats")
    print(f"   Total unique jobs seen: {total}")
    print(f"\n🕐 Recent Runs (last {len(runs)}):")
    if not runs:
        print("   No runs yet.")
    else:
        print(f"   {'Run':>5}  {'Date':>20}  {'Found':>7}  {'New':>5}  {'Notified':>9}  Status")
        print("   " + "-" * 62)
        for run in runs:
            print(
                f"   {run['id']:>5}  {run['run_at'][:19]:>20}  "
                f"{run['jobs_found']:>7}  {run['jobs_new']:>5}  "
                f"{'yes' if run['notified'] else 'no':>9}  {run['status']}"
            )
    print()


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Job Search Alert Bot — fetch, filter, and notify about new job listings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                           # Full daily run
  python main.py --dry-run                 # Preview digest without sending
  python main.py --source remoteok         # Test RemoteOK fetcher only
  python main.py --source company_careers  # Test company career pages
  python main.py --stats                   # Show DB stats and run history
        """,
    )
    parser.add_argument(
        "--config", default="config.yaml", help="Path to config YAML (default: config.yaml)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch and filter, print digest to stdout — no notifications, no DB writes"
    )
    parser.add_argument(
        "--source", metavar="SOURCE",
        choices=["remoteok", "weworkremotely", "wellfound", "naukri", "company_careers", "linkedin_email"],
        help="Run only this source (for testing)"
    )
    parser.add_argument(
        "--stats", action="store_true", help="Show store statistics and recent run history"
    )
    args = parser.parse_args()

    # Load config
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Setup logging
    log_level = config.get("logging", {}).get("level", "INFO")
    setup_logging(log_level)
    logger = logging.getLogger("main")

    if args.stats:
        show_stats(config)
        return

    logger.info("Starting Job Search Alert Bot (dry_run=%s, source=%s)", args.dry_run, args.source)

    try:
        new_count = run(config, dry_run=args.dry_run, only_source=args.source)
        logger.info("Done. %d new job(s) in this run.", new_count)
        sys.exit(0)
    except KeyboardInterrupt:
        logger.info("Interrupted.")
        sys.exit(0)
    except Exception as e:
        logger.error("Pipeline failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
