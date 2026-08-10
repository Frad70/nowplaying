import asyncio, json
from pathlib import Path
from telethon import TelegramClient
from telethon.tl.types import MessageEntityCustomEmoji

ROOT = Path("/home/frad70/nowplaying")
cfg = json.loads((ROOT / "config.json").read_text())

async def main():
    client = TelegramClient(str(ROOT / "nowplaying"), int(cfg["api_id"]), cfg["api_hash"])
    await client.connect()
    msg = (await client.get_messages("me", limit=1))[0]
    ids = [e.document_id for e in (msg.entities or []) if isinstance(e, MessageEntityCustomEmoji)]
    if not ids:
        print("NO_CUSTOM_EMOJI (обычный юникод-смайл, без document_id)")
        return
    cfg["emoji_document_id"] = ids[0]
    (ROOT / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
    print(f"PICKED {ids[0]}")

asyncio.run(main())
