#!/usr/bin/env python3
"""Pick the custom emoji used as the Telegram status and store it in config.json.

Four ways to get a document_id:

  emoji.py --id 5382196073469540426   already know the id (e.g. from @emojiinfobot)
  emoji.py --saved                    take it from the newest message in Saved Messages
  emoji.py --find                     search the emoji catalogue by emoticon
  emoji.py --default                  pick from the account's default status set

Without arguments the modes are tried in order: saved -> find -> default.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.functions.account import GetDefaultEmojiStatusesRequest
from telethon.tl.functions.messages import (
    GetCustomEmojiDocumentsRequest,
    SearchCustomEmojiRequest,
)
from telethon.tl.types import MessageEntityCustomEmoji

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
SESSION = str(ROOT / "nowplaying")

DEFAULT_CANDIDATES = ["\U0001f3b5", "\U0001f3a7", "\U0001f3b6", "\U0001f3bc", "\U0001f3a4"]


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_document_id(doc_id: int) -> None:
    cfg = load_config()
    cfg["emoji_document_id"] = int(doc_id)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(CONFIG_PATH)
    print(f"saved emoji_document_id = {doc_id}")


async def from_saved(client: TelegramClient) -> int | None:
    """Send the emoji to Saved Messages, then run this."""
    messages = await client.get_messages("me", limit=1)
    if not messages:
        print("Saved Messages is empty")
        return None
    entities = messages[0].entities or []
    ids = [e.document_id for e in entities if isinstance(e, MessageEntityCustomEmoji)]
    if not ids:
        print("no custom emoji in the newest Saved message "
              "(a plain unicode emoji has no document_id)")
        return None
    return ids[0]


async def from_search(client: TelegramClient, candidates: list[str]) -> int | None:
    for emoticon in candidates:
        result = await client(SearchCustomEmojiRequest(emoticon=emoticon, hash=0))
        ids = getattr(result, "document_id", []) or []
        if not ids:
            continue
        docs = await client(GetCustomEmojiDocumentsRequest(document_id=ids[:5]))
        for doc in docs:
            alt = next((a.alt for a in doc.attributes if hasattr(a, "alt")), "?")
            print(f"candidate {emoticon} id={doc.id} alt={alt}")
        if docs:
            return docs[0].id
    print("nothing found for", " ".join(candidates))
    return None


async def from_defaults(client: TelegramClient, candidates: list[str]) -> int | None:
    result = await client(GetDefaultEmojiStatusesRequest(hash=0))
    ids = [s.document_id for s in getattr(result, "statuses", [])
           if getattr(s, "document_id", None)]
    if not ids:
        print("no default emoji statuses available")
        return None
    docs = await client(GetCustomEmojiDocumentsRequest(document_id=ids[:200]))
    for doc in docs:
        for attr in doc.attributes:
            alt = getattr(attr, "alt", None)
            if alt and alt in candidates:
                print(f"picked {alt} from default statuses")
                return doc.id
    print("no music emoji among the default statuses")
    return None


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--id", type=int, metavar="DOCUMENT_ID",
                       help="write a known document_id straight into config.json")
    group.add_argument("--saved", action="store_true",
                       help="read the newest message in Saved Messages")
    group.add_argument("--find", action="store_true",
                       help="search the custom emoji catalogue by emoticon")
    group.add_argument("--default", action="store_true",
                       help="pick from the account's default status set")
    parser.add_argument("--emoji", nargs="+", metavar="EMOJI",
                        help="emoticons to look for (default: music notes / headphones)")
    args = parser.parse_args()

    if args.id is not None:
        save_document_id(args.id)
        return 0

    cfg = load_config()
    candidates = args.emoji or cfg.get("emoji_candidates") or DEFAULT_CANDIDATES

    client = TelegramClient(SESSION, int(cfg["api_id"]), cfg["api_hash"])
    await client.connect()
    if not await client.is_user_authorized():
        print("session is not authorized; run login.py first", file=sys.stderr)
        return 1

    try:
        if args.saved:
            doc_id = await from_saved(client)
        elif args.find:
            doc_id = await from_search(client, candidates)
        elif args.default:
            doc_id = await from_defaults(client, candidates)
        else:
            doc_id = (await from_saved(client)
                      or await from_search(client, candidates)
                      or await from_defaults(client, candidates))
    finally:
        await client.disconnect()

    if doc_id is None:
        return 1
    save_document_id(doc_id)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
