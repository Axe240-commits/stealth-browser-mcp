"""MCP Server with 7 stealth browser tools."""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urlparse, urljoin, urldefrag

from mcp.server.fastmcp import FastMCP, Context

from stealth_browser.browser_manager import BrowserManager
from stealth_browser.config import Config
from stealth_browser.dom_extractor import extract_dom_data
from stealth_browser.extractor import extract_content
from stealth_browser.security import SecurityError, smart_truncate, validate_url

logger = logging.getLogger(__name__)

VALID_OUTPUT_FORMATS = {"markdown", "text", "html", "links"}
VALID_ENGINES = {"auto", "chromium", "firefox"}

BOT_BLOCK_SIGNALS = [
    "bot detected",
    "just a moment",
    "attention required",
    "access denied",
    "blocked by bot protection",
    "checking your browser",
    "verify you are human",
    "please enable cookies",
]


def _is_bot_blocked(result: dict) -> bool:
    """Detect whether the response looks like a bot-block page."""
    if "error" in result:
        return False  # actual error, not a bot block

    title = (result.get("title") or "").lower()
    content = result.get("content") or ""
    status = result.get("status_code")

    if status == 403:
        return True
    if any(sig in title for sig in BOT_BLOCK_SIGNALS):
        return True
    if len(content.strip()) < 50 and status in (200, 204):
        return True  # Empty page = likely JS challenge not resolved
    return False


@dataclass
class AppContext:
    manager: BrowserManager
    config: Config


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    """Start browser on server init, stop on shutdown."""
    config = Config()
    manager = BrowserManager()
    await manager.start(config)
    try:
        yield AppContext(manager=manager, config=config)
    finally:
        await manager.stop()


mcp = FastMCP(
    "stealth-browser",
    lifespan=app_lifespan,
)


def _get_app(ctx: Context) -> AppContext:
    """Extract AppContext from lifespan context."""
    return ctx.request_context.lifespan_context


def _resolve_engine(engine: str, app: AppContext) -> str:
    """Resolve 'auto' to 'chromium' (the first-try engine)."""
    if engine == "auto":
        return "chromium"
    return engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _ephemeral_session(
    manager: BrowserManager, session_id: str | None, engine: str = "chromium"
):
    """Manage session lifecycle: auto-close only if we created it.

    If session_id is None: create new session, auto-close in finally.
    If session_id is provided: reuse existing, never auto-close.
    """
    created = session_id is None
    session = await manager.get_or_create_session(session_id, engine=engine)
    try:
        yield session
    except Exception:
        if created:
            await manager.close_session(session.id)
        raise
    else:
        if created:
            await manager.close_session(session.id)


async def _extract_formatted(page, output_format: str, max_length: int) -> tuple[str, str]:
    """Extract content in the requested format.

    Returns (content, extraction_method).
    """
    if output_format == "html":
        raw = await page.content()
        content, truncated = smart_truncate(raw, max_length)
        return content, "html"

    if output_format == "links":
        links = await page.evaluate("""
            () => {
                const seen = new Set();
                const results = [];
                document.querySelectorAll('a[href]').forEach(el => {
                    if (results.length >= 500) return;
                    const href = el.href;
                    if (!href || seen.has(href)) return;
                    seen.add(href);
                    results.push({
                        text: (el.textContent || '').trim().slice(0, 200),
                        href: href
                    });
                });
                return JSON.stringify(results);
            }
        """)
        return links, "links"

    # markdown and text: use existing 3-tier pipeline (auto mode)
    content, method = await extract_content(page, mode="auto")
    content, _ = smart_truncate(content, max_length)
    return content, method


