"""Tests for heuristic X topic research summarization."""

from stealth_browser.x_research import summarize_x_topic


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
        },
        {
            "username": "alice",
            "tweet_text": "AI agents automate work with tools. https://example.com/other",
            "has_media": False,
            "is_promoted": False,
        },
        {
            "username": "bob",
            "tweet_text": "Agents and tools are the future. https://another.com/x",
            "has_media": False,
            "is_promoted": True,
        },
    ]

    result = summarize_x_topic("ai agents", tweets)
    assert result["tweet_count"] == 3
    assert result["top_accounts"][0] == {"username": "alice", "mentions": 2}
    assert result["linked_domains"][0] == {"domain": "example.com", "count": 2}
    assert result["media_count"] == 1
    assert result["promoted_count"] == 1
    assert "Extracted 3 tweets" in result["summary"]
    assert any(item["term"] == "agents" for item in result["top_terms"])
