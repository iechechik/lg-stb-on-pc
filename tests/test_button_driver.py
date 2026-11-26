"""Драйвер кнопок: порядок нажатий, сроки и цена запуска.

Двойное нажатие обрабатывает драйвер (приёмник + lib/stbgesture), одинаково в
обоих режимах; режим подключается позже — после того как драйвер сказал «одно»
или «два». Здесь закреплено то, что ломается незаметно:

  * придержанная кнопка уходит раньше новой, порядок нажатий сохраняется;
  * окно выдержки Back — 0.5 с;
  * проверка истории после одиночного Back — 0.25 с;
  * спящий телевизор отбивается проверкой порта, а не ожиданием;
  * asyncio не тянется при каждом запуске.
"""
import ast
import io
import os
import pathlib

ROOT = pathlib.Path(os.environ.get("STB_ROOT", "/opt/stb"))


def src(rel):
    return io.open(str(ROOT / rel), encoding="utf-8").read()


def test_held_key_fires_before_new_one():
    """Придержанный Back не может прийти после кнопки, нажатой следом."""
    recv = src("bin/stb-wifi-remote")
    assert "async def _flush_pending" in recv
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


def test_asyncio_imported_on_demand():
    """`stbtv` тянет asyncio: на верхнем уровне его быть не должно."""
    tree = ast.parse(src("lib/stbcommon.py"))
    top = [n.module for n in tree.body
           if isinstance(n, ast.ImportFrom) and n.module]
    assert "stbtv" not in top
