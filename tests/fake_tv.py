#!/usr/bin/env python3
"""Поддельный телевизор: сокет демона с задержкой, как у настоящего.

    python3 tests/fake_tv.py --socket /tmp/fake.sock --log /tmp/fake.log

Пишет по строке на каждый запрос — по этому журналу видно частоту опроса.
Отвечает состоянием Active и нужным выходом звука, чтобы сторожа ничего
не переключали на настоящем телевизоре.
"""
import argparse
import asyncio
import json
import os
import time

STATE = {
    "power": "Active",
    "sound": "external_arc",
    "app": "com.webos.app.hdmi3",
    "volume": 10,
    "muted": False,
}


def log(path, line):
    with open(path, "a", encoding="utf-8") as f:
        f.write("%s %s\n" % (time.strftime("%H:%M:%S"), line))


async def handle(reader, writer, delay, logpath):
    try:
        line = await reader.readline()
        if not line:
            return
        try:
            req = json.loads(line.decode("utf-8", "replace"))
        except ValueError:
            req = {"cmd": "?"}
        log(logpath, req.get("cmd", "?"))
        if delay:
            await asyncio.sleep(delay)
        writer.write((json.dumps({"ok": True, "state": STATE}, ensure_ascii=False) + "\n").encode())
        await writer.drain()
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", default="/tmp/fake-tv.sock")
    ap.add_argument("--log", default="/tmp/fake-tv.log")
    ap.add_argument("--delay", type=float, default=0.02, help="задержка ответа, секунды")
    args = ap.parse_args()

    if os.path.exists(args.socket):
        os.unlink(args.socket)
    open(args.log, "w").close()
    server = await asyncio.start_unix_server(
        lambda r, w: handle(r, w, args.delay, args.log), path=args.socket)
    os.chmod(args.socket, 0o666)
    print("поддельный телевизор слушает", args.socket)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
