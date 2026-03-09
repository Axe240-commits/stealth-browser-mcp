"""Formatting, normalization, and persistence helpers for X research outputs."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from stealth_browser.persistence import get_app_dir


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def slugify(text: str, default: str = "report") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return slug[:80] or default


def get_reports_dir() -> Path:
    path = get_app_dir() / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


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


def save_report_bundle(result: dict, kind: str, name: str | None = None) -> dict:
    """Save normalized JSON and markdown report to disk."""
    normalized = result.get("normalized") or normalize_research_result(result, kind=kind)
    markdown = result.get("report_markdown") or render_research_markdown(result)
    query = result.get("query") or name or kind
    stamp = _now().strftime("%Y%m%d-%H%M%S")
    slug = slugify(name or query)
    bundle_dir = get_reports_dir() / f"{stamp}-{slug}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    json_path = bundle_dir / "report.json"
    md_path = bundle_dir / "report.md"
    meta_path = bundle_dir / "meta.json"

    json_path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False, sort_keys=True))
    md_path.write_text(markdown)
    meta = {
        "query": query,
        "kind": normalized.get("kind", kind),
        "generated_at": normalized.get("generated_at", _now_iso()),
        "tweet_count": normalized.get("tweet_count"),
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True))

    return {
        "bundle_dir": str(bundle_dir),
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "meta_path": str(meta_path),
        "meta": meta,
    }


def list_saved_reports() -> list[dict]:
    reports_dir = get_reports_dir()
    results = []
    for entry in sorted(reports_dir.iterdir(), key=lambda p: p.name, reverse=True):
        if not entry.is_dir():
            continue
        meta_path = entry / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            meta = {"error": "invalid_meta"}
        results.append({
            "bundle_dir": str(entry),
            "meta": meta,
        })
    return results
