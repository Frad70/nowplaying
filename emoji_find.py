import asyncio, json
from pathlib import Path
from telethon import TelegramClient
from telethon.tl.functions.messages import SearchCustomEmojiRequest, GetCustomEmojiDocumentsRequest

ROOT = Path("/home/frad70/nowplaying")
cfg = json.loads((ROOT / "config.json").read_text())

async def main():
    client = TelegramClient(str(ROOT / "nowplaying"), int(cfg["api_id"]), cfg["api_hash"])
    await client.connect()
    for emo in ["🎵", "🎧", "🎶"]:
        res = await client(SearchCustomEmojiRequest(emoticon=emo, hash=0))
        ids = getattr(res, "document_id", [])
        if ids:
            docs = await client(GetCustomEmojiDocumentsRequest(document_id=ids[:5]))
            for d in docs:
                free = not any(getattr(a, "free", False) is False for a in d.attributes)
                alt = next((a.alt for a in d.attributes if hasattr(a, "alt")), "?")
                print(f"CANDIDATE {emo} id={d.id} alt={alt}")
            cfg["emoji_document_id"] = docs[0].id
            (ROOT / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
            print(f"PICKED {docs[0].id}")
            return
    print("NONE_FOUND")

asyncio.run(main())
