#!/usr/bin/env python3
"""Nexa News fetcher.

Reads the enabled sources in sources.json, keeps entries that are about Nexa, flags price talk,
shilling and spam for the editor, deduplicates, and writes:

  data/items.json      every item we know about (status: pending | published | rejected)
  queue/review.json    what the editor still has to look at (with a local-only teaser)
  state/*.json         HTTP cache, seen pages, source health, local teasers (never published)

Nothing fetched here is published by itself. The editor approves items in queue/approved.json
with a summary in their own words; build.py only shows approved items (except in --preview).

Usage:
  ./fetch.sh                      daily run (looks back 14 days)
  ./fetch.sh --days 120           longer look-back (first run)
  ./fetch.sh --only nexa-forum    just some source ids (comma separated)
  ./fetch.sh --add URL [--title T --date YYYY-MM-DD --author A --platform P --category official|independent]
     Add one item by hand. X/Twitter, Reddit and YouTube URLs are never fetched: give --title and --date.
"""
import argparse, datetime as dt, hashlib, json, os, re, sys, time
import urllib.parse, urllib.robotparser
import requests, feedparser
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
def path(*p): return os.path.join(HERE, *p)
UTC = dt.timezone.utc
NOW = dt.datetime.now(UTC)

def read_json(p, default):
    try:
        with open(p, encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError: return default
def write_json(p, data):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1); f.write("\n")
    os.replace(p + ".tmp", p)

CONF = read_json(path("sources.json"), None)
AGENT = CONF["user_agent"]
GAP = float(CONF.get("min_delay_seconds", 2))
os.makedirs(path("logs"), exist_ok=True)
_logf = open(path("logs", NOW.astimezone().strftime("fetch-%Y%m%d-%H%M%S.log")), "w", encoding="utf-8")
def say(*parts):
    line = " ".join(str(p) for p in parts); print(line); _logf.write(line + "\n"); _logf.flush()

# ---------------------------------------------------------------- polite HTTP
class Polite:
    """robots.txt check per host, a minimum gap between requests to the same host, and ETag/Last-Modified."""
    def __init__(self):
        self.robots, self.last = {}, {}
        self.cache = read_json(path("state", "http_cache.json"), {})
    def allowed(self, url):
        u = urllib.parse.urlsplit(url); root = f"{u.scheme}://{u.netloc}"
        if root not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = requests.get(root + "/robots.txt", headers={"User-Agent": AGENT}, timeout=15)
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except requests.RequestException:
                rp.parse([])
            self.robots[root] = rp
        return self.robots[root].can_fetch(AGENT, url)
    def get(self, url, conditional=True):
        host = urllib.parse.urlsplit(url).netloc
        pause = GAP - (time.time() - self.last.get(host, 0))
        if pause > 0: time.sleep(pause)
        headers = {"User-Agent": AGENT, "Accept": "application/atom+xml, application/rss+xml, application/xml;q=0.9, text/html;q=0.8, */*;q=0.5"}
        c = self.cache.get(url, {}) if conditional else {}
        if c.get("etag"): headers["If-None-Match"] = c["etag"]
        if c.get("modified"): headers["If-Modified-Since"] = c["modified"]
        r = requests.get(url, headers=headers, timeout=30)
        self.last[host] = time.time()
        if r.status_code == 200 and conditional:
            self.cache[url] = {"etag": r.headers.get("ETag"), "modified": r.headers.get("Last-Modified")}
        return r
    def save(self): write_json(path("state", "http_cache.json"), self.cache)

# ---------------------------------------------------------------- relevance and flags
# Unambiguous Nexa terms. "Nexa" alone is also a car brand, a font, a spyware firm, a card scheme ...
STRONG = re.compile(r"nexa\.org|\bNexa(?:'s)? (?:blockchain|network|chain|full[- ]node|node|coin|wallet|token|tokens|community|forum|foundation|developers?|mainnet|testnet|upgrade|hard ?fork|crypto|cryptocurrency|L1|layer[- ]1|mining|miners?)\b|\bNexa \(NEXA\)|\bNEXA token\b|"
                    r"\bNEXA coin\b|\$NEXA\b|\bBitcoin Unlimited\b|\bWally ?Wallet\b|\bOtoplo\b|\bRostrum\b|\bVotePeer\b|\bBuild On Nexa\b|\bNexScript\b|"
                    r"\blibnexa|\bNexaPow\b|\bNiftyArt\b|\bTailstorm\b.*\bNexa\b|\bNexa\b.*\bTailstorm\b|\bnexajs\b|\bnexa-js\b", re.I | re.S)
