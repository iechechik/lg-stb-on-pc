"""Кнопки с выдержкой: одиночное и двойное нажатие как два события."""
import os
import sys

ROOT = os.environ.get("STB_ROOT", "/opt/stb")
sys.path.insert(0, os.path.join(ROOT, "lib"))

import stbgesture  # noqa: E402


def conf(**kwargs):
    """Подставной конфиг: getter(имя, по умолчанию)."""
    return lambda name, default=None: kwargs.get(name, default)


def test_window_and_gap_come_from_config():
    keys = stbgesture.load(conf(GESTURES="BACK", DOUBLE_BACK="0.8", DUP_BACK="0.2"))
    assert list(keys) == ["BACK"]
    assert keys["BACK"].window == 0.8
    assert keys["BACK"].dup_gap == 0.2


def test_defaults_without_config():
    keys = stbgesture.load(conf())
    assert list(keys) == ["BACK"], "по умолчанию через слой идёт только Back"
    assert keys["BACK"].window == stbgesture.DEFAULT_WINDOW
    assert keys["BACK"].dup_gap == stbgesture.DEFAULT_DUP_GAP


def test_new_key_needs_only_config():
    """Новая кнопка — одна строка в GESTURES, код не меняется."""
    keys = stbgesture.load(conf(GESTURES="BACK HOME", DOUBLE_HOME="0.5"))
    assert set(keys) == {"BACK", "HOME"}
    assert keys["HOME"].window == 0.5
    assert keys["HOME"].dup_gap == stbgesture.DEFAULT_DUP_GAP


def test_broken_number_is_default():
    keys = stbgesture.load(conf(GESTURES="BACK", DOUBLE_BACK="полторы"))
    assert keys["BACK"].window == stbgesture.DEFAULT_WINDOW


def test_single_press_waits_then_fires():
    gest = stbgesture.Gesture(window=1.0)
    assert gest.press() == "wait"
    assert gest.pending is True
    gest.fired()
    assert gest.pending is False


def test_double_press_inside_window():
    gest = stbgesture.Gesture(window=1.0)
    assert gest.press() == "wait"
    assert gest.press() == "double"
    assert gest.pending is False


def test_third_press_starts_new_pair():
    gest = stbgesture.Gesture(window=1.0)
    assert gest.press() == "wait"
    assert gest.press() == "double"
    assert gest.press() == "wait", "третье нажатие — начало новой пары"


def test_duplicate_events_glued():
    gest = stbgesture.Gesture(dup_gap=0.25)
    assert gest.duplicate(10.0) is False
    assert gest.duplicate(10.05) is True
    assert gest.duplicate(10.19) is True
    assert gest.duplicate(10.5) is False


def test_double_action_name():
    assert stbgesture.double_action("BACK") == "back-double"
    assert stbgesture.double_action(" home ") == "home-double"
