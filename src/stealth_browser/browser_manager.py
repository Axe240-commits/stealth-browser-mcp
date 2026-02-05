"""Browser lifecycle management and session pool."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from patchright.async_api import async_playwright

from stealth_browser.config import Config
from stealth_browser.session import Session

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages a single browser instance and a pool of BrowserContext sessions."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._sessions: dict[str, Session] = {}
        self._config: Config | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()  # protects session creation/removal

    async def start(self, config: Config) -> None:
        """Launch the browser and start the cleanup loop."""
        self._config = config
        self._playwright = await async_playwright().start()
        await self._launch_browser()
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("BrowserManager started (headless=%s)", config.headless)

    async def _launch_browser(self) -> None:
        """Launch (or re-launch) the browser."""
        launch_args = []
        if self._config.block_media:
            # Block images/media for speed
            launch_args.extend([
                "--blink-settings=imagesEnabled=false",
            ])

        self._browser = await self._playwright.chromium.launch(
            headless=self._config.headless,
            channel=self._config.channel if self._config.channel != "chromium" else None,
            args=launch_args,
        )
        logger.info("Browser launched (pid=%s)", self._browser.process.pid if hasattr(self._browser, 'process') and self._browser.process else "?")

    async def stop(self) -> None:
        """Close all sessions, browser, and playwright."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Close all sessions
        for session in list(self._sessions.values()):
            await session.close()
        self._sessions.clear()

        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass

        logger.info("BrowserManager stopped")

    async def get_or_create_session(self, session_id: str | None = None) -> Session:
        """Get an existing session or create a new one.

        If session_id is provided and exists, returns it.
        If session_id is None, creates a new session with a generated ID.
        If at max capacity, evicts the oldest idle session.
        """
        async with self._lock:
            # Return existing session
            if session_id and session_id in self._sessions:
                return self._sessions[session_id]

            # Ensure browser is alive
            await self._ensure_browser()

            # Evict if at capacity
            if len(self._sessions) >= self._config.max_sessions:
                await self._evict_oldest()

            # Create new session
            sid = session_id or str(uuid.uuid4())[:8]
            context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                java_script_enabled=True,
            )

            page = await context.new_page()

            # Block media resources if configured
            if self._config.block_media:
                await page.route(
                    "**/*.{png,jpg,jpeg,gif,svg,webp,ico,mp4,webm,ogg,mp3,woff,woff2,ttf,eot}",
                    lambda route: route.abort(),
                )

            session = Session(id=sid, context=context, page=page)
            session._setup_request_interceptor()
            self._sessions[sid] = session
            logger.info("Created session %s (%d active)", sid, len(self._sessions))
            return session

    async def close_session(self, session_id: str) -> None:
        """Close and remove a specific session."""
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                await session.close()
                logger.info("Closed session %s (%d remaining)", session_id, len(self._sessions))

    async def _ensure_browser(self) -> None:
        """Check browser is alive, restart if crashed."""
        if self._browser and self._browser.is_connected():
            return
        logger.warning("Browser disconnected, restarting...")
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        await self._launch_browser()
        # All sessions are dead after restart
        self._sessions.clear()

    async def _evict_oldest(self) -> None:
        """Evict the least recently used session."""
        if not self._sessions:
            return
        oldest = min(self._sessions.values(), key=lambda s: s.last_used)
        logger.info("Evicting idle session %s", oldest.id)
        self._sessions.pop(oldest.id, None)
        await oldest.close()

    async def _cleanup_loop(self) -> None:
        """Periodically evict sessions idle longer than timeout."""
        while True:
            try:
                await asyncio.sleep(60)
                await self._evict_expired()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.debug("Cleanup error", exc_info=True)

    async def _evict_expired(self) -> None:
        """Evict sessions that exceeded idle timeout."""
        if not self._config:
            return
        now = datetime.now(timezone.utc)
        timeout_seconds = self._config.session_timeout_minutes * 60
        expired = []

        for sid, session in self._sessions.items():
            idle = (now - session.last_used).total_seconds()
            if idle > timeout_seconds:
                expired.append(sid)

        async with self._lock:
            for sid in expired:
                session = self._sessions.pop(sid, None)
                if session:
                    await session.close()
                    logger.info("Evicted expired session %s", sid)
