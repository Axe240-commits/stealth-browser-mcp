"""MCP Server with 4 stealth browser tools."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP, Context

from stealth_browser.browser_manager import BrowserManager
from stealth_browser.config import Config
from stealth_browser.security import SecurityError, validate_url

logger = logging.getLogger(__name__)


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


@mcp.tool()
async def browse(
    url: str,
    session_id: str | None = None,
    wait_for: str | None = None,
    ctx: Context = None,
) -> dict:
    """Navigate to a URL and return page content as clean markdown.

    Args:
        url: The URL to navigate to (http/https only).
        session_id: Optional session ID to reuse. If omitted, creates a new session.
        wait_for: Optional CSS selector to wait for before extracting content.

    Returns structured data:
        url, title, content, session_id, truncated, captcha_detected,
        extraction_method, timing_ms, status_code
    """
    app = _get_app(ctx)

    # SSRF validation
    try:
        validate_url(url)
    except SecurityError as e:
        return {"error": str(e), "session_id": session_id or ""}

    session = await app.manager.get_or_create_session(session_id)
    try:
        result = await session.navigate(
            url=url,
            wait_until=app.config.wait_until,
            wait_for=wait_for,
            timeout_ms=app.config.navigation_timeout_ms,
            max_content_length=app.config.max_content_length,
        )
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