NEXA_WORD = re.compile(r"\bnexa\b", re.I)
CRYPTO_CTX = re.compile(r"blockchain|crypto|coin\b|token|mining|miner|wallet|smart contract|layer[- ]?1|\bUTXO\b|bitcoin|BCH|proof[- ]of[- ]work|\bPoW\b|exchange|node", re.I)
FLAGS = {
    "price": re.compile(r"\bprice\b|price prediction|\bpump|\bdump\b|\bmoon|to the moon|\b\d{2,4}x\b|\bATH\b|all[- ]time high|\brally\b|\bsurges?\b|\bplunges?\b|\bsoars?\b|\bbullish\b|\bbearish\b|market cap|\btrading volume|technical analysis|\bTA\b|\b(?:price|candlestick|trading|NEXA/USDT?) charts?\b|\bbuy (?:now|the dip)\b|\bportfolio\b|\b(?:hodl|hold)\b[^.]{0,40}\b(?:price|moon|x\b|gains?)", re.I),
    "shill": re.compile(r"\bsponsored\b|press release|partner content|\bpromoted\b|\bairdrop|\bgiveaways?\b[^.]{0,60}\b(?:enter|win|retweet|RT|follow|tag|join|claim|free)\b|\b(?:enter|win|join|claim)\b[^.]{0,40}\bgiveaways?\b|\bpresale|\bpre-sale|referral|\bbonus\b|pay[- ]per[- ]tweet|\b(?:100|1000)x gem|next big|don't miss|\bshill", re.I),
    "spam": re.compile(r"casino|betting|\bporn|\bcrack(?:ed)?\b|free money|recover (?:your )?(?:lost )?(?:crypto|funds)|hacker for hire|whatsapp \+?\d|telegram @\w+ for", re.I),
}
EXCLUDE = [re.compile(p, re.I) for p in CONF.get("exclude_patterns", [])]

def is_relevant(text, mode):
    """Return (keep, reason). mode: all | nexa | strict."""
    if mode == "all": return True, "all"
    if any(x.search(text) for x in EXCLUDE): return False, "excluded (different 'Nexa' or known noise)"
    if STRONG.search(text): return True, "strong term"
    if mode == "nexa" and NEXA_WORD.search(text) and CRYPTO_CTX.search(text): return True, "Nexa + crypto context"
    return False, "no Nexa term"
NON_ENGLISH = re.compile(r"\b(?:não|são|com|para|uma|mercado|cripto|revela|fundos|agora|el|la|los|las|por|del|una|apuesta|escalabilidad|und|der|die|das|mit|für|le|les|des|est|pour|avec|dans)\b|[一-龥가-힣]", re.I)
def flags_for(text, why=""):
    f = [name for name, rx in FLAGS.items() if rx.search(text)]
    if len(NON_ENGLISH.findall(text.split("\n")[0])) >= 2: f.append("not-english")
    if why == "Nexa + crypto context": f.append("ambiguous-nexa")
    return f

# ---------------------------------------------------------------- helpers
EMAIL = re.compile(r"\s*[(<]?[\w.+-]+@[\w-]+\.[\w.-]+[)>]?\s*")
def no_email(name): return EMAIL.sub(" ", name or "").strip(" ,;")
def plain(html_text):
    return re.sub(r"\s+", " ", BeautifulSoup(html_text or "", "lxml").get_text(" ")).strip()
TRACKING = ("utm_", "fbclid", "gclid", "mc_", "ref_src", "source")
def tidy_url(url):
    u = urllib.parse.urlsplit(url.strip())
    q = [(k, v) for k, v in urllib.parse.parse_qsl(u.query) if not k.lower().startswith(TRACKING)]
    return urllib.parse.urlunsplit((u.scheme or "https", u.netloc, u.path, urllib.parse.urlencode(q), ""))
