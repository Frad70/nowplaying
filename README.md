# nowplaying

MPRIS to Telegram bridge. Watches a media player over DBus (matched by MPRIS
Identity, resilient to bus name changes) and mirrors the current track into the
Telegram profile: bio line plus a custom emoji status while music is playing.

## Behavior

- Bio format: `♪ Artist — Title | <base_bio>`, trimmed to the account limit.
- Track changes are throttled (`min_interval`, default 45 s) and deduplicated
  to stay clear of Telegram flood limits; `FLOOD_WAIT` is honored.
- Pause or player exit longer than `pause_grace` seconds restores the base bio
  and clears the emoji status.

## Setup

1. `python -m venv .venv && .venv/bin/pip install telethon dbus-next qrcode[pil]`
2. `cp config.example.json config.json`, fill `api_id` / `api_hash` (from
   my.telegram.org) and `phone`.
3. Authorize the session: `.venv/bin/python login.py` (code flow) or
   `qr_export_wait.py` (QR flow; the token can be accepted programmatically by
   an already-authorized session via `auth.AcceptLoginTokenRequest`).
4. `systemctl --user enable --now nowplaying.service` (adjust paths in the
   unit if the checkout lives elsewhere).

## Emoji status

`emoji_from_saved.py` reads the newest message in Saved Messages and stores its
custom emoji `document_id` into `config.json` — send the desired emoji to Saved
Messages and run the script. `emoji_find.py` searches by emoticon instead.
