"""Карты кнопок: действия из карт совпадают с диспетчером команд.

Проверяется стык трёх вещей: файлы карт (buttons-*.conf), таблица маршрутов
(lib/stbkeys.py) и список действий, которые понимает команда `stb key`.
Новое действие в карте без маршрута — ошибка, которую видно здесь, а не на
пульте.
"""
import importlib.machinery
import importlib.util
import os
import pathlib

import stbkeys

ROOT = pathlib.Path(os.environ.get("STB_ROOT", "/opt/stb"))


def map_actions(path):
    """Строки «КНОПКА=действие» карты: {кнопка: действие}."""
    if not isinstance(path, pathlib.Path):
        path = ROOT / "config" / path
    actions = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, action = line.split("=", 1)
        actions[key.strip()] = action.split("#")[0].strip()
    return actions


def dispatcher_actions():
    """Действия, которые знает диспетчер: KEY_ACTIONS из самой команды stb."""
    loader = importlib.machinery.SourceFileLoader("stb_cli_maps", str(ROOT / "lib/stbactions.py"))
    spec = importlib.util.spec_from_loader("stb_cli_maps", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return set(module.KEY_ACTIONS)


def test_every_action_has_a_route():
    """Каждое действие карт уходит либо в демон, либо в диспетчер."""
    known = set(stbkeys.KEY_ACTIONS) | set(stbkeys.DISPATCHER_ONLY)
    used = set(map_actions("buttons-wifi.conf").values()) | \
        set(map_actions("buttons-bt.conf").values())
    unknown = used - known
    assert not unknown, "неизвестные действия: %s" % sorted(unknown)


def test_power_and_tobox_stay_in_dispatcher():
    """Питание и возврат на приставку демон не трогают: это работа диспетчера."""
    assert stbkeys.request("power") is None
    assert stbkeys.request("tobox") is None


def test_navigation_goes_to_daemon():
    assert stbkeys.request("up") == {"cmd": "key", "name": "UP"}
    assert stbkeys.request("ok") == {"cmd": "key", "name": "ENTER"}
    assert stbkeys.request("volup") == {"cmd": "vol", "dir": "up"}


def test_digits_and_colors():
    assert stbkeys.request("5") == {"cmd": "key", "name": "5"}
    assert stbkeys.request("red") == {"cmd": "key", "name": "RED"}


def test_wifi_map_actions_are_known():
    unknown = set(map_actions("buttons-wifi.conf").values()) - dispatcher_actions()
    assert not unknown, "в карте Wi-Fi есть неизвестные действия: %s" % sorted(unknown)


def test_bt_map_actions_are_known():
    unknown = set(map_actions("buttons-bt.conf").values()) - dispatcher_actions()
    assert not unknown, "в карте BT есть неизвестные действия: %s" % sorted(unknown)


def test_both_maps_are_not_empty():
    assert map_actions("buttons-wifi.conf")
    assert map_actions("buttons-bt.conf")
