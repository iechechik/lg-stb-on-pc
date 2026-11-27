#!/usr/bin/env python3
"""stbkeys — какие кнопки можно отправить телевизору напрямую, без диспетчера.

Раньше каждое нажатие в режиме телевизора запускало два процесса:
stb-key-action и внутри него tv. Здесь — таблица «действие → команда демона»;
Power и возврат на приставку остаются в диспетчере: там нужна логика.
"""
import time

# действие → (команда демона, аргумент)
KEY_ACTIONS = {
    "up": ("key", "UP"),
    "down": ("key", "DOWN"),
    "left": ("key", "LEFT"),
    "right": ("key", "RIGHT"),
    "ok": ("key", "ENTER"),
    "back": ("key", "BACK"),
    "home": ("key", "HOME"),
    "menu": ("key", "MENU"),
    "play": ("key", "ENTER"),
    "playkey": ("key", "PLAY"),
    "pausekey": ("key", "PAUSE"),
    "chup": ("key", "CHANNELUP"),
    "chdown": ("key", "CHANNELDOWN"),
    "prev": ("key", "LEFT"),
    "next": ("key", "RIGHT"),
    "info": ("key", "INFO"),
    "guide": ("key", "GUIDE"),
    "cc": ("key", "CC"),
    "exit": ("key", "EXIT"),
    "red": ("key", "RED"),
    "green": ("key", "GREEN"),
    "yellow": ("key", "YELLOW"),
    "blue": ("key", "BLUE"),
    "volup": ("vol", "up"),
    "voldown": ("vol", "down"),
    "mute": ("key", "MUTE"),
}
for _d in range(10):
    KEY_ACTIONS[str(_d)] = ("key", str(_d))

# действия, которые остаются за диспетчером (нужна логика, а не одна кнопка)
DISPATCHER_ONLY = {"power", "tobox", "del", "erase", "tab", "tabback"}


def request(action):
    """Команда демона для действия или None, если нужен диспетчер."""
    if action in DISPATCHER_ONLY:
        return None
    if action in KEY_ACTIONS:
        kind, arg = KEY_ACTIONS[action]
        if kind == "key":
            return {"cmd": "key", "name": arg}
        if kind == "vol":
            return {"cmd": "vol", "dir": arg}
    return None


def log_line(action, log_path="/var/log/stb/keys.log"):
    """Запись в общий журнал нажатий: формат тот же, что у диспетчера."""
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("%s [tv] %s → ТВ (демон)\n" % (time.strftime("%F %T"), action))
    except OSError:
        pass
