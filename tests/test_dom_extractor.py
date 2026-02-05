"""Tests for structured DOM extraction."""

import pytest
from unittest.mock import AsyncMock

from stealth_browser.dom_extractor import extract_dom_data, ALLOWED_SECTIONS


@pytest.fixture
def mock_page():
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value={
        "metadata": {
            "description": "Test page",
            "canonical": "https://example.com/test",
            "language": "en",
            "author": "Test Author",
        },
        "og_tags": {"og:title": "OG Title", "og:image": "https://example.com/img.png"},
        "json_ld": [{"@type": "Article", "name": "Test"}],
        "headings": [
            {"level": 1, "text": "Main Heading"},
            {"level": 2, "text": "Sub Heading"},
        ],
        "links": [
            {"text": "Example", "href": "https://example.com"},
            {"text": "Other", "href": "https://other.com"},
        ],
        "tables": [[["A", "B"], ["1", "2"]]],
        "forms": [{"action": "/submit", "method": "POST", "fields": [
            {"tag": "input", "type": "text", "name": "q", "id": "search"}
        ]}],
    })
    return page


class TestExtractDomData:
    @pytest.mark.asyncio
    async def test_all_sections_returned(self, mock_page):
        result = await extract_dom_data(mock_page)
        assert set(result.keys()) == ALLOWED_SECTIONS
        assert result["metadata"]["description"] == "Test page"
        assert len(result["headings"]) == 2
        assert len(result["links"]) == 2
        assert len(result["tables"]) == 1
        assert len(result["forms"]) == 1

    @pytest.mark.asyncio
    async def test_include_filter(self, mock_page):
        result = await extract_dom_data(mock_page, include=["metadata", "headings"])
        assert set(result.keys()) == {"metadata", "headings"}
        assert result["metadata"]["author"] == "Test Author"
        assert result["headings"][0]["level"] == 1

    @pytest.mark.asyncio
    async def test_include_single(self, mock_page):
        result = await extract_dom_data(mock_page, include=["json_ld"])
        assert set(result.keys()) == {"json_ld"}
        assert result["json_ld"][0]["@type"] == "Article"

    @pytest.mark.asyncio
    async def test_include_empty_list(self, mock_page):
        result = await extract_dom_data(mock_page, include=[])
        assert result == {}

    @pytest.mark.asyncio
    async def test_unknown_section_raises(self, mock_page):
        with pytest.raises(ValueError, match="Unknown sections.*bogus"):
            await extract_dom_data(mock_page, include=["metadata", "bogus"])

    @pytest.mark.asyncio
    async def test_unknown_section_error_message_lists_allowed(self, mock_page):
        with pytest.raises(ValueError, match="Allowed:"):
            await extract_dom_data(mock_page, include=["nope"])

    @pytest.mark.asyncio
    async def test_multiple_unknown_sections(self, mock_page):
        with pytest.raises(ValueError, match="Unknown sections.*'bad1'.*'bad2'"):
            await extract_dom_data(mock_page, include=["bad1", "bad2"])

    @pytest.mark.asyncio
    async def test_none_include_returns_all(self, mock_page):
        result = await extract_dom_data(mock_page, include=None)
        assert set(result.keys()) == ALLOWED_SECTIONS


class TestExtractDomDataEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_dom_result(self):
        page = AsyncMock()
        page.evaluate = AsyncMock(return_value={
            "metadata": {"description": "", "canonical": "", "language": "", "author": ""},
            "og_tags": {},
            "json_ld": [],
            "headings": [],
            "links": [],
            "tables": [],
            "forms": [],
        })
        result = await extract_dom_data(page)
        assert result["json_ld"] == []
        assert result["links"] == []
        assert result["tables"] == []

    @pytest.mark.asyncio
    async def test_large_data_passthrough(self):
        """Verify we pass through what JS returns (JS enforces limits)."""
        page = AsyncMock()
        many_headings = [{"level": 1, "text": f"H{i}"} for i in range(200)]
        page.evaluate = AsyncMock(return_value={
            "metadata": {"description": "", "canonical": "", "language": "", "author": ""},
            "og_tags": {},
            "json_ld": [],
            "headings": many_headings,
            "links": [],
            "tables": [],
            "forms": [],
        })
        result = await extract_dom_data(page, include=["headings"])
        assert len(result["headings"]) == 200
