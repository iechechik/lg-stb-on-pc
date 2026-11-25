"""Память «что показывал телевизор»: записать чужое приложение, вернуть его."""
import io
import os
import sys

ROOT = os.environ.get("STB_ROOT", "/opt/stb")
sys.path.insert(0, os.path.join(ROOT, "lib"))

import stbtvlast  # noqa: E402


def conf(**kwargs):
    base = {"TV_INPUT_ID": "HDMI_3"}
    base.update(kwargs)
    return lambda name, default=None: base.get(name, default)


def test_our_input_name():
    assert stbtvlast.ours(conf()) == "com.webos.app.hdmi3"
    assert stbtvlast.ours(conf(TV_INPUT_ID="HDMI_1")) == "com.webos.app.hdmi1"
    assert stbtvlast.ours(conf(TV_INPUT_ID="")) == ""


def test_our_input_is_not_foreign():
    assert stbtvlast.is_foreign("com.webos.app.hdmi3", conf()) is False
    assert stbtvlast.is_foreign("", conf()) is False
    assert stbtvlast.is_foreign("com.webos.app.livetv", conf()) is True


def test_remember_writes_foreign(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_TV_LAST", str(tmp_path / "tv-last"))
    assert stbtvlast.remember("com.webos.app.livetv", conf()) is True
    assert stbtvlast.last() == "com.webos.app.livetv"
    assert stbtvlast.remember("com.webos.app.livetv", conf()) is False, "то же значение — не пишем"
    assert stbtvlast.remember("com.webos.app.hdmi3", conf()) is False, "наш вход не запоминаем"
    assert stbtvlast.last() == "com.webos.app.livetv"


def test_last_is_empty_without_file(tmp_path, monkeypatch):
    monkeypatch.setenv("STB_TV_LAST", str(tmp_path / "нет-такого"))
    assert stbtvlast.last() == ""


def test_path_from_config(tmp_path, monkeypatch):
    monkeypatch.delenv("STB_TV_LAST", raising=False)
    target = str(tmp_path / "conf-last")
    assert stbtvlast.path(conf(STB_TV_LAST=target)) == target


def test_watcher_remembers_and_tile_restores():
    """Сторож запоминает, плитка открывает: и то и другое в коде."""
    watch = io.open(os.path.join(ROOT, "bin/stb-watch"), encoding="utf-8").read()
    assert "import stbtvlast" in watch
    assert "stbtvlast.remember(" in watch

    stb = io.open(os.path.join(ROOT, "bin/stb"), encoding="utf-8").read()
    start = stb.index("def cmd_live(")
    end = stb.find("\ndef ", start + 5)
    live = stb[start:] if end == -1 else stb[start:end]
    assert "stbtvlast.last(" in live, "плитка открывает запомненное"
    assert "TV_FALLBACK_APP" in live, "без памяти есть запасное приложение"
    assert "TV_RESTORE_LAST" in live, "память можно выключить"
