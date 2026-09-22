#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "=== Setting up i-cli in $SCRIPT_DIR ==="

# Check external system tools
echo -n "Checking for imv... "
if command -v imv >/dev/null 2>&1; then
    echo "found ($(imv -v 2>&1 | head -n 1))"
else
    echo "WARNING: imv not found. Image preview (:p) will be disabled."
fi

echo -n "Checking for mpv... "
if command -v mpv >/dev/null 2>&1; then
    echo "found ($(mpv --version 2>&1 | head -n 1))"
else
    echo "WARNING: mpv not found. Video/Audio preview (:p) will be disabled."
fi

echo -n "Checking for chafa... "
if command -v chafa >/dev/null 2>&1; then
    echo "found ($(chafa --version 2>&1 | head -n 1))"
else
    echo "WARNING: chafa not found. In-chat thumbnails will be disabled."
fi

# Create virtual environment if needed
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

echo "Installing / updating dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

chmod +x "$SCRIPT_DIR/i-cli" "$SCRIPT_DIR/setup.sh"

# Install git security hooks to prevent accidental credential commits
if [ -d "$SCRIPT_DIR/.git" ]; then
    git config core.hooksPath .githooks 2>/dev/null || true
    chmod +x "$SCRIPT_DIR/.githooks/"* 2>/dev/null || true
fi

echo ""
echo "=== Setup completed successfully! ==="
echo "You can now run: ./i-cli"
echo "Or link it: ln -sf $SCRIPT_DIR/i-cli ~/.local/bin/i-cli"
