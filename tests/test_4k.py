"""Выбор сессии плеера: по клиенту, с необязательным именем устройства."""
import importlib.util
import os
import sys

ROOT = os.environ.get("STB_ROOT", "/opt/stb")
sys.path.insert(0, os.path.join(ROOT, "lib"))


def load():
    spec = importlib.util.spec_from_file_location(
        "stb4k", os.path.join(ROOT, "lib", "stb4k.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def session(device, client, playing=True, height=2160, width=3840, paused=False, fps=23.976):
    item = {"MediaStreams": [{"Type": "Video", "Height": height, "Width": width,
                             "RealFrameRate": fps}]} if playing else None
    return {"DeviceName": device, "Client": client,
            "NowPlayingItem": item, "PlayState": {"IsPaused": paused}}


def test_choose_by_client_not_by_name():
    k = load()
    items = [session("Living Room TV", "Jellyfin Web"),
             session("renamed-box", "Jellyfin Desktop"),
             session("Seerr", "Seerr")]
    assert k.pick_session(items)["DeviceName"] == "renamed-box"


def test_skip_sessions_without_playback():
    k = load()
    items = [{"DeviceName": "tv-box1", "Client": "Jellyfin Desktop", "NowPlayingItem": None},
             session("tv-box1", "Jellyfin Desktop")]
    assert k.pick_session(items)["NowPlayingItem"] is not None


def test_device_name_narrows_choice():
    k = load()
    items = [session("other", "Jellyfin Desktop"), session("tv-box1", "Jellyfin Desktop")]
    k._conf = lambda key, default="": "tv-box1" if key == "JELLYFIN_DEVICE" else default
    assert k.pick_session(items)["DeviceName"] == "tv-box1"


def test_unknown_client_falls_back_to_playing():
    k = load()
    items = [{"DeviceName": "x", "Client": "Что-то новое", "NowPlayingItem": None},
             session("x", "Unknown Client")]
    assert k.pick_session(items)["DeviceName"] == "x"


def test_empty_sessions():
    k = load()
    assert k.pick_session([]) is None
    assert k.pick_session(None) is None


def test_playing_reads_stream_geometry(monkeypatch=None):
    k = load()
    k.sessions = lambda: [session("box", "Jellyfin Desktop", height=1600, width=3840, fps=24)]
    assert k.playing() == (1600, False, 24, 3840)
