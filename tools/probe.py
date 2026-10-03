import sys, requests, feedparser, urllib.robotparser, urllib.parse
UA="NexaNews/1.0 (+https://jqrgen.github.io/nexa-news/about/; news aggregator bot)"
rp={}
def ok(u):
    p=urllib.parse.urlparse(u); b=f"{p.scheme}://{p.netloc}"
    if b not in rp:
        r=urllib.robotparser.RobotFileParser()
        try:
            t=requests.get(b+"/robots.txt",headers={"User-Agent":UA},timeout=15); r.parse(t.text.splitlines() if t.status_code==200 else [])
        except Exception: r.parse([])
        rp[b]=r
    return rp[b].can_fetch(UA,u)
for u in sys.argv[1:]:
    if not ok(u): print("ROBOTS-NO", u); continue
    try:
        r=requests.get(u,headers={"User-Agent":UA},timeout=20)
        f=feedparser.parse(r.content)
        print(r.status_code, len(f.entries), u, "|", (f.entries[0].get("title","")[:70]+" "+str(f.entries[0].get("published", f.entries[0].get("updated","")))) if f.entries else r.headers.get("content-type"))
    except Exception as e: print("ERR",u,e)
