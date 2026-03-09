"""Formatting and normalization helpers for X research outputs."""

from __future__ import annotations

from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_research_result(result: dict, kind: str) -> dict:
    """Normalize different X research outputs into a stable envelope."""
    return {
        "kind": kind,
        "generated_at": _now_iso(),
        "query": result.get("query"),
        "session_id": result.get("session_id"),
        "engine": result.get("engine"),
        "profile_name": result.get("profile_name"),
        "page_url": result.get("page_url") or result.get("search_url") or result.get("url"),
        "tweet_count": result.get("extracted_count") or result.get("tweet_count") or len(result.get("tweets", [])),
        "data": result,
    }


def render_research_markdown(result: dict) -> str:
    """Render a compact markdown report for research_x_topic(_deep) output."""
    query = result.get("query", "")
    research = result.get("deep_research") or result.get("research") or {}
    tweets = result.get("tweets", [])
    lines = []
    lines.append(f"# X Research Report: {query}")
    lines.append("")
    if research.get("summary"):
        lines.append("## Summary")
        lines.append(research["summary"])
        lines.append("")

    top_accounts = research.get("top_accounts") or []
    if top_accounts:
        lines.append("## Top Accounts")
        for item in top_accounts[:5]:
            lines.append(f"- @{item['username']} ({item['mentions']})")
        lines.append("")

    top_terms = research.get("top_terms") or []
    if top_terms:
        lines.append("## Frequent Terms")
        lines.append(", ".join(f"{item['term']} ({item['count']})" for item in top_terms[:10]))
        lines.append("")

    domains = research.get("linked_domains") or []
    if domains:
        lines.append("## Linked Domains")
        for item in domains[:5]:
            lines.append(f"- {item['domain']} ({item['count']})")
        lines.append("")

    deep = result.get("deep_research") or {}
    highlights = deep.get("deep_dive_highlights") or []
    if highlights:
        lines.append("## Deep Dive Highlights")
        for item in highlights[:5]:
            user = item.get("username") or "unknown"
            text = item.get("text") or ""
            url = item.get("tweet_url") or ""
            lines.append(f"- @{user}: {text}")
            if url:
                lines.append(f"  - {url}")
        lines.append("")

    if tweets:
        lines.append("## Sample Tweets")
        for tweet in tweets[:5]:
            user = tweet.get("username") or "unknown"
            text = tweet.get("tweet_text") or ""
            url = tweet.get("tweet_url") or ""
            lines.append(f"- @{user}: {text}")
            if url:
                lines.append(f"  - {url}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"
