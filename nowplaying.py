#!/usr/bin/env python3
"""Now-playing bridge: MPRIS -> Telegram bio + emoji status."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from dbus_next import BusType, Message, MessageType
from dbus_next.aio import MessageBus
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.account import (
    UpdateEmojiStatusRequest,
    UpdateProfileRequest,
)
from telethon.tl.types import EmojiStatus, EmojiStatusEmpty

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
SESSION = str(ROOT / "nowplaying")

log = logging.getLogger("nowplaying")

MPRIS_PREFIX = "org.mpris.MediaPlayer2."
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
ROOT_IFACE = "org.mpris.MediaPlayer2"
OBJ_PATH = "/org/mpris/MediaPlayer2"


@dataclass(frozen=True)
class Track:
    artist: str
    title: str

    def __bool__(self) -> bool:
        return bool(self.artist or self.title)


def load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def u16len(text: str) -> int:
    """Length in UTF-16 code units -- this is how Telegram counts limits."""
    return len(text.encode("utf-16-le")) // 2


def u16trim(text: str, budget: int) -> str:
    """Trim to at most `budget` UTF-16 code units without splitting a surrogate pair."""
    if budget <= 0:
        return ""
    if u16len(text) <= budget:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if u16len(text[:mid]) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo]


def render_bio(track: Track, cfg: dict) -> str:
    limit = int(cfg.get("bio_limit", 140))
    base = cfg.get("base_bio", "")
    prefix = cfg.get("prefix", "♪ ")
    tail = f" | {base}" if base else ""
    budget = limit - u16len(prefix) - u16len(tail)
    if budget < 8:
        return u16trim(base, limit)

    if track.artist and track.title:
        name = f"{track.artist} — {track.title}"
    else:
        name = track.title or track.artist
    if u16len(name) > budget:
        name = u16trim(name, max(1, budget - 1)).rstrip() + "…"
    return u16trim(f"{prefix}{name}{tail}", limit)


class MprisWatcher:
    """Follows one MPRIS player selected by its Identity string."""

    def __init__(self, identity: str, on_change) -> None:
        self._identity = identity
        self._on_change = on_change
        self._bus: MessageBus | None = None
        self._owner: str | None = None
        self._name: str | None = None
        self._tasks: set[asyncio.Task] = set()

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def start(self) -> None:
        self._bus = await MessageBus(bus_type=BusType.SESSION).connect()
        self._bus.add_message_handler(self._handle)
        await self._call("org.freedesktop.DBus", "/org/freedesktop/DBus",
                         "org.freedesktop.DBus", "AddMatch", "s",
                         ["type='signal',interface='org.freedesktop.DBus.Properties',"
                          f"member='PropertiesChanged',path='{OBJ_PATH}'"])
        await self._call("org.freedesktop.DBus", "/org/freedesktop/DBus",
                         "org.freedesktop.DBus", "AddMatch", "s",
                         ["type='signal',interface='org.freedesktop.DBus',"
                          "member='NameOwnerChanged'"])
        await self._rescan()

    async def _call(self, dest, path, iface, member, signature, body):
        assert self._bus is not None
        reply = await self._bus.call(Message(destination=dest, path=path, interface=iface,
                                             member=member, signature=signature, body=body))
        if reply is None:
            return None
        if reply.message_type is MessageType.ERROR:
            raise RuntimeError(reply.body[0] if reply.body else reply.error_name)
        return reply.body[0] if reply.body else None

    async def _get_prop(self, dest: str, iface: str, prop: str):
        variant = await self._call(dest, OBJ_PATH, "org.freedesktop.DBus.Properties",
                                   "Get", "ss", [iface, prop])
        return variant.value if variant is not None else None

    async def _rescan(self) -> None:
        names = await self._call("org.freedesktop.DBus", "/org/freedesktop/DBus",
                                 "org.freedesktop.DBus", "ListNames", "", [])
        for name in names or []:
            if not name.startswith(MPRIS_PREFIX):
                continue
            try:
                if await self._get_prop(name, ROOT_IFACE, "Identity") == self._identity:
                    await self._attach(name)
                    return
            except Exception:
                continue
        if self._name is not None:
            log.info("player gone")
            self._name = self._owner = None
            await self._on_change(None, Track("", ""))

    async def _attach(self, name: str) -> None:
        if name == self._name:
            return
        self._name = name
        self._owner = await self._call("org.freedesktop.DBus", "/org/freedesktop/DBus",
                                       "org.freedesktop.DBus", "GetNameOwner", "s", [name])
        log.info("attached to %s (%s)", name, self._identity)
        await self._emit_current()

    async def _emit_current(self) -> None:
        assert self._name is not None
        status = await self._get_prop(self._name, PLAYER_IFACE, "PlaybackStatus")
        meta = await self._get_prop(self._name, PLAYER_IFACE, "Metadata") or {}
        await self._on_change(status, self._parse(meta))

    @staticmethod
    def _parse(meta: dict) -> Track:
        def unwrap(key: str, join: bool = False) -> str:
            value = meta.get(key)
            value = getattr(value, "value", value)
            if isinstance(value, list):
                parts = [str(v).strip() for v in value if str(v).strip()]
                value = ", ".join(parts) if join else (parts[0] if parts else "")
            return str(value or "").strip()

        return Track(artist=unwrap("xesam:artist", join=True), title=unwrap("xesam:title"))

    def _handle(self, msg: Message) -> None:
        if msg.message_type is not MessageType.SIGNAL:
            return
        if msg.member == "NameOwnerChanged" and msg.body[0].startswith(MPRIS_PREFIX):
            name, _old, new = msg.body[0], msg.body[1], msg.body[2]
            if not new and name == self._name:
                self._name = self._owner = None
                self._spawn(self._on_change(None, Track("", "")))
            elif new:
                self._spawn(self._rescan())
            return
        if msg.member == "PropertiesChanged" and msg.sender == self._owner:
            iface, changed, _ = msg.body
            if iface != PLAYER_IFACE:
                return
            status = changed.get("PlaybackStatus")
            meta = changed.get("Metadata")
            self._spawn(self._on_props(
                getattr(status, "value", None),
                self._parse(getattr(meta, "value", {}) or {}) if meta is not None else None,
            ))

    async def _on_props(self, status: str | None, track: Track | None) -> None:
        if status is None or track is None:
            if self._name is None:
                return
            await self._emit_current()
            return
        await self._on_change(status, track)


class Publisher:
    """Throttled writer of bio + emoji status."""

    def __init__(self, client: TelegramClient, cfg: dict) -> None:
        self._client = client
        self._cfg = cfg
        self._interval = float(cfg.get("min_interval", 45))
        self._grace = float(cfg.get("pause_grace", 20))
        self._desired: Track | None = None
        self._published: Track | None = None
        self._emoji_on = False
        self._wake = asyncio.Event()
        self._clear_at: float | None = None

    def set_playing(self, track: Track) -> None:
        self._clear_at = None
        if track != self._desired:
            self._desired = track
            self._wake.set()

    def set_idle(self) -> None:
        if self._desired is None and self._published is None:
            return
        loop = asyncio.get_running_loop()
        if self._clear_at is None:
            self._clear_at = loop.time() + self._grace
        self._wake.set()

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        next_allowed = 0.0
        while True:
            timeout = None
            now = loop.time()
            if self._clear_at is not None:
                timeout = max(0.0, self._clear_at - now)
            elif self._desired is not None and self._desired != self._published:
                timeout = max(0.0, next_allowed - now)
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

            now = loop.time()
            if self._clear_at is not None and now >= self._clear_at:
                self._clear_at = None
                self._desired = None
                if self._published is not None or self._emoji_on:
                    delay = await self._write(None)
                    next_allowed = loop.time() + (delay or self._interval)
                continue
            if self._clear_at is not None:
                continue
            if self._desired is None or self._desired == self._published:
                continue
            if now < next_allowed:
                continue
            delay = await self._write(self._desired)
            next_allowed = loop.time() + (delay or self._interval)

    async def _write(self, track: Track | None) -> float | None:
        """Push bio + emoji. Returns a suggested extra cooldown (seconds) or None."""
        retry: float | None = None
        bio = render_bio(track, self._cfg) if track else self._cfg.get("base_bio", "")
        try:
            await self._client(UpdateProfileRequest(about=bio))
            self._published = track
            log.info("bio -> %s", bio.replace("\n", " | "))
        except FloodWaitError as exc:
            log.warning("flood wait %ss on bio", exc.seconds)
            retry = exc.seconds + 1
        except Exception as exc:
            log.error("bio update failed: %s", exc)
            retry = self._interval

        emoji_retry = await self._write_emoji(track is not None)
        if emoji_retry is not None:
            retry = emoji_retry if retry is None else max(retry, emoji_retry)
        return retry

    async def _write_emoji(self, on: bool) -> float | None:
        if not self._cfg.get("emoji_status", True) or on == self._emoji_on:
            return None
        doc_id = self._cfg.get("emoji_document_id")
        if on and not doc_id:
            return None
        try:
            status = EmojiStatus(document_id=int(doc_id)) if on else EmojiStatusEmpty()
            await self._client(UpdateEmojiStatusRequest(emoji_status=status))
            self._emoji_on = on
            log.info("emoji status -> %s", "music" if on else "cleared")
        except FloodWaitError as exc:
            log.warning("flood wait %ss on emoji", exc.seconds)
            return exc.seconds + 1
        except Exception as exc:
            log.error("emoji status failed: %s", exc)
        return None


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    if not cfg.get("emoji_document_id") and cfg.get("emoji_status", True):
        log.info("no emoji_document_id in config; run emoji.py to pick one")
    client = TelegramClient(SESSION, int(cfg["api_id"]), cfg["api_hash"])
    await client.connect()
    if not await client.is_user_authorized():
        log.error("session is not authorized; run login.py first")
        return 1

    publisher = Publisher(client, cfg)

    async def on_change(status: str | None, track: Track) -> None:
        if status == "Playing" and track:
            publisher.set_playing(track)
        else:
            publisher.set_idle()

    identity = cfg.get("player_identity", "YandexMusic")
    watcher = MprisWatcher(identity, on_change)
    await watcher.start()
    log.info("watching %s", identity)
    await publisher.run()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