def url_key(url):
    u = urllib.parse.urlsplit(tidy_url(url))
    host = u.netloc.lower().removeprefix("www.").replace("twitter.com", "x.com").replace("mobile.x.com", "x.com")
    return host + (u.path.rstrip("/") or "/") + ("?" + u.query if u.query else "")
def make_id(url): return hashlib.sha256(url_key(url).encode()).hexdigest()[:12]
def title_key(t): return re.sub(r"\W+", " ", (t or "").lower()).strip()
def entry_date(e):
    for k in ("published_parsed", "updated_parsed"):
        if e.get(k): return dt.datetime(*e[k][:6], tzinfo=UTC)
    return None
MONTHS = "January February March April May June July August September October November December".split()
def page_date(soup, raw):
    for attrs in ({"property": "article:published_time"}, {"name": "date"}, {"itemprop": "datePublished"}, {"name": "publish-date"}):
        m = soup.find("meta", attrs=attrs)
        if m and m.get("content"):
            try:
                d = dt.datetime.fromisoformat(m["content"].replace("Z", "+00:00"))
                return d if d.tzinfo else d.replace(tzinfo=UTC)
            except ValueError: pass
    t = soup.find("time", attrs={"datetime": True})
    if t:
        try:
            d = dt.datetime.fromisoformat(t["datetime"].replace("Z", "+00:00")); return d if d.tzinfo else d.replace(tzinfo=UTC)
        except ValueError: pass
    m = re.search(r"\b(" + "|".join(MONTHS) + r") (\d{1,2}),? (20\d\d)\b", raw)
    if m: return dt.datetime(int(m[3]), MONTHS.index(m[1]) + 1, int(m[2]), 12, tzinfo=UTC)
    return None
def page_meta(http, url):
    """Public page metadata only: title, description, author, date. Never the article body."""
    r = http.get(url, conditional=False); r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    meta = lambda **k: (soup.find("meta", attrs=k) or {}).get("content") or ""
    title = meta(property="og:title") or (soup.title.get_text() if soup.title else "")
    desc = meta(property="og:description") or meta(name="description")
    author = meta(name="author") or meta(property="article:author")
    # nexa.org: the article's own date is the first date in the page body (later dates are the sidebar)
    return plain(title), plain(desc), plain(author), page_date(soup, r.text)
def domain_category(url, fallback):
    k = url_key(url); host = k.split("/")[0]
    for d in CONF.get("official_domains", []):
        if "/" in d:
            if k == d or k.startswith(d + "/"): return "official"
        elif host == d or host.endswith("." + d): return "official"
    return fallback
PLATFORM_BY_HOST = [("x.com", "x"), ("twitter.com", "x"), ("reddit.com", "reddit"), ("youtube.com", "youtube"), ("youtu.be", "youtube"),
                    ("medium.com", "medium"), ("gitlab.com", "gitlab"), ("forum.", "forum"), ("t.me", "telegram"), ("nexa.org", "blog")]
def platform_for(url):
    host = urllib.parse.urlsplit(url).netloc.lower()
    for h, p in PLATFORM_BY_HOST:
        if h in host: return p
    return "web"
NO_FETCH_HOSTS = ("x.com", "twitter.com", "reddit.com", "youtube.com", "youtu.be", "t.me", "discord")