# ---------------------------------------------------------------------------
# Core tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def browse(
    url: str,
    session_id: str | None = None,
    wait_for: str | None = None,
    engine: str = "auto",
    ctx: Context = None,
) -> dict:
    """Navigate to a URL and return page content as clean markdown.

    Args:
        url: The URL to navigate to (http/https only).
        session_id: Optional session ID to reuse. If omitted, creates a new session.
        wait_for: Optional CSS selector to wait for before extracting content.
        engine: Browser engine — 'auto' (try Chromium, fallback to Firefox on bot-block),
                'chromium' (Patchright only), or 'firefox' (Camoufox only).

    Returns structured data:
        url, title, content, session_id, truncated, captcha_detected,
        extraction_method, timing_ms, status_code, engine
    """
    app = _get_app(ctx)

    if engine not in VALID_ENGINES:
        return {"error": f"Invalid engine: {engine!r}. Valid: {sorted(VALID_ENGINES)}"}

    # SSRF validation
    try:
        validate_url(url)
    except SecurityError as e:
        return {"error": str(e), "session_id": session_id or ""}

    use_auto = engine == "auto"
    first_engine = _resolve_engine(engine, app)

    session = await app.manager.get_or_create_session(session_id, engine=first_engine)
    try:
        result = await session.navigate(
            url=url,
            wait_until=app.config.wait_until,
            wait_for=wait_for,
            timeout_ms=app.config.navigation_timeout_ms,
            max_content_length=app.config.max_content_length,
        )
        result["engine"] = first_engine

        # Auto-fallback: if bot-blocked on chromium, retry with firefox
        if use_auto and first_engine == "chromium" and _is_bot_blocked(result):
            if app.manager._camoufox_browser:
                logger.info("Bot-blocked on chromium for %s, retrying with firefox", url)
                # Close the chromium session if we created it
                if not session_id:
                    await app.manager.close_session(session.id)
                ff_session = await app.manager.get_or_create_session(engine="firefox")
                try:
                    result = await ff_session.navigate(
                        url=url,
                        wait_until=app.config.wait_until,
                        wait_for=wait_for,
                        timeout_ms=app.config.navigation_timeout_ms,
                        max_content_length=app.config.max_content_length,
                    )
                    result["engine"] = "firefox"
                    result["fallback"] = True
                except Exception as e:
                    logger.error("Firefox fallback failed: %s", e, exc_info=True)
                    # Return original chromium result if firefox also fails
                    result["fallback_error"] = str(e)

        return result
    except SecurityError as e:
        return {"error": str(e), "session_id": session.id}
    except Exception as e:
        logger.error("browse failed: %s", e, exc_info=True)
        return {"error": str(e), "session_id": session.id}


@mcp.tool()
async def interact(
    session_id: str,
    action: str,
    selector: str,
    value: str | None = None,
    ctx: Context = None,
) -> dict:
    """Interact with the current page in a session.

    Args:
        session_id: The session to interact with (from a previous browse call).
        action: One of: click, type, select, hover, scroll.
        selector: CSS selector for the target element (ignored for scroll without target).
        value: Required for 'type' and 'select' actions. For 'scroll', pixel amount.

    Returns structured data:
        success, session_id, action_performed, page_url, timing_ms
    """
    app = _get_app(ctx)

    session = app.manager._sessions.get(session_id)
    if not session:
        return {"error": f"Session {session_id!r} not found", "success": False}

    try:
        result = await session.perform_action(action, selector, value)

        # Validate URL after action (may have navigated)
        try:
            validate_url(session.page.url)
        except SecurityError:
            # Page navigated to blocked URL, go back
            await session.page.goto("about:blank")
            return {"error": "Action caused navigation to blocked URL", "success": False, "session_id": session_id}

        return result
    except Exception as e:
        return {"error": str(e), "success": False, "session_id": session_id}


@mcp.tool()
async def extract(
    session_id: str,
    mode: str = "auto",
    ctx: Context = None,
) -> dict:
    """Re-extract content from the current page of a session.

    Args:
        session_id: The session to extract from.
        mode: Extraction mode - 'auto' (try all tiers), 'article', or 'text' (raw innertext).

    Returns structured data:
        content, session_id, url, extraction_method, truncated
    """
    app = _get_app(ctx)

    session = app.manager._sessions.get(session_id)
    if not session:
        return {"error": f"Session {session_id!r} not found"}

    try:
        result = await session.get_content(
            mode=mode, max_length=app.config.max_content_length
        )
        return result
    except Exception as e:
        return {"error": str(e), "session_id": session_id}


@mcp.tool()
async def close_session(
    session_id: str,
    ctx: Context = None,
) -> dict:
    """Close a browser session and free its resources.

    Args:
        session_id: The session to close.

    Returns:
        status message confirming closure.
    """
    app = _get_app(ctx)

    if session_id not in app.manager._sessions:
        return {"status": "not_found", "message": f"Session {session_id!r} not found"}

    await app.manager.close_session(session_id)
    return {"status": "closed", "session_id": session_id}


