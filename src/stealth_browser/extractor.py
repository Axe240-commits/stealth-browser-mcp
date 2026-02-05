"""3-tier content extraction pipeline: trafilatura → readability → innertext."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from patchright.async_api import Page

logger = logging.getLogger(__name__)

MIN_CONTENT_LENGTH = 200


async def extract_content(page: Page, mode: str = "auto") -> tuple[str, str]:
    """Extract page content as markdown.

    Returns (content, extraction_method).

    Modes:
        auto    - try all tiers in order
        article - same as auto (article-optimized extractors)
        text    - skip to innertext directly
    """
    if mode == "text":
        text = await page.inner_text("body")
        return text.strip(), "innertext"

    html = await page.content()

    # Tier 1: trafilatura (best for articles)
    try:
        import trafilatura

        result = trafilatura.extract(
            html,
            include_tables=True,
            include_links=True,
            output_format="txt",
        )
        if result and len(result) > MIN_CONTENT_LENGTH:
            return result.strip(), "trafilatura"
    except Exception as e:
        logger.debug("trafilatura failed: %s", e)

    # Tier 2: readability + html2text
    try:
        from readability import Document
        import html2text

        doc = Document(html)
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        result = h.handle(doc.summary())
        if result and len(result) > MIN_CONTENT_LENGTH:
            return result.strip(), "readability"
    except Exception as e:
        logger.debug("readability failed: %s", e)

    # Tier 3: raw innertext (works for SPAs)
    try:
        text = await page.inner_text("body")
        if text and text.strip():
            return text.strip(), "innertext"
    except Exception as e:
        logger.debug("innertext failed: %s", e)

    return "", "none"
