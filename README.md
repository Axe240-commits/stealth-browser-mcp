# Stealth Browser MCP Server

A Model Context Protocol (MCP) server that provides stealth web browsing capabilities using [Patchright](https://github.com/AeroTechLab/patchright) — a stealthy Playwright fork that bypasses bot detection on most sites (Cloudflare, DataDome, Imperva, etc.).

Built for use with [Claude Code](https://claude.ai/claude-code) and other MCP-compatible AI agents.

## Features

- **Stealth browsing** — Patchright patches detection vectors that flag standard Playwright/Puppeteer
- **4 MCP tools** — `browse`, `interact`, `extract`, `close_session`
- **Structured JSON responses** — every tool returns typed, parseable data (not raw text)
- **3-tier content extraction** — trafilatura → readability → innertext fallback chain
- **Session pooling** — persistent browser, up to 5 isolated BrowserContext sessions
- **SSRF-hardened** — DNS resolution validation blocks localhost, private IPs, cloud metadata, `file://`
- **Smart truncation** — large pages truncated at 50K chars on paragraph boundaries
- **CAPTCHA detection** — detects Cloudflare Turnstile, reCAPTCHA, hCaptcha; reports structured `captcha_detected` flag
- **Auto-cleanup** — idle sessions evicted after 10 minutes, crashed browser auto-restarts

## Tools

### `browse`

Navigate to a URL and return page content as clean markdown.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | yes | URL to navigate to (http/https only) |
| `session_id` | string | no | Reuse an existing session. If omitted, creates a new one |
| `wait_for` | string | no | CSS selector to wait for before extracting |

**Returns:**
```json
{
  "url": "https://example.com/",
  "title": "Example Domain",
  "content": "# Example Domain\n\nThis domain is for use in...",
  "session_id": "a1b2c3d4",
  "truncated": false,
  "captcha_detected": false,
  "extraction_method": "trafilatura",
  "timing_ms": 521,
  "status_code": 200
}
```

### `interact`

Interact with the current page in a session.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | yes | Session from a previous `browse` call |
| `action` | string | yes | One of: `click`, `type`, `select`, `hover`, `scroll` |
| `selector` | string | yes | CSS selector for the target element |
| `value` | string | no | Required for `type` and `select`. For `scroll`, pixel amount |

**Returns:**
```json
{
  "success": true,
  "session_id": "a1b2c3d4",
  "action_performed": "clicked #submit",
  "page_url": "https://example.com/result",
  "timing_ms": 312
}
```

### `extract`

Re-extract content from the current page without re-navigating. Use this instead of `browse` when you're already on the page.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | yes | Session to extract from |
| `mode` | string | no | `auto` (default), `article`, or `text` (raw innertext) |

**Returns:**
```json
{
  "content": "...",
  "session_id": "a1b2c3d4",
  "url": "https://example.com/",
  "extraction_method": "trafilatura",
  "truncated": false
}
```

### `close_session`

Close a browser session and free its resources.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | string | yes | Session to close |

**Returns:**
```json
{
  "status": "closed",
  "session_id": "a1b2c3d4"
}
```

## Installation

### Prerequisites

**System libraries** (Ubuntu/Debian/WSL2):

```bash
sudo apt-get install -y libnspr4 libnss3 libatk1.0-0 libatk-bridge2.0-0 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
  libpango-1.0-0 libcairo2 libasound2t64
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

Add to `~/.claude.json` under `"mcpServers"`:

```json
{
  "mcpServers": {
    "stealth-browser": {
      "type": "stdio",
      "command": "/path/to/stealth-browser-mcp/.venv/bin/python",
      "args": ["-m", "stealth_browser"]
    }
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
      "mcp__stealth-browser__close_session"
    ]
  }
}
```

Restart Claude Code. The 4 tools will be available immediately.

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Claude Code / MCP Client                       │
│                                                 │
│  browse() → interact() → extract() → close()   │
└────────────────┬────────────────────────────────┘
                 │ stdio (JSON-RPC)
┌────────────────▼────────────────────────────────┐
│  server.py — FastMCP Server                     │
│  ├── security.py — SSRF validation (every URL)  │
│  ├── session.py — per-session lock + state      │
│  ├── browser_manager.py — pool + lifecycle      │
│  └── extractor.py — 3-tier content extraction   │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│  Patchright (stealth Playwright fork)           │
│  └── Chromium (headless, patched fingerprints)  │
└─────────────────────────────────────────────────┘
```

### Content Extraction Pipeline

```
trafilatura (best for articles, tables, links)
    ↓ fallback if < 200 chars
readability-lxml + html2text (complex HTML)
    ↓ fallback if < 200 chars
page.inner_text('body') (SPAs, JS-rendered content)
```

### Session Management

- **One persistent browser** process launched at MCP server start
- Each `browse()` call with no `session_id` creates a new `BrowserContext` (~100ms)
- Sessions are isolated (separate cookies, storage, state)
- Max **5 concurrent sessions**, oldest evicted if at capacity
- Idle sessions evicted after **10 minutes**
- All operations per session are serialized via `asyncio.Lock`

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
- Default navigation uses `domcontentloaded` (fast, reliable) — use `wait_for` if you need a specific element

## Project Structure

```
stealth-browser-mcp/
├── pyproject.toml              # Dependencies, build config
├── setup.sh                    # One-command setup
├── src/stealth_browser/
│   ├── __init__.py
│   ├── __main__.py             # Entry: python -m stealth_browser
│   ├── server.py               # MCP server, 4 tools, lifespan
│   ├── browser_manager.py      # Browser lifecycle, context pool
│   ├── session.py              # Session state, locking, actions
│   ├── extractor.py            # 3-tier content extraction
│   ├── security.py             # SSRF-hardened URL validation
│   ├── config.py               # Configuration dataclass
│   └── proxy.py                # Stub (Phase 2: Tor)
└── tests/
    ├── test_security.py        # 26 tests: IP checks, URL validation
    └── test_extractor.py       # 4 tests: extraction modes, fallbacks
```

## Configuration

Defaults in `config.py` — no config file needed:

| Setting | Default | Description |
|---------|---------|-------------|
| `headless` | `True` | Run browser headless |
| `max_sessions` | `5` | Max concurrent browser sessions |
| `session_timeout_minutes` | `10` | Idle session eviction timeout |
| `navigation_timeout_ms` | `30000` | Page load timeout |
| `wait_until` | `domcontentloaded` | Navigation wait strategy |
| `max_content_length` | `50000` | Content truncation limit (chars) |
| `block_media` | `True` | Block images/fonts/media for speed |

## Dependencies

| Package | Purpose |
|---------|---------|
| [mcp](https://pypi.org/project/mcp/) | MCP server framework (Anthropic) |
| [patchright](https://github.com/AeroTechLab/patchright) | Stealth Playwright fork |
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
  libpango-1.0-0 libcairo2 libasound2t64
```

Check for remaining missing libs:
```bash
ldd ~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell 2>&1 | grep "not found"
```

### MCP server not showing in Claude Code

The server must be registered in `~/.claude.json` (not `~/.claude/mcp_servers.json`):

```json
{
  "mcpServers": {
    "stealth-browser": {
      "type": "stdio",
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "stealth_browser"]
    }
  }
}
```

After adding, **restart Claude Code** — MCP servers are loaded at startup only.

### Tools show "Permission denied"

Add the tools to `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__stealth-browser__browse",
      "mcp__stealth-browser__interact",
      "mcp__stealth-browser__extract",
      "mcp__stealth-browser__close_session"
    ]
  }
}
```

### `Sec-CH-UA` shows "HeadlessChrome"

This is expected. Patchright patches browser-level detection vectors (JavaScript APIs, WebDriver flags, navigator properties), not raw HTTP headers. Sites like httpbin echo headers verbatim, but actual bot detection systems (Cloudflare, DataDome) check browser behavior, not the UA string.

### Page content is empty or too short

- Try `extract` with `mode="text"` for SPAs/JS-heavy pages
- Add `wait_for` parameter with a CSS selector to wait for dynamic content
- The default `domcontentloaded` doesn't wait for lazy-loaded content — pass a selector that appears after the page fully renders

### CAPTCHA detected but page won't load

The server auto-waits 5 seconds for Cloudflare Turnstile auto-resolve. If `captcha_detected: true` persists, the site requires manual solving. Phase 2 will add `screenshot` for debugging these cases.

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
