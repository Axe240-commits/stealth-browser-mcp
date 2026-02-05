"""Configuration for stealth browser."""

from dataclasses import dataclass


@dataclass
class Config:
    headless: bool = False
    use_xvfb: bool = True
    max_sessions: int = 5
    session_timeout_minutes: int = 10
    navigation_timeout_ms: int = 30000
    wait_until: str = "domcontentloaded"
    max_content_length: int = 50_000
    block_media: bool = True
    channel: str = "chromium"
    crawl_per_page_max: int = 10_000
    crawl_max_pages_limit: int = 20
    camoufox_enabled: bool = True
