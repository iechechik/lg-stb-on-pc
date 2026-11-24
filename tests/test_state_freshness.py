"""Свежесть состояния по полям и безопасное периодическое обновление.

Проверяется то, на что указало ревью: ответ на вопрос о звуке не должен делать
свежим устаревшее питание, а зависший запрос звука не должен держать очередь
команд вечно.
"""
import asyncio
import importlib.machinery
import importlib.util
import os
import time

import pytest

ROOT = os.environ.get("STB_ROOT", "/opt/stb")


@pytest.fixture(scope="module")
def link():
    loader = importlib.machinery.SourceFileLoader("stblink_age", os.path.join(ROOT, "bin/stb-tv-link"))
    spec = importlib.util.spec_from_loader("stblink_age", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class SilentPower:
    """Телевизор молчит про питание, но отвечает про звук и приложение."""

    async def get_power_state(self):
        raise RuntimeError("нет ответа на get_power_state")

    async def get_sound_output(self):
        return "external_arc"

    async def get_current_app(self):
        return "com.webos.app.hdmi3"


class HungSound:
    """Телевизор, у которого запрос звука зависает."""

    def __init__(self):
        self.closed = False

    async def get_sound_output(self):
        await asyncio.sleep(3600)

    async def close(self):
        self.closed = True


def test_power_stays_stale_when_others_answer(link):
    link.STATE.update({"power": "Active", "power_updated": time.time() - 600,
                       "updated": time.time() - 600})
    result = asyncio.run(link.cmd_state(SilentPower()))
    assert result["ok"] is True
    # Питание не обновилось: значение прежнее, возраст прежний.
    assert result["state"]["power"] == "Active"
    assert result["ages"]["power"] >= 599
    # А звук и приложение — свежие.
    assert result["ages"]["sound"] is not None and result["ages"]["sound"] < 5
    assert result["ages"]["app"] is not None and result["ages"]["app"] < 5


def test_refresh_sound_gives_up_on_hung_tv(link):
    hung = HungSound()
    link.STATE["power"] = "Active"
    link._client = hung
    started = time.time()
    ok = asyncio.run(link.refresh_sound())
    spent = time.time() - started
    assert ok is False
    # Ждали не дольше своего таймаута (плюс запас на планировщик).
    assert spent < link.PERIODIC_QUERY + 2
    # Замок свободен: следующая команда не получит «демон занят».
    assert link._lock.locked() is False
    # Мёртвый клиент снят, чтобы следующая команда подняла новое соединение.
    assert link._client is None


def test_refresh_sound_skips_when_tv_off(link):
    link.STATE["power"] = "Suspend"
    link._client = HungSound()
    assert asyncio.run(link.refresh_sound()) is False
    assert link._lock.locked() is False
    link._client = None
