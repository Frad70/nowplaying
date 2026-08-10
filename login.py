#!/usr/bin/env python3
"""One-off authorization for the now-playing session."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from telethon import TelegramClient

ROOT = Path(__file__).resolve().parent


async def main() -> int:
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    client = TelegramClient(str(ROOT / "nowplaying"), int(cfg["api_id"]), cfg["api_hash"],
                            device_model="now-playing bridge", system_version="linux",
                            app_version="1.0")
    await client.connect()
    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"already authorized as @{me.username}")
        return 0

    phone = cfg["phone"]
    sent = await client.send_code_request(phone)
    print("CODE_SENT")
    code = input("code: ").strip()
    try:
        await client.sign_in(phone, code, phone_code_hash=sent.phone_code_hash)
    except Exception as exc:
        if "password" not in str(exc).lower() and "2fa" not in str(exc).lower():
            raise
        await client.sign_in(password=input("2fa password: ").strip())
    me = await client.get_me()
    print(f"authorized as @{me.username}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
