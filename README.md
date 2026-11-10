# reddit-api

Read-only access to my own Reddit account through the official API (PRAW, script-app password grant).

## Setup

1. Go to https://www.reddit.com/prefs/apps, click **create another app**, choose **script**,
   set the redirect URI to `http://localhost:8080`.
2. `cp .env.example .env` and fill in the client ID (the string under "personal use script"),
   secret, username and password.
3. `uv run reddit.py whoami`

Two-factor auth: the password grant does not work with 2FA turned on unless the password is
sent as `password:123456` with a live TOTP code, which expires. If 2FA is on, switch to the
OAuth refresh-token flow instead.

## Commands

```
uv run reddit.py whoami
uv run reddit.py saved --limit 50
uv run reddit.py comments --limit 0 --json > exports/comments.json
uv run reddit.py posts | upvoted | inbox | subs
```

## Saved items via private RSS (no API key)

Reddit stopped issuing new API keys in November 2025 and has announced that RSS ends on
2026-11-13. Until then, the private "saved" feed at https://www.reddit.com/prefs/feeds returns the
title and text of saved posts and comments. Put that link in `.env` as `REDDIT_SAVED_RSS`, then:

```
uv run rss_saved.py --export path/to/unzipped/reddit-export
```

Results go to `exports/saved_rss.json` (gitignored).

Listings are capped by Reddit at roughly 1000 items. For full history, use the data export at
https://www.reddit.com/settings/data-request.
