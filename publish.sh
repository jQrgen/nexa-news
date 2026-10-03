#!/usr/bin/env bash
# Publish site/ – ONLY after jQrgen has approved, and only with --yes.
#
#   ./publish.sh          public build + privacy check, then stop (nothing leaves the machine)
#   ./publish.sh --yes    public build + privacy check, then push site/ to PUBLISH_BRANCH of PUBLISH_REMOTE
#
# Target is set in publish.conf (kept out of git). For GitHub Pages:
#   PUBLISH_REMOTE=git@github.com:jQrgen/nexa-news.git    (or https://github.com/jQrgen/nexa-news.git)
#   PUBLISH_BRANCH=gh-pages
#   PUBLISH_URL=https://jqrgen.github.io/nexa-news/
# Only the built site/ goes to gh-pages. The code on main is pushed separately (see README).
set -euo pipefail
cd "$(dirname "$0")"
.venv/bin/python build.py              # always a public build: never --preview
.venv/bin/python tools/privacy_check.py site
[ -e site/PREVIEW-BUILD-DO-NOT-PUBLISH.txt ] && { echo "refusing: site/ is a preview build" >&2; exit 1; }
n=$(.venv/bin/python -c 'import json;print(len(json.load(open("site/data/items.json"))["items"]))')
if [ "${1:-}" != "--yes" ]; then
  echo "Built and checked locally: $n published items in site/. Nothing was published."
  echo "Publish only after jQrgen approves:  ./publish.sh --yes"
  exit 0
fi
[ -f publish.conf ] || { echo "refusing: no publish.conf. Nothing was published." >&2; exit 1; }
# shellcheck disable=SC1091
. ./publish.conf
: "${PUBLISH_REMOTE:?set PUBLISH_REMOTE in publish.conf}"; : "${PUBLISH_BRANCH:=gh-pages}"
[ "$n" -gt 0 ] || { echo "refusing: no published items (the editor has approved nothing yet)" >&2; exit 1; }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
# A normal commit on top of the existing gh-pages branch (no force push). The first publish creates the branch.
if git ls-remote --exit-code --heads "$PUBLISH_REMOTE" "$PUBLISH_BRANCH" >/dev/null 2>&1; then
  git clone -q --depth 1 --branch "$PUBLISH_BRANCH" --single-branch "$PUBLISH_REMOTE" "$tmp/out"
else
  git init -q -b "$PUBLISH_BRANCH" "$tmp/out"; git -C "$tmp/out" remote add origin "$PUBLISH_REMOTE"
fi
find "$tmp/out" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -a site/. "$tmp/out/"
touch "$tmp/out/.nojekyll"             # GitHub Pages: serve files as-is, no Jekyll
git -C "$tmp/out" add -A
if git -C "$tmp/out" diff --cached --quiet; then echo "$PUBLISH_BRANCH: no changes"; exit 0; fi
name=$(git config user.name || echo "Nexa News"); mail=$(git config user.email || echo "nexa-news@users.noreply.github.com")
git -C "$tmp/out" -c user.name="$name" -c user.email="$mail" commit -q -m "Publish $(date '+%Y-%m-%d %H:%M %Z')"
git -C "$tmp/out" push -q origin "$PUBLISH_BRANCH"
echo "Pushed $n items to $PUBLISH_REMOTE ($PUBLISH_BRANCH)."
if [ -n "${PUBLISH_URL:-}" ]; then
  for _ in $(seq 1 30); do code=$(curl -s -o /dev/null -w '%{http_code}' "$PUBLISH_URL" || true); [ "$code" = 200 ] && break; sleep 10; done
  echo "live check: $PUBLISH_URL -> HTTP $code"
fi
