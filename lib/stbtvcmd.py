#!/usr/bin/env python3
"""stb — одна команда для всего, что делает приставка.

Здесь только телевизор: питание и вход, приложения, громкость и звуковая
панель, текст в поле ввода, пробуждение пакетом WoL. Выделено из bin/stb без
изменения поведения; общие помощники — в lib/stbcommon.py.
"""
import json
import os
import re
import subprocess
import sys
import time

import stbcommon
import stbconf
from stbcommon import (CLI, PY, STB_HOME, TV, TV_PORT, TVCTL, as_user, cli_call,
                       daemon, key_log, mark_clear, need_tv, say, tv_alive)


TV_MAC = stbconf.get("TV_MAC", "")


TV_IF = stbconf.get("TV_IF", "enp0s25")


TV_INPUT = stbconf.get("TV_INPUT_ID", "")


TV_APP = stbconf.get("TV_APP_ID", "")


TV_LIVE = stbconf.get("TV_LIVE_APP", "com.webos.app.livetv")


TV_SPEAKER = stbconf.get("TV_SPEAKER", "")


TV_SPEAKERS = stbconf.get("TV_SPEAKERS", "")


def daemon_alive():
    """Служба демона запущена? Сокет может остаться от прошлого запуска."""
    try:
        out = subprocess.run(["systemctl", "is-active", "stb-tv-link"],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return out.strip() == "active"


def tv_command(req, *fallback):
    """Команда телевизору через демон.

    Прямой вызов библиотеки — только когда демона нет вовсе. Если демон жив и
    ответил отказом, повторять команду вторым соединением нельзя: это ломает
    единственное SSAP-подключение к телевизору, а нажатие может сработать
    дважды (клиент уже отправил его, демон всё ещё выполняет).
    """
    answer = daemon().ask(req)
    if answer.get("ok"):
        return 0
    if answer.get("transport") and not answer.get("sent") and not daemon_alive():
        need_tv()
        return cli_call(*fallback).returncode
    print(answer.get("msg") or "телевизор не выполнил команду", file=sys.stderr)
    return 1


def cmd_tv(argv):
    what = argv[0] if argv else ""
    rest = argv[1:]
    d = daemon()

    if what == "on":
        if not TV_MAC:
            print("не задан TV_MAC в /etc/stb/config", file=sys.stderr)
            return 1
        return subprocess.run(["sudo", "etherwake", "-i", TV_IF, TV_MAC]).returncode

    if what == "off":
        return tv_command({"cmd": "power", "state": "off"}, "power_off")

    if what == "powerstate":
        power = d.power()
        if power:
            print(power)
            return 0
        need_tv()
        out = cli_call("get_power_state").stdout
        match = re.search(r"'state': '([^']*)'", out)
        if match:
            print(match.group(1))
            return 0
        return 1

    if what == "status":
        need_tv()
        # Короткая проба состояния. Раньше здесь стоял обычный запрос (8 с), и
        # после выключения телевизора status висел: демон молчит, а следом ещё
        # три прямых вызова по 12 с — итого под минуту ожидания на ровном месте.
        power = tv_state(3).get("power") or ""
        if not power:
            print("телевизор не ответил за 3 с", file=sys.stderr)
            return 1
        if power != "Active":
            print("телевизор выключен (%s)" % power)
            return 0
        for name in ("get_sound_output", "get_audio_status", "get_current_app"):
            line = cli_call(name, timeout=5).stdout.strip()
            if line:
                print(line)
        return 0

    if what == "key":
        if not rest:
            print("укажи кнопку: stb tv key UP", file=sys.stderr)
            return 2
        return tv_command({"cmd": "key", "name": rest[0].upper()}, "button", rest[0])

    if what in ("up", "down"):
        return tv_command({"cmd": "vol", "dir": what}, "volume_" + what)

    if what in ("mute", "unmute"):
        return tv_command({"cmd": "mute", "on": what == "mute"},
                          "set_mute", "True" if what == "mute" else "False")

    if what == "vol":
        if not rest:
            print("укажи громкость: stb tv vol 12", file=sys.stderr)
            return 2
        try:
            level = int(rest[0])
        except ValueError:
            print("громкость — число от 0 до 100", file=sys.stderr)
            return 2
        return tv_command({"cmd": "vol", "level": level}, "set_volume", rest[0])

    if what == "setinput":
        if not rest:
            print("укажи вход: stb tv setinput HDMI_3", file=sys.stderr)
            return 2
        return tv_command({"cmd": "input", "id": rest[0]}, "set_input", rest[0])

    if what == "getinputs":
        need_tv()
        out = cli_call("get_inputs").stdout.strip()
        try:
            import ast
            for item in ast.literal_eval(out):
                if isinstance(item, dict) and item.get("id"):
                    print(item["id"])
        except Exception:  # noqa: BLE001
            print(out)
        return 0

    if what == "app":
        if not rest:
            print("укажи приложение: stb tv app com.webos.app.browser", file=sys.stderr)
            return 2
        return tv_command({"cmd": "app", "id": rest[0]}, "launch_app", rest[0])

    if what == "getapps":
        need_tv()
        return show_apps()

    if what == "speakers":
        cur = d.state().get("sound")
        if cur:
            print("сейчас: %s" % cur)
        else:
            need_tv()
            print("сейчас: %s" % cli_call("get_sound_output").stdout.strip().strip("'\""))
        if TV_SPEAKERS:
            print("возможные (из конфига): %s" % TV_SPEAKERS)
        return 0

    if what == "speaker":
        if not rest:
            print("укажи выход: stb tv speaker external_arc", file=sys.stderr)
            return 2
        return tv_command({"cmd": "speaker", "id": rest[0]}, "change_sound_output", rest[0])

    if what == "speaker-auto":
        if not TV_SPEAKER or not tv_alive():
            return 0
        cur = d.state().get("sound") or cli_call("get_sound_output").stdout.strip().strip("'\"")
        if cur == TV_SPEAKER:
            return 0
        d.ask({"cmd": "speaker", "id": TV_SPEAKER})
        print("звук: %s → %s" % (cur, TV_SPEAKER))
        return 0

    if what == "text":
        return cmd_tv_text(rest)

    if what == "setting":
        return cmd_tv_setting(rest)

    if what == "wake":
        return cmd_tv_wake(rest)

    if what == "register":
        return cmd_tv_register(rest)

    if what == "learn":
        return cmd_tv_learn(rest)

    if what == "shutdown":
        return cmd_tv_shutdown(rest)

    print(__doc__.strip().split("\n\n")[0], file=sys.stderr)
    print("неизвестная команда: tv %s" % what, file=sys.stderr)
    return 1


def show_apps():
    """Список приложений телевизора без системных (кроме браузера и эфира)."""
    import ast

    hidden = ("com.webos.", "com.palm", "com.palmdts.")
    keep = {"com.webos.app.browser", "com.webos.app.livetv"}
    out = subprocess.run(CLI + [TV, "get_apps_all", "true"], capture_output=True,
                         text=True, timeout=30).stdout.strip()
    try:
        for item in ast.literal_eval(out):
            if isinstance(item, dict) and item.get("id"):
                app_id = str(item["id"])
                if app_id.startswith(hidden) and app_id not in keep:
                    continue
                print("%s  (%s)" % (app_id, item.get("title", "")))
    except Exception:  # noqa: BLE001
        print(out)
    return 0


def wake_tv(seconds=45):
    """Разбудить телевизор и дождаться ответа."""
    if cmd_tv(["on"]) != 0:
        return False
    for _ in range(int(seconds)):
        if tv_state().get("power") == "Active" or tv_alive():
            return True
        time.sleep(1)
    return False


ETHERWAKE = "/usr/sbin/etherwake"


def magic():
    if not TV_MAC:
        return False
    try:
        return subprocess.run(["sudo", ETHERWAKE, "-i", TV_IF, TV_MAC],
                              capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def awake():
    return tv_state().get("power") == "Active"


def cmd_tv_wake(argv):
    """Разбудить телевизор и дождаться ответа: stb tv wake [секунды].

    Отметка /run/stb/waking снимается при любом исходе: иначе одно
    прерванное пробуждение навсегда блокирует кнопку питания с пульта.
    """
    limit = int(argv[0]) if argv and argv[0].isdigit() else 45
    try:
        if tv_alive() and awake():
            say("wake: уже включён")
            cmd_tv(["speaker-auto"])
            return 0
        started = time.time()
        for attempt in range(1, 13):
            magic()
            if attempt == 1:
                # Телевизор разбудён нами: интерфейс поднимаем не дожидаясь
                # его появления в сети — панель зажигается с задержкой.
                subprocess.Popen([stbcommon.SELF, "idle", "on"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 encoding="utf-8")
            if not tv_alive():
                # Телевизор ещё не в сети: спрашивать состояние бессмысленно
                # (демон ждёт до 5 с). Ждём сеть секундой.
                time.sleep(1)
                if time.time() - started >= limit:
                    say("wake: не дождались за %d с" % limit)
                    return 1
                continue
            if awake():
                say("wake: проснулся через %d с (попытка %d)"
                    % (time.time() - started, attempt))
                cmd_tv(["speaker-auto"])
                return 0
            for _ in range(3):
                time.sleep(1)
                if awake():
                    say("wake: проснулся через %d с (попытка %d)"
                        % (time.time() - started, attempt))
                    cmd_tv(["speaker-auto"])
                    return 0
                if time.time() - started >= limit:
                    say("wake: не дождались за %d с" % limit)
                    return 1
        say("wake: не дождались")
        return 1
    finally:
        mark_clear("/run/stb/waking")


def cmd_tv_register(argv):
    """Знакомство с телевизором: подтвердить запрос на его экране (90 с)."""
    print("== проверка канала до телевизора: %s:%s ==" % (TV, TV_PORT))
    check = subprocess.run(["curl", "-s", "-i", "-m", "5",
                            "-H", "Connection: Upgrade", "-H", "Upgrade: websocket",
                            "-H", "Sec-WebSocket-Version: 13",
                            "-H", "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==",
                            "http://%s:%s/" % (TV, TV_PORT)], capture_output=True, text=True)
    print("\n".join(check.stdout.splitlines()[:3]))
    print()
    print("== регистрация: подтвердите запрос на экране телевизора (90 секунд) ==")
    # Свой срок и свой вызов: status отвечает быстро и нарочно обрывается,
    # а знакомство может ждать, пока человек нажмёт «Да» на экране.
    res = cli_call("get_power_state", timeout=90)
    print("exit=%d" % res.returncode)
    tail = (res.stdout or "").strip().splitlines()
    if tail:
        print(tail[-1])
    return res.returncode


def cmd_tv_learn(argv):
    """Спариться с телевизором и показать id приложения и входов."""
    print("== 1. спаривание (на телевизоре нужно нажать «Да») ==")
    print("   спаривание прошло" if cmd_tv_register([]) == 0
          else "   спаривание не завершилось — повторите")
    print("\n== 2. приложение Jellyfin на телевизоре ==")
    apps = subprocess.run([stbcommon.SELF, "tv", "getapps"], capture_output=True, text=True).stdout
    jelly = [line for line in apps.splitlines() if "jelly" in line.lower()]
    print("\n".join(jelly) if jelly else "   не найдено (проверьте: stb tv getapps)")
    print("\n== 3. HDMI-входы телевизора ==")
    inputs = subprocess.run([stbcommon.SELF, "tv", "getinputs"], capture_output=True, text=True).stdout
    print(inputs.strip() or "   не удалось получить список")
    print("\nВпишите найденное в /opt/stb/config/stb.conf:")
    print("  TV_APP_ID   = id приложения Jellyfin (например org.jellyfin.webos)")
    print("  TV_INPUT_ID = id входа, на котором сидит коробка (например HDMI_3)")
    return 0


def cmd_tv_shutdown(argv):
    """Хук выключения приставки: погасить телевизор, если смотрели приставку."""
    jobs = subprocess.run(["systemctl", "list-jobs", "--no-pager"],
                          capture_output=True, text=True).stdout
    if "reboot.target" in jobs:
        say("shutdown: перезагрузка — телевизор не гашу")
        return 0
    mark = "/run/stb/keep-tv"
    if os.path.exists(mark):
        try:
            os.remove(mark)
        except OSError:
            pass
        say("shutdown: просили оставить телевизор включённым")
        return 0
    if not tv_alive():
        say("shutdown: телевизор уже не в сети")
        return 0
    # Гасим всегда, каким бы путём ни выключали (кнопка корпуса, shutdown -h,
    # плитка), и обязательно ждём, пока телевизор уйдёт в ожидание: работающий
    # телевизор поднимает приставку обратно через WoL, и выходит перезапуск.
    if power_off_tv():
        say("shutdown: телевизор погашен и подтвердил ожидание")
    else:
        say("shutdown: телевизор не подтвердил выключение")
    return 0


def cmd_tv_text(argv):
    """Текст в приложение телевизора через внутренний сервис ввода webOS."""
    import asyncio
    import glob

    for extra in glob.glob(os.path.join(STB_HOME, "tvctl", "lib", "python3*", "site-packages")):
        sys.path.insert(0, extra)
    import bscpylgtv

    try:
        text, enter, delete = parse_args(argv)
    except SystemExit as exc:
        print(json.dumps({"ok": False, "msg": str(exc)}, ensure_ascii=False))
        return 2
    if text is None and not enter and not delete:
        print(json.dumps({"ok": False, "msg": "нужен текст, --enter или --delete N"}, ensure_ascii=False))
        return 2

    async def send():
        client = await bscpylgtv.WebOsClient.create(
            TV, key_file_path=os.path.join(STB_HOME, ".aiopylgtv.sqlite"),
            manifest_file_path=os.path.join(TVCTL, "nuc_manifest.json"), states=[])
        await client.connect()
        try:
            # URI без схемы: bscpylgtv сам подставляет "ssap://". Полный
            # "luna://com.webos.service.ime/..." превращался на проводе в
            # "ssap://luna://..." и телевизор отвечал 404 — из-за этого мы
            # решили, что службы ввода нет. Она есть и работает по сети.
            replies = []
            if delete:
                replies.append(("deleteCharacters", await asyncio.wait_for(
                    client.request("com.webos.service.ime/deleteCharacters",
                                   {"count": int(delete)}), 10)))
            if text:
                replies.append(("insertText", await asyncio.wait_for(
                    client.request("com.webos.service.ime/insertText",
                                   {"text": text, "replace": 0}), 10)))
            if enter:
                replies.append(("sendEnterKey", await asyncio.wait_for(
                    client.request("com.webos.service.ime/sendEnterKey"), 10)))
            return replies
        finally:
            # disconnect(), а не close(): close() — это медиакоманда и
            # закрывала плеер на телевизоре вместо соединения.
            await client.disconnect()

    try:
        replies = asyncio.run(send())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "msg": repr(exc)[:200]}, ensure_ascii=False))
        return 1
    for method, reply in replies:
        if isinstance(reply, dict) and reply.get("returnValue") is False:
            why = reply.get("errorText") or reply.get("errorCode") or reply
            print(json.dumps({"ok": False,
                              "msg": "%s: телевизор отказал — %s" % (method, why)},
                             ensure_ascii=False))
            return 1
    what = text or ("стереть %d" % delete if delete else "")
    print(json.dumps({"ok": True, "msg": "отправлено: %s%s" % (what, " + Enter" if enter else "")},
                     ensure_ascii=False))
    return 0


