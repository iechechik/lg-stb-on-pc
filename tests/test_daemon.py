"""Демон телевизора: протокол команд, сроки, отказы и повторы."""
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


def test_missing_daemon_marks_transport():
    from stbtv import TvDaemon

    tv = TvDaemon(path="/tmp/нет-такого-сокета.sock")
    answer = tv.ask({"cmd": "state"}, timeout=1)
    assert answer["ok"] is False
    assert answer.get("transport") is True


def test_client_waits_longer_than_daemon():
    """Клиентский срок должен быть больше бюджета демона."""
    import stbtv

    with open(os.path.join(ROOT, "bin/stb-tv-link"), encoding="utf-8") as f:
        link = f.read()
    budget = float(link.split("COMMAND_TIMEOUT = ")[1].split()[0])
    assert stbtv.DEFAULT_TIMEOUT > budget


def test_aask_single_deadline(monkeypatch):
    from stbtv import TvDaemon

    async def slow(_path):
        await asyncio.sleep(3600)

    monkeypatch.setattr(asyncio, "open_unix_connection", slow)
    tv = TvDaemon(path="/tmp/x.sock")
    started = time.monotonic()
    answer = asyncio.run(tv.aask({"cmd": "state"}, timeout=1))
    spent = time.monotonic() - started
    assert answer.get("transport") is True
    assert spent < 3


@pytest.fixture(scope="module")
def cli():
    import importlib.machinery
    import importlib.util
    import sys

    loader = importlib.machinery.SourceFileLoader("stb_cli_budget", os.path.join(ROOT, "bin/stb"))
    spec = importlib.util.spec_from_loader("stb_cli_budget", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["stb_cli_budget"] = module
    loader.exec_module(module)
    return module


class Answer:
    def __init__(self, payload):
        self.payload = payload

    def ask(self, req):
        return self.payload


def test_refusal_does_not_fall_back(cli, monkeypatch):
    """Телевизор отказал — прямое подключение не открываем."""
    calls = []
    monkeypatch.setattr(cli, "daemon", lambda: Answer({"ok": False, "msg": "нет"}))
    monkeypatch.setattr(cli, "daemon_alive", lambda: True)
    monkeypatch.setattr(cli, "cli_call", lambda *a, **k: calls.append(a))
    rc = cli.tv_command({"cmd": "key", "name": "UP"}, "button", "UP")
    assert rc == 1
    assert calls == []


def test_dead_daemon_falls_back(cli, monkeypatch):
    """Демона нет вовсе — прямое подключение разрешено."""
    calls = []

    class Done:
        returncode = 0

    monkeypatch.setattr(cli, "daemon", lambda: Answer({"ok": False, "transport": True}))
    monkeypatch.setattr(cli, "daemon_alive", lambda: False)
    monkeypatch.setattr(cli, "need_tv", lambda: None)
    monkeypatch.setattr(cli, "cli_call", lambda *a, **k: (calls.append(a), Done())[1])
    rc = cli.tv_command({"cmd": "key", "name": "UP"}, "button", "UP")
    assert rc == 0
    assert calls == [("button", "UP")]


def test_live_silent_daemon_does_not_fall_back(cli, monkeypatch):
    """Демон жив, но молчит — ждём его, второе соединение не открываем."""
    calls = []
    monkeypatch.setattr(cli, "daemon", lambda: Answer({"ok": False, "transport": True}))
    monkeypatch.setattr(cli, "daemon_alive", lambda: True)
    monkeypatch.setattr(cli, "cli_call", lambda *a, **k: calls.append(a))
    rc = cli.tv_command({"cmd": "key", "name": "UP"}, "button", "UP")
    assert rc == 1
    assert calls == []


def test_server_total_budget(link, monkeypatch):
    """Очередь + подключение + команда укладываются в один срок."""
    async def slow_ensure():
        await asyncio.sleep(30)

    async def slow_dispatch(client, cmd, req):
        await asyncio.sleep(30)

    monkeypatch.setattr(link, "ensure", slow_ensure)
    monkeypatch.setattr(link, "dispatch", slow_dispatch)
    started = time.monotonic()
    answer = asyncio.run(link.handle({"cmd": "key", "name": "UP"}))
    spent = time.monotonic() - started
    assert answer["ok"] is False
    assert spent < link.COMMAND_TIMEOUT + 2


def test_client_timeout_exceeds_server_budget(link):
    import stbtv

    assert stbtv.DEFAULT_TIMEOUT > link.COMMAND_TIMEOUT


def test_wifi_does_not_repeat_on_refusal(wifi, monkeypatch):
    monkeypatch.setattr(wifi, "daemon_alive", lambda: True)
    assert wifi.should_use_cli({"ok": False, "msg": "нет связи"}) is False
    # Живой демон, но молчит — тоже не повторяем: он может ещё выполнять.
    assert wifi.should_use_cli({"ok": False, "transport": True}) is False


def test_wifi_falls_back_only_when_daemon_down(wifi, monkeypatch):
    monkeypatch.setattr(wifi, "daemon_alive", lambda: False)
    assert wifi.should_use_cli({"ok": False, "transport": True}) is True
    assert wifi.should_use_cli({"ok": False, "msg": "отказ"}) is False


@pytest.fixture(scope="module")
def wifi():
    """Приёмник пульта как модуль: проверяются правила повтора команд."""
    loader = importlib.machinery.SourceFileLoader(
        "stb_wifi_retry", os.path.join(ROOT, "bin/stb-wifi-remote"))
    spec = importlib.util.spec_from_loader("stb_wifi_retry", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module
