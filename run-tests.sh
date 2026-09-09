#!/usr/bin/env bash
# Two runs, not one, and the reason is worth stating: the Home Assistant test plugin blocks
# sockets and enforces its own cleanup for everything in its process. The client tests exist
# precisely to talk to a real HTTP server, so they run with plugin autoloading off and only
# pytest-asyncio enabled.
set -euo pipefail

PYTHON=${PYTHON:-.venv/bin/python}

echo "== client (real HTTP, without Home Assistant) =="
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$PYTHON" -m pytest tests/client -q -p pytest_asyncio.plugin

echo
echo "== integration (inside Home Assistant) =="
"$PYTHON" -m pytest tests/homeassistant -q
