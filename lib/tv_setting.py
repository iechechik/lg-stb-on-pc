#!/usr/bin/env python3
"""tv-setting — чтение и запись системных настроек телевизора LG.

    tv-setting get autoOff15Min [ключ ...]
    tv-setting set autoOff15Min off

Категория настроек — general. Ошибки печатаются одной строкой, без трассировки.
Параметры подключения берутся из окружения: TV_IP, TV_KEYFILE, TV_MANIFEST.
"""
import asyncio
import json
import os
import sys

import bscpylgtv

# Ключи живут в разных категориях: autoOff15Min — в time, экранные — в general.
CATEGORIES = ["time", "general", "option"]


def fail(message: str, code: int = 1) -> int:
    print("ERROR: %s" % message)
    return code


async def run(action: str, key: str, value) -> int:
    client = await bscpylgtv.WebOsClient.create(
        os.environ["TV_IP"],
        key_file_path=os.environ["TV_KEYFILE"],
        manifest_file_path=os.environ["TV_MANIFEST"],
        states=[],
        timeout_connect=2,
        connect_retry_attempts=3,
    )
    try:
        await client.connect()
    except Exception as exc:  # noqa: BLE001
        return fail("телевизор не отвечает: %s" % exc)

    try:
        if action == "get":
            last = None
            for cat in CATEGORIES:
                try:
                    res = await client.get_system_settings(cat, [key], jsonOutput=True)
                except Exception as exc:  # noqa: BLE001
                    last = exc
                    continue
                data = res
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except ValueError:
                        pass
                settings = (data or {}).get("settings") if isinstance(data, dict) else None
                if settings and settings.get(key) is not None:
                    print("%s:%s" % (cat, settings[key]))
                    return 0
            return fail("ключ %s не поддерживается: %s" % (key, last))
        last = None
        for cat in CATEGORIES:
            try:
                res = await client.set_system_settings(cat, {key: value})
            except Exception as exc:  # noqa: BLE001
                last = exc
                continue
            if isinstance(res, dict) and res.get("returnValue") is False:
                last = res
                continue
            print("ok (%s)" % cat)
            return 0
        return fail("не удалось записать %s: %s" % (key, last))
    except Exception as exc:  # noqa: BLE001
        return fail("не удалось: %s" % exc)
    finally:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: tv-setting get KEY | tv-setting set KEY VALUE", file=sys.stderr)
        return 2
    action, key = sys.argv[1], sys.argv[2]
    if action == "get":
        return asyncio.run(run("get", key, None))
    if action == "set":
        if len(sys.argv) < 4:
            print("usage: tv-setting set KEY VALUE", file=sys.stderr)
            return 2
        return asyncio.run(run("set", key, sys.argv[3]))
    print("usage: tv-setting get KEY | tv-setting set KEY VALUE", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
