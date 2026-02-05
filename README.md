# Stealth Browser MCP Server

A Model Context Protocol (MCP) server that provides stealth web browsing capabilities using dual browser engines — [Patchright](https://github.com/AeroTechLab/patchright) (Chromium) and [Camoufox](https://github.com/AuroraWright/camoufox) (Firefox) — with automatic bot-detection bypass.

Built for use with [Claude Code](https://claude.ai/claude-code) and other MCP-compatible AI agents.

## Features

- **Dual Engine Architecture** — Patchright (Chromium) as primary engine, Camoufox (Firefox) as fallback with stronger anti-fingerprinting
- **Auto Bot-Block Detection** — Detects Cloudflare, CAPTCHAs, and other bot protection; automatically retries with Firefox when `engine: auto`
- **Headed Mode via Xvfb** — Runs real browser windows (not headless) to beat fingerprint detection
- **7 MCP Tools** — Browse, interact, extract, scrape, crawl, structured data extraction, and session management
- **3-Tier Content Extraction** — trafilatura → readability → innertext fallback chain
- **SSRF-Hardened** — DNS resolution validation blocks localhost, private IPs, cloud metadata, `file://`
- **Session Pooling** — Up to 5 isolated BrowserContext sessions per engine, with 10-minute idle eviction
- **Smart Truncation** — Large pages truncated at 50K chars on paragraph boundaries
- **CAPTCHA Detection** — Detects Cloudflare Turnstile, reCAPTCHA, hCaptcha; reports structured `captcha_detected` flag
- **Auto-Cleanup** — Idle sessions evicted after 10 minutes, crashed browser auto-restarts

## Tools

### `browse`

Navigate to a URL and return page content as clean markdown.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | yes | URL to navigate to (http/https only) |
| `session_id` | string | no | Reuse an existing session. If omitted, creates a new one |
| `wait_for` | string | no | CSS selector to wait for before extracting |
| `engine` | string | no | `auto` (default), `chromium`, or `firefox` |

**Returns:** `url`, `title`, `content`, `session_id`, `truncated`, `captcha_detected`, `extraction_method`, `timing_ms`, `status_code`, `engine`

### `interact`

Interact with the current page in a session.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | yes | Session from a previous `browse` call |
| `action` | string | yes | One of: `click`, `type`, `select`, `hover`, `scroll` |
| `selector` | string | yes | CSS selector for the target element |
| `value` | string | no | Required for `type` and `select`. For `scroll`, pixel amount |

**Returns:** `success`, `session_id`, `action_performed`, `page_url`, `timing_ms`

### `extract`

Re-extract content from the current page without re-navigating. Use this instead of `browse` when you're already on the page.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | yes | Session to extract from |
| `mode` | string | no | `auto` (default), `article`, or `text` (raw innertext) |

**Returns:** `content`, `session_id`, `url`, `extraction_method`, `truncated`

### `close_session`

Close a browser session and free its resources.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | yes | Session to close |

**Returns:** `status`, `session_id`

### `scrape_webpage`

Navigate to a URL, extract content in the requested format, and auto-close the session.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | yes | URL to scrape (http/https only) |
| `output_format` | string | no | `markdown` (default), `text`, `html`, or `links` |
| `session_id` | string | no | Reuse session. If omitted, creates ephemeral session that auto-closes |
| `wait_for` | string | no | CSS selector to wait for before extracting |
| `engine` | string | no | `auto` (default), `chromium`, or `firefox` |

**Returns:** `url`, `title`, `content`, `session_id`, `status_code`, `timing_ms`, `extraction_method`, `engine`

### `extract_structured_data`

Extract structured DOM data (metadata, links, tables, JSON-LD, etc.) from a webpage.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | yes | URL to extract from (http/https only) |
| `session_id` | string | no | Reuse session. If omitted, creates ephemeral session |
| `include` | list | no | Sections to include. Default: all. Options: `metadata`, `og_tags`, `json_ld`, `headings`, `links`, `tables`, `forms` |
| `wait_for` | string | no | CSS selector to wait for before extracting |
| `engine` | string | no | `auto` (default), `chromium`, or `firefox` |

**Returns:** `url`, `title`, `session_id`, `timing_ms`, `engine`, + requested data sections

### `crawl_pages`

Crawl multiple pages via BFS starting from a URL.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | yes | Starting URL (http/https only) |
| `max_pages` | int | no | Maximum pages to crawl (1-20, default 5) |
| `link_pattern` | string | no | Regex to filter link hrefs |
| `output_format` | string | no | `markdown` (default), `text`, `html`, or `links` |
| `same_domain` | bool | no | Only follow same-domain links (default: true) |
| `engine` | string | no | `auto` (default), `chromium`, or `firefox` |

**Returns:** `pages` (list of `{url, title, content, status_code}`), `total_pages`, `total_timing_ms`, `engine`

## Installation

### Prerequisites

**System libraries** (Ubuntu/Debian/WSL2):

```bash
sudo apt-get install -y libnspr4 libnss3 libatk1.0-0 libatk-bridge2.0-0 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
  libpango-1.0-0 libcairo2 libasound2t64 xvfb
```

**Python 3.12+** and **uv** (recommended) or pip.

### Setup

```bash
git clone https://github.com/Axe240-commits/stealth-browser-mcp.git
cd stealth-browser-mcp
chmod +x setup.sh
./setup.sh
```

Or manually:

```bash
uv venv
uv pip install -e ".[dev]"
.venv/bin/python -m patchright install chromium
```

### Verify

```bash
# Run tests
.venv/bin/python -m pytest tests/ -v

# Start server (will wait for MCP stdio input)
.venv/bin/python -m stealth_browser
```

## Register with Claude Code

Add to `~/.claude/mcp_servers.json`:

```json
{
  "stealth-browser": {
    "type": "stdio",
    "command": "/path/to/stealth-browser-mcp/.venv/bin/python",
    "args": ["-m", "stealth_browser"]
  }
}
```

Then add permissions in `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__stealth-browser__browse",
      "mcp__stealth-browser__interact",
      "mcp__stealth-browser__extract",
      "mcp__stealth-browser__close_session",
      "mcp__stealth-browser__scrape_webpage",
      "mcp__stealth-browser__extract_structured_data",
      "mcp__stealth-browser__crawl_pages"
    ]
  }
}
```

Restart Claude Code. The 7 tools will be available immediately.

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Claude Code / MCP Client                       │
│                                                 │
│  browse ─ interact ─ extract ─ close_session    │
│  scrape_webpage ─ extract_structured_data       │
│  crawl_pages                                    │
└────────────────┬────────────────────────────────┘
                 │ stdio (JSON-RPC)
┌────────────────▼────────────────────────────────┐
│  server.py — FastMCP Server (7 tools)           │
│  ├── security.py — SSRF validation (every URL)  │
│  ├── session.py — per-session lock + state      │
│  ├── browser_manager.py — dual engine pool      │
│  ├── extractor.py — 3-tier content extraction   │
│  ├── dom_extractor.py — structured DOM data     │
│  └── config.py — configuration                  │
└───────┬─────────────────┬───────────────────────┘
        │                 │
┌───────▼──────┐  ┌───────▼──────┐
│  Patchright   │  │  Camoufox    │
│  (Chromium)   │  │  (Firefox)   │
│  Primary      │  │  Fallback    │
└───────┬──────┘  └───────┬──────┘
        │                 │
┌───────▼─────────────────▼───────────────────────┐
│  Xvfb :99 — 1920x1080 (headed mode)            │
└─────────────────────────────────────────────────┘
```

### Dual Engine & Auto-Fallback

With `engine: auto` (the default), every request:

1. Tries **Patchright (Chromium)** first — fast, low overhead
2. Checks for bot-block signals: HTTP 403, title keywords ("Just a moment", "Attention Required"), empty content
3. If blocked, automatically retries with **Camoufox (Firefox)** which has stronger anti-fingerprinting

For `crawl_pages`, the engine switch happens on the first page and sticks for the rest of the crawl.

### Content Extraction Pipeline

```
trafilatura (best for articles, tables, links)
    ↓ fallback if < 200 chars
readability-lxml + html2text (complex HTML)
    ↓ fallback if < 200 chars
page.inner_text('body') (SPAs, JS-rendered content)
```

### Session Management

- **Two persistent browsers** launched at MCP server start (Chromium + Firefox)
- Each `browse()` call with no `session_id` creates a new `BrowserContext` (~100ms)
- Sessions are isolated (separate cookies, storage, state)
- Max **5 concurrent sessions**, oldest evicted if at capacity
- Idle sessions evicted after **10 minutes**
- All operations per session are serialized via `asyncio.Lock`
- Each session tracks its engine type (`chromium` or `firefox`)

### Security (SSRF Protection)

Every URL is validated before navigation:

1. **Scheme check** — only `http` and `https` allowed
2. **DNS resolution** — hostname resolved to actual IPs
3. **IP validation** — all resolved IPs checked against private/reserved ranges
4. **Redirect validation** — redirects re-validated at each hop

Blocked:
- `localhost`, `127.0.0.1`, `::1`
- Private ranges (`10.x`, `172.16.x`, `192.168.x`)
- Cloud metadata (`169.254.169.254`)
- Link-local, multicast, reserved IPs
- `file://`, `data://`, `javascript://`, `ftp://`

## Usage Tips for AI Agents

- Use `extract` to re-read the same page — don't call `browse` again
- Use `browse` only for actual navigation (new URL or page change)
- Reuse `session_id` across related operations
- Always call `close_session` when done to free resources
- Use `scrape_webpage` for one-shot scraping (auto-closes session)
- Use `crawl_pages` to spider multiple pages from a starting URL
- Default navigation uses `domcontentloaded` (fast, reliable) — use `wait_for` if you need a specific element

## Project Structure

```
stealth-browser-mcp/
├── pyproject.toml              # Dependencies, build config
├── setup.sh                    # One-command setup
├── src/stealth_browser/
│   ├── __init__.py
│   ├── __main__.py             # Entry: python -m stealth_browser
│   ├── server.py               # MCP server, 7 tools, lifespan
│   ├── browser_manager.py      # Dual engine lifecycle, context pool
│   ├── session.py              # Session state, locking, actions
│   ├── extractor.py            # 3-tier content extraction
│   ├── dom_extractor.py        # Structured DOM data extraction
│   ├── security.py             # SSRF-hardened URL validation
│   ├── config.py               # Configuration dataclass
│   └── proxy.py                # Stub (Phase 2: Tor)
└── tests/
    ├── test_security.py        # URL/IP validation tests
    ├── test_extractor.py       # Extraction mode/fallback tests
    ├── test_dom_extractor.py   # DOM structured data tests
    └── test_server_helpers.py  # Server helper function tests
```

## Configuration

Defaults in `config.py` — no config file needed:

| Setting | Default | Description |
|---------|---------|-------------|
| `headless` | `False` | Headed mode (Xvfb) for better stealth |
| `use_xvfb` | `True` | Auto-start Xvfb for headed mode |
| `max_sessions` | `5` | Max concurrent browser sessions |
| `session_timeout_minutes` | `10` | Idle session eviction timeout |
| `navigation_timeout_ms` | `30000` | Page load timeout |
| `wait_until` | `domcontentloaded` | Navigation wait strategy |
| `max_content_length` | `50000` | Content truncation limit (chars) |
| `block_media` | `True` | Block images/fonts/media for speed |
| `camoufox_enabled` | `True` | Enable Firefox fallback engine |
| `crawl_max_pages_limit` | `20` | Hard cap for crawl_pages |
| `crawl_per_page_max` | `10000` | Content limit per crawled page |

## Dependencies

| Package | Purpose |
|---------|---------|
| [mcp](https://pypi.org/project/mcp/) | MCP server framework (Anthropic) |
| [patchright](https://github.com/AeroTechLab/patchright) | Stealth Playwright fork (Chromium) |
| [camoufox](https://github.com/AuroraWright/camoufox) | Anti-fingerprint Firefox (fallback engine) |
| [trafilatura](https://github.com/adbar/trafilatura) | Article/content extraction |
| [readability-lxml](https://github.com/buriy/python-readability) | Fallback HTML extraction |
| [html2text](https://github.com/Alir3z4/html2text/) | HTML to markdown conversion |

## Troubleshooting

### Browser fails to launch: `error while loading shared libraries`

Chromium needs system libraries that aren't installed by default on minimal Linux/WSL2:

```
error while loading shared libraries: libnspr4.so: cannot open shared object file
```

**Solution:**
```bash
sudo apt-get install -y libnspr4 libnss3 libatk1.0-0 libatk-bridge2.0-0 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
  libpango-1.0-0 libcairo2 libasound2t64 xvfb
```

### Camoufox won't start

Camoufox requires `xvfb` for headed mode:
```bash
sudo apt-get install -y xvfb
```

If Camoufox still fails, it falls back gracefully — Chromium-only mode still works.

### MCP server not showing in Claude Code

The server must be registered in `~/.claude/mcp_servers.json`:

```json
{
  "stealth-browser": {
    "type": "stdio",
    "command": "/absolute/path/to/.venv/bin/python",
    "args": ["-m", "stealth_browser"]
  }
}
```

After adding, **restart Claude Code** — MCP servers are loaded at startup only.

### Tools show "Permission denied"

Add all 7 tools to `~/.claude/settings.json` permissions (see Register section above).

### Page content is empty or too short

- Try `extract` with `mode="text"` for SPAs/JS-heavy pages
- Add `wait_for` parameter with a CSS selector to wait for dynamic content
- Try `engine: firefox` — some sites respond better to Camoufox
- The default `domcontentloaded` doesn't wait for lazy-loaded content — pass a selector that appears after the page fully renders

### Bot-blocked on both engines

If `engine: auto` falls back to Firefox and still gets blocked, the site may require:
- A different IP/proxy (Phase 2)
- Manual CAPTCHA solving
- Specific cookies/authentication

### Session not found

Sessions are evicted after 10 minutes of inactivity or when the 5-session limit is reached. If you get `"Session 'xyz' not found"`, create a new one with `browse`.

## Phase 2 (Planned)

- `screenshot` tool — for CAPTCHA/consent debugging
- `evaluate_js` tool — targeted DOM queries
- `session_info` tool — list active sessions and state
- Per-toolcall hard timeout guard
- Proxy/Tor opt-in support

## License

MIT
