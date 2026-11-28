"""Карта кнопок пульта: каждое действие должно существовать."""
import io
import os
import sys

ROOT = os.environ.get("STB_ROOT", "/opt/stb")
sys.path.insert(0, os.path.join(ROOT, "lib"))

import stbactions  # noqa: E402


def parse(path):
    table = {}
    with io.open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, action = line.split("=", 1)
            action = action.split("#", 1)[0].strip()
            if name.strip() and action:
                table[name.strip().upper()] = action
    return table


def test_every_button_action_exists():
    path = os.path.join(ROOT, "config", "buttons-wifi.conf")
    table = parse(path)
    assert table, "карта кнопок пуста"
    unknown = {name: act for name, act in table.items()
               if act not in stbactions.KEY_ACTIONS}
    assert unknown == {}, "неизвестные действия: %s" % unknown


def test_inline_comment_is_not_part_of_action():
    path = os.path.join(ROOT, "config", "buttons-wifi.conf")
    table = parse(path)
    for name, act in table.items():
        assert "#" not in act, "%s: комментарий попал в действие" % name