# ---------------------------------------------------------------- store
class Store:
    def __init__(self):
        self.data = read_json(path("data", "items.json"), {"items": []})
        self.teasers = read_json(path("state", "teasers.json"), {})
        self.by_url = {url_key(i["url"]): i for i in self.data["items"]}
        self.by_title = {title_key(i["title"]) + "|" + i["source_id"]: i for i in self.data["items"]}
        self.new = []; self.skipped = {}
    def add(self, *, url, title, teaser, published, source, author="", kind=None, category=None, platform=None, extra=None, mode="all", cutoff=None, manual=False):
        url = tidy_url(url); title = title.strip()
        if not url or not title: return None
        text = f"{title}\n{teaser}\n{author}"
        keep, why = (True, "manual") if manual else is_relevant(text, mode)
        if keep and not manual and source.get("require") and not re.search(source["require"], text, re.I):
            keep, why = False, "source 'require' rule not met"
        if not keep:
            self.skipped[why] = self.skipped.get(why, 0) + 1; return None
        if not published: self.skipped["no date"] = self.skipped.get("no date", 0) + 1; return None
        if cutoff and published < cutoff: self.skipped["older than --days"] = self.skipped.get("older than --days", 0) + 1; return None
        k = url_key(url); tk = title_key(title) + "|" + source["id"]
        old = self.by_url.get(k) or self.by_title.get(tk)
        if old:
            if source["id"] not in old.setdefault("seen_in", []): old["seen_in"].append(source["id"])
            return None
        if (kind or source.get("kind")) in ("release", "tag") and extra and extra.get("project"):
            ver = re.sub(r"\D", "", title)
            for o in self.data["items"]:
                if o.get("project") == extra["project"] and o["kind"] in ("release", "tag") and re.sub(r"\D", "", o["title"]) == ver and ver:
                    if source["id"] not in o.setdefault("seen_in", []): o["seen_in"].append(source["id"])
                    self.skipped["tag duplicates a release"] = self.skipped.get("tag duplicates a release", 0) + 1
                    return None
        item = {
            "id": make_id(url), "url": url, "title": title[:300], "author": no_email(author)[:120],
            "platform": platform or source.get("platform") or platform_for(url),
            "category": category or (("official" if author.strip().lower() in {a.lower() for a in source["official_authors"]} else "independent")
                                     if source.get("official_authors") else domain_category(url, source.get("category", "independent"))),
            "kind": kind or source.get("kind", "article"),
            "source_id": source["id"], "source_name": source["name"], "seen_in": [source["id"]],
            "published": published.astimezone(UTC).isoformat(timespec="seconds"),
            "fetched": NOW.isoformat(timespec="seconds"),
            "flags": flags_for(text, why), "match": why, "status": "pending", "summary": None,
        }
        if extra: item.update(extra)
        self.data["items"].append(item); self.by_url[k] = item; self.by_title[tk] = item
        self.teasers[item["id"]] = (teaser or "")[:500]   # local working note for the editor; never published
        self.new.append(item); return item
    def save(self):
        self.data["items"].sort(key=lambda i: i["published"], reverse=True)
        self.data["updated"] = NOW.isoformat(timespec="seconds")
        write_json(path("data", "items.json"), self.data); write_json(path("state", "teasers.json"), self.teasers)

# ---------------------------------------------------------------- source readers
def bing_target(link):
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(link).query)
    return (q.get("url") or [link])[0]

def read_feed(http, store, s, cutoff):
    urls = [s["feed"].format(q=urllib.parse.quote_plus(q)) for q in s["queries"]] if s["type"] == "search" else [s["feed"]]
    ok = entries = 0; err = None
    for u in urls:
        if not http.allowed(u): err = "blocked by robots.txt"; continue
        try:
            r = http.get(u)
            if r.status_code == 304: ok += 1; continue
            if r.status_code != 200: err = f"HTTP {r.status_code}"; continue
            feed = feedparser.parse(r.content); ok += 1; entries += len(feed.entries)
            for e in feed.entries:
                link = e.get("link") or ""
                if s["type"] == "search": link = bing_target(link)
                title = plain(e.get("title"))
                teaser = plain(e.get("summary") or e.get("description") or "")
                author = plain(e.get("author") or e.get("news_source") or (e.get("source") or {}).get("title") or "")
                if s["type"] == "search" and not author: author = urllib.parse.urlsplit(link).netloc.removeprefix("www.")
                extra = {}
                if s.get("kind") in ("release", "tag"):
                    extra = {"project": s.get("project")}
                if s.get("platform") == "mastodon" and not title:
                    title = teaser[:110] + ("…" if len(teaser) > 110 else "")
                store.add(url=link, title=title, teaser=teaser, published=entry_date(e), source=s, author=author,
                          mode=s.get("filter", "nexa"), cutoff=cutoff, extra=extra)
        except Exception as ex:
            err = f"{type(ex).__name__}: {ex}"[:200]; say("  error", s["id"], u, err)
    return {"ok": ok > 0, "requests": len(urls), "ok_requests": ok, "entries": entries, "error": err}

