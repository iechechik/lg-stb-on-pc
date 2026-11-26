"""Проверки окон: заголовок определяет, где мы, — одно место, четыре предиката.

Раньше проверки писались строкой врозь ("Приставка" / "Mozilla"), и в разных
местах они означали разное. Здесь закреплено соглашение: сетка — приставка,
браузер — Mozilla, приложение — всё прочее с заголовком.
"""
import importlib.machinery
import importlib.util
import os

import pytest

import stbcommon

ROOT = os.environ.get("STB_ROOT", "/opt/stb")


@pytest.fixture(scope="module")
def cli():
    loader = importlib.machinery.SourceFileLoader("stb_cli_windows", os.path.join(ROOT, "bin/stb"))
    spec = importlib.util.spec_from_loader("stb_cli_windows", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


GRID = "Приставка — Mozilla Firefox"
SITE = "YouTube — Mozilla Firefox"
APP = "Jellyfin Desktop"


def test_grid_is_our_grid(cli):
    assert stbcommon.is_grid(GRID) is True
    assert stbcommon.is_grid(APP) is False


def test_browser_window_counts_as_browser(cli):
    assert stbcommon.is_browser(GRID) is True      # сетка живёт в браузере
    assert stbcommon.is_browser(SITE) is True
    assert stbcommon.is_browser(APP) is False


def test_ours_covers_grid_and_browser(cli):
    assert stbcommon.is_ours(GRID) is True
    assert stbcommon.is_ours(SITE) is True
    assert stbcommon.is_ours(APP) is False


def test_app_is_everything_else_with_title(cli):
    assert stbcommon.is_app(APP) is True
    assert stbcommon.is_app(GRID) is False
    assert stbcommon.is_app("") is False           # пустой заголовок — не приложение


def test_titles_are_single_source(cli):
    """Заголовки заданы константами, а не рассыпаны строками по коду."""
    import stbcommon
    assert stbcommon.GRID_TITLE == "Приставка"
    assert stbcommon.BROWSER_TITLE == "Mozilla"
