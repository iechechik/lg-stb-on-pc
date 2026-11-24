"""Протокол stb ↔ stb-tv-link: разбор команд демона без телевизора.

Проверяется то, что однажды уже ломалось: mute приходит с полем `on`,
а демон читал `state` — звук включался вместо выключения; `vol` с числом
игнорировал уровень и делал «громче».
"""
import asyncio
import importlib.machinery
import importlib.util
import os
import time

import pytest

ROOT = os.environ.get("STB_ROOT", "/opt/stb")


@pytest.fixture(scope="module")
def link():
    loader = importlib.machinery.SourceFileLoader("stblink", os.path.join(ROOT, "bin/stb-tv-link"))
    spec = importlib.util.spec_from_loader("stblink", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class FakeClient:
    """Заглушка вместо телевизора: запоминает, что у него попросили."""

    def __init__(self):
        self.calls = []

    async def button(self, name):
        self.calls.append(("button", name))

    async def volume_up(self):
        self.calls.append(("volume_up", None))

    async def volume_down(self):
        self.calls.append(("volume_down", None))

    async def set_volume(self, level):
        self.calls.append(("set_volume", level))

    async def set_mute(self, on):
        self.calls.append(("set_mute", on))

    async def power_off(self):
        self.calls.append(("power_off", None))

    async def set_input(self, ident):
        self.calls.append(("set_input", ident))

    async def get_power_state(self):
        return {"state": "Active"}

    async def get_sound_output(self):
        return "external_arc"

    async def get_current_app(self):
        return "com.webos.app.hdmi3"


def run(link, req):
    client = FakeClient()
    result = asyncio.run(link.dispatch(client, req["cmd"], req))
    return client.calls, result


@pytest.mark.parametrize("req,expected", [
    ({"cmd": "mute", "on": True}, ("set_mute", True)),
    ({"cmd": "mute", "on": False}, ("set_mute", False)),
    ({"cmd": "mute", "state": "on"}, ("set_mute", True)),
    ({"cmd": "mute", "state": "off"}, ("set_mute", False)),
])
def test_mute(link, req, expected):
    calls, _ = run(link, req)
    assert calls == [expected]


@pytest.mark.parametrize("req,expected", [
    ({"cmd": "vol", "level": 12}, ("set_volume", 12)),
    ({"cmd": "vol", "level": 0}, ("set_volume", 0)),
    ({"cmd": "vol", "dir": "up"}, ("volume_up", None)),
    ({"cmd": "vol", "dir": "down"}, ("volume_down", None)),
])
def test_volume(link, req, expected):
    calls, _ = run(link, req)
    assert calls == [expected]


def test_power_on_is_refused(link):
    calls, result = run(link, {"cmd": "power", "state": "on"})
    assert calls == []
    assert result["ok"] is False


def test_power_off(link):
    calls, result = run(link, {"cmd": "power", "state": "off"})
    assert calls == [("power_off", None)]
    assert result["ok"] is True


def test_state_marks_update(link):
    _, result = run(link, {"cmd": "state"})
    updated = result["state"].get("updated")
    assert updated and time.time() - updated < 30


def test_unknown_command(link):
    _, result = run(link, {"cmd": "нет-такой"})
    assert result["ok"] is False
