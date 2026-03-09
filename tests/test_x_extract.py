"""Tests for X/Twitter-specific extraction helpers."""

from unittest.mock import AsyncMock

import pytest

from stealth_browser.x_extract import (
    VALID_X_SEARCH_MODES,
    build_x_search_url,
    extract_x_search_results,
)


def test_build_x_search_url_top():
    url = build_x_search_url("ai agents", mode="top")
    assert url == "https://x.com/search?q=ai+agents&src=typed_query"


def test_build_x_search_url_latest():
    url = build_x_search_url("ai agents", mode="latest")
    assert url == "https://x.com/search?q=ai+agents&src=typed_query&f=live"


def test_build_x_search_url_invalid_mode():
    with pytest.raises(ValueError, match="Invalid mode"):
        build_x_search_url("ai agents", mode="users")


@pytest.mark.asyncio
async def test_extract_x_search_results_passes_through_page_evaluate():
    page = AsyncMock()
    page.evaluate = AsyncMock(
        return_value={
            "tweets": [
                {
                    "author_name": "Alice",
                    "username": "alice",
                    "tweet_text": "AI agents are everywhere",
                    "timestamp": "2026-03-09T10:00:00.000Z",
                    "tweet_url": "https://x.com/alice/status/123",
                    "has_media": False,
                    "is_promoted": False,
                    "reply_count": 1,
                    "retweet_count": 2,
                    "like_count": 3,
                }
            ],
            "extracted_count": 1,
            "page_url": "https://x.com/search?q=ai+agents&src=typed_query",
            "page_title": "Search / X",
        }
    )

    result = await extract_x_search_results(page, max_items=15)
    assert result["extracted_count"] == 1
    assert result["tweets"][0]["username"] == "alice"
    assert result["max_items"] == 15
    page.evaluate.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_x_search_results_clamps_max_items():
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value={"tweets": [], "extracted_count": 0, "page_url": "https://x.com", "page_title": "X"})

    result = await extract_x_search_results(page, max_items=999)
    assert result["max_items"] == 50


def test_valid_modes_constant():
    assert VALID_X_SEARCH_MODES == {"top", "latest"}
