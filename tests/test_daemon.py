"""Демон телевизора: протокол команд, сроки, отказы и повторы."""
import asyncio
import importlib.machinery
import importlib.util
import io
import os
import time

import pytest

ROOT = os.environ.get("STB_ROOT", "/opt/stb")





@pytest.fixture(scope="module")
def link():
    loader = importlib.machinery.SourceFileLoader("stblink", os.path.join(ROOT, "bin/stb-tv-link"))
    spec = importlib.util.spec_from_loader("stblink", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class FakeClient:
    """Заглушка вместо телевизора: запоминает, что у него попросили."""

    def __init__(self):
        self.calls = []

    async def button(self, name):
        self.calls.append(("button", name))

    async def volume_up(self):
        self.calls.append(("volume_up", None))

    async def volume_down(self):
        self.calls.append(("volume_down", None))

    async def set_volume(self, level):
        self.calls.append(("set_volume", level))

    async def set_mute(self, on):
        self.calls.append(("set_mute", on))

    async def power_off(self):
        self.calls.append(("power_off", None))

    async def set_input(self, ident):
        self.calls.append(("set_input", ident))

    async def get_power_state(self):
        return {"state": "Active"}

    async def get_sound_output(self):
        return "external_arc"

    async def get_current_app(self):
        return "com.webos.app.hdmi3"


def run(link, req):
    client = FakeClient()
    result = asyncio.run(link.dispatch(client, req["cmd"], req))
    return client.calls, result


@pytest.mark.parametrize("req,expected", [
    ({"cmd": "mute", "on": True}, ("set_mute", True)),
    ({"cmd": "mute", "on": False}, ("set_mute", False)),
    ({"cmd": "mute", "state": "on"}, ("set_mute", True)),
    ({"cmd": "mute", "state": "off"}, ("set_mute", False)),
])
def test_mute(link, req, expected):
    calls, _ = run(link, req)
    assert calls == [expected]


@pytest.mark.parametrize("req,expected", [
    ({"cmd": "vol", "level": 12}, ("set_volume", 12)),
    ({"cmd": "vol", "level": 0}, ("set_volume", 0)),
    ({"cmd": "vol", "dir": "up"}, ("volume_up", None)),
    ({"cmd": "vol", "dir": "down"}, ("volume_down", None)),
])
def test_volume(link, req, expected):
    calls, _ = run(link, req)
    assert calls == [expected]


def test_power_on_is_refused(link):
    calls, result = run(link, {"cmd": "power", "state": "on"})
    assert calls == []
    assert result["ok"] is False


def test_power_off(link):
    calls, result = run(link, {"cmd": "power", "state": "off"})
    assert calls == [("power_off", None)]
    assert result["ok"] is True


def test_state_marks_update(link):
    _, result = run(link, {"cmd": "state"})
    updated = result["state"].get("updated")
    assert updated and time.time() - updated < 30


def test_unknown_command(link):
    _, result = run(link, {"cmd": "нет-такой"})
    assert result["ok"] is False


def test_missing_daemon_marks_transport():
    from stbtv import TvDaemon

    tv = TvDaemon(path="/tmp/нет-такого-сокета.sock")
    answer = tv.ask({"cmd": "state"}, timeout=1)
    assert answer["ok"] is False
    assert answer.get("transport") is True


def test_client_waits_longer_than_daemon():
    """Клиентский срок должен быть больше бюджета демона."""
    import stbtv

    with open(os.path.join(ROOT, "bin/stb-tv-link"), encoding="utf-8") as f:
        link = f.read()
    budget = float(link.split("COMMAND_TIMEOUT = ")[1].split()[0])
    assert stbtv.DEFAULT_TIMEOUT > budget


def test_aask_single_deadline(monkeypatch):
    from stbtv import TvDaemon

    async def slow(_path):
        await asyncio.sleep(3600)

    monkeypatch.setattr(asyncio, "open_unix_connection", slow)
    tv = TvDaemon(path="/tmp/x.sock")
    started = time.monotonic()
    answer = asyncio.run(tv.aask({"cmd": "state"}, timeout=1))
    spent = time.monotonic() - started
    assert answer.get("transport") is True
    assert spent < 3


@pytest.fixture(scope="module")
def cli():
    import importlib.machinery
    import importlib.util
    import sys

    loader = importlib.machinery.SourceFileLoader("stb_cli_budget", os.path.join(ROOT, "bin/stb"))
    spec = importlib.util.spec_from_loader("stb_cli_budget", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["stb_cli_budget"] = module
    loader.exec_module(module)
    return module


class Answer:
    def __init__(self, payload):
        self.payload = payload

    def ask(self, req):
        return self.payload


def test_refusal_does_not_fall_back(cli, monkeypatch):
    """Телевизор отказал — прямое подключение не открываем."""
    calls = []
    monkeypatch.setattr(cli, "daemon", lambda: Answer({"ok": False, "msg": "нет"}))
    monkeypatch.setattr(cli, "daemon_alive", lambda: True)
    monkeypatch.setattr(cli, "cli_call", lambda *a, **k: calls.append(a))
    rc = cli.tv_command({"cmd": "key", "name": "UP"}, "button", "UP")
    assert rc == 1
    assert calls == []


def test_dead_daemon_falls_back(cli, monkeypatch):
    """Демона нет вовсе — прямое подключение разрешено."""
    calls = []

    class Done:
        returncode = 0

    monkeypatch.setattr(cli, "daemon", lambda: Answer({"ok": False, "transport": True}))
    monkeypatch.setattr(cli, "daemon_alive", lambda: False)
    monkeypatch.setattr(cli, "need_tv", lambda: None)
    monkeypatch.setattr(cli, "cli_call", lambda *a, **k: (calls.append(a), Done())[1])
    rc = cli.tv_command({"cmd": "key", "name": "UP"}, "button", "UP")
    assert rc == 0
    assert calls == [("button", "UP")]


def test_live_silent_daemon_does_not_fall_back(cli, monkeypatch):
    """Демон жив, но молчит — ждём его, второе соединение не открываем."""
    calls = []
    monkeypatch.setattr(cli, "daemon", lambda: Answer({"ok": False, "transport": True}))
    monkeypatch.setattr(cli, "daemon_alive", lambda: True)
    monkeypatch.setattr(cli, "cli_call", lambda *a, **k: calls.append(a))
    rc = cli.tv_command({"cmd": "key", "name": "UP"}, "button", "UP")
    assert rc == 1
    assert calls == []


def test_server_total_budget(link, monkeypatch):
    """Очередь + подключение + команда укладываются в один срок."""
    async def slow_ensure():
        await asyncio.sleep(30)

    async def slow_dispatch(client, cmd, req):
        await asyncio.sleep(30)

    monkeypatch.setattr(link, "ensure", slow_ensure)
    monkeypatch.setattr(link, "dispatch", slow_dispatch)
    started = time.monotonic()
    answer = asyncio.run(link.handle({"cmd": "key", "name": "UP"}))
    spent = time.monotonic() - started
    assert answer["ok"] is False
    assert spent < link.COMMAND_TIMEOUT + 2


def test_client_timeout_exceeds_server_budget(link):
    import stbtv

    assert stbtv.DEFAULT_TIMEOUT > link.COMMAND_TIMEOUT


def test_wifi_does_not_repeat_on_refusal(wifi, monkeypatch):
    monkeypatch.setattr(wifi, "daemon_alive", lambda: True)
    assert wifi.should_use_cli({"ok": False, "msg": "нет связи"}) is False
    # Живой демон, но молчит — тоже не повторяем: он может ещё выполнять.
    assert wifi.should_use_cli({"ok": False, "transport": True}) is False


def test_wifi_falls_back_only_when_daemon_down(wifi, monkeypatch):
    monkeypatch.setattr(wifi, "daemon_alive", lambda: False)
    assert wifi.should_use_cli({"ok": False, "transport": True}) is True
    assert wifi.should_use_cli({"ok": False, "msg": "отказ"}) is False


@pytest.fixture(scope="module")
def wifi():
    """Приёмник пульта как модуль: проверяются правила повтора команд."""
    loader = importlib.machinery.SourceFileLoader(
        "stb_wifi_retry", os.path.join(ROOT, "bin/stb-wifi-remote"))
    spec = importlib.util.spec_from_loader("stb_wifi_retry", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# --------------------------------------------------------------- отказ связи
class HangingClose:
    """Клиент, у которого disconnect() не завершается."""

    def __init__(self):
        self.disconnect_started = False

    def is_connected(self):
        return True

    async def disconnect(self):
        self.disconnect_started = True
        await asyncio.sleep(30)

    async def close(self):
        raise AssertionError("close() — это media.viewer/close, а не закрытие связи")


def test_drop_forgets_client_before_closing(link):
    """Зависшее закрытие не оставляет ссылку на старый клиент."""
    client = HangingClose()
    link._client = client
    started = time.monotonic()
    asyncio.run(link.safe_drop())
    spent = time.monotonic() - started
    assert link._client is None, "демон остался со старым клиентом"
    assert client.disconnect_started is True
    assert spent < link.DROP_TIMEOUT + 0.5


class HangingConnect:
    """Клиент, который не успевает подключиться."""

    instances = []

    def __init__(self):
        self.disconnected = False
        HangingConnect.instances.append(self)

    def is_connected(self):
        return False

    async def connect(self):
        await asyncio.sleep(30)

    async def disconnect(self):
        self.disconnected = True

    async def close(self):
        raise AssertionError("close() — это media.viewer/close, а не закрытие связи")


async def _fake_create(*args, **kwargs):
    return HangingConnect()


def test_cancelled_connect_closes_client(link, monkeypatch):
    """Отмена на подключении не оставляет открытый сокет."""
    HangingConnect.instances = []
    monkeypatch.setattr(link.bscpylgtv, "WebOsClient",
                        type("FakeWebOsClient", (), {"create": staticmethod(_fake_create)}))
    link._client = None

    async def scenario():
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(link.connect(), timeout=0.05)
        await asyncio.sleep(0.2)          # фоновое закрытие успевает пройти

    asyncio.run(scenario())
    assert link._client is None
    assert HangingConnect.instances, "клиент не создавался"
    assert all(c.disconnected for c in HangingConnect.instances), "сокет остался открытым"


def test_expired_budget_refuses_without_waiting(link, monkeypatch):
    """Вышедший срок не продлевается искусственным остатком.

    Срок нулевой: старое `max(0.1, ...)` всё равно дало бы 0.1 с и пустило
    команду дальше, новое — отказывает сразу, не дойдя до телевизора.
    """
    calls = []

    async def any_dispatch(client, cmd, req):
        calls.append(cmd)
        return {"ok": True}

    async def ready():
        return object()

    monkeypatch.setattr(link, "ensure", ready)
    monkeypatch.setattr(link, "dispatch", any_dispatch)
    monkeypatch.setattr(link, "COMMAND_TIMEOUT", 0.0)
    answer = asyncio.run(link.handle({"cmd": "key", "name": "UP"}))
    assert answer["ok"] is False
    assert calls == [], "команда ушла в телевизор при вышедшем сроке"


def test_budget_leaves_room_for_answer(link):
    """Работа и закрытие соединения оставляют клиенту запас на ответ."""
    import stbtv

    spare = stbtv.DEFAULT_TIMEOUT - (link.COMMAND_TIMEOUT + link.DROP_TIMEOUT)
    assert spare >= 1.0, "запас до клиентского срока всего %.1f с" % spare


# --------------------------------------------------- исход запроса: два класса
def test_transport_not_sent_when_daemon_absent(tmp_path):
    """Демона нет — запрос точно не ушёл."""
    import stbtv

    answer = stbtv.TvDaemon(str(tmp_path / "no.sock")).ask({"cmd": "state"}, timeout=1)
    assert answer["transport"] is True
    assert answer["sent"] is False
    assert "unknown" not in answer


def _one_shot_server(path, answer_after=None):
    """Сервер на один запрос: читает его и закрывает связь (или отвечает)."""
    import socket
    import threading

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    srv.listen(1)

    def serve():
        conn, _ = srv.accept()
        try:
            conn.recv(65536)
            if answer_after is not None:
                conn.sendall(answer_after)
        finally:
            conn.close()
            srv.close()

    threading.Thread(target=serve, daemon=True).start()
    return srv


def test_transport_unknown_after_send(tmp_path):
    """Демон принял запрос и оборвал связь: повторять нельзя."""
    import stbtv

    path = str(tmp_path / "s.sock")
    _one_shot_server(path)
    answer = stbtv.TvDaemon(path).ask({"cmd": "key", "name": "VOLUMEUP"}, timeout=2)
    assert answer["transport"] is True
    assert answer["sent"] is True
    assert answer.get("unknown") is True


def test_async_transport_unknown_after_send(tmp_path):
    import stbtv

    path = str(tmp_path / "a.sock")
    _one_shot_server(path)
    answer = asyncio.run(stbtv.TvDaemon(path).aask({"cmd": "key", "name": "VOLUMEUP"},
                                                  timeout=2))
    assert answer["transport"] is True
    assert answer["sent"] is True
    assert answer.get("unknown") is True


def test_json_without_newline_still_parsed(tmp_path):
    """Полный JSON без перевода строки — обычный ответ."""
    import stbtv

    path = str(tmp_path / "h.sock")
    _one_shot_server(path, answer_after=b'{"ok": true}')
    answer = stbtv.TvDaemon(path).ask({"cmd": "state"}, timeout=2)
    assert answer == {"ok": True}


def test_empty_answer_is_not_success(tmp_path):
    """Пустой ответ — не «нулевое состояние», а обрыв: исход неизвестен."""
    import stbtv

    path = str(tmp_path / "e.sock")
    _one_shot_server(path)                     # прочитал запрос и молча закрыл
    answer = stbtv.TvDaemon(path).ask({"cmd": "state"}, timeout=2)
    assert answer.get("ok") is not True
    assert answer["transport"] is True
    assert answer["sent"] is True

def test_cli_no_fallback_when_outcome_unknown(cli, monkeypatch):
    """Демон умер после отправки — громкость не повторяем."""
    calls = []
    monkeypatch.setattr(cli, "daemon", lambda: Answer(
        {"ok": False, "transport": True, "sent": True, "unknown": True}))
    monkeypatch.setattr(cli, "daemon_alive", lambda: False)
    monkeypatch.setattr(cli, "cli_call", lambda *a, **k: calls.append(a))
    rc = cli.tv_command({"cmd": "vol", "dir": "up"}, "volumeup")
    assert rc == 1
    assert calls == [], "команда повторена после неизвестного исхода"


def test_wifi_no_fallback_when_outcome_unknown(wifi, monkeypatch):
    monkeypatch.setattr(wifi, "daemon_alive", lambda: False)
    assert wifi.should_use_cli({"transport": True, "sent": True}) is False
    assert wifi.should_use_cli({"transport": True, "sent": False, "ok": False}) is True


# ------------------------------------------------- скрытое окно и отказ X11
class RunResult:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


@pytest.fixture
def hidden(cli, tmp_path, monkeypatch):
    """Отметка скрытого окна постарела на 20 минут; X подменяется."""
    mark = tmp_path / "stb-app-hidden"
    mark.write_text("Jellyfin Desktop", encoding="utf-8")
    old = time.time() - 20 * 60
    os.utime(str(mark), (old, old))

    killed = []
    monkeypatch.setattr(cli, "hidden_mark", lambda: str(mark))
    monkeypatch.setattr(cli, "user_env", lambda: {})
    monkeypatch.setattr(cli, "say", lambda *a, **k: None)
    monkeypatch.setattr(cli, "mark_clear", lambda *a, **k: None)
    monkeypatch.setattr(cli.stbconf, "get",
                        lambda name, default="": "10" if name == "APP_HIDE_MINUTES" else default)
    monkeypatch.setattr(cli, "jelly_kill", lambda env, why: killed.append(why))
    return killed


def test_hidden_x_error_does_not_kill_app(hidden, cli, monkeypatch):
    """xdotool не смог спросить X — приложение не закрываем."""
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda *a, **k: RunResult(returncode=3, stdout=""))
    cli.hidden_check()
    assert hidden == [], "приложение закрыто при отказе X"


def test_hidden_unviewable_unverified_does_not_kill(hidden, cli, monkeypatch):
    """Окно есть, но xwininfo не отвечает — тоже не закрываем."""
    def run(cmd, *a, **k):
        if cmd[0] == "xdotool":
            return RunResult(0, "12345\n")
        return RunResult(returncode=2, stdout="")

    monkeypatch.setattr(cli.subprocess, "run", run)
    cli.hidden_check()
    assert hidden == [], "приложение закрыто без подтверждения состояния окна"


def test_hidden_without_windows_kills(hidden, cli, monkeypatch):
    """xdotool: подходящих окон нет (код 1) — это и значит «скрыто»."""
    def run(cmd, *a, **k):
        if cmd[0] == "xdotool":
            return RunResult(1, "")
        return RunResult(returncode=1, stdout="")

    monkeypatch.setattr(cli.subprocess, "run", run)
    cli.hidden_check()
    assert hidden, "приложение не закрыто, хотя окна нет"


# --------------------------------------------- приёмник пульта без карты кнопок
def test_wifi_imports_without_keymap(tmp_path, monkeypatch):
    """Пропавшая карта кнопок не должна ронять приёмник на импорте.

    Раньше `KEYS = load_keymap()` звал `w()` до его определения: при
    отсутствующем buttons-wifi.conf модуль падал с NameError, и пульт
    переставал приниматься целиком. Заодно проверяется, что импорт не пишет
    в конфиг: UUID придумывается при старте службы, а не при загрузке модуля.
    """
    import importlib.machinery
    import importlib.util

    import stbconf

    nl = chr(10)
    monkeypatch.setenv("FAKETV_LOG", str(tmp_path / "faketv.log"))
    empty = tmp_path / "cfg"
    empty.mkdir()
    conf = empty / "stb.conf"
    original = 'WF_UUID=""' + nl
    conf.write_text(original, encoding="utf-8")
    monkeypatch.setattr(stbconf, "CONFIG", str(conf))
    monkeypatch.setattr(stbconf, "get",
                        lambda name, default="": str(empty) if name == "STB_CONFIG_DIR" else default)

    loader = importlib.machinery.SourceFileLoader(
        "stb_wifi_nokeymap", os.path.join(ROOT, "bin/stb-wifi-remote"))
    spec = importlib.util.spec_from_loader("stb_wifi_nokeymap", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    assert module.KEYS == {}
    assert conf.read_text(encoding="utf-8") == original, "импорт переписал конфиг"


# ------------------------------------------------ диспетчер кнопок в приёмнике
def test_keys_run_in_process(wifi):
    """Диспетчер загружен: иначе каждая кнопка запускает python отдельно."""
    assert hasattr(wifi, "press_in_process")
    assert wifi.STBCLI is not None, "bin/stb не загрузился как модуль"
    assert callable(wifi.STBCLI.cmd_key)


def _dispatch_block():
    src = io.open(os.path.join(ROOT, "bin/stb-wifi-remote"), encoding="utf-8").read()
    start = src.index("async def press_in_process(")
    end = src.find("\n# ---- диспетчер", start + 10)
    return src, src[start:] if end == -1 else src[start:end]


def test_subprocess_is_only_a_fallback():
    """Отдельный процесс остаётся один — если модуль не загрузился."""
    src, block = _dispatch_block()
    # Два запуска остаются только как запасные пути: демон не запущен и модуль
    # не загрузился. Обычный путь идёт через свой процесс.
    assert src.count('arun(["/opt/stb/bin/stb", "key", act])') == 2
    assert 'await press_in_process(act)' in src
    assert "asyncio.to_thread" in block, "вызов уходит в поток, цикл не блокируется"
    assert "DISPATCH_LOCK" in block, "кнопки не должны выполняться параллельно"


def test_key_failure_is_not_retried():
    """Повтор нажатия при сбое дал бы двойное срабатывание."""
    _, block = _dispatch_block()
    assert "повторять не буду" in block
