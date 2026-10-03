#!/usr/bin/env python3
"""Build the static Nexa News site into site/.

  .venv/bin/python build.py            public build: only items the editor approved (queue/approved.json)
  .venv/bin/python build.py --preview  local review build: also shows pending items, clearly marked,
                                       without summaries. A preview build can never be published.

All links are relative, so the site works at any path (example.org/, example.org/nexa-news/ ...).
No trackers, cookies, web fonts or third-party scripts.
"""
import argparse, datetime as dt, glob, html, json, os, re, shutil, sys
from zoneinfo import ZoneInfo
import markdown

HERE = os.path.dirname(os.path.abspath(__file__))
def path(*p): return os.path.join(HERE, *p)
OUT = path("site")
OSLO = ZoneInfo("Europe/Oslo")
esc = lambda s: html.escape("" if s is None else str(s), quote=True)

def read_json(p, default):
    try:
        with open(p, encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError: return default
def write(rel, text):
    p = os.path.join(OUT, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f: f.write(text)
def dump(rel, data): write(rel, json.dumps(data, ensure_ascii=False, indent=1) + "\n")

PLATFORMS = {"forum": "Forum", "blog": "nexa.org", "gitlab": "GitLab", "medium": "Medium", "news": "News", "mastodon": "Mastodon",
             "x": "X", "reddit": "Reddit", "youtube": "YouTube", "podcast": "Podcast", "web": "Web", "nostr": "Nostr"}
FLAG_LABEL = {"price": "price talk?", "shill": "promotion?", "spam": "spam?", "not-english": "not English", "ambiguous-nexa": "other 'Nexa'?"}
def display_title(i):
    t, p = i["title"], i.get("project")
    if i["kind"] in ("release", "tag") and p and p.split()[0].lower() not in t.lower(): return f"{p} {t}"
    return t
def day(iso):
    d = dt.datetime.fromisoformat(iso).astimezone(OSLO); return f"{d.day} {d:%b %Y}"

# ------------------------------------------------------------------ editor decisions
def apply_editor(items):
    """queue/approved.json -> item status. Returns warnings. Only the editor's file can publish anything."""
    ap = read_json(path("queue", "approved.json"), {"approve": [], "reject": []})
    by_id = {i["id"]: i for i in items}
    by_url = {i["url"].rstrip("/"): i for i in items}
    warn = []; approved = set()
    for r in ap.get("reject", []):
        it = by_id.get(r.get("id")) or by_url.get((r.get("url") or "").rstrip("/"))
        if it: it.update(status="rejected", summary=None, reject_reason=r.get("reason"))
    for a in ap.get("approve", []):
        it = by_id.get(a.get("id")) or by_url.get((a.get("url") or "").rstrip("/"))
        if not it: warn.append(f"approved item not found: {a.get('id') or a.get('url')}"); continue
        if it["status"] == "rejected": warn.append(f"{it['id']} is both approved and rejected; kept out"); continue
        summary = (a.get("summary") or "").strip()
        if not summary: warn.append(f"{it['id']} has no summary; not published"); continue
        if it.get("flags") and not a.get("flags_checked"): warn.append(f"{it['id']} has flags {it['flags']} and no flags_checked:true; not published"); continue
        copied = copied_from_teaser(summary, it["id"])
        if copied: warn.append(f"{it['id']} summary repeats {copied} words of the source text in a row; rewrite it; not published"); continue
        it.update(status="published", summary=summary, approved_by=a.get("approved_by", "editor"), approved_at=a.get("approved_at"))
        for k in ("title", "author", "category", "platform", "sponsored", "correction", "outlet_note"):
            if a.get(k): it[k] = a[k]
        approved.add(it["id"])
    # state/hold.json (local, not in git): ids jQrgen wants kept off the site for now, even if approved
    hold = set(read_json(path("state", "hold.json"), {}).get("ids", []))
    approved -= hold
    if hold: warn.append(f"held back by state/hold.json: {sorted(hold)}")
    for it in items:   # removing an approval unpublishes the item at the next build
        if it["status"] == "published" and it["id"] not in approved: it["status"] = "pending"; it["summary"] = None
    return warn

_teasers = None
def copied_from_teaser(summary, iid, run=10):
    """Longest run of words shared with the source teaser, if >= run (we write our own summaries)."""
    global _teasers
    if _teasers is None: _teasers = read_json(path("state", "teasers.json"), {})
    a = re.findall(r"\w+", summary.lower()); b = " " + " ".join(re.findall(r"\w+", (_teasers.get(iid) or "").lower())) + " "
    best = 0
    for i in range(len(a)):
        for j in range(i + run, len(a) + 1):
            if " " + " ".join(a[i:j]) + " " in b: best = max(best, j - i)
            else: break
    return best if best >= run else 0

# ------------------------------------------------------------------ page shell
NAV = [("", "Feed"), ("releases/", "Releases"), ("sources/", "Sources"), ("about/", "About"), ("changelog/", "Changelog"), ("screen/", "Office screen")]
def shell(rel, title, body, *, here, desc, preview, scripts=""):
    up = "../" * rel.count("/")
    nav = "".join(f'<a href="{up}{href}"{" aria-current=page" if href == here else ""}>{esc(label)}</a>' for href, label in NAV)
    bar = ('<div class="preview-bar"><div class="wrap"><b>Local preview.</b> Includes items still waiting for editor review. '
           'Pending items have no summary yet and are not public.</div></div>') if preview else ""
    robots = '<meta name="robots" content="noindex">' if preview else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">{robots}
<meta name="referrer" content="strict-origin-when-cross-origin">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%230f766e'/%3E%3Ctext x='16' y='23' font-size='20' text-anchor='middle' fill='white' font-family='sans-serif' font-weight='bold'%3EN%3C/text%3E%3C/svg%3E">
<link rel="stylesheet" href="{up}assets/style.css"></head>
<body><a class="skip" href="#main">Skip to content</a>{bar}
<div class="disclosure"><div class="wrap">Run by Jørgen S. Notland (jQrgen), who works on Nexa with Bitcoin Unlimited. Not an official Nexa channel. Not investment advice. <a href="{up}about/#disclosure">Disclosure</a></div></div>
<header class="site"><div class="wrap"><a class="brand" href="{up or './'}"><span class="logo" aria-hidden="true">N</span>Nexa News</a>
<nav class="main" aria-label="Main">{nav}</nav><span class="tagline">Unofficial · AI-assisted · run by jQrgen</span></div></header>
<main id="main" class="wrap">
{body}
</main>
<footer class="site"><div class="wrap">
<p><b>Nexa News</b> is run by Jørgen S. Notland (jQrgen), Oslo, with help from AI assistants. An editor reviews every item.</p>
<p><b>Disclosure:</b> jQrgen works on Nexa with Bitcoin Unlimited. Items are labelled official or independent. Nothing here is investment advice. No tracking, no cookies, no third-party scripts. <a href="{up}about/">About, policy and corrections</a> · <a href="{up}changelog/">Changelog</a>.</p>
</div></footer>{scripts}
</body></html>"""

# ------------------------------------------------------------------ pieces
def item_html(i, preview, up=""):
    pf = i["platform"]; cat = i["category"]
    badges = f'<span class="badge {"off" if cat == "official" else "ind"}">{"Official" if cat == "official" else "Independent"}</span>'
    if i.get("sponsored"): badges += '<span class="badge flag">Sponsored</span>'
    if i["status"] == "pending":
        badges += '<span class="badge pend">Pending review</span>' + "".join(f'<span class="badge flag">{esc(FLAG_LABEL.get(f, f))}</span>' for f in i.get("flags", []))
    who = esc(re.sub(r"\s*[(<]?[\w.+-]+@[\w-]+\.[\w.-]+[)>]?", "", i.get("author") or "").strip())
    src = esc(i["source_name"]) if i["source_id"] != "manual" else ""
    meta = " · ".join(x for x in [f"<b>{who}</b>" if who else "", src if src and src != who else "",
                                  f'<time datetime="{esc(i["published"])}">{day(i["published"])}</time>'] if x)
    title = display_title(i)
    summary = (f'<p class="sum">{esc(i["summary"])}</p>' if i.get("summary") else
               '<p class="sum wait">Awaiting editor summary.</p>' if preview else "")
    if i.get("outlet_note"): meta += f' · <span title="Who runs this outlet">{esc(i["outlet_note"])}</span>'
    if i.get("correction"):
        c = i["correction"]; summary += f'<p class="meta"><b>Corrected {esc(c.get("date", ""))}:</b> {esc(c.get("note", ""))}</p>'
    xcard = ""
    if pf == "x":
        xcard = (f'<div class="xcard">Post on X by <b>{who}</b>. This is a plain link: we show no X embed and load no X scripts. '
                 f'<a href="{esc(i["url"])}" rel="noopener noreferrer" target="_blank">Open on x.com</a></div>')
    return (f'<li class="item" data-p="{esc(pf)}" data-c="{esc(cat)}"><div><span class="pf pf-{esc(pf)}"><i aria-hidden="true"></i>{esc(PLATFORMS.get(pf, pf))}</span>{badges}</div>'
            f'<h3><a href="{esc(i["url"])}" rel="noopener noreferrer" target="_blank">{esc(title)}</a></h3>'
            f'<div class="meta">{meta}</div>{summary}{xcard}</li>')

def side_list(items, empty, up=""):
    if not items: return f'<p class="meta">{empty}</p>'
    out = []
    for i in items:
        t = display_title(i)
        out.append(f'<li><a href="{esc(i["url"])}" rel="noopener noreferrer" target="_blank">{esc(t)}</a>'
                   f'<div class="meta">{esc(i.get("author") or i["source_name"])} · {day(i["published"])}{" · pending" if i["status"] == "pending" else ""}</div></li>')
    return "<ul>" + "".join(out) + "</ul>"

def public_fields(i):
    keep = ("id", "url", "title", "author", "platform", "category", "kind", "project", "source_name", "published", "summary", "status", "sponsored", "correction", "outlet_note")
    d = {k: i.get(k) for k in keep if i.get(k) is not None}
    if d.get("author"): d["author"] = re.sub(r"\s*[(<]?[\w.+-]+@[\w-]+\.[\w.-]+[)>]?", "", d["author"]).strip()
    d["title"] = display_title(i)
    if i["status"] == "pending": d["flags"] = i.get("flags", [])
    return d

# ------------------------------------------------------------------ build
def build(preview):
    store = read_json(path("data", "items.json"), {"items": []})
    items = store["items"]
    warnings = apply_editor(items)
    with open(path("data", "items.json"), "w", encoding="utf-8") as f: json.dump(store, f, ensure_ascii=False, indent=1); f.write("\n")
    conf = read_json(path("sources.json"), {}); health = read_json(path("state", "source_status.json"), {})
    shown = [i for i in items if i["status"] == "published" or (preview and i["status"] == "pending")]
    shown.sort(key=lambda i: i["published"], reverse=True)
    news = [i for i in shown if i["kind"] not in ("release", "tag")]
    releases = [i for i in shown if i["kind"] in ("release", "tag")]
    if os.path.exists(OUT): shutil.rmtree(OUT)
    os.makedirs(OUT)
    shutil.copytree(path("assets"), os.path.join(OUT, "assets"))
    updated = store.get("updated")
    upd = dt.datetime.fromisoformat(updated).astimezone(OSLO).strftime("%-d %b %Y, %H:%M") + " Oslo time" if updated else "never"

    # ---- feed
    plats = [p for p in PLATFORMS if any(i["platform"] == p for i in shown)]
    chips = "".join(f'<button type="button" class="chip" data-platform="{p}" aria-pressed="false">{esc(PLATFORMS[p])}</button>' for p in plats)
    lis = "".join(item_html(i, preview) for i in shown) or '<li class="empty">No items yet.</li>'
    indep = [i for i in news if i["category"] == "independent"][:6]
    pend_n = sum(1 for i in shown if i["status"] == "pending")
    body = f"""<h1>Everything public about Nexa, in one place</h1>
<p class="lead">News, forum posts, articles, releases and independent coverage of the Nexa blockchain, Wally Wallet, Otoplo, Rostrum and Build On Nexa. Each item links to the original and has a short summary in our own words. Last fetched {esc(upd)}. {len(shown)} items{f", {pend_n} pending review" if preview else ""}.</p>
<div class="layout"><div>
<div class="toolbar" role="group" aria-label="Filter the feed">
<div class="seg" role="group" aria-label="Category"><button type="button" data-cat="" aria-pressed="true">All</button><button type="button" data-cat="official" aria-pressed="false">Official</button><button type="button" data-cat="independent" aria-pressed="false">Independent coverage</button></div>
<div class="chips" role="group" aria-label="Platform">{chips}</div>
<input type="search" id="q" placeholder="Search titles" aria-label="Search titles"><span id="count" aria-live="polite"></span></div>
<ol class="feed" id="feed">{lis}</ol>
</div>
<aside>
<div class="box" id="independent"><h2>Independent coverage</h2>{side_list(indep, "No independent coverage in this period yet.")}<a class="more" href="#category=independent">All independent coverage →</a></div>
<div class="box"><h2>Latest releases</h2>{side_list(releases[:5], "No releases yet.")}<a class="more" href="releases/">Release timeline →</a></div>
<div class="box"><h2>On X</h2><p class="meta">We don't read X automatically. Notable posts are added by hand as plain links. Official account: <a href="https://x.com/NexaMoney" rel="noopener noreferrer">@NexaMoney</a>.</p></div>
<div class="box"><h2>Office screen</h2><p class="meta">A full-screen view for a TV or monitor, portrait or landscape. <a href="screen/">Open the office screen →</a></p></div>
</aside></div>
<p class="notice">Summaries are written by the editor from the title and public description. We don't copy posts and don't publish price talk or promotion. Nothing here is investment advice.</p>"""
    write("index.html", shell("", "Nexa News – everything public about the Nexa blockchain", body, here="", preview=preview,
                              desc="News, forum posts, releases and independent coverage of the Nexa blockchain, collected daily with short summaries.",
                              scripts='<script src="assets/feed.js"></script>'))

    # ---- releases timeline
    rows, month = [], None
    for i in releases:
        m = dt.datetime.fromisoformat(i["published"]).astimezone(OSLO).strftime("%B %Y")
        if m != month: rows.append(f'</ol><div class="month">{m}</div><ol class="timeline">'); month = m
        rows.append(f'<li><div class="ver"><a href="{esc(i["url"])}" rel="noopener noreferrer" target="_blank">{esc(display_title(i))}</a> <span class="meta">{esc(i.get("project") or "")}</span></div>'
                    f'<div class="meta">{"Release" if i["kind"] == "release" else "Tag"} · {day(i["published"])}{(" · by " + esc(i["author"])) if i.get("author") else ""}'
                    f'{" · <span class=\"badge pend\">Pending review</span>" if i["status"] == "pending" else ""}</div>'
                    + (f'<p class="sum">{esc(i["summary"])}</p>' if i.get("summary") else "") + '</li>')
    tl = ("<ol>" + "".join(rows) + "</ol>").replace("<ol></ol>", "", 1) if rows else '<p class="empty">No releases yet.</p>'
    projects = sorted({i.get("project") for i in releases if i.get("project")})
    body = f"""<h1>Release timeline</h1>
<p class="lead">Releases and tags from the public GitLab projects behind Nexa: {esc(", ".join(projects)) or "none yet"}. Read straight from GitLab's Atom feeds. Releases older than two years are not shown.</p>
{tl}"""
    write("releases/index.html", shell("releases/", "Release timeline – Nexa News", body, here="releases/", preview=preview,
                                       desc="Timeline of Nexa full node, Rostrum, Wally Wallet and library releases from GitLab."))

    # ---- sources
    def state_of(s):
        h = health.get(s["id"], {})
        if s["type"] == "manual": return "st-man", "added by hand"
        if s["type"] == "reference" and "down" in s.get("status", "")[:6]: return "st-bad", "down"
        if s["type"] == "reference" and s.get("status", "").startswith("not found"): return "st-bad", "not found"
        if s["type"] == "reference": return "st-ref", "not fetched"
        if not s.get("enabled"): return "st-bad", "not used"
        if h and not h.get("ok"): return "st-bad", "failing"
        return "st-ok", "working"
    srows = []
    for s in conf.get("sources", []):
        cls, lab = state_of(s); h = health.get(s["id"], {})
        checked = day(h["checked"]) if h.get("checked") else (day(s["verified"] + "T12:00:00+00:00") if s.get("verified") else "")
        note = re.sub(r"^ok[:,]\s*", "", s.get("status", "")).strip(); note = note[:1].upper() + note[1:]
        if note and not note.endswith("."): note += "."
        method = {"feed": "RSS/Atom feed", "search": "news search RSS", "sitemap": "sitemap + page titles", "manual": "added by hand", "reference": "listed only"}[s["type"]]
        srows.append(f'<tr><td data-l="Source"><a href="{esc(s["url"])}" rel="noopener noreferrer" target="_blank">{esc(s["name"])}</a></td>'
                     f'<td data-l="Type">{esc(PLATFORMS.get(s.get("platform"), s.get("platform", "")))} · <span class="badge {"off" if s["category"] == "official" else "ind"}">{s["category"].capitalize()}</span></td>'
                     f'<td data-l="Method">{method}</td><td data-l="Status" class="{cls}">{lab}</td>'
                     f'<td data-l="Notes">{esc(note)}{(" Checked " + esc(checked) + ".") if checked else ""}</td></tr>')
    bing = next((s for s in conf.get("sources", []) if s["id"] == "bing-news"), {})
    body = f"""<h1>Sources</h1>
<p class="lead">Where Nexa News looks, and whether it works. The fetcher identifies itself with its own user agent, follows robots.txt, waits at least {conf.get("min_delay_seconds", 2)} seconds between requests to the same site, and only reads public feeds and page titles. It never logs in and never reads text behind a paywall.</p>
<table class="list"><thead><tr><th>Source</th><th>Type</th><th>Method</th><th>Status</th><th>Notes</th></tr></thead><tbody>{"".join(srows)}</tbody></table>
<h2>Official and independent</h2>
<p class="prose"><span class="badge off">Official</span> means the item comes from Nexa, Bitcoin Unlimited or a project linked from nexa.org (including articles by jQrgen, who works on Nexa). <span class="badge ind">Independent</span> means anyone else: crypto news sites, blogs, podcasts and forum threads found through public search.</p>
<h2>News search terms</h2>
<p class="prose">{esc(", ".join(bing.get("queries", [])))}. "Nexa" is also the name of a car brand, a font, a payment card and other companies, so search results need an unambiguous Nexa term, and the editor reviews every match.</p>
<h2>X (Twitter)</h2>
<p class="prose">Not read automatically: there is no free API and scraping breaks X's terms. Posts are added by hand by URL and shown as plain links with our own summary, with no X embeds or scripts. Official accounts: <a href="https://x.com/NexaMoney" rel="noopener noreferrer">@NexaMoney</a> (linked from nexa.org) and <a href="https://x.com/BitcoinUnlimit" rel="noopener noreferrer">@BitcoinUnlimit</a> (listed on bitcoinunlimited.info).</p>
<p class="meta">Know a source we miss? Suggest it in <a href="https://github.com/jQrgen/nexa-news/issues" rel="noopener noreferrer">GitHub Issues</a>.</p>"""
    write("sources/index.html", shell("sources/", "Sources – Nexa News", body, here="sources/", preview=preview,
                                      desc="The feeds, searches and channels Nexa News follows, and whether each one works."))

    # ---- about (+ the editor's own policy and disclosure documents, rendered as written)
    docs = []
    for p in editor_docs():
        txt = open(p, encoding="utf-8").read()
        docs.append(f'<section class="editor-doc" data-file="{esc(os.path.basename(p))}">' + markdown.markdown(demote(txt), extensions=["extra", "sane_lists"]) + "</section>")
    about = open(path("templates", "about.html"), encoding="utf-8").read().replace(
        "__EDITOR_DOCS__", "".join(docs) or '<p class="meta">The editorial policy is being written and will appear here.</p>')
    write("about/index.html", shell("about/", "About – Nexa News", about, here="about/", preview=preview,
                                    desc="Who runs Nexa News, the disclosure, the editorial policy, and how to ask for corrections."))

    # ---- changelog (site changes only, from changelog.json)
    cl = read_json(path("changelog.json"), {"entries": []})
    entries = sorted(cl.get("entries", []), key=lambda e: e["date"], reverse=True)
    body = '<h1>Changelog</h1><p class="lead">Changes to the Nexa News site itself: new pages, sections and source types. Newest first. Daily news items are not listed here.</p>' + "".join(
        f'<section class="prose"><h2><time datetime="{esc(e["date"])}">{day(e["date"] + "T12:00:00+00:00")}</time>: {esc(e.get("title", ""))}</h2><ul>'
        + "".join(f"<li>{esc(c)}</li>" for c in e.get("changes", [])) + "</ul></section>" for e in entries)
    write("changelog/index.html", shell("changelog/", "Changelog – Nexa News", body, here="changelog/", preview=preview,
                                        desc="Changes to the Nexa News site: new pages, sections and source types."))

    # ---- office screen + data for it
    write("screen/index.html", open(path("templates", "screen.html"), encoding="utf-8").read().replace("__PREVIEW__", "true" if preview else "false"))
    dump("data/items.json", {"updated": updated, "preview": preview, "items": [public_fields(i) for i in news]})
    dump("data/releases.json", {"updated": updated, "items": [public_fields(i) for i in releases]})
    dump("data/sources.json", {"working": sorted({s["name"] for s in conf.get("sources", []) if s.get("enabled") and health.get(s["id"], {}).get("ok", True)})})
    write("robots.txt", "User-agent: *\nDisallow: /\n" if preview else "User-agent: *\nAllow: /\n")
    write(".nojekyll", "")
    if preview: write("PREVIEW-BUILD-DO-NOT-PUBLISH.txt", "This site/ folder was built with --preview and contains unreviewed items.\n")
    for w in warnings: print("editor:", w, file=sys.stderr)
    print(f"build{' (PREVIEW)' if preview else ''}: {len(shown)} items shown ({sum(i['status']=='published' for i in items)} published, "
          f"{sum(i['status']=='pending' for i in items)} pending, {sum(i['status']=='rejected' for i in items)} rejected), {len(releases)} releases -> site/")

def editor_docs():
    """The editor's policy/disclosure drafts. Read only, never written by the build."""
    names = ["EDITORIAL_POLICY.md", "editorial-policy.md", "editorial_policy.md", "POLICY.md", "policy.md", "DISCLOSURE.md", "disclosure.md"]
    found = [path(n) for n in names if os.path.exists(path(n))]
    for pat in ("editorial/*.md", "editor/*.md", "policy/*.md", "*policy*.md", "*disclosure*.md", "*Policy*.md", "*Disclosure*.md"):
        found += sorted(glob.glob(path(pat)))
    seen, out = set(), []
    for p in found:
        rp = os.path.realpath(p)
        if rp not in seen: seen.add(rp); out.append(p)
    return out
def demote(md):
    """Editor docs start at H1; on the About page they sit under H1, so shift headings down one level."""
    return re.sub(r"^(#{1,5}) ", lambda m: "#" + m[1] + " ", md, flags=re.M)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--preview", action="store_true"); a = ap.parse_args()
    build(a.preview)
