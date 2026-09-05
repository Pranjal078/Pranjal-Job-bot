"""
tests/test_visa_and_live_filter.py — Unit tests for Visa/Relocation tagging and Live URL checks.
"""

from unittest.mock import MagicMock, patch
from filter import tag_visa_sponsorship, is_url_live, apply_filters


class TestVisaSponsorshipTagging:
    def test_visa_sponsorship_keyword_matched(self):
        job = {
            "title": "Senior Data Analyst",
            "location": "Berlin, Germany",
            "description": "We offer visa sponsorship and relocation assistance for EU Blue Card eligible candidates.",
        }
        keywords = ["visa sponsorship", "relocation assistance", "eu blue card"]
        is_visa, term = tag_visa_sponsorship(job, keywords)
        assert is_visa is True
        assert term in keywords

    def test_visa_sponsorship_title_matched(self):
        job = {
            "title": "Business Analyst (Visa Sponsorship Provided)",
            "location": "Dubai, UAE",
            "description": "Join our team in Dubai.",
        }
        keywords = ["visa sponsorship"]
        is_visa, term = tag_visa_sponsorship(job, keywords)
        assert is_visa is True
        assert term == "visa sponsorship"

    def test_visa_sponsorship_no_match(self):
        job = {
            "title": "Product Analyst",
            "location": "Gurgaon, India",
            "description": "Standard local hiring process.",
        }
        keywords = ["visa sponsorship", "relocation provided"]
        is_visa, term = tag_visa_sponsorship(job, keywords)
        assert is_visa is False
        assert term is None


class TestLiveUrlAvailabilityCheck:
    @patch("requests.head")
    def test_live_url_check_404(self, mock_head):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_head.return_value = mock_resp

        url = "https://example.com/job/expired-123"
        assert is_url_live(url) is False

    @patch("requests.get")
    @patch("requests.head")
    def test_live_url_check_closed_text(self, mock_head, mock_get):
        mock_head_resp = MagicMock()
        mock_head_resp.status_code = 200
        mock_head_resp.headers = {"content-type": "text/html"}
        mock_head.return_value = mock_head_resp

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.headers = {"content-type": "text/html"}
        mock_get_resp.text = "<html><body>This position has been closed</body></html>"
        mock_get.return_value = mock_get_resp

        url = "https://example.com/job/closed-456"
        assert is_url_live(url) is False

    @patch("requests.head")
    def test_live_url_check_active(self, mock_head):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.text = "<html><body>Active job listing details...</body></html>"
        mock_head.return_value = mock_resp

        url = "https://example.com/job/active-789"
        assert is_url_live(url) is True