def read_sitemap(http, store, s, cutoff, seen):
    if not http.allowed(s["feed"]): return {"ok": False, "requests": 1, "ok_requests": 0, "entries": 0, "error": "blocked by robots.txt"}
    r = http.get(s["feed"], conditional=False)
    if r.status_code != 200: return {"ok": False, "requests": 1, "ok_requests": 0, "entries": 0, "error": f"HTTP {r.status_code}"}
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)
    skip = set(s.get("exclude_paths", []))
    pages = [u for u in locs if (urllib.parse.urlsplit(u).path.rstrip("/") or "/") not in skip]
    fetched = 0; err = None
    for u in pages:
        if u not in seen:
            if fetched >= s.get("max_new_per_run", 30): continue
            if not http.allowed(u): seen[u] = {"skip": "robots"}; continue
            try:
                t, d, a, when = page_meta(http, u); fetched += 1
                seen[u] = {"title": t, "teaser": d, "author": a, "date": when.isoformat() if when else None}
            except Exception as ex:
                err = f"{type(ex).__name__}: {ex}"[:200]; continue
        m = seen[u]
        if m.get("title"):
            when = dt.datetime.fromisoformat(m["date"]) if m.get("date") else None
            title = re.sub(r"^NEXA:\s*", "", m["title"]) if m["title"].startswith("NEXA:") else m["title"]
            store.add(url=u, title=title, teaser=m.get("teaser", ""), published=when, source=s, author=m.get("author") or "Nexa",
                      mode=s.get("filter", "all"), cutoff=cutoff)
    return {"ok": True, "requests": 1 + fetched, "ok_requests": 1 + fetched, "entries": len(pages), "error": err}

def _json(http, url, headers=None):
    if not http.allowed(url): raise PermissionError("blocked by robots.txt")
    r = http.get(url, conditional=False); r.raise_for_status(); return r.json()

def read_hn(http, store, s, cutoff):
    """Hacker News via the public Algolia API (hn.algolia.com, no robots.txt restrictions, documented public API)."""
    ok = entries = 0; err = None
    for q in s["queries"]:
        u = "https://hn.algolia.com/api/v1/search_by_date?" + urllib.parse.urlencode({"query": q, "tags": "(story,comment)", "hitsPerPage": 50,
                                                                                    "numericFilters": f"created_at_i>{int(cutoff.timestamp())}"})
        try: d = _json(http, u); ok += 1
        except Exception as ex: err = f"{type(ex).__name__}: {ex}"[:200]; continue
        for h in d.get("hits", []):
            entries += 1
            hn = f"https://news.ycombinator.com/item?id={h['objectID']}"
            if h.get("comment_text"):
                title = "Comment on: " + (h.get("story_title") or "Hacker News thread"); teaser = plain(h["comment_text"])
            else:
                title = h.get("title") or ""; teaser = plain(h.get("story_text") or "") + " " + (h.get("url") or "")
            when = dt.datetime.fromtimestamp(h["created_at_i"], UTC)
            store.add(url=hn, title=title, teaser=teaser, published=when, source=s, author=h.get("author") or "", kind="thread",
                      mode=s.get("filter", "strict"), cutoff=cutoff, extra={"link_out": h.get("url")} if h.get("url") else None)
    return {"ok": ok > 0, "requests": len(s["queries"]), "ok_requests": ok, "entries": entries, "error": err}

def read_github(http, store, s, cutoff):
    """GitHub repository search via the public REST API, unauthenticated (10 requests/minute). Repos are dated by creation."""
    ok = entries = 0; err = None
    me = {r.lower() for r in s.get("exclude_repos", [])}
    for q in s["queries"]:
        u = "https://api.github.com/search/repositories?" + urllib.parse.urlencode({"q": q, "sort": "updated", "per_page": 50})
        try: d = _json(http, u); ok += 1
        except Exception as ex: err = f"{type(ex).__name__}: {ex}"[:200]; continue
        for r in d.get("items", []):
            entries += 1
            if r["full_name"].lower() in me or r.get("fork"): continue
            desc = r.get("description") or ""
            when = dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
            item = store.add(url=r["html_url"], title=f'{r["full_name"]}: {desc}'[:200] if desc else r["full_name"], teaser=desc + " " + " ".join(r.get("topics") or []),
                             published=when, source=s, author=r["owner"]["login"], kind="repo", mode=s.get("filter", "strict"), cutoff=cutoff)
            if item and re.search(r"\bofficial\b", desc, re.I):
                item["flags"].append("claims-official")   # third-party repo calling itself official: possible impersonation or malware
    return {"ok": ok > 0, "requests": len(s["queries"]), "ok_requests": ok, "entries": entries, "error": err}

