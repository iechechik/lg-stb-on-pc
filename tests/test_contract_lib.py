"""Контракт с библиотекой телевизора: методы, которые мы зовём, существуют.

Тесты демона подменяют клиента своим FakeClient и потому проверяют нашу модель
библиотеки, а не саму библиотеку. Здесь — проверка на настоящем классе из
site-packages: так ловятся расхождения вроде close() вместо disconnect().
"""
import glob
import inspect
import io
import os
import sys

import pytest

ROOT = os.environ.get("STB_ROOT", "/opt/stb")


def lib():
    for pattern in ("/home/stbuser/tvctl/lib/python3*/site-packages",
                    "/usr/lib/python3/dist-packages"):
        for path in glob.glob(pattern):
            if path not in sys.path:
                sys.path.insert(0, path)
    return pytest.importorskip("bscpylgtv", reason="библиотека телевизора не установлена")


def test_close_is_media_command_not_teardown():
    """close() — это media.viewer/close: закрывает плеер, а не соединение."""
    client = lib().WebOsClient
    assert "MEDIA_CLOSE" in inspect.getsource(client.close), (
        "close() перестал быть медиакомандой — перечитать обвязку демона")
    assert "disconnect" in inspect.getsource(client), "соединение рвёт disconnect()"
    assert hasattr(client, "is_connected"), "ensure() проверяет is_connected()"


def test_our_code_disconnects_instead_of_closing_media():
    for rel in ("bin/stb-tv-link", "bin/stb"):
        src = io.open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert "client.close()" not in src, "%s: close() вместо disconnect()" % rel
        assert "dropped.close()" not in src, "%s: close() вместо disconnect()" % rel
    daemon = io.open(os.path.join(ROOT, "bin/stb-tv-link"), encoding="utf-8").read()
    assert "client.disconnect()" in daemon
    assert "is_connected()" in daemon, "ensure() должен проверять живость клиента"


def test_unknown_state_has_a_cap():
    """Затянувшееся молчание SSAP не держит «включён» вечно."""
    watch = io.open(os.path.join(ROOT, "bin/stb-watch"), encoding="utf-8").read()
    assert "TV_UNKNOWN_LIMIT" in watch
    assert "ask_power_direct" in watch
