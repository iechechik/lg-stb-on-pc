"""Тесты на решение заставки и на решение 4K: без сети, без X."""
import importlib.util
import os
import sys

import pytest

import stbcommon


@pytest.fixture(autouse=True)
def silent_log(monkeypatch):
    """Журнал кнопок — боевой файл; тесты в него писать не должны."""
    monkeypatch.setattr(stbcommon, "log_to", lambda *a, **kw: None)


ROOT = os.environ.get("STB_ROOT", "/opt/stb")
sys.path.insert(0, os.path.join(ROOT, "lib"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "lib", path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def settle(k):
    """Разрешить смену: намерение уже зарегистрировано и «ждёт» давно."""
    k._state["want_since"] = 0.0


def test_quiet_is_zero_while_frames_unknown():
    ss = load("stbscreensaver", "stbscreensaver.py")
    assert ss.quiet_ms(1000.0, 400.0, blind_since=900.0) == 0


def test_quiet_counts_when_frames_are_fresh():
    ss = load("stbscreensaver", "stbscreensaver.py")
    assert ss.quiet_ms(1000.0, 400.0, blind_since=0.0) == 600000


def test_off_keeps_hd_even_for_4k_stream():
    k = load("stb4k", "stb4k.py")
    calls = []
    k.video_mode = lambda: "off"
    k.playing = lambda: (2160, False, 24, 3840)
    k.player_active = lambda: True
    k.set_mode = lambda mode, rate=None: calls.append(mode) or True
    k.check()            # регистрация намерения
    settle(k)
    k.check()            # смена
    assert calls and calls[-1] == k.MODE_HD


def test_all_lifts_fhd_to_4k():
    k = load("stb4k", "stb4k.py")
    calls = []
    k.video_mode = lambda: "all"
    k.playing = lambda: (1080, False, 23.976, 1920)
    k.player_active = lambda: True
    k.set_mode = lambda mode, rate=None: calls.append((mode, rate)) or True
    k.check()
    settle(k)
    k.check()
    assert calls[-1][0] == k.MODE_4K
    assert calls[-1][1] == "23.98"


def test_auto_keeps_fhd_at_1080():
    k = load("stb4k", "stb4k.py")
    calls = []
    k.video_mode = lambda: "auto"
    k.playing = lambda: (1080, False, 25, 1920)
    k.player_active = lambda: True
    k.set_mode = lambda mode, rate=None: calls.append(mode) or True
    k.check()
    settle(k)
    k.check()
    assert calls[-1] == k.MODE_HD


def test_auto_recognises_wide_4k():
    k = load("stb4k", "stb4k.py")
    calls = []
    k.video_mode = lambda: "auto"
    k.playing = lambda: (1600, False, 24, 3840)     # 3840x1600 — тоже 4K
    k.player_active = lambda: True
    k.set_mode = lambda mode, rate=None: calls.append(mode) or True
    k.check()
    settle(k)
    k.check()
    assert calls[-1] == k.MODE_4K


def test_hysteresis_does_not_switch_on_single_flicker():
    k = load("stb4k", "stb4k.py")
    calls = []
    k.video_mode = lambda: "all"
    k.playing = lambda: (1080, False, 24, 1920)
    k.player_active = lambda: True
    k.set_mode = lambda mode, rate=None: calls.append(mode) or True
    k.check()                    # заметили фильм, но ещё не переключаем
    assert k.MODE_4K not in calls        # экран в 4K не дёргаем
    k.player_active = lambda: False      # фокус мигнул
    k.check()
    assert k.MODE_4K not in calls        # и после мигания 4K не включился


def test_hysteresis_switches_after_dwell():
    k = load("stb4k", "stb4k.py")
    calls = []
    k.video_mode = lambda: "all"
    k.playing = lambda: (1080, False, 24, 1920)
    k.player_active = lambda: True
    k.set_mode = lambda mode, rate=None: calls.append(mode) or True
    k.check()
    settle(k)
    k.check()
    assert calls == [k.MODE_4K]


def test_set_mode_failure_keeps_state():
    k = load("stb4k", "stb4k.py")

    class Failed:
        returncode = 1
        stderr = "xrandr: иди сюда"

    k.stbcommon.as_user = lambda *a, **kw: Failed()
    k.current_mode = lambda: "1920x1080"
    k._state["mode"] = ""
    assert k.set_mode(k.MODE_4K, "23.98") is False
    assert k._state["mode"] == ""        # состояние не обманывает
