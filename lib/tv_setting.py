#!/usr/bin/env python3
"""tv-setting — чтение и запись системных настроек телевизора LG.

    tv-setting get audioGuidance
    tv-setting set audioGuidance on

Прошивка отдаёт не все ключи: на 49UK6450 работает категория option
(audioGuidance), а picture/time отвечают «Some keys are not allowed».
Ошибки печатаются одной строкой, без трассировки.
Параметры подключения: TV_IP, TV_KEYFILE, TV_MANIFEST — из окружения, а если их
там нет, из конфига и домашнего каталога пользователя приставки (как в stb-tv-link).
"""
import asyncio
import json
import os
import sys

import bscpylgtv

import stbconf

STB_HOME = stbconf.get("STB_HOME", "/home/stbuser")
TV_IP = os.environ.get("TV_IP") or stbconf.get("TV_IP", "")
TV_KEYFILE = os.environ.get("TV_KEYFILE") or os.path.join(STB_HOME, ".aiopylgtv.sqlite")
TV_MANIFEST = (os.environ.get("TV_MANIFEST")
               or os.path.join(STB_HOME, "tvctl/nuc_manifest.json"))

# Ключи живут в разных категориях: autoOff15Min — в time, экранные — в general.
CATEGORIES = ["time", "general", "option"]


def fail(message: str, code: int = 1) -> int:
    print("ERROR: %s" % message)
    return code


async def run(action: str, key: str, value) -> int:
    if not TV_IP:
        return fail("не знаю адрес телевизора: задайте TV_IP в stb.conf")
    client = await bscpylgtv.WebOsClient.create(
        TV_IP,
        key_file_path=TV_KEYFILE,
        manifest_file_path=TV_MANIFEST,
        states=[],
        timeout_connect=2,
        connect_retry_attempts=3,
    )
    try:
        await client.connect()
    except Exception as exc:  # noqa: BLE001
        return fail("телевизор не отвечает: %s" % exc)

    try:
        if action == "power":
            # Своё короткое соединение мимо демона: нужно, когда демон отдаёт
            # устаревшее состояние, а спросить больше некого.
            res = await client.get_power_state()
            state = (res or {}).get("state") if isinstance(res, dict) else ""
            if not state:
                return fail("состояние питания не получено: %r" % (res,))
            print(state)
            return 0
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
            return fail("ключ %s этот телевизор не отдаёт: %s" % (key, last))
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
    if len(sys.argv) < 2:
        print("usage: tv-setting get KEY | tv-setting set KEY VALUE | tv-setting power",
              file=sys.stderr)
        return 2
    if sys.argv[1] == "power":
        return asyncio.run(run("power", "", None))
    if len(sys.argv) < 3:
        print("usage: tv-setting get KEY | tv-setting set KEY VALUE | tv-setting power",
              file=sys.stderr)
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
