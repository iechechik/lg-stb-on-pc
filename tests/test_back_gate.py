"""Логика Back: склейка дублей и двойное нажатие."""
from stbback import BackGate


def test_single_press_waits():
    """Одиночное нажатие придерживается, а не уходит сразу."""
    gate = BackGate()
    assert gate.press() == "wait"
    assert gate.pending is True
    gate.fired()
    assert gate.pending is False


def test_double_press_returns_to_box():
    gate = BackGate()
    assert gate.press() == "wait"
    assert gate.press() == "tobox"
    assert gate.pending is False


def test_triple_press_is_double_plus_single():
    gate = BackGate()
    assert gate.press() == "wait"
    assert gate.press() == "tobox"
    assert gate.press() == "wait"


def test_duplicate_events_are_merged():
    """Приложение присылает одно нажатие дважды с разницей 0–200 мс."""
    gate = BackGate(dup_gap=0.25)
    assert gate.duplicate(10.0) is False      # первое событие нажима
    assert gate.duplicate(10.05) is True      # его дубль
    assert gate.duplicate(10.19) is True      # ещё дубль
    assert gate.duplicate(10.5) is False      # новый нажим


def test_cancel_clears_pending():
    gate = BackGate()
    gate.press()
    gate.cancel()
    assert gate.pending is False
    assert gate.press() == "wait"
