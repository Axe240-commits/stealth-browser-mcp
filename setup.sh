#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "=== Stealth Browser MCP Setup ==="

# Check for system dependencies
echo "[1/5] Checking system dependencies..."
MISSING_LIBS=""
for lib in libnspr4.so libnss3.so libatk-1.0.so.0 libatk-bridge-2.0.so.0 \
           libdrm.so.2 libxkbcommon.so.0 libXcomposite.so.1 libXdamage.so.1 \
           libXrandr.so.2 libgbm.so.1 libpango-1.0.so.0 libcairo.so.2 libasound.so.2; do
    if ! ldconfig -p 2>/dev/null | grep -q "$lib"; then
        MISSING_LIBS="$MISSING_LIBS $lib"
    fi
done

if [ -n "$MISSING_LIBS" ]; then
    echo "Missing system libraries:$MISSING_LIBS"
    echo "Install with: sudo apt-get install -y libnspr4 libnss3 libatk1.0-0 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2t64"
    exit 1
fi
echo "  System dependencies OK"

# Check for Xvfb (needed for headed mode without a display)
if ! command -v Xvfb &>/dev/null; then
    echo "  WARNING: Xvfb not found. Install with: sudo apt-get install -y xvfb"
    echo "  (Headed mode will require a real display without Xvfb)"
fi

# Create venv if needed
echo "[2/5] Setting up virtual environment..."
if [ ! -d ".venv" ]; then
    uv venv
fi

# Install project with dependencies
echo "[3/5] Installing Python dependencies..."
uv pip install -e ".[dev]"

# Install Patchright's Chromium
echo "[4/5] Installing Patchright Chromium..."
.venv/bin/python -m patchright install chromium

# Fetch Camoufox browser
echo "[5/5] Fetching Camoufox Firefox..."
.venv/bin/python -c "import camoufox; camoufox.install()" 2>/dev/null || echo "  Camoufox fetch skipped (install manually if needed)"

echo ""
echo "=== Setup complete ==="
echo "Run:  .venv/bin/python -m stealth_browser"
