"""Fetch my saved posts and comments from Reddit's private RSS feed.

Reddit gives each account private feed links at https://www.reddit.com/prefs/feeds,
authenticated by a token in the URL. Reddit has announced that RSS support ends
on 2026-11-13, so this is a one-off rescue of saved-item content.

Usage:
    uv run rss_saved.py                 # fetch everything the feed will give
    uv run rss_saved.py --export DIR    # also match against a Reddit data export

Put the feed URL in .env as REDDIT_SAVED_RSS. The token in it grants read access
to your saved items, so keep it out of chat, commits and logs; this script never
prints it.

Output: exports/saved_rss.json (gitignored).
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from xml.etree.ElementTree import ParseError

import defusedxml.ElementTree as ET
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
ATOM = "{http://www.w3.org/2005/Atom}"
PAGE_SIZE = 100
MAX_PAGES = 20
PAUSE_S = 3
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def clean(s) -> str:
    return _CONTROL.sub(" ", str(s))


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br", "li", "div", "blockquote"):
            self.parts.append("\n")


def html_to_text(s: str) -> str:
    p = _Text()
    p.feed(html.unescape(s or ""))
    text = "".join(p.parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # RSS bodies end with "submitted by /u/x [link] [comments]"; drop that footer.
    text = re.sub(r"\s*submitted by\s+/u/\S+.*$", "", text, flags=re.S)
    return text.strip()


def page_url(base: str, after: str | None) -> str:
    parts = urllib.parse.urlsplit(base)
    q = dict(urllib.parse.parse_qsl(parts.query))
    q["limit"] = str(PAGE_SIZE)
    if after:
        q["after"] = after
    else:
        q.pop("after", None)
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(q)))


def fetch(url: str, user: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": f"script:personal-reddit-reader:0.1 (by /u/{user})",
        "Accept": "application/atom+xml",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    out = []
    for e in root.findall(f"{ATOM}entry"):
        fullname = (e.findtext(f"{ATOM}id") or "").strip()  # t3_abc (post) / t1_abc (comment)
        link = e.find(f"{ATOM}link")
        cat = e.find(f"{ATOM}category")
        body_html = e.findtext(f"{ATOM}content") or ""
        out.append({
            "fullname": fullname,
            "id": fullname.split("_", 1)[-1],
            "kind": {"t1": "comment", "t3": "post"}.get(fullname[:2], "other"),
            "title": e.findtext(f"{ATOM}title") or "",
            "author": (e.findtext(f"{ATOM}author/{ATOM}name") or "").removeprefix("/u/"),
            "subreddit": cat.get("term") if cat is not None else "",
            "url": link.get("href") if link is not None else "",
            "updated": e.findtext(f"{ATOM}updated") or e.findtext(f"{ATOM}published") or "",
            "text": html_to_text(body_html),
            "html": body_html,
        })
    return out


def load_export_ids(export_dir: str) -> dict[str, str]:
    ids = {}
    for name, kind in (("saved_posts.csv", "post"), ("saved_comments.csv", "comment")):
        path = os.path.join(export_dir, name)
        if os.path.exists(path):
            with open(path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    ids[row["id"]] = kind
    return ids


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", help="folder of an unzipped Reddit data export, to report coverage")
    ap.add_argument("--out", default=os.path.join(HERE, "exports", "saved_rss.json"))
    a = ap.parse_args()

    load_dotenv(os.path.join(HERE, ".env"))
    base = os.environ.get("REDDIT_SAVED_RSS", "").strip()
    if not base:
        sys.exit("Missing REDDIT_SAVED_RSS in .env (copy the 'saved' feed link from reddit.com/prefs/feeds)")
    user = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(base).query)).get("user", "unknown")

    items: dict[str, dict] = {}
    after = None
    for page in range(1, MAX_PAGES + 1):
        try:
            batch = parse(fetch(page_url(base, after), user))
        except urllib.error.HTTPError as e:
            sys.exit(f"Reddit returned HTTP {e.code} on page {page} (feed may be retired or the token wrong)")
        except ParseError:
            sys.exit(f"Page {page} was not a valid feed (Reddit may have returned an error page)")
        new = [b for b in batch if b["fullname"] and b["fullname"] not in items]
        for b in new:
            items[b["fullname"]] = b
        print(f"page {page}: {len(batch)} entries, {len(new)} new, {len(items)} total")
        if len(batch) < PAGE_SIZE or not new:
            break
        after = batch[-1]["fullname"]
        time.sleep(PAUSE_S)

    rows = list(items.values())
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    posts = sum(r["kind"] == "post" for r in rows)
    print(f"\nSaved {len(rows)} items ({posts} posts, {len(rows) - posts} comments) to {clean(a.out)}")

    if a.export:
        ids = load_export_ids(a.export)
        got = {r["id"] for r in rows}
        matched = got & set(ids)
        print(f"Export lists {len(ids)} saved items; feed returned content for {len(matched)} of them"
              f" ({len(got - set(ids))} feed items not in the export)")


if __name__ == "__main__":
    main()
