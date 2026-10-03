#!/usr/bin/env bash
# Fetch new Nexa items into the editor queue. Publishes nothing.
#   ./fetch.sh               daily run (14-day look-back)
#   ./fetch.sh --days 120    longer look-back
#   ./fetch.sh --add URL --title "..." --date YYYY-MM-DD   add one item by hand (X, Reddit, YouTube ...)
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/python fetch.py "$@"
