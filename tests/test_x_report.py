"""Tests for X research result normalization/report rendering."""

from stealth_browser.x_report import normalize_research_result, render_research_markdown


def test_normalize_research_result():
    result = {
        "query": "ai agents",
        "session_id": "abcd1234",
        "engine": "chromium",
        "profile_name": "x-main",
        "search_url": "https://x.com/search?q=ai+agents",
        "tweets": [{"tweet_url": "u1"}, {"tweet_url": "u2"}],
    }
    normalized = normalize_research_result(result, kind="topic")
    assert normalized["kind"] == "topic"
    assert normalized["query"] == "ai agents"
    assert normalized["tweet_count"] == 2
    assert normalized["page_url"] == "https://x.com/search?q=ai+agents"
    assert normalized["data"] is result


def test_render_research_markdown():
    result = {
        "query": "ai agents",
        "tweets": [{"username": "alice", "tweet_text": "hello", "tweet_url": "u1"}],
        "research": {
            "summary": "Extracted 1 tweets for 'ai agents'.",
            "top_accounts": [{"username": "alice", "mentions": 1}],
            "top_terms": [{"term": "agents", "count": 1}],
            "linked_domains": [],
        },
    }
    md = render_research_markdown(result)
    assert "# X Research Report: ai agents" in md
    assert "## Summary" in md
    assert "@alice" in md
    assert "Sample Tweets" in md
