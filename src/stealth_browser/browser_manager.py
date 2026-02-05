"""Browser lifecycle management and session pool."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone

from patchright.async_api import async_playwright

from stealth_browser.config import Config
from stealth_browser.session import Session

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages Patchright (Chromium) and optionally Camoufox (Firefox) browsers
    behind a single session pool, with Xvfb for headed mode on Linux."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None  # Patchright Chromium
        self._camoufox_browser = None  # Camoufox Firefox
        self._sessions: dict[str, Session] = {}
        self._config: Config | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()  # protects session creation/removal
        self._xvfb_proc: subprocess.Popen | None = None

    # ------------------------------------------------------------------
    # Xvfb management
    # ------------------------------------------------------------------

    def _start_xvfb(self) -> None:
        """Start Xvfb virtual display for headed mode on Linux."""
        if self._config.headless or not self._config.use_xvfb:
            return

        if not shutil.which("Xvfb"):
            logger.warning("Xvfb not found — headed mode will need a real display")
            return

        display = ":99"
        # Check if something already owns :99
        if os.environ.get("DISPLAY") == display:
            logger.info("DISPLAY already set to %s, skipping Xvfb start", display)
            return

        try:
            self._xvfb_proc = subprocess.Popen(
                ["Xvfb", display, "-screen", "0", "1920x1080x24", "-nolisten", "tcp"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            os.environ["DISPLAY"] = display
            logger.info("Xvfb started on %s (pid=%d)", display, self._xvfb_proc.pid)
        except Exception as e:
            logger.warning("Failed to start Xvfb: %s", e)
            self._xvfb_proc = None

    def _stop_xvfb(self) -> None:
        """Stop the Xvfb subprocess if we started it."""
        if self._xvfb_proc is not None:
            try:
                self._xvfb_proc.terminate()
                self._xvfb_proc.wait(timeout=5)
            except Exception:
                try:
                    self._xvfb_proc.kill()
                except Exception:
                    pass
            logger.info("Xvfb stopped")
            self._xvfb_proc = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, config: Config) -> None:
        """Launch browser(s) and start the cleanup loop."""
        self._config = config

        # Start Xvfb before any browser
        self._start_xvfb()

        # Patchright (Chromium)
        self._playwright = await async_playwright().start()
        await self._launch_browser()

        # Camoufox (Firefox)
        if config.camoufox_enabled:
            await self._launch_camoufox()

        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(
            "BrowserManager started (headless=%s, xvfb=%s, camoufox=%s)",
            config.headless,
            self._xvfb_proc is not None,
            self._camoufox_browser is not None,
        )

    async def _launch_browser(self) -> None:
        """Launch (or re-launch) the Patchright Chromium browser."""
        launch_args = []
        if self._config.block_media:
            launch_args.extend([
                "--blink-settings=imagesEnabled=false",
            ])

        self._browser = await self._playwright.chromium.launch(
            headless=self._config.headless,
            channel=self._config.channel if self._config.channel != "chromium" else None,
            args=launch_args,
        )
        pid = self._browser.process.pid if hasattr(self._browser, 'process') and self._browser.process else "?"
        logger.info("Chromium launched (pid=%s)", pid)

    async def _launch_camoufox(self) -> None:
        """Launch the Camoufox Firefox browser."""
        try:
            from camoufox.async_api import AsyncCamoufox
        except ImportError:
            logger.warning("camoufox not installed — Firefox engine disabled")
            self._camoufox_browser = None
            return

        try:
            # AsyncCamoufox is a context manager that yields a browser
            self._camoufox_cm = AsyncCamoufox(headless=self._config.headless)
            self._camoufox_browser = await self._camoufox_cm.__aenter__()
            logger.info("Camoufox Firefox launched")
        except Exception as e:
            logger.warning("Failed to launch Camoufox: %s", e)
            self._camoufox_browser = None

    async def stop(self) -> None:
        """Close all sessions, browsers, playwright, and Xvfb."""
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

        # Close Camoufox
        if self._camoufox_browser:
            try:
                await self._camoufox_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._camoufox_browser = None

        # Close Patchright Chromium
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

        # Stop Xvfb last
        self._stop_xvfb()

        logger.info("BrowserManager stopped")

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def get_or_create_session(
        self, session_id: str | None = None, engine: str = "chromium"
    ) -> Session:
        """Get an existing session or create a new one.

        Args:
            session_id: Reuse existing session if provided.
            engine: "chromium" or "firefox". Ignored when reusing an existing session.
        """
        async with self._lock:
            # Return existing session
            if session_id and session_id in self._sessions:
                return self._sessions[session_id]

            # Pick the right browser
            if engine == "firefox":
                if not self._camoufox_browser:
                    raise RuntimeError("Camoufox Firefox engine not available")
                browser = self._camoufox_browser
            else:
                await self._ensure_browser()
                browser = self._browser

            # Evict if at capacity
            if len(self._sessions) >= self._config.max_sessions:
                await self._evict_oldest()

            # Create new session
            sid = session_id or str(uuid.uuid4())[:8]
            context = await browser.new_context(
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

            session = Session(id=sid, context=context, page=page, engine=engine)
            session._setup_request_interceptor()
            self._sessions[sid] = session
            logger.info("Created %s session %s (%d active)", engine, sid, len(self._sessions))
            return session

    async def close_session(self, session_id: str) -> None:
        """Close and remove a specific session."""
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                await session.close()
                logger.info("Closed session %s (%d remaining)", session_id, len(self._sessions))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_browser(self) -> None:
        """Check Chromium browser is alive, restart if crashed."""
        if self._browser and self._browser.is_connected():
            return
        logger.warning("Chromium disconnected, restarting...")
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        await self._launch_browser()
        # Chromium sessions are dead after restart
        dead = [sid for sid, s in self._sessions.items() if s.engine == "chromium"]
        for sid in dead:
            self._sessions.pop(sid, None)

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
