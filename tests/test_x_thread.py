"""Tests for X thread extraction helpers."""

from unittest.mock import AsyncMock

import pytest

from stealth_browser.x_extract import read_x_thread


@pytest.mark.asyncio
async def test_read_x_thread_splits_main_tweet_and_replies():
    page = AsyncMock()
    page.evaluate = AsyncMock(
        return_value={
            "tweets": [
                {"tweet_url": "https://x.com/alice/status/1", "tweet_text": "main", "username": "alice"},
                {"tweet_url": "https://x.com/bob/status/2", "tweet_text": "reply 1", "username": "bob"},
                {"tweet_url": "https://x.com/carl/status/3", "tweet_text": "reply 2", "username": "carl"},
            ],
            "extracted_count": 3,
            "page_url": "https://x.com/alice/status/1",
            "page_title": "Alice on X",
        }
    )

    result = await read_x_thread(page, max_items=10)
    assert result["main_tweet"]["tweet_text"] == "main"
    assert result["reply_count_extracted"] == 2
    assert len(result["replies"]) == 2
    assert result["max_items"] == 10


@pytest.mark.asyncio
async def test_read_x_thread_handles_empty_thread():
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value={"tweets": [], "extracted_count": 0, "page_url": "https://x.com", "page_title": "X"})

    result = await read_x_thread(page, max_items=5)
    assert result["main_tweet"] is None
    assert result["replies"] == []
    assert result["reply_count_extracted"] == 0
