"""Heuristic summarization helpers for X/Twitter search results."""

from __future__ import annotations

import re
from collections import Counter

STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "have", "your", "about",
    "there", "their", "they", "them", "would", "could", "should", "into", "while",
    "what", "when", "where", "which", "will", "just", "than", "then", "also", "more",
    "less", "over", "under", "after", "before", "because", "some", "such", "only",
    "very", "much", "many", "still", "being", "been", "were", "does", "dont", "did",
    "not", "you", "are", "our", "out", "all", "any", "can", "get", "got", "too",
    "ein", "eine", "einer", "eines", "einem", "einen", "und", "oder", "aber", "doch",
    "nicht", "kein", "keine", "der", "die", "das", "den", "dem", "des", "ist", "sind",
    "war", "waren", "mit", "auf", "für", "von", "bei", "aus", "wie", "was", "wer",
    "wird", "werden", "noch", "schon", "auch", "nur", "mehr", "sehr", "eine", "einer",
    "zum", "zur", "über", "unter", "wenn", "dann", "weil", "dass", "man", "wir", "ihr",
    "sie", "ich", "du", "im", "in", "an", "am", "zu", "so", "es",
}

WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß0-9_#@-]{3,}")


def _tokenize(text: str) -> list[str]:
    tokens = []
    for raw in WORD_RE.findall(text or ""):
        token = raw.lower().strip("-_@#")
        if len(token) < 3 or token in STOPWORDS or token.isdigit():
            continue
        tokens.append(token)
    return tokens


def summarize_x_topic(query: str, tweets: list[dict], top_n: int = 5) -> dict:
    top_n = max(1, min(int(top_n), 10))
    total = len(tweets)

    usernames = Counter()
    terms = Counter()
    domains = Counter()
    media_count = 0
    promoted_count = 0

    for tweet in tweets:
        username = tweet.get("username")
        if username:
            usernames[username] += 1

        text = tweet.get("tweet_text") or ""
        terms.update(_tokenize(text))

        for match in re.findall(r"https?://([^/\s]+)", text):
            domains[match.lower()] += 1

        if tweet.get("has_media"):
            media_count += 1
        if tweet.get("is_promoted"):
            promoted_count += 1

    top_accounts = [
        {"username": username, "mentions": count}
        for username, count in usernames.most_common(top_n)
    ]
    top_terms = [
        {"term": term, "count": count}
        for term, count in terms.most_common(top_n)
    ]
    linked_domains = [
        {"domain": domain, "count": count}
        for domain, count in domains.most_common(top_n)
    ]

    if total == 0:
        short_summary = f"No tweet results extracted for query: {query}"
    else:
        summary_parts = [f"Extracted {total} tweets for '{query}'."]
        if top_accounts:
            summary_parts.append(
                "Most visible accounts: " + ", ".join(f"@{a['username']} ({a['mentions']})" for a in top_accounts[:3])
            )
        if top_terms:
            summary_parts.append(
                "Frequent terms: " + ", ".join(f"{t['term']} ({t['count']})" for t in top_terms[:5])
            )
        if linked_domains:
            summary_parts.append(
                "Common linked domains: " + ", ".join(f"{d['domain']} ({d['count']})" for d in linked_domains[:3])
            )
        if media_count:
            summary_parts.append(f"{media_count} tweets include media.")
        if promoted_count:
            summary_parts.append(f"{promoted_count} extracted cards look promoted.")
        short_summary = " ".join(summary_parts)

    return {
        "query": query,
        "tweet_count": total,
        "top_accounts": top_accounts,
        "top_terms": top_terms,
        "linked_domains": linked_domains,
        "media_count": media_count,
        "promoted_count": promoted_count,
        "summary": short_summary,
    }
