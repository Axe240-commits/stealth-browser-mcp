"""Tests for content extraction pipeline."""

import pytest
from unittest.mock import AsyncMock, patch

from stealth_browser.extractor import extract_content, MIN_CONTENT_LENGTH


@pytest.fixture
def mock_page():
    """Create a mock Patchright page."""
    page = AsyncMock()
    page.content = AsyncMock(return_value="<html><body><p>Hello World</p></body></html>")
    page.inner_text = AsyncMock(return_value="Hello World from innertext")
    return page


class TestExtractContent:
    @pytest.mark.asyncio
    async def test_text_mode_uses_innertext(self, mock_page):
        content, method = await extract_content(mock_page, mode="text")
        assert method == "innertext"
        assert "Hello World from innertext" in content
        mock_page.inner_text.assert_called_once_with("body")

    @pytest.mark.asyncio
    async def test_fallback_to_innertext(self, mock_page):
        """When trafilatura returns too little, falls through to later tiers."""
        with patch("trafilatura.extract", return_value="short"):
            content, method = await extract_content(mock_page, mode="auto")
            # Should have fallen through since trafilatura returned too little
            assert method in ("readability", "innertext")

    @pytest.mark.asyncio
    async def test_trafilatura_success(self, mock_page):
        long_content = "A" * (MIN_CONTENT_LENGTH + 100)
        with patch("trafilatura.extract", return_value=long_content):
            content, method = await extract_content(mock_page, mode="auto")
            assert method == "trafilatura"
            assert content == long_content

    @pytest.mark.asyncio
    async def test_empty_page(self, mock_page):
        mock_page.content = AsyncMock(return_value="<html><body></body></html>")
        mock_page.inner_text = AsyncMock(return_value="")
        content, method = await extract_content(mock_page, mode="auto")
        assert method in ("none", "innertext")
