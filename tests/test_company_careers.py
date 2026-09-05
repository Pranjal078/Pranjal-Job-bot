"""
tests/test_company_careers.py — Unit tests for company career page fetchers.
Tests all ATS integrations (Workday, SmartRecruiters, Greenhouse, Workable, Oracle HCM)
using mock HTTP responses to ensure correctness without live network calls.
"""

import pytest
from unittest.mock import patch, MagicMock
from fetch.company_careers import (
    _fetch_workday,
    _fetch_smartrecruiters,
    _fetch_greenhouse,
    _fetch_workable,
    _fetch_oracle_hcm,
    fetch,
)


class TestWorkdayFetcher:
    @patch("fetch.company_careers.requests.post")
    def test_workday_fetch_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "jobPostings": [
                {
                    "title": "Data Analyst",
                    "externalPath": "/job/123",
                    "postedOn": "2026-09-01T00:00:00Z",
                    "locationsText": "Bangalore, India",
                }
            ]
        }
        mock_post.return_value = mock_resp

        jobs = _fetch_workday("TestCo", "https://example.com/cxs", "https://example.com")
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Data Analyst"
        assert jobs[0]["company"] == "TestCo"
        assert jobs[0]["url"] == "https://example.com/job/123"
        assert jobs[0]["location"] == "Bangalore, India"

        # Verify appliedFacets was included and limit is capped at <= 20
        called_payload = mock_post.call_args[1]["json"]
        assert "appliedFacets" in called_payload
        assert called_payload["limit"] <= 20

    @patch("fetch.company_careers.requests.post")
    def test_workday_fetch_error_handled(self, mock_post):
        mock_post.side_effect = Exception("Connection timeout")
        jobs = _fetch_workday("TestCo", "https://example.com/cxs", "https://example.com")
        assert jobs == []


class TestSmartRecruitersFetcher:
    @patch("fetch.company_careers.requests.get")
    def test_smartrecruiters_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [
                {
                    "id": "abc-456",
                    "name": "Senior Business Analyst",
                    "releasedDate": "2026-09-02T10:00:00Z",
                    "location": {"city": "Bengaluru", "country": "India"},
                }
            ]
        }
        mock_get.return_value = mock_resp

        jobs = _fetch_smartrecruiters("Visa", "Visa")
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Senior Business Analyst"
        assert jobs[0]["company"] == "Visa"
        assert jobs[0]["url"] == "https://jobs.smartrecruiters.com/Visa/abc-456"
        assert jobs[0]["location"] == "Bengaluru, India"


class TestGreenhouseFetcher:
    @patch("fetch.company_careers.requests.get")
    def test_greenhouse_success_with_keyword_filter(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "jobs": [
                {
                    "title": "Operations Analyst",
                    "absolute_url": "https://boards.greenhouse.io/job/1",
                    "updated_at": "2026-09-03T10:00:00Z",
                    "location": {"name": "Bengaluru"},
                },
                {
                    "title": "Lead Software Engineer",
                    "absolute_url": "https://boards.greenhouse.io/job/2",
                    "updated_at": "2026-09-03T10:00:00Z",
                    "location": {"name": "Bengaluru"},
                },
            ]
        }
        mock_get.return_value = mock_resp

        jobs = _fetch_greenhouse("Razorpay", "razorpaysoftwareprivatelimited", filter_keyword="analyst")
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Operations Analyst"
        assert jobs[0]["company"] == "Razorpay"


class TestWorkableFetcher:
    @patch("fetch.company_careers.requests.get")
    def test_workable_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "jobs": [
                {
                    "title": "Data Science Analyst",
                    "url": "https://apply.workable.com/job/1",
                    "published": "2026-09-01T00:00:00Z",
                    "city": "Chennai",
                    "country": "India",
                }
            ]
        }
        mock_get.return_value = mock_resp

        jobs = _fetch_workable("Tiger Analytics", "tiger-analytics", filter_keyword="analyst")
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Data Science Analyst"
        assert jobs[0]["location"] == "Chennai, India"


class TestOracleHCMFetcher:
    @patch("fetch.company_careers.requests.get")
    def test_oracle_hcm_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "requisitionList": [
                        {
                            "Id": "REQ-789",
                            "Title": "Financial Analyst",
                            "PostedDate": "2026-09-04T00:00:00Z",
                            "PrimaryLocation": "Gurgaon, HR, India",
                        }
                    ]
                }
            ]
        }
        mock_get.return_value = mock_resp

        jobs = _fetch_oracle_hcm("American Express", "https://example.com/hcm", "https://example.com/preview/")
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Financial Analyst"
        assert jobs[0]["url"] == "https://example.com/preview/REQ-789"
        assert jobs[0]["location"] == "Gurgaon, HR, India"


class TestCompanyCareersDispatcher:
    def test_skips_disabled_companies(self):
        config = {
            "company_targets": [
                {"name": "Citi", "type": "citi", "enabled": False}
            ]
        }
        jobs = fetch(config)
        assert jobs == []

    def test_skips_unknown_company_type(self):
        config = {
            "company_targets": [
                {"name": "Mystery", "type": "mystery_unknown", "enabled": True}
            ]
        }
        jobs = fetch(config)
        assert jobs == []