def cmd_tv_setting(argv):
    """Системные настройки телевизора: stb tv setting get|set КЛЮЧ [ЗНАЧЕНИЕ]."""
    return subprocess.run([PY, "/opt/stb/lib/tv_setting.py"] + list(argv)).returncode


def tv_state(timeout=3):
    """Быстрая проба состояния телевизора. Пустой словарь — не ответил.

    Срок задаётся явно, потому что зовут её и в горячих местах (сторож
    заставки, Power, Home, хук загрузки): там обычные 8 секунд ожидания — это
    отставший цикл и «задумчивая» кнопка. Команды телевизору, наоборот,
    остаются с прежним сроком: медленный ответ после пробуждения — норма.
    """
    try:
        answer = daemon().ask({"cmd": "state"}, timeout=timeout)
        return (answer.get("state") or {}) if isinstance(answer, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def tv_shows_own_app():
    """Телевизор показывает своё приложение, а не вход приставки.

    Тогда заставка и гашение по простою запрещены: человек смотрит телевизор,
    просто нажатий в нашу коробку не приходит. Именно из-за этого телевизор
    однажды выключился посреди фильма.
    """
    if not TV_INPUT:
        return False
    ours = "com.webos.app." + TV_INPUT.lower().replace("_", "")
    try:
        app = tv_state(2).get("app") or ""
    except Exception:  # noqa: BLE001
        app = ""
    if not app:
        # None — «неизвестно», а не «телевизор показывает своё»: со значением
        # True потеря связи с демоном сбрасывала отсчёт простоя.
        return None
    return app.lower() != ours


SLEEP_STATES = ("Standby", "Screen Off", "Power Off", "Suspend", "Active Standby")


def tv_power_state():
    """Состояние телевизора строкой; пусто, если он не отвечает."""
    out = as_user("tv", "powerstate").stdout.strip()
    return out


def power_off_tv(timeout=20.0):
    """Погасить телевизор и дождаться, что он действительно ушёл в ожидание.

    Ждать обязательно: если приставка выключится, пока телевизор работает,
    телевизор поднимает её обратно через WoL. Возвращает True, если телевизор
    подтвердил выключение.
    """
    key_log("выключение: сначала гашу телевизор")
    cmd_tv(["off"])
    deadline = time.time() + timeout
    state = ""
    while time.time() < deadline:
        time.sleep(0.5)
        state = tv_power_state()
        if not state or state in SLEEP_STATES:
            key_log("выключение: телевизор %s" % (state or "не отвечает — считаю выключенным"))
            return True
    key_log("выключение: телевизор не подтвердил (%s) — выключаюсь всё равно" % (state or "молчит"))
    return False


def parse_args(argv):
    """--enter, --delete N, «--» и дальше текст (иначе дефисы съест разбор опций)."""
    enter = "--enter" in argv
    args = [a for a in argv if a != "--enter"]
    if "--" in args:
        sep = args.index("--")
        text = " ".join(args[sep + 1:]) if len(args) > sep + 1 else None
        return text, enter, 0
    if args and args[0] == "--delete":
        try:
            return None, enter, int(args[1])
        except (IndexError, ValueError):
            raise SystemExit("после --delete нужно число символов") from None
    if args and args[0].startswith("--"):
        raise SystemExit("неизвестная опция %s; для текста используйте «--»" % args[0])
    return (args[0] if args else None), enter, 0
