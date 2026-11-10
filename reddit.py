"""Read-only access to my Reddit account.

Usage:
    uv run reddit.py whoami
    uv run reddit.py saved    [--limit N]
    uv run reddit.py comments [--limit N]
    uv run reddit.py posts    [--limit N]
    uv run reddit.py upvoted  [--limit N]
    uv run reddit.py inbox    [--limit N]
    uv run reddit.py subs

Add --json to any listing command for machine-readable output.
Nothing here posts, votes, replies or deletes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import praw
from dotenv import load_dotenv

REQUIRED = ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD"]


def client() -> praw.Reddit:
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)} (see .env.example)")
    user = os.environ["REDDIT_USERNAME"]
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        username=user,
        password=os.environ["REDDIT_PASSWORD"],
        user_agent=f"script:personal-reddit-reader:0.1 (by /u/{user})",
        check_for_async=False,
    )


def ts(utc: float) -> str:
    return datetime.fromtimestamp(utc, tz=timezone.utc).strftime("%Y-%m-%d")


def describe(item) -> dict:
    if isinstance(item, praw.models.Comment):
        return {
            "kind": "comment",
            "date": ts(item.created_utc),
            "subreddit": str(item.subreddit),
            "score": item.score,
            "text": item.body,
            "url": f"https://www.reddit.com{item.permalink}",
        }
    if isinstance(item, praw.models.Submission):
        return {
            "kind": "post",
            "date": ts(item.created_utc),
            "subreddit": str(item.subreddit),
            "score": item.score,
            "title": item.title,
            "text": item.selftext,
            "url": f"https://www.reddit.com{item.permalink}",
        }
    # inbox messages
    return {
        "kind": "message",
        "date": ts(item.created_utc),
        "from": str(item.author) if item.author else None,
        "subject": getattr(item, "subject", ""),
        "text": item.body,
    }


def show(items, as_json: bool) -> None:
    rows = [describe(i) for i in items]
    if as_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    for r in rows:
        head = r.get("title") or (r["text"][:100].replace("\n", " ") if r.get("text") else "")
        where = f"r/{r['subreddit']}" if "subreddit" in r else f"from {r.get('from')}"
        print(f"{r['date']}  [{r['kind']}] {where}  {head}")
        if "url" in r:
            print(f"            {r['url']}")
    print(f"\n{len(rows)} items")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["whoami", "saved", "comments", "posts", "upvoted", "inbox", "subs"])
    p.add_argument("--limit", type=int, default=25, help="max items (0 = as many as Reddit returns, ~1000)")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()

    r = client()
    me = r.user.me()
    limit = None if a.limit == 0 else a.limit

    if a.command == "whoami":
        print(f"u/{me.name}  karma: {me.link_karma} post / {me.comment_karma} comment  joined {ts(me.created_utc)}")
    elif a.command == "saved":
        show(me.saved(limit=limit), a.json)
    elif a.command == "comments":
        show(me.comments.new(limit=limit), a.json)
    elif a.command == "posts":
        show(me.submissions.new(limit=limit), a.json)
    elif a.command == "upvoted":
        show(me.upvoted(limit=limit), a.json)
    elif a.command == "inbox":
        show(r.inbox.all(limit=limit), a.json)
    elif a.command == "subs":
        names = sorted(str(s) for s in r.user.subreddits(limit=None))
        print(json.dumps(names, indent=2) if a.json else "\n".join(f"r/{n}" for n in names))
        if not a.json:
            print(f"\n{len(names)} subreddits")


if __name__ == "__main__":
    main()
