#!/usr/bin/env python3
"""Privacy check for the built site. Exits 1 if anything looks private.

Prints only the file, line and rule name, never the matched text itself.
Personal terms (health, finances ...) live in state/private_terms.json, which stays out of git.
If that file is missing, the check fails (fail closed).

  .venv/bin/python tools/privacy_check.py site [more folders ...]
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = re.compile(r"https?://[^\s\"'<>)]+")
# checked on the full text, including inside URLs
ANYWHERE = {
    "email address": re.compile(r"(?<![\w/])[\w.+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}(?:\.[A-Za-z]{2,})*"),
    "access token": re.compile(r"\b(?:glpat-[\w-]{10,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,}|xox[abprs]-[\w-]{10,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|nsec1[02-9ac-hj-np-z]{20,}|AIza[\w-]{30,})"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\b[5KL][1-9A-HJ-NP-Za-km-z]{50,51}\b"),
    "auth header": re.compile(r"\b(?:Bearer|Basic) [A-Za-z0-9+/=._-]{20,}"),
    "private path": re.compile(r"(?:/home/\w+|/workspace/|/Users/\w+|/root/|[A-Z]:\\\\Users\\\\|/etc/(?:passwd|shadow)|\.ssh/|\.env\b|agent-data)"),
    "seed phrase hint": re.compile(r"\b(?:seed phrase|recovery phrase|mnemonic)\s*[:=]", re.I),
}
# checked with URLs removed (long numbers in URLs are article or post ids)
OUTSIDE_URLS = {
    "phone number": re.compile(r"\+\d{2}[\s-]?\d{2,4}[\s-]?\d{2,4}[\s-]?\d{2,4}\b|(?<![\d.,:/-])\b[2-9]\d{7}\b(?![\d.,:])|\b\d{2} \d{2} \d{2} \d{2}\b"),
    "organisation number": re.compile(r"(?i)\borg(?:anisation|anization)?\.? ?(?:nr|no|number)\.?:? ?\d|(?<![\d.,:/-])\b\d{3} ?\d{3} ?\d{3}\b(?![\d.,:-])|\bMVA\b"),
    "national id number": re.compile(r"(?<![\d.,:/-])\b[0-3]\d[01]\d{3} ?\d{5}\b(?![\d.,:-])"),
    "bank account / IBAN / card": re.compile(r"\b\d{4}[ .]\d{2}[ .]\d{5}\b|\b[A-Z]{2}\d{2} ?(?:\d{4} ?){2,7}\d{1,4}\b|\b(?:\d{4}[ -]){3}\d{4}\b"),
}
terms_file = os.path.join(HERE, "state", "private_terms.json")
if not os.path.exists(terms_file):
    print("privacy check: FAILED, state/private_terms.json is missing (fail closed)", file=sys.stderr); sys.exit(1)
PERSONAL = {k: re.compile(v, re.I) for k, v in json.load(open(terms_file, encoding="utf-8")).items() if not k.startswith("_")}

hits = files = 0
for top in sys.argv[1:] or ["site"]:
    for dp, _, fs in os.walk(top):
        for f in fs:
            if not f.endswith((".html", ".json", ".js", ".css", ".txt", ".xml", ".md", ".svg")): continue
            files += 1; p = os.path.join(dp, f)
            for n, line in enumerate(open(p, encoding="utf-8", errors="replace"), 1):
                bare = URL.sub(" ", line)
                for rule, rx in ANYWHERE.items():
                    if rx.search(line): hits += 1; print(f"  {p}:{n}  {rule}", file=sys.stderr)
                for rule, rx in list(OUTSIDE_URLS.items()) + list(PERSONAL.items()):
                    if rx.search(bare): hits += 1; print(f"  {p}:{n}  {rule}", file=sys.stderr)
if hits:
    print(f"privacy check: FAILED, {hits} hit(s) in {files} files. Do not publish.", file=sys.stderr); sys.exit(1)
print(f"privacy check: OK ({files} files, {len(ANYWHERE) + len(OUTSIDE_URLS) + len(PERSONAL)} rules)")
