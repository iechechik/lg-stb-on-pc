#!/usr/bin/env python3
"""stb — одна команда для всего, что делает приставка.

Кнопки пульта: что делает каждая в режиме приставки и телевизора, склейка
двойных нажатий, повторы, защита от дребезга и сборка карты кнопок.
"""
import os
import subprocess
import sys
import time

import stbcommon
import stbconf
from stbcommon import (STB_HOME, as_user, is_app, is_browser, is_grid,
                       key_log, mark_clear, mark_set, mode_get, mode_set,
                       sink_mute, screensaver_on, tv_alive, user_gid, user_uid,
                       window_title, xdo)
import stb4k  # noqa: E402
import stbtabs  # noqa: E402
from stbdesktop import BROWSER_WINDOW, window_mode  # noqa: E402
from stbcommon import STB_USER  # noqa: E402
from stbtvcmd import TV_INPUT  # noqa: E402
from stbtvcmd import awake  # noqa: E402
from stbdesktop import cmd_hide  # noqa: E402
from stbdesktop import close_splash_now  # noqa: E402
from stbtvcmd import cmd_tv  # noqa: E402
from stbcommon import current_app  # noqa: E402
from stbdesktop import finish_all  # noqa: E402
from stbdesktop import finish_app  # noqa: E402


def scroll_key(grid_key, scroll):
    if is_grid():
        xdo("key", "--clearmodifiers", grid_key)
        key_log("%s (сетка)" % grid_key)
    else:
        xdo("key", "--clearmodifiers", scroll)
        key_log("прокрутка %s" % scroll)


def debounce(name, seconds):
    stamp = "/run/stb/%s.stamp" % name
    try:
        last = float(open(stamp, encoding="utf-8").read().strip())
    except (OSError, ValueError):
        last = 0.0
    now = time.time()
    if now - last < seconds:
        key_log("%s: пропуск (дребезг, %s с)" % (name, seconds))
        return False
    try:
        with open(stamp, "w", encoding="utf-8") as f:
            f.write(str(now))
    except OSError:
        pass
    return True


