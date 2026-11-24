"""Цикл «телевизор выключили/включили» — решения сторожа без живого телевизора.

Проверяется чистая функция decide() из bin/stb-watch: по ней сторож решает,
поднимать интерфейс или гасить. Раньше эти правила менялись без проверки
цикла целиком, и каждая правка ломала соседний случай.
"""
import importlib.machinery
import importlib.util
import os

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

def test_start_unknown_does_not_power_off(watch, monkeypatch):
    """Телевизор в сети, но состояние ещё не получено — не решаем «выключен»."""
    monkeypatch.setattr(watch, "tv_in_network", lambda: True)
    monkeypatch.setattr(watch, "daemon_ask", lambda req, timeout=5.0: {"ok": False})
    watch._last_on = None
    watch._last_state = None
    assert watch.tv_is_on() is None
