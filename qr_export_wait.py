import asyncio, base64, json, os, sys
from pathlib import Path
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

ROOT = Path("/home/frad70/nowplaying")
cfg = json.loads((ROOT / "config.json").read_text())

async def main():
    client = TelegramClient(str(ROOT / "nowplaying"), int(cfg["api_id"]), cfg["api_hash"],
                            device_model="now-playing bridge", system_version="linux", app_version="1.0")
    await client.connect()
    if await client.is_user_authorized():
        print("ALREADY_AUTHORIZED", flush=True); return
    qr = await client.qr_login()
    Path("/tmp/qr_token.b64").write_text(base64.b64encode(qr.token).decode())
    print("TOKEN_EXPORTED", flush=True)
    try:
        await qr.wait(timeout=120)
        me = await client.get_me()
        print(f"AUTHORIZED @{me.username}", flush=True)
    except SessionPasswordNeededError:
        pw = Path("/tmp/.tg2fa").read_text().strip() if Path("/tmp/.tg2fa").exists() else ""
        if not pw:
            print("PASSWORD_NEEDED", flush=True)
            return
        await client.sign_in(password=pw)
        me = await client.get_me()
        print(f"AUTHORIZED @{me.username}", flush=True)
    except asyncio.TimeoutError:
        print("WAIT_TIMEOUT", flush=True)

asyncio.run(main())
