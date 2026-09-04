# tests/test_fetch_remoteok.py — Unit tests for fetch/remoteok.py

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import responses as responses_lib
from fetch.remoteok import fetch, REMOTEOK_API


# ─────────────────────────────────────────────────────────────────────────────
# Sample API response data
# ─────────────────────────────────────────────────────────────────────────────

# RemoteOK returns a list where first item is a legal notice (no "id" field)
SAMPLE_RESPONSE = [
    {"legal": "Remote OK jobs board"},  # metadata — should be skipped
    {
        "id": "123456",
        "position": "Data Analyst",
        "company": "TechCorp",
        "url": "https://remoteok.com/remote-jobs/123456",
        "location": "Remote",
        "date": "1700000000",  # epoch
        "salary_min": 60000,
        "salary_max": 90000,
    },
    {
        "id": "789012",
        "position": "Business Analyst",
        "company": "FinCo",
        "url": "https://remoteok.com/remote-jobs/789012",
        "location": "Worldwide",
        "date": "1700050000",
        "salary_min": None,
        "salary_max": None,
    },
    {
        # Missing position — should be skipped
        "id": "000001",
        "company": "BadCorp",
        "url": "https://remoteok.com/remote-jobs/000001",
        "date": "1700000000",
    },
    {
        # Missing company — should be skipped
        "id": "000002",
        "position": "Analyst",
        "url": "https://remoteok.com/remote-jobs/000002",
        "date": "1700000000",
    },
]


CONFIG = {}  # Config not used by remoteok fetcher currently


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRemoteOKFetch:
    @responses_lib.activate
    def test_returns_normalized_jobs(self):
        responses_lib.add(
            responses_lib.GET,
            REMOTEOK_API,
            json=SAMPLE_RESPONSE,
            status=200,
        )
        jobs = fetch(CONFIG)
        assert len(jobs) == 2  # Skips metadata, missing title, missing company

    @responses_lib.activate
    def test_job_schema(self):
        responses_lib.add(responses_lib.GET, REMOTEOK_API, json=SAMPLE_RESPONSE, status=200)
        jobs = fetch(CONFIG)
        required_keys = {"title", "company", "location", "url", "posted_date", "source", "comp_if_available"}
        for job in jobs:
            assert required_keys.issubset(job.keys()), f"Missing keys in: {job}"

    @responses_lib.activate
    def test_source_is_remoteok(self):
        responses_lib.add(responses_lib.GET, REMOTEOK_API, json=SAMPLE_RESPONSE, status=200)
        jobs = fetch(CONFIG)
        for job in jobs:
            assert job["source"] == "RemoteOK"

    @responses_lib.activate
    def test_comp_extracted_when_present(self):
        responses_lib.add(responses_lib.GET, REMOTEOK_API, json=SAMPLE_RESPONSE, status=200)
        jobs = fetch(CONFIG)
        # First job has salary_min and salary_max
        data_analyst = next(j for j in jobs if j["title"] == "Data Analyst")
        assert data_analyst["comp_if_available"] is not None
        assert "$60,000" in data_analyst["comp_if_available"]
        assert "$90,000" in data_analyst["comp_if_available"]

    @responses_lib.activate
    def test_comp_none_when_absent(self):
        responses_lib.add(responses_lib.GET, REMOTEOK_API, json=SAMPLE_RESPONSE, status=200)
        jobs = fetch(CONFIG)
        biz_analyst = next(j for j in jobs if j["title"] == "Business Analyst")
        assert biz_analyst["comp_if_available"] is None

    @responses_lib.activate
    def test_skips_metadata_entry(self):
        responses_lib.add(responses_lib.GET, REMOTEOK_API, json=SAMPLE_RESPONSE, status=200)
        jobs = fetch(CONFIG)
        titles = [j["title"] for j in jobs]
        assert "legal" not in titles  # The first metadata entry has no "id" or "position"

    @responses_lib.activate
    def test_returns_empty_on_http_error(self):
        responses_lib.add(responses_lib.GET, REMOTEOK_API, status=429)
        jobs = fetch(CONFIG)
        assert jobs == []

    @responses_lib.activate
    def test_returns_empty_on_invalid_json(self):
        responses_lib.add(
            responses_lib.GET,
            REMOTEOK_API,
            body="<html>not json</html>",
            status=200,
            content_type="text/html",
        )
        jobs = fetch(CONFIG)
        assert jobs == []

    @responses_lib.activate
    def test_returns_empty_on_empty_response(self):
        responses_lib.add(responses_lib.GET, REMOTEOK_API, json=[], status=200)
        jobs = fetch(CONFIG)
        assert jobs == []

    @responses_lib.activate
    def test_posted_date_is_iso_string(self):
        responses_lib.add(responses_lib.GET, REMOTEOK_API, json=SAMPLE_RESPONSE, status=200)
        jobs = fetch(CONFIG)
        for job in jobs:
            # Should be parseable as ISO 8601
            from dateutil import parser as dp
            dt = dp.parse(job["posted_date"])
            assert dt is not None

    @responses_lib.activate
    def test_url_fallback_when_missing(self):
        no_url = [
            {"legal": "notice"},
            {
                "id": "99999",
                "position": "Analyst",
                "company": "Co",
                "location": "Remote",
                "date": "1700000000",
                # No "url" field
            },
        ]
        responses_lib.add(responses_lib.GET, REMOTEOK_API, json=no_url, status=200)
        jobs = fetch(CONFIG)
        assert len(jobs) == 1
        assert "99999" in jobs[0]["url"]
