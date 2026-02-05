"""Tests for server helper functions and crawl logic."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urldefrag

from stealth_browser.server import _ephemeral_session, _extract_formatted, VALID_OUTPUT_FORMATS


class TestEphemeralSession:
    @pytest.mark.asyncio
    async def test_auto_close_when_no_session_id(self):
        manager = AsyncMock()
        session = MagicMock()
        session.id = "abc123"
        manager.get_or_create_session = AsyncMock(return_value=session)
        manager.close_session = AsyncMock()

        async with _ephemeral_session(manager, None) as s:
            assert s.id == "abc123"

        manager.close_session.assert_awaited_once_with("abc123")

    @pytest.mark.asyncio
    async def test_no_close_when_session_id_provided(self):
        manager = AsyncMock()
        session = MagicMock()
        session.id = "existing"
        manager.get_or_create_session = AsyncMock(return_value=session)
        manager.close_session = AsyncMock()

        async with _ephemeral_session(manager, "existing") as s:
            assert s.id == "existing"

        manager.close_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_auto_close_on_exception(self):
        manager = AsyncMock()
        session = MagicMock()
        session.id = "temp"
        manager.get_or_create_session = AsyncMock(return_value=session)
        manager.close_session = AsyncMock()

        with pytest.raises(RuntimeError):
            async with _ephemeral_session(manager, None) as s:
                raise RuntimeError("boom")

        manager.close_session.assert_awaited_once_with("temp")

    @pytest.mark.asyncio
    async def test_no_close_on_exception_with_existing_session(self):
        manager = AsyncMock()
        session = MagicMock()
        session.id = "existing"
        manager.get_or_create_session = AsyncMock(return_value=session)
        manager.close_session = AsyncMock()

        with pytest.raises(RuntimeError):
            async with _ephemeral_session(manager, "existing") as s:
                raise RuntimeError("boom")

        manager.close_session.assert_not_awaited()


class TestExtractFormatted:
    @pytest.mark.asyncio
    async def test_html_format(self):
        page = AsyncMock()
        page.content = AsyncMock(return_value="<html><body>Hello</body></html>")
        content, method = await _extract_formatted(page, "html", 50_000)
        assert method == "html"
        assert "<html>" in content

    @pytest.mark.asyncio
    async def test_links_format(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value='[{"text":"Example","href":"https://example.com"}]')
        content, method = await _extract_formatted(page, "links", 50_000)
        assert method == "links"
        assert "example.com" in content

    @pytest.mark.asyncio
    async def test_markdown_uses_auto_extract(self):
        page = AsyncMock()
        with patch("stealth_browser.server.extract_content", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = ("# Hello World", "trafilatura")
            content, method = await _extract_formatted(page, "markdown", 50_000)
            assert method == "trafilatura"
            assert "Hello World" in content
            mock_extract.assert_awaited_once_with(page, mode="auto")

    @pytest.mark.asyncio
    async def test_text_uses_auto_extract(self):
        page = AsyncMock()
        with patch("stealth_browser.server.extract_content", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = ("Plain text content", "innertext")
            content, method = await _extract_formatted(page, "text", 50_000)
            assert method == "innertext"
            mock_extract.assert_awaited_once_with(page, mode="auto")

    @pytest.mark.asyncio
    async def test_html_truncation(self):
        page = AsyncMock()
        page.content = AsyncMock(return_value="x" * 100_000)
        content, method = await _extract_formatted(page, "html", 1000)
        assert len(content) < 2000  # truncated + notice


class TestCrawlUrlNormalization:
    def test_fragment_stripped(self):
        url = "https://example.com/page#section"
        normalized = urldefrag(url)[0]
        assert normalized == "https://example.com/page"

    def test_no_fragment(self):
        url = "https://example.com/page"
        normalized = urldefrag(url)[0]
        assert normalized == "https://example.com/page"

    def test_empty_fragment(self):
        url = "https://example.com/page#"
        normalized = urldefrag(url)[0]
        assert normalized == "https://example.com/page"


class TestValidOutputFormats:
    def test_expected_formats(self):
        assert VALID_OUTPUT_FORMATS == {"markdown", "text", "html", "links"}
