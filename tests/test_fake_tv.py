"""Поддельный телевизор: проверка клиента без настоящего ТВ."""
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time

import pytest

ROOT = os.environ.get("STB_ROOT", "/opt/stb")
# Свой каталог на прогон: чужой или старый сокет (например root-овый после
# ручного запуска) больше не мешает поднять поддельный телевизор.
WORKDIR = tempfile.mkdtemp(prefix="stb-test-")
SOCK = os.path.join(WORKDIR, "tv.sock")
LOG = os.path.join(WORKDIR, "tv.log")


@pytest.fixture(scope="module")
def fake_tv():
    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "tests/fake_tv.py"),
         "--socket", SOCK, "--log", LOG, "--delay", "0.01"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.2)
    yield SOCK
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    shutil.rmtree(WORKDIR, ignore_errors=True)


def test_client_reads_state(fake_tv):
    from stbtv import TvDaemon

    tv = TvDaemon(fake_tv)
    state = tv.state()
    assert state["power"] == "Active"
    assert state["sound"] == "external_arc"
    assert state["app"].startswith("com.webos.app.")


def test_key_and_volume_commands(fake_tv):
    from stbtv import TvDaemon

    tv = TvDaemon(fake_tv)

    async def scenario():
        return (await tv.key("up")).get("ok"), (await tv.vol("up")).get("ok")

    key_ok, vol_ok = asyncio.run(scenario())
    assert key_ok is True
    assert vol_ok is True


def test_requests_are_logged(fake_tv):
    """Журнал поддельного ТВ показывает, что запросы действительно дошли."""
    with open(LOG, encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
    assert any("state" in line for line in lines)
    assert any("key" in line for line in lines)
