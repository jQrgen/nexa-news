#!/usr/bin/env python3
"""Editor helper for queue/approved.json (the only file that can publish anything).

  .venv/bin/python tools/editor.py list [--flagged] [--all]      pending items (id, flags, platform, date, title, url)
  .venv/bin/python tools/editor.py show ID                       one item, with the local-only teaser
  .venv/bin/python tools/editor.py approve ID "Summary in your own words." [--flags-checked] [--title "English title"] [--category official|independent]
       [--sponsored] [--outlet-note "who runs the outlet"] [--correction "what changed"]
  .venv/bin/python tools/editor.py reject ID "reason"
  .venv/bin/python tools/editor.py unpublish ID                   remove an approval (unpublished at the next build)
"""
import argparse, datetime as dt, json, os, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def p(*a): return os.path.join(HERE, *a)
def rd(f, d):
    try: return json.load(open(f, encoding="utf-8"))
    except FileNotFoundError: return d
def wr(f, d):
    with open(f + ".tmp", "w", encoding="utf-8") as h: json.dump(d, h, ensure_ascii=False, indent=1); h.write("\n")
    os.replace(f + ".tmp", f)
items = {i["id"]: i for i in rd(p("data", "items.json"), {"items": []})["items"]}
ap = rd(p("queue", "approved.json"), {"approve": [], "reject": []})
ap.setdefault("_how_to", "Written by the editor (or tools/editor.py). approve: id + summary in your own words (1-2 sentences, never copied); "
              "flagged items also need flags_checked: true. reject: id + reason. Then ./build.sh.")
ap.setdefault("approve", []); ap.setdefault("reject", [])
a = argparse.ArgumentParser(); s = a.add_subparsers(dest="cmd", required=True)
l = s.add_parser("list"); l.add_argument("--flagged", action="store_true"); l.add_argument("--all", action="store_true")
s.add_parser("show").add_argument("id")
x = s.add_parser("approve"); x.add_argument("id"); x.add_argument("summary"); x.add_argument("--flags-checked", action="store_true")
x.add_argument("--title"); x.add_argument("--category", choices=["official", "independent"])
x.add_argument("--sponsored", action="store_true", help="publisher marks it as sponsored; shows a Sponsored label")
x.add_argument("--outlet-note", help="who runs the outlet (independent coverage), e.g. 'crypto news site, Brazil'")
x.add_argument("--correction", help="correction note; shown as 'Corrected <date>: <note>'")
r = s.add_parser("reject"); r.add_argument("id"); r.add_argument("reason")
s.add_parser("unpublish").add_argument("id")
o = a.parse_args()
decided = {e["id"] for e in ap["approve"]} | {e["id"] for e in ap["reject"]}
if o.cmd == "list":
    for i in sorted(items.values(), key=lambda i: i["published"], reverse=True):
        if not o.all and (i["status"] != "pending" or i["id"] in decided): continue
        if o.flagged and not i.get("flags"): continue
        print(f'{i["id"]}  {i["status"][:4]}  {i["published"][:10]}  {i["platform"]:<8} {i["category"][:3]}  {",".join(i.get("flags", [])) or "-":<22} {i["title"][:70]}\n{"":14}{i["url"]}')
    sys.exit()
if o.id not in items: sys.exit(f"unknown id {o.id}")
it = items[o.id]
if o.cmd == "show":
    t = rd(p("state", "teasers.json"), {}).get(o.id, "")
    print(json.dumps(it, ensure_ascii=False, indent=1)); print("teaser (local only, do not copy):", t); sys.exit()
ap["approve"] = [e for e in ap["approve"] if e["id"] != o.id]; ap["reject"] = [e for e in ap["reject"] if e["id"] != o.id]
today = dt.date.today().isoformat()
if o.cmd == "approve":
    if it.get("flags") and not o.flags_checked: sys.exit(f"item has flags {it['flags']}: check them, then add --flags-checked (or reject it)")
    e = {"id": o.id, "url": it["url"], "summary": o.summary.strip(), "approved_by": "Nexa News editor", "approved_at": today}
    if o.flags_checked: e["flags_checked"] = True
    if o.title: e["title"] = o.title
    if o.category: e["category"] = o.category
    if o.sponsored: e["sponsored"] = True
    if o.outlet_note: e["outlet_note"] = o.outlet_note
    if o.correction: e["correction"] = {"date": today, "note": o.correction}
    ap["approve"].append(e)
elif o.cmd == "reject":
    ap["reject"].append({"id": o.id, "url": it["url"], "reason": o.reason, "rejected_at": today})
wr(p("queue", "approved.json"), ap); print(f"{o.cmd}: {o.id} {it['title'][:70]}")