# ---------------------------------------------------------------------------
# High-level tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def scrape_webpage(
    url: str,
    output_format: str = "markdown",
    session_id: str | None = None,
    wait_for: str | None = None,
    engine: str = "auto",
    ctx: Context = None,
) -> dict:
    """Scrape a webpage and return content in the requested format.

    Args:
        url: The URL to scrape (http/https only).
        output_format: One of 'markdown', 'text', 'html', 'links'. Default 'markdown'.
        session_id: Optional session ID to reuse. If omitted, creates an ephemeral session that auto-closes.
        wait_for: Optional CSS selector to wait for before extracting.
        engine: Browser engine — 'auto', 'chromium', or 'firefox'.

    Returns structured data:
        url, title, content, session_id, status_code, timing_ms, extraction_method, engine
    """
    app = _get_app(ctx)

    if output_format not in VALID_OUTPUT_FORMATS:
        return {"error": f"Invalid output_format: {output_format!r}. Valid: {sorted(VALID_OUTPUT_FORMATS)}"}

    if engine not in VALID_ENGINES:
        return {"error": f"Invalid engine: {engine!r}. Valid: {sorted(VALID_ENGINES)}"}

    try:
        validate_url(url)
    except SecurityError as e:
        return {"error": str(e)}

    use_auto = engine == "auto"
    first_engine = _resolve_engine(engine, app)

    try:
        async with _ephemeral_session(app.manager, session_id, engine=first_engine) as session:
            start = time.monotonic()

            nav = await session.navigate_only(
                url=url,
                wait_until=app.config.wait_until,
                wait_for=wait_for,
                timeout_ms=app.config.navigation_timeout_ms,
            )

            content, method = await _extract_formatted(
                session.page, output_format, app.config.max_content_length
            )

            elapsed = int((time.monotonic() - start) * 1000)

            result = {
                "url": nav["url"],
                "title": nav["title"],
                "content": content,
                "session_id": session.id,
                "status_code": nav["status_code"],
                "timing_ms": elapsed,
                "extraction_method": method,
                "engine": first_engine,
            }

            # Auto-fallback
            if use_auto and first_engine == "chromium" and _is_bot_blocked(result):
                if app.manager._camoufox_browser:
                    logger.info("Bot-blocked on chromium for %s, retrying with firefox", url)
                    async with _ephemeral_session(app.manager, None, engine="firefox") as ff_session:
                        start2 = time.monotonic()
                        nav2 = await ff_session.navigate_only(
                            url=url,
                            wait_until=app.config.wait_until,
                            wait_for=wait_for,
                            timeout_ms=app.config.navigation_timeout_ms,
                        )
                        content2, method2 = await _extract_formatted(
                            ff_session.page, output_format, app.config.max_content_length
                        )
                        elapsed2 = int((time.monotonic() - start2) * 1000)
                        result = {
                            "url": nav2["url"],
                            "title": nav2["title"],
                            "content": content2,
                            "session_id": ff_session.id,
                            "status_code": nav2["status_code"],
                            "timing_ms": elapsed2,
                            "extraction_method": method2,
                            "engine": "firefox",
                            "fallback": True,
                        }

            return result
    except SecurityError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.error("scrape_webpage failed: %s", e, exc_info=True)
        return {"error": str(e)}


@mcp.tool()
async def extract_structured_data(
    url: str,
    session_id: str | None = None,
    include: list[str] | None = None,
    wait_for: str | None = None,
    engine: str = "auto",
    ctx: Context = None,
) -> dict:
    """Extract structured data (metadata, links, tables, JSON-LD, etc.) from a webpage.

    Args:
        url: The URL to extract from (http/https only).
        session_id: Optional session ID to reuse. If omitted, creates an ephemeral session that auto-closes.
        include: Sections to include. Default all. Allowed: metadata, og_tags, json_ld, headings, links, tables, forms.
        wait_for: Optional CSS selector to wait for before extracting.
        engine: Browser engine — 'auto', 'chromium', or 'firefox'.

    Returns structured data:
        url, title, session_id, timing_ms, engine, + requested sections
    """
    app = _get_app(ctx)

    if engine not in VALID_ENGINES:
        return {"error": f"Invalid engine: {engine!r}. Valid: {sorted(VALID_ENGINES)}"}

    try:
        validate_url(url)
    except SecurityError as e:
        return {"error": str(e)}

    first_engine = _resolve_engine(engine, app)

    try:
        async with _ephemeral_session(app.manager, session_id, engine=first_engine) as session:
            start = time.monotonic()

            nav = await session.navigate_only(
                url=url,
                wait_until=app.config.wait_until,
                wait_for=wait_for,
                timeout_ms=app.config.navigation_timeout_ms,
            )

            dom_data = await extract_dom_data(session.page, include=include)
            elapsed = int((time.monotonic() - start) * 1000)

            result = {
                "url": nav["url"],
                "title": nav["title"],
                "session_id": session.id,
                "timing_ms": elapsed,
                "engine": first_engine,
            }
            result.update(dom_data)
            return result

    except ValueError as e:
        return {"error": str(e)}
    except SecurityError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.error("extract_structured_data failed: %s", e, exc_info=True)
        return {"error": str(e)}


