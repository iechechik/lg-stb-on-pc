"""Общие помощники тестов: загрузка скриптов приставки как модулей."""
import importlib.machinery
import importlib.util
import os
import sys

import pytest

ROOT = os.environ.get("STB_ROOT", "/opt/stb")
sys.path.insert(0, os.path.join(ROOT, "lib"))
os.environ.setdefault("DISPLAY", ":0")


def load(path, name):
    """Скрипты приставки без расширения .py — грузим по явному загрузчику."""
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def faketv():
    """Приёмник пульта: кадры WebSocket, буфер текста."""
    return load(os.path.join(ROOT, "bin/stb-wifi-remote"), "stb_faketv")


@pytest.fixture(scope="session")
def stbweb():
    """Веб-сервер сетки: препроцессор плиток."""
    return load(os.path.join(ROOT, "web/stb-web.py"), "stb_web")


@pytest.fixture(scope="session")
def tvtext():
    """Утилита ввода текста в телевизор: разбор аргументов."""
    return load(os.path.join(ROOT, "bin/stb"), "stb_cli")
