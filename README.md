# nowplaying

MPRIS to Telegram bridge. Watches a media player over DBus (matched by MPRIS
Identity, resilient to bus name changes) and mirrors the current track into the
Telegram profile: bio line plus a custom emoji status while music is playing.

## Behavior

- Bio format: `♪ Artist — Title | <base_bio>`, trimmed to the account limit
  (counted in UTF-16 code units, the way Telegram counts it).
- Track changes are throttled (`min_interval`, default 45 s) and deduplicated
  to stay clear of Telegram flood limits; `FLOOD_WAIT` is honored and extends
  the cooldown instead of blocking the loop.
- Pause or player exit longer than `pause_grace` seconds restores the base bio
  and clears the emoji status.

## Setup

1. `python -m venv .venv && .venv/bin/pip install -r requirements.txt`
2. `cp config.example.json config.json`, fill `api_id` / `api_hash` (from
   my.telegram.org) and `phone`.
3. Authorize the session: `.venv/bin/python login.py`.
4. Pick the emoji status: `.venv/bin/python emoji.py` (see below).
5. `cp nowplaying.service ~/.config/systemd/user/` and
   `systemctl --user enable --now nowplaying.service`. The unit assumes the
   checkout lives in `~/nowplaying`.

`config.json` and `*.session` are gitignored — the session file is full access
to the account, never commit or share it.

## Emoji status

`emoji.py` resolves a custom emoji `document_id` into `config.json`. Four modes:

| Command | What it does |
| --- | --- |
| `emoji.py --id 5382196073469540426` | write a known id (e.g. from @emojiinfobot) |
| `emoji.py --saved` | read the newest message in Saved Messages |
| `emoji.py --find` | search the emoji catalogue by emoticon |
| `emoji.py --default` | pick from the account's default status set |

Without arguments it tries saved → find → default. `--emoji 🎵 🎧` overrides the
emoticons used for search. A custom emoji status requires Telegram Premium;
without it, set `"emoji_status": false` in the config.
