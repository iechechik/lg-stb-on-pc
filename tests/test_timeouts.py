"""Границы таймаутов: транспорт отличается от отказа, повтора нет.

Проверяется то, на что указало ревью: клиент не должен считать команду
неудачной раньше демона и не должен повторять её вторым соединением с
телевизором.
"""
import asyncio
import os
import time

import pytest

ROOT = os.environ.get("STB_ROOT", "/opt/stb")


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
