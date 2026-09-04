# tests/test_filter.py — Unit tests for filter.py

import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from datetime import datetime, timezone, timedelta
from filter import apply_filters, url_hash, _matches_keyword, _matches_location, _parse_comp_inr_lpa


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def make_job(**overrides) -> dict:
    """Create a minimal valid job dict."""
    base = {
        "title": "Data Analyst",
        "company": "Acme Corp",
        "location": "Remote",
        "url": "https://example.com/jobs/1",
        "posted_date": datetime.now(timezone.utc).isoformat(),
        "source": "TestSource",
        "comp_if_available": None,
    }
    base.update(overrides)
    return base


SAMPLE_CONFIG = {
    "filters": {
        "title_keywords": ["Business Analyst", "Data Analyst", "Product Analyst"],
        "exclude_title_keywords": ["Senior Manager", "Director", "VP"],
        "locations": ["Remote", "India", "Gurgaon", "Germany"],
        "max_age_days": 7,
        "comp_floor_lpa": 20,
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# url_hash tests
# ─────────────────────────────────────────────────────────────────────────────

class TestUrlHash:
    def test_same_url_same_hash(self):
        assert url_hash("https://example.com/jobs/1") == url_hash("https://example.com/jobs/1")

    def test_different_urls_different_hash(self):
        assert url_hash("https://example.com/jobs/1") != url_hash("https://example.com/jobs/2")

    def test_case_insensitive(self):
        assert url_hash("HTTPS://EXAMPLE.COM/JOBS/1") == url_hash("https://example.com/jobs/1")

    def test_strips_whitespace(self):
        assert url_hash("  https://example.com/jobs/1  ") == url_hash("https://example.com/jobs/1")

    def test_returns_32_chars(self):
        h = url_hash("https://example.com")
        assert len(h) == 32


# ─────────────────────────────────────────────────────────────────────────────
# Keyword matching tests
# ─────────────────────────────────────────────────────────────────────────────

class TestKeywordMatching:
    def test_exact_match(self):
        assert _matches_keyword("Data Analyst", ["Data Analyst"])

    def test_case_insensitive(self):
        assert _matches_keyword("data analyst", ["Data Analyst"])
        assert _matches_keyword("DATA ANALYST", ["data analyst"])

    def test_partial_match(self):
        assert _matches_keyword("Senior Data Analyst", ["Data Analyst"])

    def test_no_match(self):
        assert not _matches_keyword("Software Engineer", ["Data Analyst", "Business Analyst"])

    def test_multiple_keywords_first_matches(self):
        # "Senior Business Analyst" contains "Business Analyst" — should match
        assert _matches_keyword("Senior Business Analyst", ["Business Analyst", "Data Analyst"])

    def test_empty_keywords_no_match(self):
        # Empty keyword list → no keywords to match → returns False
        assert not _matches_keyword("Data Analyst", [])


# ─────────────────────────────────────────────────────────────────────────────
# Location matching tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLocationMatching:
    def test_remote_match(self):
        assert _matches_location("Remote", ["Remote", "India"])

    def test_india_match(self):
        assert _matches_location("Gurgaon, India", ["India", "Gurgaon"])

    def test_germany_match(self):
        assert _matches_location("Berlin, Germany", ["Germany"])

    def test_case_insensitive(self):
        assert _matches_location("remote", ["Remote"])

    def test_no_match(self):
        assert not _matches_location("São Paulo, Brazil", ["Remote", "India", "Germany"])

    def test_partial_location_string(self):
        assert _matches_location("Gurugram (NCR)", ["Gurgaon", "NCR"])


# ─────────────────────────────────────────────────────────────────────────────
# Comp parsing tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCompParsing:
    def test_usd_annual(self):
        lpa = _parse_comp_inr_lpa("$80,000 – $100,000 USD/yr")
        assert lpa is not None
        # $80k * 83 INR / 100,000 = 66.4 LPA
        assert 60 < lpa < 70

    def test_inr_lpa(self):
        lpa = _parse_comp_inr_lpa("25 LPA")
        assert lpa == 25.0

    def test_none_input(self):
        assert _parse_comp_inr_lpa(None) is None

    def test_empty_string(self):
        assert _parse_comp_inr_lpa("") is None

    def test_no_numbers(self):
        assert _parse_comp_inr_lpa("Competitive salary") is None

    def test_eur_annual(self):
        lpa = _parse_comp_inr_lpa("€60,000 EUR")
        assert lpa is not None
        # €60k * 90 / 100,000 = 54 LPA
        assert 50 < lpa < 58


# ─────────────────────────────────────────────────────────────────────────────
# apply_filters integration tests
# ─────────────────────────────────────────────────────────────────────────────

class TestApplyFilters:
    def test_passes_valid_job(self):
        jobs = [make_job()]
        result = apply_filters(jobs, SAMPLE_CONFIG, seen_hashes=set())
        assert len(result) == 1

    def test_filters_wrong_keyword(self):
        jobs = [make_job(title="Software Engineer")]
        result = apply_filters(jobs, SAMPLE_CONFIG, seen_hashes=set())
        assert len(result) == 0

    def test_filters_excluded_title(self):
        jobs = [make_job(title="VP of Data Analytics")]
        result = apply_filters(jobs, SAMPLE_CONFIG, seen_hashes=set())
        assert len(result) == 0

    def test_filters_wrong_location(self):
        jobs = [make_job(location="São Paulo, Brazil")]
        result = apply_filters(jobs, SAMPLE_CONFIG, seen_hashes=set())
        assert len(result) == 0

    def test_filters_too_old(self):
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        jobs = [make_job(posted_date=old_date)]
        result = apply_filters(jobs, SAMPLE_CONFIG, seen_hashes=set())
        assert len(result) == 0

    def test_filters_duplicate(self):
        job = make_job()
        h = url_hash(job["url"])
        result = apply_filters([job], SAMPLE_CONFIG, seen_hashes={h})
        assert len(result) == 0

    def test_url_hash_added_to_job(self):
        jobs = [make_job()]
        result = apply_filters(jobs, SAMPLE_CONFIG, seen_hashes=set())
        assert "url_hash" in result[0]
        assert len(result[0]["url_hash"]) == 32

    def test_comp_flagged_when_above_floor(self):
        jobs = [make_job(comp_if_available="$100,000 USD/yr")]
        result = apply_filters(jobs, SAMPLE_CONFIG, seen_hashes=set())
        assert len(result) == 1
        assert result[0]["comp_flagged"] is True

    def test_comp_not_flagged_when_below_floor(self):
        # $10k USD = ~8.3 LPA — below 20 LPA floor
        jobs = [make_job(comp_if_available="$10,000 USD/yr")]
        result = apply_filters(jobs, SAMPLE_CONFIG, seen_hashes=set())
        assert len(result) == 1
        assert result[0]["comp_flagged"] is False

    def test_comp_not_flagged_when_unlisted(self):
        jobs = [make_job(comp_if_available=None)]
        result = apply_filters(jobs, SAMPLE_CONFIG, seen_hashes=set())
        assert len(result) == 1
        assert result[0]["comp_flagged"] is False

    def test_no_title_filtered_out(self):
        jobs = [make_job(title="")]
        result = apply_filters(jobs, SAMPLE_CONFIG, seen_hashes=set())
        assert len(result) == 0

    def test_no_url_filtered_out(self):
        jobs = [make_job(url="")]
        result = apply_filters(jobs, SAMPLE_CONFIG, seen_hashes=set())
        assert len(result) == 0

    def test_multiple_jobs_partial_pass(self):
        jobs = [
            make_job(title="Data Analyst", url="https://example.com/1"),
            make_job(title="Software Engineer", url="https://example.com/2"),  # keyword miss
            make_job(title="Business Analyst", url="https://example.com/3"),
        ]
        result = apply_filters(jobs, SAMPLE_CONFIG, seen_hashes=set())
        assert len(result) == 2
        titles = {j["title"] for j in result}
        assert titles == {"Data Analyst", "Business Analyst"}

    def test_no_keywords_in_config_passes_all(self):
        config_no_kw = {"filters": {"title_keywords": [], "locations": [], "max_age_days": 7}}
        jobs = [make_job(title="Anything")]
        result = apply_filters(jobs, config_no_kw, seen_hashes=set())
        assert len(result) == 1
