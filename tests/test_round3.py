"""Тесты границ третьей версии: срок демона, повторы, свежесть, утечки."""
import asyncio
import importlib.machinery
import importlib.util
import os
import sys
import time

import pytest

ROOT = os.environ.get("STB_ROOT", "/opt/stb")
sys.path.insert(0, os.path.join(ROOT, "lib"))


def load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def link():
    return load(os.path.join(ROOT, "bin/stb-tv-link"), "stblink_deadline")


@pytest.fixture(scope="module")
def wifi():
    return load(os.path.join(ROOT, "bin/stb-wifi-remote"), "stb_wifi_retry")


@pytest.fixture(scope="module")
def watch():
    return load(os.path.join(ROOT, "bin/stb-watch"), "stb_watch_fresh")


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


def test_watchdog_does_not_trust_updated(watch, monkeypatch):
    """`updated` двигается и командами — подтверждением питания он не является."""
    fresh = time.time()
    monkeypatch.setattr(watch, "daemon_ask",
                        lambda req, timeout=5.0: {"ok": True, "state": {
                            "power": "Screen Off", "updated": fresh}})
    state, age = watch.power_state()
    assert state == "Screen Off"
    assert age is None


def frame(payload, opcode=0x1, fin=True):
    """Кадр с маской, как от приложения."""
    import struct

    data = payload.encode() if isinstance(payload, str) else payload
    mask = os.urandom(4)
    head = bytearray([(0x80 if fin else 0) | opcode])
    n = len(data)
    head.append(0x80 | n)
    body = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return bytes(head) + mask + body


def test_ws_reader_forgotten_on_disconnect():
    import stbws

    async def scenario():
        reader = asyncio.StreamReader()
        # Начало сообщения и обрыв: продолжения не будет.
        reader.feed_data(frame("начало", fin=False))
        reader.feed_eof()
        with pytest.raises(asyncio.IncompleteReadError):
            await stbws.read_ws_message(reader)
        return dict(stbws._PENDING)

    assert asyncio.run(scenario()) == {}


def test_jelly_diagnostics_failure_is_failsafe(watch, monkeypatch):
    class Broken:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(watch.subprocess, "run", lambda *a, **k: Broken())
    assert watch.jelly_has_window() is True

def test_watch_uses_shared_client(watch, monkeypatch):
    """Сторож ходит к демону общим клиентом, а не своим сокет-кодом."""
    seen = {}

    class Client:
        def __init__(self, path):
            seen["path"] = path

        def ask(self, req, timeout=None):
            seen["timeout"] = timeout
            return {"ok": True, "state": {"power": "Active", "power_updated": time.time()}}

    monkeypatch.setattr(watch, "TvDaemon", Client)
    answer = watch.daemon_ask({"cmd": "state"})
    assert answer["ok"] is True
    assert seen["path"] == watch.DAEMON_SOCK
    assert seen["timeout"] == watch.WATCH_TIMEOUT


def test_watch_marks_transport_when_daemon_gone(watch, monkeypatch):
    monkeypatch.setattr(watch, "DAEMON_SOCK", "/tmp/нет-демона.sock")
    answer = watch.daemon_ask({"cmd": "state"})
    assert answer["ok"] is False
    assert answer.get("transport") is True


def test_watch_power_state_without_confirmation(watch, monkeypatch):
    monkeypatch.setattr(watch, "daemon_ask",
                        lambda req, timeout=None: {"ok": False, "transport": True})
    state, age = watch.power_state()
    assert state == ""
    assert age is None