def read_youtube_api(http, store, s, cutoff):
    """Third-party videos via the official YouTube Data API v3 search. Needs YOUTUBE_API_KEY in the environment.
    No YouTube pages are fetched. Thumbnails are copied to data/thumbs/ (served from our own site) when ytimg.com allows it."""
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key: return {"ok": False, "requests": 0, "ok_requests": 0, "entries": 0, "error": "YOUTUBE_API_KEY is not set"}
    ok = entries = 0; err = None
    skip = {c.lower() for c in s.get("exclude_channel_ids", [])}
    for q in s["queries"]:
        params = {"part": "snippet", "type": "video", "q": q, "order": "date", "maxResults": 25, "relevanceLanguage": "en",
                  "publishedAfter": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"), "key": key}
        try:
            r = requests.get("https://www.googleapis.com/youtube/v3/search", params=params, headers={"User-Agent": AGENT}, timeout=30)
            r.raise_for_status(); d = r.json(); ok += 1
        except Exception as ex:
            err = f"{type(ex).__name__}"[:200]; continue   # never log the URL: it contains the key
        for v in d.get("items", []):
            entries += 1; sn = v["snippet"]; vid = v["id"].get("videoId")
            if not vid or sn.get("channelId", "").lower() in skip: continue
            when = dt.datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
            item = store.add(url=f"https://www.youtube.com/watch?v={vid}", title=html_unescape(sn.get("title", "")), teaser=html_unescape(sn.get("description", "")),
                             published=when, source=s, author=sn.get("channelTitle", ""), kind="video", mode=s.get("filter", "strict"), cutoff=cutoff)
            if item: save_thumb(http, item, (sn.get("thumbnails") or {}).get("medium", {}).get("url"))
    return {"ok": ok > 0, "requests": len(s["queries"]), "ok_requests": ok, "entries": entries, "error": err}

def html_unescape(t):
    import html as _h; return _h.unescape(t or "")
def save_thumb(http, item, url):
    if not url or not http.allowed(url): return
    try:
        r = http.get(url, conditional=False)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/") and len(r.content) < 300_000:
            os.makedirs(path("data", "thumbs"), exist_ok=True)
            with open(path("data", "thumbs", item["id"] + ".jpg"), "wb") as f: f.write(r.content)
            item["thumb"] = f"thumbs/{item['id']}.jpg"
    except requests.RequestException: pass

READERS = {"hn": read_hn, "github": read_github, "youtube-api": read_youtube_api}

# ---------------------------------------------------------------- manual add
X_URL = re.compile(r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/(\w{1,15})/status/(\d+)")
def manual_add(http, store, a):
    url = a.add.strip()
    host = urllib.parse.urlsplit(url).netloc.lower()
    if not url.startswith("https://"): sys.exit("--add needs a full https:// URL")
    platform = a.platform or platform_for(url)
    title, teaser, author, when = a.title or "", a.note or "", a.author or "", None
    if a.date: when = dt.datetime.fromisoformat(a.date).replace(hour=12, tzinfo=UTC)
    xm = X_URL.match(url)
    if platform == "x":
        if not xm: sys.exit("X URLs must look like https://x.com/<account>/status/<id>")
        url = f"https://x.com/{xm[1]}/status/{xm[2]}"; author = author or "@" + xm[1]
    if any(h in host for h in NO_FETCH_HOSTS):
        # never fetched: X has no free API and scraping breaks its terms; Reddit/YouTube robots.txt disallow bots
        if not (title and when): sys.exit(f"{host} is never fetched. Give --title (first line, our wording is fine) and --date YYYY-MM-DD.")
    else:
        if not a.no_fetch and not http.allowed(url):
            sys.exit("robots.txt does not allow fetching this page. Give --title and --date and add --no-fetch.")
        if not a.no_fetch:
            t, d, au, w = page_meta(http, url)
            title = title or t; teaser = teaser or d; author = author or au; when = when or w
        if not title: sys.exit("no title found on the page; give --title")
        if not when: sys.exit("no date found on the page; give --date YYYY-MM-DD")
    src = {"id": "manual", "name": a.source_name or {"x": "X (added by hand)", "reddit": "Reddit (added by hand)", "youtube": "YouTube (added by hand)"}.get(platform, "Added by hand"),
           "platform": platform, "category": a.category or domain_category(url, "independent")}
    if platform == "x" and not a.category:
        src["category"] = "official" if xm and xm[1].lower() in {h.lower().lstrip("@") for h in CONF.get("official_x_accounts", [])} else "independent"
    item = store.add(url=url, title=title, teaser=teaser, published=when, source=src, author=author, manual=True,
                     kind={"x": "x-post", "youtube": "video", "reddit": "thread"}.get(platform, "article"))
    say(("ADDED " + item["id"] + ": ") if item else "ALREADY KNOWN: ", title, f"({when.date()}, {platform}, {src['category']})")

# ---------------------------------------------------------------- queue for the editor
def write_queue(store):
    q = {"_how_to": ("Editor: for each item, write a 1-2 sentence summary in your own words (never copied text) and add it to "
                     "queue/approved.json under 'approve' with the item id. Reject off-topic, price talk, shilling and spam under 'reject'. "
                     "Items with flags need \"flags_checked\": true to be published. Then run ./build.sh."),
         "updated": NOW.isoformat(timespec="seconds"), "pending": []}
    for i in store.data["items"]:
        if i["status"] != "pending": continue
        q["pending"].append({"id": i["id"], "title": i["title"], "author": i.get("author"), "platform": i["platform"], "category": i["category"],
                             "source": i["source_name"], "url": i["url"], "published": i["published"], "flags": i["flags"], "match": i.get("match"),
                             "teaser_local_only": store.teasers.get(i["id"], "")})
    write_json(path("queue", "review.json"), q)
    return q

def main():
    ap = argparse.ArgumentParser(description="Fetch Nexa news into the editor queue")
    ap.add_argument("--days", type=int, default=14, help="look-back window (default 14)")
    ap.add_argument("--only", help="comma separated source ids")
    ap.add_argument("--add", metavar="URL", help="add one item by hand (researcher)")
    ap.add_argument("--title"); ap.add_argument("--date", help="YYYY-MM-DD"); ap.add_argument("--author")
    ap.add_argument("--platform", help="x, reddit, youtube, medium, news, blog, forum, podcast, web ...")
    ap.add_argument("--category", choices=["official", "independent"]); ap.add_argument("--source-name")
    ap.add_argument("--note", help="local-only note for the editor (not published)")
    ap.add_argument("--refresh", action="store_true", help="ignore the ETag cache (re-read feeds that did not change)")
    ap.add_argument("--no-fetch", action="store_true", help="with --add: do not fetch the page, use the given --title/--date")
    a = ap.parse_args()
    http = Polite(); store = Store()
    if a.refresh: http.cache = {}
    if a.add:
        manual_add(http, store, a)
    else:
        cutoff = NOW - dt.timedelta(days=a.days)
        health = read_json(path("state", "source_status.json"), {})
        seen = read_json(path("state", "pages_seen.json"), {})
        only = set(a.only.split(",")) if a.only else None
        for s in CONF["sources"]:
            if not s.get("enabled") or (only and s["id"] not in only): continue
            before = len(store.new)
            cutoff = NOW - dt.timedelta(days=max(a.days, s.get("lookback_days", 0)))
            if s["type"] == "sitemap": res = read_sitemap(http, store, s, cutoff, seen)
            elif s["type"] in READERS: res = READERS[s["type"]](http, store, s, cutoff)
            else: res = read_feed(http, store, s, cutoff)
            res.update(checked=NOW.isoformat(timespec="seconds"), new=len(store.new) - before)
            health[s["id"]] = res
            say(f"{s['id']:<20} ok={res['ok_requests']}/{res['requests']} entries={res['entries']} new={res['new']} error={res['error']}")
        write_json(path("state", "source_status.json"), health); write_json(path("state", "pages_seen.json"), seen)
        say("skipped:", json.dumps(store.skipped))
    http.save(); store.save(); q = write_queue(store)
    flagged = sum(1 for i in store.new if i["flags"])
    say(f"DONE: {len(store.new)} new ({flagged} flagged), {len(store.data['items'])} total, {len(q['pending'])} pending in queue/review.json")

if __name__ == "__main__":
    main()
