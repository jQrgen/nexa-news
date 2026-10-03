#!/usr/bin/env python3
"""Screenshots of the built site for QA, into shots/. Serves site/ locally on a free port.
  .venv/bin/python tools/screens.py
"""
import os, socket, subprocess, sys, time, urllib.parse
from playwright.sync_api import sync_playwright
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with socket.socket() as s: s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
# Serve site/ under /nexa-news/ (the GitHub Pages project path) to prove every link is relative.
import tempfile
root = tempfile.mkdtemp(prefix="nn-serve-"); os.symlink(os.path.join(HERE, "site"), os.path.join(root, "nexa-news"))
srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "-d", root],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1); base = f"http://127.0.0.1:{port}/nexa-news/"
SHOTS = [("", 1366, 900, "desktop-feed.png", True), ("releases/", 1366, 900, "desktop-releases.png", True),
         ("sources/", 1366, 900, "desktop-sources.png", True), ("about/", 1366, 900, "desktop-about.png", True), ("changelog/", 1366, 900, "desktop-changelog.png", False), ("changelog/", 390, 844, "mobile-changelog.png", False),
         ("", 390, 844, "mobile-feed.png", True), ("sources/", 390, 844, "mobile-sources.png", False), ("about/", 390, 844, "mobile-about.png", False),
         ("releases/", 390, 844, "mobile-releases.png", False),
         ("screen/", 1920, 1080, "screen-landscape-1920x1080.png", False), ("screen/", 1080, 1920, "screen-portrait-1080x1920.png", False),
         ("screen/?theme=light", 1920, 1080, "screen-landscape-light.png", False)]
out = os.path.join(HERE, "shots"); os.makedirs(out, exist_ok=True)
errors = []
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        for rel, w, h, name, full in SHOTS:
            pg = b.new_page(viewport={"width": w, "height": h})
            pg.on("console", lambda m, n=name: errors.append(f"{n}: console {m.type}: {m.text}") if m.type == "error" else None)
            pg.on("requestfailed", lambda r, n=name: errors.append(f"{n}: failed {r.url}"))
            pg.on("request", lambda r, n=name: errors.append(f"{n}: EXTERNAL request {r.url}") if not r.url.startswith(f"http://127.0.0.1:{port}/") and not r.url.startswith("data:") else None)
            resp = pg.goto(base + rel); pg.wait_for_timeout(1800)
            if resp.status != 200: errors.append(f"{name}: HTTP {resp.status}")
            over = pg.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
            if over: errors.append(f"{name}: horizontal overflow ({pg.evaluate('document.documentElement.scrollWidth')}px > {w}px)")
            pg.screenshot(path=os.path.join(out, name), full_page=full); pg.close(); print("shots/" + name)
        # follow every same-site link on every page and require HTTP 200 under /nexa-news/
        import urllib.request, re as _re
        todo, seen = [base], set()
        while todo:
            u = todo.pop()
            if u in seen: continue
            seen.add(u)
            try: body = urllib.request.urlopen(u).read().decode("utf-8", "replace")
            except Exception as ex: errors.append(f"crawl: {u} -> {ex}"); continue
            if not u.endswith((".html", "/")): continue
            for h in _re.findall(r'(?:href|src)="([^"#?]+)', body):
                if h.startswith(("http:", "https:", "data:", "mailto:")): continue
                if h.startswith("/"): errors.append(f"crawl: absolute path {h} on {u}"); continue
                todo.append(urllib.parse.urljoin(u, h))
        print(f"crawled {len(seen)} internal URLs under /nexa-news/")
        b.close()
finally:
    srv.terminate(); os.remove(os.path.join(root, "nexa-news")); os.rmdir(root)
print("\n".join(errors) if errors else "no console errors, failed or external requests, or horizontal overflow")
