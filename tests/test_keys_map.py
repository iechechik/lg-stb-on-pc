"""Быстрый путь кнопок: всё из карт либо в таблице, либо осознанно у диспетчера."""
import pathlib

import stbkeys

ROOT = pathlib.Path("/opt/stb")


def map_actions(name):
    actions = {}
    for line in (ROOT / "config" / name).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, action = line.split("=", 1)
        actions[key.strip()] = action.split("#")[0].strip()
    return set(actions.values())


def test_every_action_has_a_route():
    """Каждое действие карт должно либо уходить в демон, либо в диспетчер."""
    known = set(stbkeys.KEY_ACTIONS) | set(stbkeys.DISPATCHER_ONLY)
    unknown = (map_actions("buttons-wifi.conf") | map_actions("buttons-bt.conf")) - known
    assert not unknown, "неизвестные действия: %s" % sorted(unknown)


def test_power_and_tobox_stay_in_dispatcher():
    assert stbkeys.request("power") is None
    assert stbkeys.request("tobox") is None


def test_navigation_goes_to_daemon():
    assert stbkeys.request("up") == {"cmd": "key", "name": "UP"}
    assert stbkeys.request("ok") == {"cmd": "key", "name": "ENTER"}
    assert stbkeys.request("volup") == {"cmd": "vol", "dir": "up"}


def test_digits_and_colors():
    assert stbkeys.request("5") == {"cmd": "key", "name": "5"}
    assert stbkeys.request("red") == {"cmd": "key", "name": "RED"}
