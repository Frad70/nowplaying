#!/usr/bin/env python3
"""Write a user systemd unit for this checkout without starting it."""
from __future__ import annotations

import argparse
from pathlib import Path


def quote(value: Path) -> str:
    text = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'"{text}"'


def directory_value(value: Path) -> str:
    text = str(value).replace("%", "%%")
    return text.replace("\\", "\\x5c").replace(" ", "\\x20").replace('"', "\\x22")


def render(root: Path) -> str:
    return f"""[Unit]
Description=Now-playing bridge (MPRIS to Telegram)
After=graphical-session.target dbus.socket
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart={quote(root / '.venv/bin/python')} {quote(root / 'nowplaying.py')}
WorkingDirectory={directory_value(root)}
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print", action="store_true", dest="preview",
                        help="show the unit without writing it")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    unit = render(root)
    if args.preview:
        print(unit, end="")
        return
    target = Path.home() / ".config/systemd/user/nowplaying.service"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(unit, encoding="utf-8")
    print(f"Wrote {target}")
    print("Run: systemctl --user daemon-reload && systemctl --user enable --now nowplaying.service")


if __name__ == "__main__":
    main()
