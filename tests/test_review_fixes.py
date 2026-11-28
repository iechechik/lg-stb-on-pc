"""Решения из рецензии: что гасить и какая сессия опознана."""
import importlib.util
import os
import sys

ROOT = os.environ.get("STB_ROOT", "/opt/stb")
sys.path.insert(0, os.path.join(ROOT, "lib"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "lib", path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_unknown_app_blanks_nothing():
    ss = load("stbscreensaver", "stbscreensaver.py")
    assert ss.blank_choice("", "com.webos.app.hdmi3") == "none"


def test_tv_app_blanks_panel():
    ss = load("stbscreensaver", "stbscreensaver.py")
    assert ss.blank_choice("com.webos.app.livetv", "com.webos.app.hdmi3") == "panel"


def test_our_input_blanks_output():
    ss = load("stbscreensaver", "stbscreensaver.py")
    assert ss.blank_choice("com.webos.app.hdmi3", "com.webos.app.hdmi3") == "dim"


def test_session_info_reports_transcode():
    k = load("stb4k", "stb4k.py")
    k.sessions = lambda: [{"DeviceName": "tv-box1", "Client": "Jellyfin Desktop",
                           "NowPlayingItem": {"Name": "Фильм"},
                           "PlayState": {"PlayMethod": "Transcode"},
                           "TranscodingInfo": {"VideoCodec": "h264"}}]
    info = k.session_info()
    assert info["device"] == "tv-box1"
    assert info["method"] == "Transcode"
    assert info["codec"] == "H264"


def test_session_info_empty_without_session():
    k = load("stb4k", "stb4k.py")
    k.sessions = lambda: []
    assert k.session_info() == {}