@mcp.tool()
async def crawl_pages(
    url: str,
    max_pages: int = 5,
    link_pattern: str | None = None,
    output_format: str = "markdown",
    same_domain: bool = True,
    engine: str = "auto",
    ctx: Context = None,
) -> dict:
    """Crawl multiple pages via BFS starting from a URL.

    Args:
        url: The starting URL (http/https only).
        max_pages: Maximum pages to crawl (1-20, default 5).
        link_pattern: Optional regex to filter link hrefs.
        output_format: One of 'markdown', 'text', 'html', 'links'. Default 'markdown'.
        same_domain: If True (default), only follow links on the same domain.
        engine: Browser engine — 'auto', 'chromium', or 'firefox'.

    Returns structured data:
        pages (list of {url, title, content, status_code}), total_pages, total_timing_ms, engine
    """
    app = _get_app(ctx)

    if output_format not in VALID_OUTPUT_FORMATS:
        return {"error": f"Invalid output_format: {output_format!r}. Valid: {sorted(VALID_OUTPUT_FORMATS)}"}

    if engine not in VALID_ENGINES:
        return {"error": f"Invalid engine: {engine!r}. Valid: {sorted(VALID_ENGINES)}"}

    try:
        validate_url(url)
    except SecurityError as e:
        return {"error": str(e)}

    # Clamp max_pages
    max_pages = max(1, min(max_pages, app.config.crawl_max_pages_limit))

    # Compile link_pattern
    pattern_re = None
    if link_pattern:
        try:
            pattern_re = re.compile(link_pattern)
        except re.error as e:
            return {"error": f"Invalid link_pattern regex: {e}"}

    start_parsed = urlparse(url)
    start_domain = start_parsed.hostname

    first_engine = _resolve_engine(engine, app)
    use_auto = engine == "auto"
    active_engine = first_engine

    start = time.monotonic()
    pages = []

    # Normalize URL: strip fragment
    seed_url = urldefrag(url)[0]
    queue = deque([seed_url])
    visited = {seed_url}

    session = await app.manager.get_or_create_session(None, engine=first_engine)
    try:
        while queue and len(pages) < max_pages:
            current_url = queue.popleft()

            # SSRF check each URL
            try:
                validate_url(current_url)
            except SecurityError:
                logger.debug("Skipping SSRF-blocked URL: %s", current_url)
                continue

            try:
                nav = await session.navigate_only(
                    url=current_url,
                    wait_until=app.config.wait_until,
                    timeout_ms=app.config.navigation_timeout_ms,
                )

                content, method = await _extract_formatted(
                    session.page, output_format, app.config.crawl_per_page_max
                )

                page_result = {
                    "url": nav["url"],
                    "title": nav["title"],
                    "content": content,
                    "status_code": nav["status_code"],
                }

                # Auto-fallback on first page only
                if (
                    use_auto
                    and active_engine == "chromium"
                    and len(pages) == 0
                    and _is_bot_blocked(page_result)
                    and app.manager._camoufox_browser
                ):
                    logger.info("Bot-blocked on chromium for crawl %s, switching to firefox", url)
                    await app.manager.close_session(session.id)
                    session = await app.manager.get_or_create_session(None, engine="firefox")
                    active_engine = "firefox"
                    # Re-navigate the first page with firefox
                    nav = await session.navigate_only(
                        url=current_url,
                        wait_until=app.config.wait_until,
                        timeout_ms=app.config.navigation_timeout_ms,
                    )
                    content, method = await _extract_formatted(
                        session.page, output_format, app.config.crawl_per_page_max
                    )
                    page_result = {
                        "url": nav["url"],
                        "title": nav["title"],
                        "content": content,
                        "status_code": nav["status_code"],
                    }

                pages.append(page_result)
            except Exception as e:
                logger.debug("Crawl failed for %s: %s", current_url, e)
                continue

            # Extract links for BFS (cap 100 per page)
            if len(pages) < max_pages:
                try:
                    raw_links = await session.page.evaluate("""
                        () => {
                            const results = [];
                            document.querySelectorAll('a[href]').forEach(el => {
                                if (results.length >= 100) return;
                                const href = el.href;
                                if (href) results.push(href);
                            });
                            return results;
                        }
                    """)

                    page_url = session.page.url
                    for href in raw_links:
                        # Absolutize (browser already does this, but be safe)
                        abs_url = urljoin(page_url, href)

                        # Strip fragment
                        abs_url = urldefrag(abs_url)[0]

                        # Skip already visited
                        if abs_url in visited:
                            continue

                        # Parse for checks
                        parsed = urlparse(abs_url)

                        # Only http/https
                        if parsed.scheme not in ("http", "https"):
                            continue

                        # Same domain check via parsed hostname
                        if same_domain and parsed.hostname != start_domain:
                            continue

                        # Pattern filter
                        if pattern_re and not pattern_re.search(abs_url):
                            continue

                        visited.add(abs_url)
                        queue.append(abs_url)

                except Exception as e:
                    logger.debug("Link extraction failed: %s", e)

        elapsed = int((time.monotonic() - start) * 1000)

        return {
            "pages": pages,
            "total_pages": len(pages),
            "total_timing_ms": elapsed,
            "engine": active_engine,
        }

    finally:
        await app.manager.close_session(session.id)
