# Nexa News

A small, open-source static site that collects public material about the Nexa blockchain (nexa.org, NEXA, Wally Wallet,
Otoplo, Rostrum, VotePeer, Build On Nexa, Nexa tokens) on one page, refreshed daily. Each item has a short summary written by
an editor. Run by Jørgen S. Notland (jQrgen), who works on Nexa with Bitcoin Unlimited. AI-assisted, editor-reviewed. No trackers.

**Live:** https://jqrgen.github.io/nexa-news/ (GitHub Pages from the `gh-pages` branch of `jQrgen/nexa-news`).
Corrections and source suggestions: https://github.com/jQrgen/nexa-news/issues. All links are relative, so the built `site/`
works under `/nexa-news/` (tested) or any other path. Site changes are listed in `changelog.json` (shown at `/changelog/`).

## How it works

```
./fetch.sh ──► data/items.json (status: pending) ──► queue/review.json      what the editor still has to review
                                                         │
                         the editor writes queue/approved.json (tools/editor.py helps)
                                                         ▼
./build.sh ──► site/ (approved items only) ──► tools/privacy_check.py ──► ./publish.sh --yes  (after jQrgen approves)
```

1. **Fetch** (`./fetch.sh`, once a day). Reads the enabled sources in `sources.json`: RSS/Atom feeds (Nexa Forum, Bitcoin
   Unlimited Forum, GitLab releases and tags, Medium, Mastodon), the Bing News RSS search, and the nexa.org sitemap (page titles
   and descriptions only). Follows robots.txt, sends its own user agent, waits at least 2 s between requests to a host, uses
   ETag/If-Modified-Since, never logs in, never reads text behind a paywall. Keeps only entries about Nexa ("Nexa" alone is
   also a car brand, a font, a card scheme ...). Flags price talk, promotion, spam, non-English titles and unclear "Nexa"
   matches for the editor. Each item gets `status: pending`.
2. **Edit.** The editor writes a 1-2 sentence summary in their own words for each item they approve, in
   `queue/approved.json`. Flagged items need `flags_checked: true`. A summary that repeats 10 or more words in a row from the
   source text is refused at build time.
3. **Build** (`./build.sh`). Builds `site/` with the approved items only, then runs the privacy check. `./build.sh --preview`
   also shows pending items, clearly marked and without summaries, for local review. A preview build can't be published.
4. **Publish** (`./publish.sh --yes`). Builds, checks, and pushes `site/` (only the built site) as a normal commit to the
   `gh-pages` branch named in `publish.conf`. Without `--yes` it only builds and checks. It refuses preview builds and empty sites.

## Commands

| What | Command |
|---|---|
| Daily fetch | `./fetch.sh` (options: `--days N`, `--only id1,id2`, `--refresh` to ignore the HTTP cache) |
| Add an item by hand (researcher) | `./fetch.sh --add URL` (title and date are read from the page) |
| Add an X post, Reddit thread or YouTube video | `./fetch.sh --add https://x.com/NexaMoney/status/123 --title "First line or our wording" --date 2026-10-03` (these sites are never fetched) |
| Editor: list the queue | `.venv/bin/python tools/editor.py list` (`--flagged`, `--all`) |
| Editor: approve / reject | `.venv/bin/python tools/editor.py approve ID "Summary." [--flags-checked] [--title ...] [--category ...] [--sponsored] [--outlet-note ...] [--correction ...]` / `... reject ID "reason"` |
| Local review build | `./build.sh --preview` then `.venv/bin/python -m http.server 8000 -d site` |
| Public build + privacy check | `./build.sh` |
| Screenshots for QA | `.venv/bin/python tools/screens.py` (writes `shots/`) |
| Keep an approved item off the site for now | add its id to `state/hold.json` (`{"ids": ["..."]}`) |
| Publish (only after jQrgen approves) | `./publish.sh --yes` |

Setup: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (and `.venv/bin/playwright install chromium` for screenshots).

## Pages

- `/` feed with filters by platform, official or independent, and a title search. Sidebar: independent coverage, latest releases.
- `/releases/` timeline of GitLab releases (Nexa full node, Rostrum, libnexakotlin, Wally Wallet, libnexa-js).
- `/sources/` every source, its method and whether it works.
- `/about/` disclosure, how it works, and the editor's policy (`editorial-policy.md`, rendered as written).
- `/changelog/` site changes (from `changelog.json`), newest first.
- `/screen/` office display: full screen, clock, rotating feed, portrait or landscape, dark or light (`?theme=light`).

## Publishing to GitHub Pages (after jQrgen's final approval)

Local preparation is done: `git init -b main`, `.gitignore`, and `publish.conf` (kept out of git):

```
PUBLISH_REMOTE=https://github.com/jQrgen/nexa-news.git   # or git@github.com:jQrgen/nexa-news.git
PUBLISH_BRANCH=gh-pages
PUBLISH_URL=https://jqrgen.github.io/nexa-news/
```

Steps once jQrgen approves:

1. Editor finishes `queue/approved.json`; run `./build.sh` (public build) and check the result.
2. Create the empty public repo `jQrgen/nexa-news` on GitHub (no README, so the first push is clean).
3. Commit and push the code: `git add -A && git commit -m "Nexa News: initial import" && git remote add origin git@github.com:jQrgen/nexa-news.git && git push -u origin main`.
   Check `git status` first: data/, state/, queue/, logs/, site/, shots/, research/ and publish.conf must not be listed.
4. Publish the site: `./publish.sh --yes` (creates `gh-pages` on the first run).
5. On GitHub: Settings → Pages → Source "Deploy from a branch", branch `gh-pages`, folder `/ (root)`. Wait for the deploy,
   then open https://jqrgen.github.io/nexa-news/ and /screen/.
6. Daily after that: `./fetch.sh`, editor review, `./publish.sh --yes`.

## X (Twitter)

X has no free API and scraping breaks its terms, so it is never read automatically. Posts are added by URL and shown as a
plain link card with our own summary. No X embed, widget or script is loaded.

## Privacy check

`tools/privacy_check.py site` fails the build if it finds anything like an email address, phone number, organisation or
national ID number, bank account, access token, private key or a local file path, or any personal term listed in
`state/private_terms.json`. That file stays out of git, and the check fails if it is missing. It prints only file, line and
rule, never the match.

## Not in the repository

`data/`, `state/`, `queue/`, `logs/`, `site/`, `shots/`, `research/` and `publish.conf` are working files (see `.gitignore`).
The published site lives only on the `gh-pages` branch.

## Licence

Code: MIT (see `LICENSE`). Summaries are our own. Linked articles, posts and videos belong to their authors. Nothing here is
investment advice.
