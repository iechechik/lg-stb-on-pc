"""Помощники отметок и защита от самовызова.

История: автозамена превратила внутренний os.remove в вызов mark_clear внутри
самого mark_clear. Функция ушла в бесконечную рекурсию, съела 7 ГБ и увела
машину в своп, а тесты этого не заметили — ни один не выполнял помощник.
"""
import ast
import importlib.machinery
import importlib.util
import os
import sys

import pytest

import stbcommon
import stbdesktop

ROOT = os.environ.get("STB_ROOT", "/opt/stb")
sys.path.insert(0, os.path.join(ROOT, "lib"))
CLI = os.path.join(ROOT, "bin/stb")


@pytest.fixture(scope="module")
def cli():
    loader = importlib.machinery.SourceFileLoader("stb_cli_marks", CLI)
    spec = importlib.util.spec_from_loader("stb_cli_marks", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_markers_roundtrip(cli, tmp_path):
    """Отметка ставится, читается, снимается; возраст считается."""
    path = str(tmp_path / "mark")
    assert stbcommon.mark_read(path, "нет") == "нет"
    assert stbdesktop.mark_age(path) is None

    assert stbcommon.mark_set(path, "значение") is True
    assert stbcommon.mark_read(path) == "значение"
    assert stbdesktop.mark_age(path) == 0

    stbcommon.mark_clear(path)
    assert stbcommon.mark_read(path, "нет") == "нет"
    assert stbdesktop.mark_age(path) is None


def test_mark_clear_tolerates_missing(cli, tmp_path):
    """Снятие несуществующей отметки — не ошибка."""
    stbcommon.mark_clear(str(tmp_path / "нет-такого"))
    stbcommon.mark_clear(str(tmp_path / "a"), str(tmp_path / "b"))


def test_no_self_recursion_in_stb():
    """Ни одна функция не вызывает сама себя напрямую.

    Прямой самовызов — почти всегда следствие неудачной замены текста,
    и в работающем коде он не нужен: все циклы написаны явно.
    """
    text = open(CLI, encoding="utf-8").read()
    tree = ast.parse(text)
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        calls = {c.func.id for c in ast.walk(node)
                 if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        if node.name in calls:
            bad.append("%s (строка %d)" % (node.name, node.lineno))
    assert not bad, "самовызов: " + ", ".join(bad)
