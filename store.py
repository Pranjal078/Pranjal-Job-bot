"""
store.py — SQLite persistence layer for the job search bot.

Tables:
  seen_jobs    — all jobs ever sent in a digest (prevents re-notification)
  digest_runs  — log of each run's metadata

A job's URL hash (SHA-256 prefix) is the primary key for dedup.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class JobStore:
    """Context-manager-compatible SQLite store for job deduplication."""

    def __init__(self, db_path: str = "jobs.db"):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def __enter__(self) -> "JobStore":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False  # Don't suppress exceptions

    def connect(self):
        """Open the SQLite connection and ensure the schema exists."""
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")  # Safe for concurrent reads
        self._create_schema()
        logger.debug("JobStore connected: %s", self.db_path)

    def close(self):
        """Commit and close the connection."""
        if self._conn:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def _create_schema(self):
        """Create tables if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS seen_jobs (
                url_hash    TEXT PRIMARY KEY,
                url         TEXT NOT NULL,
                title       TEXT,
                company     TEXT,
                location    TEXT,
                source      TEXT,
                posted_date TEXT,
                seen_at     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS digest_runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at      TEXT NOT NULL,
                jobs_found  INTEGER DEFAULT 0,
                jobs_new    INTEGER DEFAULT 0,
                notified    INTEGER DEFAULT 0,
                status      TEXT DEFAULT 'ok',
                notes       TEXT
            );
        """)
        self._conn.commit()

    # ── Dedup ──────────────────────────────────────────────────────────────

    def get_seen_hashes(self) -> set[str]:
        """Return the set of all URL hashes previously stored."""
        cursor = self._conn.execute("SELECT url_hash FROM seen_jobs")
        return {row["url_hash"] for row in cursor.fetchall()}

    def is_seen(self, url_hash: str) -> bool:
        """Check if a specific hash has been seen before."""
        cursor = self._conn.execute(
            "SELECT 1 FROM seen_jobs WHERE url_hash = ?", (url_hash,)
        )
        return cursor.fetchone() is not None

    def mark_seen(self, jobs: list[dict]):
        """
        Insert a batch of jobs into seen_jobs.
        Jobs that already exist (by url_hash) are silently ignored.

        Args:
            jobs: List of job dicts, each must have 'url_hash' and 'url' keys.
        """
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (
                job["url_hash"],
                job.get("url", ""),
                job.get("title", ""),
                job.get("company", ""),
                job.get("location", ""),
                job.get("source", ""),
                job.get("posted_date", ""),
                now,
            )
            for job in jobs
        ]
        self._conn.executemany(
            """
            INSERT OR IGNORE INTO seen_jobs
                (url_hash, url, title, company, location, source, posted_date, seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._conn.commit()
        logger.info("Marked %d jobs as seen in store", len(rows))

    # ── Run logging ────────────────────────────────────────────────────────

    def log_run(
        self,
        jobs_found: int,
        jobs_new: int,
        notified: bool,
        status: str = "ok",
        notes: str = "",
    ) -> int:
        """Log metadata about the current pipeline run. Returns run ID."""
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """
            INSERT INTO digest_runs (run_at, jobs_found, jobs_new, notified, status, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (now, jobs_found, jobs_new, int(notified), status, notes),
        )
        self._conn.commit()
        run_id = cursor.lastrowid
        logger.info(
            "Run #%d logged: found=%d, new=%d, notified=%s, status=%s",
            run_id, jobs_found, jobs_new, notified, status,
        )
        return run_id

    # ── Stats ──────────────────────────────────────────────────────────────

    def total_seen(self) -> int:
        """Return the total number of unique jobs ever stored."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM seen_jobs")
        return cursor.fetchone()[0]

    def recent_runs(self, n: int = 10) -> list[dict]:
        """Return the last n run log entries."""
        cursor = self._conn.execute(
            "SELECT * FROM digest_runs ORDER BY id DESC LIMIT ?", (n,)
        )
        return [dict(row) for row in cursor.fetchall()]
