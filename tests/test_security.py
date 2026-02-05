"""Tests for SSRF validation and smart truncation."""

import pytest

from stealth_browser.security import (
    SecurityError,
    is_private_ip,
    smart_truncate,
    validate_url,
)


class TestIsPrivateIP:
    def test_loopback_v4(self):
        assert is_private_ip("127.0.0.1") is True

    def test_loopback_v6(self):
        assert is_private_ip("::1") is True

    def test_private_10(self):
        assert is_private_ip("10.0.0.1") is True

    def test_private_172(self):
        assert is_private_ip("172.16.0.1") is True

    def test_private_192(self):
        assert is_private_ip("192.168.1.1") is True

    def test_link_local(self):
        assert is_private_ip("169.254.1.1") is True

    def test_cloud_metadata(self):
        assert is_private_ip("169.254.169.254") is True

    def test_multicast(self):
        assert is_private_ip("224.0.0.1") is True

    def test_public_ip(self):
        assert is_private_ip("8.8.8.8") is False

    def test_public_ip_2(self):
        assert is_private_ip("1.1.1.1") is False

    def test_public_v6(self):
        assert is_private_ip("2607:f8b0:4004:800::200e") is False


class TestValidateUrl:
    def test_http_public(self):
        # Should not raise for public URLs
        validate_url("https://example.com")

    def test_blocked_file_scheme(self):
        with pytest.raises(SecurityError, match="Blocked scheme"):
            validate_url("file:///etc/passwd")

    def test_blocked_javascript(self):
        with pytest.raises(SecurityError, match="Blocked scheme"):
            validate_url("javascript:alert(1)")

    def test_blocked_data(self):
        with pytest.raises(SecurityError, match="Blocked scheme"):
            validate_url("data:text/html,<h1>hi</h1>")

    def test_blocked_ftp(self):
        with pytest.raises(SecurityError, match="Blocked scheme"):
            validate_url("ftp://example.com/file")

    def test_no_hostname(self):
        with pytest.raises(SecurityError, match="No hostname"):
            validate_url("http://")

    def test_localhost_blocked(self):
        with pytest.raises(SecurityError, match="private"):
            validate_url("http://localhost/admin")

    def test_127_blocked(self):
        with pytest.raises(SecurityError, match="private"):
            validate_url("http://127.0.0.1:8080/")

    def test_private_ip_blocked(self):
        with pytest.raises(SecurityError, match="private"):
            validate_url("http://192.168.1.1/")

    def test_dns_failure(self):
        with pytest.raises(SecurityError, match="DNS resolution failed"):
            validate_url("https://this-domain-definitely-does-not-exist-xyz123.com")


class TestSmartTruncate:
    def test_no_truncation_needed(self):
        text = "Hello world"
        result, truncated = smart_truncate(text, 100)
        assert result == "Hello world"
        assert truncated is False

    def test_truncates_on_paragraph(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        result, truncated = smart_truncate(text, 30)
        assert "Paragraph one." in result
        assert "truncated" in result
        assert truncated is True

    def test_truncates_on_line(self):
        text = "Line one\nLine two\nLine three\nLine four"
        result, truncated = smart_truncate(text, 25)
        assert truncated is True
        assert "truncated" in result

    def test_exact_length(self):
        text = "x" * 100
        result, truncated = smart_truncate(text, 100)
        assert result == text
        assert truncated is False

    def test_hard_cut_when_no_boundaries(self):
        text = "a" * 200
        result, truncated = smart_truncate(text, 100)
        assert truncated is True
        assert len(result) > 90  # hard cut + truncation notice
