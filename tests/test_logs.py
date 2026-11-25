"""Формат журналов: единая отметка времени, миллисекунды только в keys.log.

По журналам считают темп двойных нажатий и разбирают поведение после жалоб,
поэтому формат — часть контракта: дата, время, при необходимости миллисекунды
и режим, затем текст.
"""
import importlib.machinery
import importlib.util
import os
import re

import pytest

ROOT = os.environ.get("STB_ROOT", "/opt/stb")


@pytest.fixture(scope="module")
def cli():
    loader = importlib.machinery.SourceFileLoader("stb_cli_logs", os.path.join(ROOT, "bin/stb"))
    spec = importlib.util.spec_from_loader("stb_cli_logs", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture()
def logs(cli, tmp_path, monkeypatch):
    """Все разделы пишут во временные файлы, система не трогается."""
    paths = {}
    for section in ("keys", "tv", "system", "idle", "pair", "audio"):
        paths[section] = str(tmp_path / ("%s.log" % section))
    monkeypatch.setattr(cli, "LOGS", paths, raising=False)
    monkeypatch.setattr(cli, "mode_get", lambda: "nuc")
    return paths


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


def test_keys_line_has_milliseconds_and_mode(cli, logs):
    cli.log_to("keys", "right → вправо")
    line = read(logs["keys"])[0]
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} \[nuc\] right → вправо$", line)


def test_other_sections_keep_seconds(cli, logs):
    cli.log_to("tv", "boot: вход переключён")
    cli.log_to("audio", "звук приставки заглушён")
    for section in ("tv", "audio"):
        line = read(logs[section])[0]
        assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ", line), line
        assert "." not in line.split(" ")[1], "миллисекунды только в keys.log"


def test_log_to_returns_the_written_line(cli, logs):
    line = cli.log_to("system", "сторож заставки: порог 5 мин")
    assert line.endswith("сторож заставки: порог 5 мин")
    assert read(logs["system"])[0] == line


def test_unknown_section_does_not_raise(cli, logs):
    """Опечатка в имени раздела не должна ронять приставку."""
    assert cli.log_to("нет-такого", "текст")
