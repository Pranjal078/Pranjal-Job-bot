# tests/test_store.py — Unit tests for store.py

import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from store import JobStore


def make_job(url: str = "https://example.com/jobs/1", **kwargs) -> dict:
    from filter import url_hash
    base = {
        "url": url,
        "url_hash": url_hash(url),
        "title": "Data Analyst",
        "company": "Acme",
        "location": "Remote",
        "source": "TestSource",
        "posted_date": "2024-01-15T12:00:00",
        "comp_if_available": None,
        "comp_flagged": False,
    }
    base.update(kwargs)
    return base


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary SQLite DB for each test."""
    db_file = tmp_path / "test_jobs.db"
    return str(db_file)


class TestJobStoreConnect:
    def test_creates_db_file(self, temp_db):
        with JobStore(temp_db) as store:
            pass
        assert os.path.exists(temp_db)

    def test_context_manager(self, temp_db):
        with JobStore(temp_db) as store:
            assert store._conn is not None
        assert store._conn is None  # closed after exit


class TestSeenHashes:
    def test_empty_store_returns_empty_set(self, temp_db):
        with JobStore(temp_db) as store:
            hashes = store.get_seen_hashes()
        assert hashes == set()

    def test_is_seen_false_for_unknown(self, temp_db):
        with JobStore(temp_db) as store:
            assert not store.is_seen("nonexistent_hash")

    def test_mark_seen_and_retrieve(self, temp_db):
        job = make_job()
        with JobStore(temp_db) as store:
            store.mark_seen([job])
            assert store.is_seen(job["url_hash"])

    def test_get_seen_hashes_returns_all(self, temp_db):
        jobs = [
            make_job("https://example.com/1"),
            make_job("https://example.com/2"),
            make_job("https://example.com/3"),
        ]
        with JobStore(temp_db) as store:
            store.mark_seen(jobs)
            hashes = store.get_seen_hashes()
        assert len(hashes) == 3
        for job in jobs:
            assert job["url_hash"] in hashes

    def test_mark_seen_duplicate_ignored(self, temp_db):
        job = make_job()
        with JobStore(temp_db) as store:
            store.mark_seen([job])
            store.mark_seen([job])  # Second insert — should be silently ignored
            assert store.total_seen() == 1

    def test_mark_seen_persists_across_connections(self, temp_db):
        job = make_job()
        with JobStore(temp_db) as store:
            store.mark_seen([job])

        # Open a new connection
        with JobStore(temp_db) as store2:
            assert store2.is_seen(job["url_hash"])
            assert store2.total_seen() == 1


class TestRunLogging:
    def test_log_run_returns_id(self, temp_db):
        with JobStore(temp_db) as store:
            run_id = store.log_run(jobs_found=100, jobs_new=5, notified=True)
        assert isinstance(run_id, int)
        assert run_id >= 1

    def test_recent_runs_empty(self, temp_db):
        with JobStore(temp_db) as store:
            runs = store.recent_runs()
        assert runs == []

    def test_recent_runs_returns_entries(self, temp_db):
        with JobStore(temp_db) as store:
            store.log_run(50, 3, True, "ok")
            store.log_run(40, 0, False, "ok", "no new jobs")
            runs = store.recent_runs(10)
        assert len(runs) == 2
        # Most recent first
        assert runs[0]["jobs_found"] == 40
        assert runs[1]["jobs_found"] == 50

    def test_recent_runs_respects_limit(self, temp_db):
        with JobStore(temp_db) as store:
            for i in range(15):
                store.log_run(i, i, True)
            runs = store.recent_runs(5)
        assert len(runs) == 5


class TestStats:
    def test_total_seen_zero(self, temp_db):
        with JobStore(temp_db) as store:
            assert store.total_seen() == 0

    def test_total_seen_increments(self, temp_db):
        jobs = [make_job(f"https://example.com/{i}") for i in range(5)]
        with JobStore(temp_db) as store:
            store.mark_seen(jobs)
            assert store.total_seen() == 5
