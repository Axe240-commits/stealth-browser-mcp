"""Browser session state with per-session locking."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from stealth_browser.extractor import extract_content
from stealth_browser.security import SecurityError, smart_truncate, validate_redirect

if TYPE_CHECKING:
    from patchright.async_api import BrowserContext, Page

logger = logging.getLogger(__name__)


CAPTCHA_SELECTORS = [
    "iframe[src*='captcha']",
    "iframe[src*='challenge']",
    "iframe[src*='turnstile']",
    "#cf-challenge-running",
    ".cf-challenge",
    "[data-testid='challenge']",
    "#captcha",
    ".g-recaptcha",
    ".h-captcha",
]


@dataclass
class PageInfo:
    url: str
    title: str
    status_code: int | None


@dataclass
class Session:
    id: str
    context: BrowserContext
    page: Page
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _status_code: int | None = field(default=None, init=False)

    def _touch(self) -> None:
        self.last_used = datetime.now(timezone.utc)

    def _setup_request_interceptor(self) -> None:
        """Intercept requests to validate redirects against SSRF."""
        def on_response(response):
            self._status_code = response.status

        self.page.on("response", on_response)

    async def navigate(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        wait_for: str | None = None,
        timeout_ms: int = 30000,
        max_content_length: int = 50_000,
    ) -> dict:
        """Navigate to URL and extract content. Returns result dict."""
        async with self.lock:
            self._touch()
            start = time.monotonic()
            self._status_code = None

            response = await self.page.goto(
                url, wait_until=wait_until, timeout=timeout_ms
            )
            if response:
                self._status_code = response.status

                # Check redirect chain for SSRF
                if response.url != url:
                    try:
                        validate_redirect(response.url)
                    except SecurityError:
                        await self.page.goto("about:blank")
                        raise

            # Optional: wait for specific selector
            if wait_for:
                try:
                    await self.page.wait_for_selector(
                        wait_for, timeout=timeout_ms
                    )
                except Exception:
                    logger.debug("wait_for selector %r timed out", wait_for)

            # Detect CAPTCHA
            captcha_detected = await self._detect_captcha()

            # If CAPTCHA detected, wait 5s for auto-resolve (Cloudflare Turnstile)
            if captcha_detected:
                await asyncio.sleep(5)
                captcha_detected = await self._detect_captcha()

            # Extract content
            content, method = await extract_content(self.page)
            content, truncated = smart_truncate(content, max_content_length)
            title = await self.page.title()
            elapsed = int((time.monotonic() - start) * 1000)

            return {
                "url": self.page.url,
                "title": title,
                "content": content,
                "session_id": self.id,
                "truncated": truncated,
                "captcha_detected": captcha_detected,
                "extraction_method": method,
                "timing_ms": elapsed,
                "status_code": self._status_code,
            }

    async def perform_action(
        self, action: str, selector: str, value: str | None = None
    ) -> dict:
        """Perform an interaction on the page. Returns result dict."""
        async with self.lock:
            self._touch()
            start = time.monotonic()
            description = ""

            action_lower = action.lower()

            if action_lower == "click":
                await self.page.click(selector)
                description = f"clicked {selector}"

            elif action_lower == "type":
                if value is None:
                    raise ValueError("'value' is required for type action")
                await self.page.fill(selector, value)
                description = f"typed into {selector}"

            elif action_lower == "select":
                if value is None:
                    raise ValueError("'value' is required for select action")
                await self.page.select_option(selector, value)
                description = f"selected '{value}' in {selector}"

            elif action_lower == "hover":
                await self.page.hover(selector)
                description = f"hovered {selector}"

            elif action_lower == "scroll":
                if value:
                    # value = pixel amount, e.g. "500" or "-500"
                    await self.page.evaluate(f"window.scrollBy(0, {int(value)})")
                    description = f"scrolled {value}px"
                else:
                    await self.page.evaluate(
                        "window.scrollBy(0, window.innerHeight)"
                    )
                    description = "scrolled one viewport down"

            else:
                raise ValueError(
                    f"Unknown action: {action!r}. "
                    f"Valid: click, type, select, hover, scroll"
                )

            # Small wait for page reactions
            await asyncio.sleep(0.3)

            elapsed = int((time.monotonic() - start) * 1000)

            return {
                "success": True,
                "session_id": self.id,
                "action_performed": description,
                "page_url": self.page.url,
                "timing_ms": elapsed,
            }

    async def get_content(self, mode: str = "auto", max_length: int = 50_000) -> dict:
        """Re-extract content from current page."""
        async with self.lock:
            self._touch()
            content, method = await extract_content(self.page, mode=mode)
            content, truncated = smart_truncate(content, max_length)
            return {
                "content": content,
                "session_id": self.id,
                "url": self.page.url,
                "extraction_method": method,
                "truncated": truncated,
            }

    async def _detect_captcha(self) -> bool:
        """Check for known CAPTCHA selectors on the page."""
        for sel in CAPTCHA_SELECTORS:
            try:
                el = await self.page.query_selector(sel)
                if el:
                    return True
            except Exception:
                pass
        return False

    async def close(self) -> None:
        """Close this session's context (and its page)."""
        try:
            await self.context.close()
        except Exception:
            logger.debug("Error closing session %s", self.id, exc_info=True)
