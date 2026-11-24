"""Карты кнопок и диспетчер: каждое действие из карты должно быть известно."""
import os
import pathlib

ROOT = pathlib.Path(os.environ.get("STB_ROOT", "/opt/stb"))


def map_actions(path):
    """Строки «КНОПКА=действие» из карты кнопок."""
    actions = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, action = line.split("=", 1)
        actions[key.strip()] = action.split("#")[0].strip()
    return actions


def dispatcher_actions():
    """Действия, которые знает диспетчер: список в самой команде stb."""
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader("stb_cli_maps", str(ROOT / "bin/stb"))
    spec = importlib.util.spec_from_loader("stb_cli_maps", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return set(module.KEY_ACTIONS)


def known_actions():
    """Плоский список действий: метки case разложены по «|»."""
    return dispatcher_actions()


def test_wifi_map_actions_are_known():
    unknown = set(map_actions(ROOT / "config/buttons-wifi.conf").values()) - known_actions()
    assert not unknown, "в карте Wi-Fi есть неизвестные действия: %s" % sorted(unknown)


def test_bt_map_actions_are_known():
    unknown = set(map_actions(ROOT / "config/buttons-bt.conf").values()) - known_actions()
    assert not unknown, "в карте BT есть неизвестные действия: %s" % sorted(unknown)


def test_both_maps_are_not_empty():
    assert map_actions(ROOT / "config/buttons-wifi.conf")
    assert map_actions(ROOT / "config/buttons-bt.conf")
