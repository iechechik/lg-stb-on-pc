"""Драйвер кнопок: порядок нажатий, гонка таймера и цена запуска.

Двойное нажатие обрабатывает драйвер (приёмник + lib/stbgesture), одинаково в
обоих режимах; режим подключается позже. Здесь закреплено то, что ломается
незаметно:

  * придержанное нажатие уходит ровно ОДИН раз — даже если отмена опоздала,
    а срок уже сработал (это и была гонка двух потоков);
  * придержанное уходит раньше новой кнопки, порядок нажатий сохраняется;
  * окно выдержки Back — 0.5 с, проверка истории — 0.25 с;
  * спящий телевизор отбивается проверкой порта, а не ожиданием;
  * резервный запрос питания идёт питоном из tvctl и пользователем из конфига;
  * asyncio не тянется при каждом запуске.
"""
import ast
import io
import os
import pathlib

import stbgesture

ROOT = pathlib.Path(os.environ.get("STB_ROOT", "/opt/stb"))


def src(rel):
    return io.open(str(ROOT / rel), encoding="utf-8").read()


# ── гонка придержанного нажатия ───────────────────────────────────────────────


class FakeHandle:
    """Срок в миниатюре: горит ровно один раз, если не отменён."""

    def __init__(self, fn, args):
        self.fn = fn
        self.args = args
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class DeafHandle(FakeHandle):
    """Отмена опоздала: таймер всё равно выстрелит (та самая гонка)."""

    def cancel(self):
        pass


class FakeLoop:
    """Цикл событий в миниатюре: сроки лежат, пока их не подожгут."""

    def __init__(self, handle_cls=FakeHandle):
        self.handle_cls = handle_cls
        self.timers = []

    def call_later(self, delay, fn, *args):
        handle = self.handle_cls(fn, args)
        self.timers.append(handle)
        return handle

    def fire(self):
        """Поджечь сроки, как это сделал бы цикл."""
        for handle in list(self.timers):
            self.timers.remove(handle)
            if not handle.cancelled:
                handle.fn(*handle.args)


def test_flushed_hold_does_not_fire_twice():
    """Кнопка пришла раньше окна: отправили сразу, таймер уже не должен."""
    loop = FakeLoop()
    fired = []
    led = stbgesture.Ledger()
    led.hold(loop, "BACK", 0.5, fired.append)

    assert led.take("BACK") is True     # пришла другая кнопка — забрали себе
    loop.fire()                          # срок сработал, но нажатие уже ушло

    assert fired == []


def test_timer_fired_then_flush_is_noop():
    """Окно истекло раньше кнопки: повторно то же нажатие не отправляем."""
    loop = FakeLoop()
    fired = []
    led = stbgesture.Ledger()
    led.hold(loop, "BACK", 0.5, fired.append)

    loop.fire()
    assert fired == ["BACK"]
    assert led.take("BACK") is False
    loop.fire()
    assert fired == ["BACK"]


def test_late_cancel_still_fires_once():
    """Гонка: отмена не сработала, срок выстрелил. Действие всё равно одно."""
    loop = FakeLoop(handle_cls=DeafHandle)
    fired = []
    led = stbgesture.Ledger()
    led.hold(loop, "BACK", 0.5, fired.append)

    assert led.take("BACK") is True     # учёт забрали, но таймер жив
    loop.fire()                          # таймер вошёл в обработчик после отмены

    assert fired == []


def test_other_than_ignores_own_key():
    """Своя кнопка не попадает в список тех, кого отправляют первыми."""
    led = stbgesture.Ledger()
    loop = FakeLoop()
    led.hold(loop, "BACK", 0.5, lambda name: None)
    led.hold(loop, "OK", 0.5, lambda name: None)

    assert led.other_than("BACK") == ["OK"]
    assert sorted(led.names()) == ["BACK", "OK"]


# ── источник правки: то, что легко потерять при следующей уборке ──────────────


def test_receiver_uses_ledger_not_threads():
    recv = src("bin/stb-wifi-remote")
    assert "PENDING = stbgesture.Ledger()" in recv
    assert "PENDING.hold(loop" in recv
    assert "threading" not in recv


def test_held_key_fires_before_new_one():
    recv = src("bin/stb-wifi-remote")
    assert 'await _flush_pending()\n            w(f"КНОПКА: {name}")' in recv


def test_double_back_window():
    conf = src("config/stb.conf")
    assert [line for line in conf.splitlines() if line.startswith("DOUBLE_BACK=")] \
        == ['DOUBLE_BACK="0.5"']


def test_back_history_check_is_short():
    act = src("lib/stbactions.py")
    assert "time.sleep(0.25)" in act
    assert "time.sleep(0.6)" not in act


def test_sleeping_tv_answers_fast():
    link = src("bin/stb-tv-link")
    assert "async def port_open" in link
    assert "телевизор спит" in link


def test_power_probe_uses_venv_python():
    """Резервный запрос питания: питон из tvctl, пользователь из конфига."""
    watch = src("bin/stb-watch")
    body = watch.split("def ask_power_direct")[1].split("\ndef ")[0]
    assert "/usr/bin/python3" not in body
    assert '"tvctl", "bin", "python"' in body
    assert "STB_USER" in body and '"stbuser"' not in body


def test_asyncio_imported_on_demand():
    tree = ast.parse(src("lib/stbcommon.py"))
    top = [n.module for n in tree.body
           if isinstance(n, ast.ImportFrom) and n.module]
    assert "stbtv" not in top


def test_first_press_after_blank_is_swallowed():
    """Нажатие, снимающее заставку, не должно доходить до приложения."""
    recv = src("bin/stb-wifi-remote")
    before_pointer = recv.split('if text.startswith("type:move")')[0]
    assert "screensaver_present()" in before_pointer
    assert "close_screensaver()" in before_pointer
    act = src("lib/stbactions.py")
    body = act.split("def cmd_key(argv):")[1].split("\ndef ")[0]
    assert "screensaver_on()" in body and "close_splash_now()" in body
