"""Entry point: python -m stealth_browser"""

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

from stealth_browser.server import mcp

mcp.run(transport="stdio")
