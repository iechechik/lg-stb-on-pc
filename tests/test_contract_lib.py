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


def test_ssap_uris_have_no_scheme():
    """bscpylgtv сам дописывает «ssap://» к uri.

    Мы однажды передали полный «luna://com.webos.service.ime/insertText»: на
    провод ушло «ssap://luna://...», телевизор ответил 404, и это было принято
    за отсутствие службы ввода. Проверка статическая: в вызовах request() не
    должно быть своей схемы.
    """
    import re

    bad = []
    for name in ("stb", "stb-tv-link", "stb-watch", "stb-wifi-remote"):
        path = os.path.join(ROOT, "bin", name)
        if not os.path.exists(path):
            continue
        src = io.open(path, encoding="utf-8").read()
        for m in re.finditer(r'request\(\s*["\'](luna|ssap)://', src):
            bad.append("%s: %s://" % (name, m.group(1)))
    assert not bad, "схема в uri ломает вызов: %s" % ", ".join(bad)


def test_tv_text_reports_refusal():
    """Отказ телевизора (returnValue: false) должен быть виден, а не «отправлено»."""
    src = io.open(os.path.join(ROOT, "bin", "stb"), encoding="utf-8").read()
    assert 'reply.get("returnValue") is False' in src
    assert "телевизор отказал" in src


def test_every_lib_module_is_in_install_check():
    """Новый модуль lib/ обязан попасть в список проверки install.sh --check.

    Иначе проверка молчит про забытый файл, и он «неожиданно» отсутствует в
    архиве — а установщик копирует каталог целиком и разницы не замечает.
    """
    import glob

    sh = io.open(os.path.join(ROOT, "install.sh"), encoding="utf-8").read()
    need = sh.split("need=\"", 1)[1].split('"', 1)[0]
    missing = []
    for path in sorted(glob.glob(os.path.join(ROOT, "lib", "*.py"))):
        rel = "lib/" + os.path.basename(path)
        if rel not in need:
            missing.append(rel)
    assert not missing, "не в списке install.sh --check: %s" % ", ".join(missing)
