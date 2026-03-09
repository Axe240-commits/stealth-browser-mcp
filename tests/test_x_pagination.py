"""Tests for multi-round X search result collection."""

from unittest.mock import AsyncMock

import pytest

from stealth_browser.x_extract import collect_x_search_results, dedupe_tweets


def test_dedupe_tweets_by_url_and_fallback_key():
    tweets = [
        {"tweet_url": "https://x.com/a/status/1", "tweet_text": "hello", "username": "a"},
        {"tweet_url": "https://x.com/a/status/1", "tweet_text": "hello", "username": "a"},
        {"tweet_url": None, "tweet_text": "same text", "username": "b"},
        {"tweet_url": None, "tweet_text": "same text", "username": "b"},
    ]
    result = dedupe_tweets(tweets)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_collect_x_search_results_across_scroll_rounds():
    page = AsyncMock()
    page.title = AsyncMock(return_value="Search / X")
    page.url = "https://x.com/search?q=test"
    page.evaluate = AsyncMock(side_effect=[
        {
            "tweets": [{"tweet_url": "https://x.com/a/status/1", "tweet_text": "one", "username": "a"}],
            "extracted_count": 1,
            "page_url": page.url,
            "page_title": "Search / X",
            "max_items": 5,
        },
        None,
        {
            "tweets": [
                {"tweet_url": "https://x.com/a/status/1", "tweet_text": "one", "username": "a"},
                {"tweet_url": "https://x.com/b/status/2", "tweet_text": "two", "username": "b"},
            ],
            "extracted_count": 2,
            "page_url": page.url,
            "page_title": "Search / X",
            "max_items": 5,
        },
    ])
    sleep_mock = AsyncMock()
    result = await collect_x_search_results(page, max_items=5, scroll_rounds=1, sleep_fn=sleep_mock)

    assert result["extracted_count"] == 2
    assert len(result["tweets"]) == 2
    assert result["scroll_rounds_completed"] == 2
    sleep_mock.assert_awaited_once()
