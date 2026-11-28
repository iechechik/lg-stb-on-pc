"""Окно сетки после смены разрешения: когда нужен повторный fullscreen."""
import importlib.util
import os
import sys

ROOT = os.environ.get("STB_ROOT", "/opt/stb")
sys.path.insert(0, os.path.join(ROOT, "lib"))


def load():
    spec = importlib.util.spec_from_file_location("stbtabs", os.path.join(ROOT, "lib", "stbtabs.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_stale_viewport_needs_refit():
    t = load()
    assert t.needs_refit(1164, 1080) is True


def test_matching_viewport_is_fine():
    t = load()
    assert t.needs_refit(1080, 1080) is False
    assert t.needs_refit(2160, 2160) is False


def test_unknown_values_do_not_trigger():
    t = load()
    assert t.needs_refit(None, 1080) is False
    assert t.needs_refit(1080, None) is False
