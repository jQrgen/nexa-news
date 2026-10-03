#!/usr/bin/env bash
# Build site/ and run the privacy check. Publishes nothing.
#   ./build.sh            public build (editor-approved items only)
#   ./build.sh --preview  local review build (also shows pending items; can never be published)
set -euo pipefail
cd "$(dirname "$0")"
.venv/bin/python build.py "$@"
.venv/bin/python tools/privacy_check.py site
