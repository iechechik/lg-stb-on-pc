#!/usr/bin/env python3
"""stb4k — режим выхода под содержимое.

Правило: интерфейс приставки и самого плеера всегда 1080p, 2160p включается
только на время фильма — пока окно плеера активно и сервер Jellyfin говорит,
что идёт воспроизведение. Что считать поводом для 4K, задаёт настройка:

    JMP_VIDEO_4K="off"   — никогда, всегда 1080p
    JMP_VIDEO_4K="auto"  — только если поток сам 4K
    JMP_VIDEO_4K="all"   — любой фильм, включая FHD (телевизор отдаёт масштаб)

Опознание — по серверу (`/sessions`: устройство, файл, разрешение, пауза), ключ
в config/jellyfin.key. Лог плеера для этого не годится: он хрупкий.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

import stbcommon
import stbconf

SERVER = str(stbconf.get("JELLYFIN_URL", "") or "").rstrip("/")
CLIENT = "jellyfin desktop"      # так плеер представляется серверу
KEY_FILE = os.path.join(stbconf.get("STB_CONFIG_DIR", "/opt/stb/config"), "jellyfin.key")

MODE_4K = "3840x2160"
MODE_HD = "1920x1080"
VALUES = ("off", "auto", "all")

_state = {"mode": "", "last_change": 0.0}


def _key():
    try:
        with open(KEY_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _conf(key, default=""):
    """Значение из конфига: stbconf.load перечитывает файл, кэша нет."""
    path = os.path.join(stbconf.get("STB_CONFIG_DIR", "/opt/stb/config"), "stb.conf")
    try:
        return stbconf.load(path).get(key, default)
    except Exception:  # noqa: BLE001
        return default


def video_mode():
    """Что делаем с 4K: off — никогда, auto — только 4K-поток, all — любой фильм."""
    value = str(_conf("JMP_VIDEO_4K", "auto") or "auto").strip().lower()
    if value not in VALUES:
        value = "auto"
    return value


def sessions():
    """Сессии сервера; пусто — сервер не ответил или нет ключа."""
    key = _key()
    if not key or not SERVER:
        return []
    req = urllib.request.Request(SERVER + "/Sessions",
                                 headers={"Authorization": 'MediaBrowser Token="%s"' % key})
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError):
        return []


def pick_session(items):
    """Выбрать сессию нашего плеера из ответа /Sessions.

    Опознаём по клиенту: имя устройства приходит от самого плеера и может
    смениться (переименовали в Jellyfin, другой профиль). Если в конфиге задано
    `JELLYFIN_DEVICE`, оно сужает выбор; если подходящей сессии нет — берём
    единственную играющую.
    """
    playing_now = [s for s in items or [] if s.get("NowPlayingItem")]
    ours = [s for s in playing_now if CLIENT in (s.get("Client") or "").lower()]
    want = str(_conf("JELLYFIN_DEVICE", "") or "").strip()
    if want:
        exact = [s for s in ours if (s.get("DeviceName") or "") == want]
        if exact:
            ours = exact
        else:
            exact = [s for s in playing_now if (s.get("DeviceName") or "") == want]
            ours = exact or ours
    return (ours or playing_now or [None])[0]


def session_info():
    """Какая сессия опознана и как она играет — для `stb status`.

    Пусто — ни одной подходящей сессии: значит и 4K решать не по чему.
    """
    sess = pick_session(sessions())
    if not sess:
        return {}
    ti = sess.get("TranscodingInfo") or {}
    return {"device": sess.get("DeviceName") or "",
            "client": sess.get("Client") or "",
            "method": (sess.get("PlayState") or {}).get("PlayMethod") or "",
            "codec": (ti.get("VideoCodec") or "").upper()}


def playing():
    """(высота, пауза, частота кадров, ширина) для нашего плеера."""
    sess = pick_session(sessions())
    if sess:
        height, width, fps = 0, 0, None
        for stream in sess["NowPlayingItem"].get("MediaStreams") or []:
            if stream.get("Type") == "Video" and stream.get("Height"):
                height = int(stream["Height"])
                width = int(stream.get("Width") or 0)
                fps = stream.get("RealFrameRate") or stream.get("FrameRate")
        paused = bool((sess.get("PlayState") or {}).get("IsPaused"))
        return height, paused, fps, width
    return 0, False, None, 0


def player_active():
    """Активно ли окно плеера — то есть смотрит ли человек фильм прямо сейчас."""
    try:
        found = stbcommon.as_user("xdotool", "search", "--name", "Jellyfin Desktop")
        windows = [w for w in (found.stdout or "").split() if w.isdigit()]
        if not windows:
            return False
        active = stbcommon.as_user("xdotool", "getactivewindow").stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    return active in windows


def current_mode():
    out = stbcommon.as_user("xrandr").stdout
    for line in out.splitlines():
        if line.startswith("HDMI-1"):
            for token in line.split():
                if "x" in token and "+" in token:
                    return token.split("+")[0]
    return ""


def set_mode(mode, rate=None):
    """Переключить выход приставки. Возвращает True, если режим сменился."""
    if _state["mode"] == mode or current_mode() == mode:
        _state["mode"] = mode
        return False
    if time.monotonic() - _state["last_change"] < 5:
        return False
    args = ["xrandr", "--output", "HDMI-1", "--mode", mode]
    if rate:
        args += ["--rate", str(rate)]
    try:
        proc = stbcommon.as_user(*args, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    if getattr(proc, "returncode", 1) != 0:
        # Режим не поставился — внутреннее состояние не трогаем, иначе следующие
        # вызовы решат, что уже переключено.
        stbcommon.log_to("keys", "режим %s не применился: %s"
                         % (mode, ((proc.stderr or "").strip()[:120] or "без текста")))
        return False
    _state["mode"] = mode
    _state["last_change"] = time.monotonic()
    _state["want"] = None          # намерение исполнено, ждать заново не надо
    _state["want_since"] = 0.0
    stbcommon.log_to("keys", "режим выхода: %s" % mode)
    try:
        import stbtabs
        stbtabs.refit()      # окно браузера иначе остаётся с размером от 4K
    except Exception:  # noqa: BLE001
        pass
    return True


def _rate(fps):
    """Ближайшая поддерживаемая частота для кадров фильма."""
    try:
        fps = float(fps)
    except (TypeError, ValueError):
        return None
    for value, name in ((23.976, "23.98"), (24.0, "23.98"), (25.0, "25"),
                        (29.97, "29.97"), (30.0, "29.97"), (50.0, "50"),
                        (59.94, "59.94"), (60.0, "60")):
        if abs(fps - value) < 0.6:
            return name
    return None


def toast(text):
    """Короткое сообщение на экране приставки."""
    try:
        stbcommon.as_user("notify-send", "-t", "3000", "Экран", text, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def to_hd():
    """Сразу 1080p: ушли из плеера — интерфейс должен быть нормального размера.

    Сервер ещё несколько секунд считает фильм играющим, поэтому здесь решению
    check() верить нельзя — ставим режим напрямую.
    """
    _state["mode"] = ""
    set_mode(MODE_HD, _conf("AUTO_HD_RATE", "60"))


# Сколько секунд новое состояние должно продержаться, прежде чем менять режим.
# Любая смена разрешения останавливает картинку на несколько секунд, поэтому
# мигание фокуса окна или обрывок опроса не должны её вызывать.
DWELL = {MODE_4K: 2.0, MODE_HD: 3.0}


def _settled(now, goal):
    """Новое состояние держится достаточно долго?"""
    if _state.get("want") != goal:
        _state["want"] = goal
        _state["want_since"] = now
        return False
    return now - _state.get("want_since", now) >= DWELL.get(goal, 3.0)


def check():
    """Решение по режиму на текущий момент. Возвращает выбранный режим."""
    mode = video_mode()
    now = time.monotonic()
    if mode == "off":
        # Выключатель: экран обязан быть в 1080p, ждать нечего.
        if _state.get("mode") != MODE_HD:
            set_mode(MODE_HD, _conf("AUTO_HD_RATE", "60"))
        return MODE_HD
    height, paused, fps, width = playing()
    big = height >= 2000 or width >= 3000      # широкоформатные 4K: 3840x1600
    if height and player_active() and (mode == "all" or big):
        if paused and _state["mode"] == MODE_4K:
            return MODE_4K                 # на паузе режим не дёргаем
        if _state.get("mode") != MODE_4K and not _settled(now, MODE_4K):
            return _state.get("mode") or MODE_HD    # ещё не время дёргать экран
        set_mode(MODE_4K, _rate(fps) or _conf("AUTO_4K_RATE", "23.98"))
        return MODE_4K
    if _state.get("mode") == MODE_4K and not _settled(now, MODE_HD):
        return MODE_4K                     # фильм только что пропал — даём время
    set_mode(MODE_HD, _conf("AUTO_HD_RATE", "60"))
    return MODE_HD


def set_value(value):
    """Записать JMP_VIDEO_4K и применить сразу."""
    path = os.path.join(stbconf.get("STB_CONFIG_DIR", "/opt/stb/config"), "stb.conf")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if re.search(r"(?m)^JMP_VIDEO_4K=", text):
            text = re.sub(r"(?m)^JMP_VIDEO_4K=.*$", 'JMP_VIDEO_4K="%s"' % value, text)
        else:
            text = text.rstrip("\n") + '\nJMP_VIDEO_4K="%s"\n' % value
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as err:
        stbcommon.log_to("keys", "настройка не записалась: %s" % err)
        return False
    _state["mode"] = ""
    stbcommon.log_to("keys", "JMP_VIDEO_4K = %s" % value)
    check()
    return True


def toggle():
    """Листнуть режим по кругу: off → auto → all → off."""
    current = video_mode()
    value = VALUES[(VALUES.index(current) + 1) % len(VALUES)]
    if not set_value(value):
        toast("настройка не записалась — режим не изменён")
        return current
    toast({"off": "4K выключен: 1080p",
           "auto": "4K: только 4K-фильмы",
           "all": "4K: все фильмы"}[value])
    return value


def cmd(argv=()):
    """stb mode4k [off|auto|all|on|toggle|status]."""
    what = (argv[0] if argv else "status").strip().lower()
    if what == "status":
        print("%s (режим экрана: %s)" % (video_mode(), current_mode()))
        return 0
    if what == "toggle":
        print(toggle())
        return 0
    if what == "on":
        what = "all"
    if what not in VALUES:
        print("usage: stb mode4k [off|auto|all|toggle|status]", file=sys.stderr)
        return 2
    if not set_value(what):
        print("не удалось записать JMP_VIDEO_4K", file=sys.stderr)
        return 1
    print(what)
    return 0
