"""Сторож телевизора: решения по состоянию, свежесть, общий клиент."""
import asyncio
import importlib.machinery
import importlib.util
import os
import time

import pytest

ROOT = os.environ.get("STB_ROOT", "/opt/stb")


@pytest.fixture(scope="module")
def watch():
    loader = importlib.machinery.SourceFileLoader("stbwatch", os.path.join(ROOT, "bin/stb-watch"))
    spec = importlib.util.spec_from_loader("stbwatch", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


FRESH = 5      # секунд — сведения свежие


OLD = 10_000   # секунд — сведения устарели


@pytest.mark.parametrize("state,fresh,online,last_on,misses,expected", [
    # 1. состояние известно: включён только Active
    ("Active", True, True, None, 0, True),
    ("Suspend", True, True, True, 0, False),
    ("Screen Off", True, True, True, 0, False),
    # 2. состояние устарело, но телевизор в сети — экран не трогаем
    ("Suspend", False, True, True, 0, True),
    ("Active", False, True, False, 0, False),
    ("", None, True, True, 0, True),
    # 3. телевизор ушёл из сети: первый промах — ждём, второй — выключен
    ("", None, False, True, 1, True),
    ("", None, False, True, 2, False),
    ("Suspend", False, False, True, 2, False),
    # 4. ничего не знаем и никогда не знали — экран не трогаем
    ("", None, True, None, 0, False),
])
def test_decide(watch, state, fresh, online, last_on, misses, expected):
    age = FRESH if fresh else (None if fresh is None else OLD)
    assert watch.decide(state, age, online, last_on, misses) is expected


def test_cycle_off_then_on(watch):
    """Полный цикл: включён → выключили → погасло → включили → поднялось."""
    # включён
    assert watch.decide("Active", FRESH, True, None, 0) is True
    # выключили: SSAP пропал, телевизор ушёл из сети
    assert watch.decide("", None, False, True, 1) is True     # первый промах — ждём
    assert watch.decide("", None, False, True, 2) is False    # подтвердили: выключен
    # включили снова и он ответил
    assert watch.decide("Active", FRESH, True, False, 0) is True


def test_no_black_screen_when_state_unknown(watch):
    """Живой телевизор, но состояние не получено — экран гасить нельзя."""
    assert watch.decide("", None, True, True, 0) is True
    assert watch.decide("Suspend", OLD, True, True, 0) is True


def test_wake_after_network_return_counts_as_on(watch, monkeypatch):
    """Телевизор вернулся в сеть, был выключен — это пробуждение, сразу включён.

    Этот LG в ждущем режиме сеть гасит, поэтому «появился в сети» после
    отсутствия = «просыпается». Ждать SSAP нельзя: панель зажигается позже,
    а картинка должна уже быть на входе.
    """
    monkeypatch.setattr(watch, "tv_in_network", lambda: True)
    monkeypatch.setattr(watch, "daemon_ask", lambda req, timeout=5.0: {"ok": False})
    watch._last_on = False
    watch._last_state = "offline2"
    watch._last_confirmed = "Standby"   # телевизор сам сказал, что спит
    watch._net_misses = 3
    assert watch.tv_is_on() is True


def test_silent_ssap_while_online_does_not_raise_interface(watch, monkeypatch):
    """Телевизор давно в сети, SSAP молчит — это сбой связи, а не включение.

    Поднимать интерфейс в этом случае нельзя: наша сетка вылезала поверх
    открытого приложения, и человек «вылетал в сетку» на ровном месте.
    """
    monkeypatch.setattr(watch, "tv_in_network", lambda: True)
    monkeypatch.setattr(watch, "daemon_ask", lambda req, timeout=5.0: {"ok": False})
    watch._last_on = True
    watch._last_state = "online"
    watch._last_confirmed = "Active"    # телевизор работает, молчит только SSAP
    watch._net_misses = 0
    assert watch.tv_is_on() is True      # телевизор по-прежнему считается включённым
    assert watch._last_state == "online"  # но «пробуждением» это не называется


@pytest.fixture(scope="module")
def link():
    loader = importlib.machinery.SourceFileLoader("stblink_age", os.path.join(ROOT, "bin/stb-tv-link"))
    spec = importlib.util.spec_from_loader("stblink_age", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class SilentPower:
    """Телевизор молчит про питание, но отвечает про звук и приложение."""

    async def get_power_state(self):
        raise RuntimeError("нет ответа на get_power_state")

    async def get_sound_output(self):
        return "external_arc"

    async def get_current_app(self):
        return "com.webos.app.hdmi3"


class HungSound:
    """Телевизор, у которого запрос звука зависает."""

    def __init__(self):
        self.closed = False

    async def get_sound_output(self):
        await asyncio.sleep(3600)

    async def close(self):
        self.closed = True


def test_power_stays_stale_when_others_answer(link):
    link.STATE.update({"power": "Active", "power_updated": time.time() - 600,
                       "updated": time.time() - 600})
    result = asyncio.run(link.cmd_state(SilentPower()))
    assert result["ok"] is True
    # Питание не обновилось: значение прежнее, возраст прежний.
    assert result["state"]["power"] == "Active"
    assert result["ages"]["power"] >= 599
    # А звук и приложение — свежие.
    assert result["ages"]["sound"] is not None and result["ages"]["sound"] < 5
    assert result["ages"]["app"] is not None and result["ages"]["app"] < 5


def test_refresh_sound_gives_up_on_hung_tv(link):
    hung = HungSound()
    link.STATE["power"] = "Active"
    link._client = hung
    started = time.time()
    ok = asyncio.run(link.refresh_sound())
    spent = time.time() - started
    assert ok is False
    # Ждали не дольше своего таймаута (плюс запас на планировщик).
    assert spent < link.PERIODIC_QUERY + 2
    # Замок свободен: следующая команда не получит «демон занят».
    assert link._lock.locked() is False
    # Мёртвый клиент снят, чтобы следующая команда подняла новое соединение.
    assert link._client is None


def test_refresh_sound_skips_when_tv_off(link):
    link.STATE["power"] = "Suspend"
    link._client = HungSound()
    assert asyncio.run(link.refresh_sound()) is False
    assert link._lock.locked() is False
    link._client = None


def test_watchdog_does_not_trust_updated(watch, monkeypatch):
    """`updated` двигается и командами — подтверждением питания он не является."""
    fresh = time.time()
    monkeypatch.setattr(watch, "daemon_ask",
                        lambda req, timeout=5.0: {"ok": True, "state": {
                            "power": "Screen Off", "updated": fresh}})
    state, age = watch.power_state()
    assert state == "Screen Off"
    assert age is None


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


def test_jelly_diagnostics_failure_is_failsafe(watch, monkeypatch):
    class Broken:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(watch.subprocess, "run", lambda *a, **k: Broken())
    assert watch.jelly_has_window() is True
