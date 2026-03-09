"""Tests for heuristic X topic research summarization."""

from stealth_browser.x_research import (
    pick_deep_dive_candidates,
    score_tweet_for_deep_dive,
    summarize_deep_research,
    summarize_x_topic,
)


def test_summarize_x_topic_empty():
    result = summarize_x_topic("ai agents", [])
    assert result["tweet_count"] == 0
    assert "No tweet results extracted" in result["summary"]


def test_summarize_x_topic_counts_accounts_terms_and_domains():
    tweets = [
        {
            "username": "alice",
            "tweet_text": "AI agents are useful. https://example.com/post",
            "has_media": True,
            "is_promoted": False,
            "quoted_tweet": None,
        },
        {
            "username": "alice",
            "tweet_text": "AI agents automate work with tools. https://example.com/other",
            "has_media": False,
            "is_promoted": False,
            "quoted_tweet": {"tweet_url": "https://x.com/z/status/9", "tweet_text": "quoted"},
        },
        {
            "username": "bob",
            "tweet_text": "Agents and tools are the future. https://another.com/x",
            "has_media": False,
            "is_promoted": True,
            "quoted_tweet": None,
        },
    ]

    result = summarize_x_topic("ai agents", tweets)
    assert result["tweet_count"] == 3
    assert result["top_accounts"][0] == {"username": "alice", "mentions": 2}
    assert result["linked_domains"][0] == {"domain": "example.com", "count": 2}
    assert result["media_count"] == 1
    assert result["promoted_count"] == 1
    assert result["quote_count"] == 1
    assert "Extracted 3 tweets" in result["summary"]
    assert any(item["term"] == "agents" for item in result["top_terms"])


def test_score_and_pick_deep_dive_candidates():
    tweets = [
        {"tweet_url": "u1", "like_count": 5, "reply_count": 1},
        {"tweet_url": "u2", "like_count": 50, "quoted_tweet": {"tweet_url": "q"}},
        {"tweet_url": "u3", "view_count": 1000},
    ]
    assert score_tweet_for_deep_dive(tweets[1]) > score_tweet_for_deep_dive(tweets[0])
    picked = pick_deep_dive_candidates(tweets, limit=2)
    assert len(picked) == 2
    assert picked[0]["tweet_url"] in {"u2", "u3"}


def test_summarize_deep_research():
    tweets = [{"username": "alice", "tweet_text": "Agents!", "tweet_url": "u1", "has_media": False, "is_promoted": False, "quoted_tweet": None}]
    threads = [
        {
            "main_tweet": {"tweet_url": "u1", "username": "alice", "tweet_text": "Agents!"},
            "reply_count_extracted": 2,
        }
    ]
    result = summarize_deep_research("agents", tweets, threads)
    assert result["thread_count"] == 1
    assert result["reply_total_extracted"] == 2
    assert result["deep_dive_urls"] == ["u1"]
    assert result["deep_dive_highlights"][0]["username"] == "alice"