def key_power():
    if not debounce("power", 2):
        return 0
    if not tv_alive():
        # Телевизора нет в сети — он выключен. Демон не спрашиваем: попытка
        # соединения с уснувшим телевизором занимает до 5 с.
        key_log("power: телевизора нет в сети — будим сразу")
        mark_set("/run/stb/waking")
        subprocess.Popen([stbcommon.SELF, "tv", "wake", "40"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, encoding="utf-8")
        if screensaver_on():
            subprocess.Popen([stbcommon.SELF, "screensaver", "close"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             encoding="utf-8")
        return 0
    if awake():
        key_log("power → ТВ off")
        subprocess.Popen([stbcommon.SELF, "tv", "off"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, encoding="utf-8")
        return 0
    flag = "/run/stb/waking"
    WAKE_FLAG_MAX = 60      # будим не дольше 40 с; старая отметка — мусор
    if os.path.exists(flag):
        age = time.time() - os.path.getmtime(flag)
        if age < WAKE_FLAG_MAX:
            key_log("power: включение уже идёт (%.0f с назад)" % age)
            return 0
        key_log("power: старая отметка включения (%.0f с) — убираю" % age)
        mark_clear(flag)
    key_log("power → ТВ on")
    mark_set("/run/stb/waking")
    subprocess.Popen([stbcommon.SELF, "tv", "wake", "40"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, encoding="utf-8")
    if screensaver_on():
        subprocess.Popen([stbcommon.SELF, "screensaver", "close"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, encoding="utf-8")
    return 0


def key_back():
    """Одиночный Back: своя реакция в каждом режиме и окне."""
    if mode_get() == "tv":
        key_log("back → ТВ")
        return cmd_tv(["key", "BACK"])
    title = window_title()
    if is_app(title):
        # У Jellyfin своя навигация: отдаём ему.
        key_log("back → приложению (%s)" % title[:30])
        xdo("key", "--clearmodifiers", "alt+Left")
        return 0
    if is_browser(title):
        before = title
        xdo("key", "--clearmodifiers", "alt+Left")
        # 0.25 с хватает, чтобы страница ушла назад; полсекунды на кнопке
        # чувствовались как «она задумалась».
        time.sleep(0.25)
        after = window_title()
        if before == after:
            # Вкладку не закрываем: раньше здесь стоял ctrl+w, и серия нажатий
            # Back вынесла все вкладки подряд. В сетку — двойной Back.
            if is_grid(after):
                key_log("back → это сетка, назад некуда")
            else:
                key_log("back → истории нет (вкладку не трогаю; двойной Back — на сетку)")
        else:
            key_log("back → шаг назад в браузере")
        return 0
    key_log("back → скрыть окно (%s)" % title)
    return cmd_hide([])


def to_grid():
    """Уйти на сетку: переключить её вкладку, сразу убрать полосы, поставить курсор.

    Полосы убираем здесь же, а не ждём сторожа: иначе сетка пару секунд висит с
    «грязным» верхом. Курсор ставим в центр выбранной плитки — иначе он остаётся
    там, где был, и нажатие PAUSE попадает не туда.
    """
    try:
        # Сначала вернуть 1080p, потом показать сетку: иначе сетка успевает
        # отрисоваться в 4K и выглядит мелкой.
        stb4k.to_hd()
    except Exception:  # noqa: BLE001
        pass
    try:
        stbtabs.activate_grid()
        placed = stbtabs.select_tile(stbtabs.last_tile())
        window_mode(True)      # сетка всегда во весь экран
        stbtabs.set_grid_bars(True)
        sink_mute(True)        # на сетке звук всегда выключен
        if not placed:
            # Страница не ответила — ставим указатель по координатам плитки.
            point = stbtabs.grid_tile_center(stbtabs.last_tile()) or stbtabs.grid_tile_center()
            if point:
                xdo("mousemove", str(point[0]), str(point[1]))
    except Exception as exc:  # noqa: BLE001
        key_log("на сетку не переключилось (%r)" % (exc,))


def key_back_double():
    """Двойной Back: отдельное событие, одиночное нажатие сюда не уходит.

    Приложение прячем (возврат тёплым, а не холодным стартом), из браузера
    уходим на сетку, в режиме телевизора — возвращаемся на приставку.
    """
    if mode_get() == "tv":
        key_log("back ×2 → на приставку")
        return cmd_key(["tobox"])
    title = window_title()
    if is_browser(title):
        key_log("back ×2 → на сетку")
        to_grid()
        return 0
    key_log("back ×2 → прячу приложение (%s)" % title[:30])
    cmd_hide([])
    # Прячем окно — и сразу на сетку: 1080p, полный экран, курсор на своей плитке.
    to_grid()
    return 0


def key_home():
    if mode_get() == "tv":
        key_log("home → меню телевизора")
        return cmd_tv(["key", "HOME"])
    app = current_app()
    if app and "hdmi" not in app.lower():
        key_log("home: возвращаю вход ТВ")
        if TV_INPUT:
            cmd_tv(["setinput", TV_INPUT])
    # Home на сетке — уборка (закрыть приложения). Home в окне приложения —
    # «я закончил»: гасим его. Back — наоборот, прячет и даёт вернуться.
    if is_grid():
        finish_all()
    else:
        finish_app()
        to_grid()          # после «закончил» показываем сетку и ставим курсор на плитку

    mode_set("nuc")
    key_log("home → на сетку")
    to_grid()
    return 0


# KEY_ACTIONS — что диспетчер `stb key` умеет в режиме приставки.
# В lib/stbkeys.py есть одноимённая таблица, но это другое: прямые
# маршруты кнопок в демон телевизора (там вместо power — конкретные
# действия). Не путать при правках.
KEY_ACTIONS = {
    "power", "volup", "voldown", "mute", "back", "home", "menu", "tobox",
    "ok", "up", "down", "left", "right", "prev", "next",
    "play", "playkey", "pausekey", "chup", "chdown",
    "red", "green", "yellow", "blue", "info", "guide", "cc", "exit", "tab", "tabback",
    "del", "erase",
} | {str(d) for d in range(10)}


TV_VOLUME = {"volup": "VOLUMEUP", "voldown": "VOLUMEDOWN", "mute": "MUTE"}


TV_ONLY = {"info": "INFO", "guide": "GUIDE", "cc": "CC",
           "chup": "CHANNELUP", "chdown": "CHANNELDOWN"}


ARROWS = {"left": "LEFT", "prev": "LEFT", "right": "RIGHT", "next": "RIGHT"}


COLOURS = ("red", "green", "yellow", "blue")


def tv_key_press(act, key_name):
    """Кнопка уходит в телевизор: запись в журнал и отправка по SSAP."""
    key_log("%s → ТВ %s" % (act, key_name))
    return cmd_tv(["key", key_name])


def cmd_key(argv):
    """Кнопка пульта с учётом режима: stb key <действие>."""
    act = (argv[0] if argv else "").strip()
    if not act:
        print("usage: stb key <действие>, список: stb keys list", file=sys.stderr)
        return 2
    if act == "back-double":
        return key_back_double()
    if act not in KEY_ACTIONS:
        print("неизвестное действие: %s" % act, file=sys.stderr)
        return 2
    # Экран погашен: это нажатие только снимает заставку, в приложение не идёт.
    if screensaver_on():
        return close_splash_now()

    # Нажатие пульта означает, что человек у экрана: заставку снимаем.
    if screensaver_on():
        subprocess.Popen([stbcommon.SELF, "screensaver", "close"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         encoding="utf-8")

    tv = mode_get() == "tv"
    if tv:
        subprocess.Popen([stbcommon.SELF, "preflight"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, encoding="utf-8")

    if act == "power":
        return key_power()
    if act == "back":
        return key_back()
    if act == "home":
        return key_home()

    # Громкость всегда в телевизор: звук идёт через HDMI, дальше ARC.
    if act in TV_VOLUME:
        return tv_key_press(act, TV_VOLUME[act])

    # В форме на телевизоре стрелки фокус не двигают, а без Tab из логина в
    # пароль не перейти. Канал вверх/вниз в режиме приставки свободен — отдаём
    # его под Tab и Shift+Tab.
    if act in ("chup", "chdown") and not tv:
        key_name = "Tab" if act == "chup" else "shift+Tab"
        key_log("%s → %s" % (act, key_name))
        xdo("key", "--clearmodifiers", key_name)
        return 0
    # Стирание в поле ввода. С клавиатуры телефона BackSpace уже приходит
    # (ime/deleteCharacters), эти действия — для пульта: стереть символ и
    # очистить поле целиком, чтобы не вычищать точками по одной.
    if act == "del":
        key_log("del → BackSpace")
        xdo("key", "--clearmodifiers", "BackSpace")
        return 0
    if act == "erase":
        key_log("erase → очистить поле")
        xdo("key", "--clearmodifiers", "ctrl+a")
        xdo("key", "--clearmodifiers", "BackSpace")
        return 0

    if act in ("tab", "tabback"):
        key_name = "Tab" if act == "tab" else "shift+Tab"
        key_log("%s → %s" % (act, key_name))
        xdo("key", "--clearmodifiers", key_name)
        return 0

    # Кнопки, которые существуют только на телевизоре.
    if act in TV_ONLY:
        if not tv:
            key_log("%s — только в режиме телевизора" % act)
            return 0
        return tv_key_press(act, TV_ONLY[act])

    if act == "tobox":
        key_log("на приставку")
        if TV_INPUT:
            cmd_tv(["setinput", TV_INPUT])
        mode_set("nuc")
        # Та же причина, что и в cmd_box: на экране сетка — звук не нужен.
        sink_mute(True)
        as_user("wmctrl", "-a", BROWSER_WINDOW)
        return 0

    if act == "menu":
        if tv:
            return tv_key_press(act, "MENU")
        key_log("menu → Escape")
        xdo("key", "--clearmodifiers", "Escape")
        return 0

    if act in ("up", "down"):
        if tv:
            return tv_key_press(act, act.upper())
        scroll_key("Up" if act == "up" else "Down", "Prior" if act == "up" else "Next")
        return 0

    if act in ARROWS:
        key_name = ARROWS[act]
        direction = "влево" if key_name == "LEFT" else "вправо"
        if tv:
            return tv_key_press(act, key_name)
        key_log("%s → %s" % (act, direction))
        xdo("key", "--clearmodifiers", key_name.capitalize())
        return 0

    if act in ("playkey", "pausekey"):
        if tv:
            return tv_key_press(act, "PLAY" if act == "playkey" else "PAUSE")
        # На сетке выбор двигают стрелки — жмём выбранную плитку.
        if is_grid(window_title()):
            key_log("%s → запуск выбранной плитки" % act)
            xdo("key", "--clearmodifiers", "Return")
            return 0
        # В чужой странице раскладка такая: PLAY — Tab (из логина в пароль и
        # дальше по форме), PAUSE — клик под указателем. Раньше обе жали под
        # указателем, и перейти в поле пароля было нечем.
        # Плей/пауза на панели с трекпадом — это ввод: навели курсор и нажали.
        # Так человек ставит курсор в поле и жмёт кнопки. Оба имени (PLAY и
        # PAUSE) приходят от одной кнопки, значит оба и есть клик.
        key_log("%s → нажатие под указателем" % act)
        xdo("click", "1")
        return 0

    if act in ("play", "ok"):
        if tv:
            return tv_key_press(act, "ENTER" if act == "ok" else "PLAY")
        # На сетке Enter запускает выбранную плитку. В чужой странице Enter
        # отправляет форму (так логин уходил с пустым паролем), поэтому там
        # нажимаем под указателем — как трекпад мышью.
        if is_grid(window_title()):
            key_log("%s → выбор плитки" % act)
            xdo("key", "--clearmodifiers", "Return")
            return 0
        # В чужой странице OK — Enter. Из поля пароля он отправляет форму, поэтому
        # целиться в кнопку входа не нужно. Переход между полями — клик по полю
        # (плей/пауза), он же ставит курсор куда надо.
        key_log("%s → Enter" % act)
        xdo("key", "--clearmodifiers", "Return")
        return 0

    if act == "blue" and not tv:
        # Синяя кнопка в режиме приставки: включить или выключить 4K-режим.
        value = stb4k.toggle()
        key_log("blue → JMP_VIDEO_4K = %s" % value)
        return 0

    if act in COLOURS:
        if not tv:
            key_log("%s — только в режиме телевизора" % act)
            return 0
        return tv_key_press(act, act.upper())

    if act == "exit":
        if not tv:
            key_log("exit — только в режиме телевизора")
            return 0
        return tv_key_press(act, "EXIT")

    if act.isdigit() and len(act) == 1:
        if tv:
            return tv_key_press(act, act)
        key_log("цифра %s" % act)
        xdo("key", "--clearmodifiers", act)
        return 0

    print("неизвестное действие: %s" % act, file=sys.stderr)
    return 2


def bt_keys_apply(dry_run=False):
    """Собрать ~/.xbindkeysrc из карты BT и перезапустить xbindkeys."""
    maps = os.path.join(stbconf.CONFIG_DIR, "buttons-bt.conf")
    target = os.path.join(STB_HOME, ".xbindkeysrc")
    if not os.access(maps, os.R_OK):
        print("нет файла %s" % maps, file=sys.stderr)
        return 1

    body = ["# Собрано из %s — правьте карту, а не этот файл." % maps,
            "# Применить: stb keys apply bt", ""]
    for raw in open(maps, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, action = line.split("=", 1)
        key, action = key.replace(" ", ""), action.split("#")[0].strip()
        if not key or not action:
            continue
        body += ['"/opt/stb/bin/stb key %s"' % action, "    %s" % key, ""]

    text = "\n".join(body)
    if dry_run:
        print(text)
        return 0

    with open(target, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        os.chown(target, user_uid(), user_gid())
    except OSError:
        pass
    print("собрано привязок: %d" % sum(1 for line in body if line.startswith('"')))

    import pwd
    uid = pwd.getpwnam(STB_USER).pw_uid
    env_prefix = ["sudo", "-n", "-u", STB_USER, "env", "DISPLAY=:0",
                  "XAUTHORITY=%s" % os.path.join(STB_HOME, ".Xauthority"),
                  "HOME=%s" % STB_HOME, "XDG_RUNTIME_DIR=/run/user/%d" % uid]
    subprocess.run(env_prefix + ["pkill", "-x", "xbindkeys"], capture_output=True)
    time.sleep(1)
    subprocess.Popen(env_prefix + ["setsid", "xbindkeys"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL, encoding="utf-8")
    time.sleep(1)
    count = subprocess.run(["pgrep", "-c", "-x", "xbindkeys"], capture_output=True,
                           text=True).stdout.strip()
    print("xbindkeys: %s процесс(ов)" % (count or 0))
    return 0


