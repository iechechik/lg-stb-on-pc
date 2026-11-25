"""Исходники без мусора: хардкод адресов, версии Python, чужие пути, шаблоны sh.

Это дешёвые проверки «на глаз», которые ловят то, что не видно тестами
поведения: адреса, вписанные руками, прибитая версия интерпретатора,
домашние каталоги с других машин и самоссылающиеся значения по умолчанию
в shell-скриптах (${X:=${X}} молча даёт пустоту).
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path("/opt/stb")

ALLOWED_IPS = {"239.255.255.250"}      # multicast SSDP, адрес стандарта
IP = re.compile(r"\b(?!127\.0\.0\.1|0\.0\.0\.0)(?:\d{1,3}\.){3}\d{1,3}\b")
PY_VERSION = re.compile(r"python3\.\d+")
FOREIGN_HOME = re.compile(r"/home/(?!stbuser|\{|\$)[a-z_]")
OLD_TREE = re.compile(r"stb-dist|usr-local-bin|systemd/user")
SELF_REF = re.compile(r"\$\{(\w+):=\$\{\1\}\}")


def code_files():
    """Python-часть приставки: команды, библиотеки, веб-сервер."""
    files = list((ROOT / "bin").glob("*"))
    files += [p for p in (ROOT / "lib").glob("*") if p.is_file()]
    files += list((ROOT / "web").glob("*.py"))
    return [f for f in files if f.is_file()]


def shell_files():
    files = list((ROOT / "bin").glob("*")) + list((ROOT / "lib").glob("*"))
    out = []
    for path in files:
        if not path.is_file():
            continue
        try:
            first = path.open(encoding="utf-8", errors="ignore").readline()
        except OSError:
            continue
        if "sh" in first and "python" not in first:
            out.append(path)
    return out


def scan(pattern, path_filter=None):
    """Найти совпадения в исходниках: {файл: [строки]}."""
    found = {}
    for path in code_files():
        if path_filter and not path_filter(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#") or '"""' in line:
                continue                  # комментарии и докстроки не в счёт
            if pattern.search(line):
                found.setdefault(str(path), []).append(lineno)
    return found


def test_no_hardcoded_addresses():
    hits = {p: lines for p, lines in scan(IP).items() if p.endswith((".py", "stb"))}
    bad = {p: [n for n in lines if True] for p, lines in hits.items()}
    for path, lines in bad.items():
        text = pathlib.Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
        bad[path] = [n for n in lines if not set(IP.findall(text[n - 1])) & ALLOWED_IPS]
    bad = {p: l for p, l in bad.items() if l}
    assert not bad, "адреса вписаны руками: %s" % bad


def test_no_pinned_python_version():
    hits = scan(PY_VERSION)
    assert not hits, "прибитая версия Python: %s" % hits


def test_no_foreign_home_paths():
    hits = scan(FOREIGN_HOME)
    assert not hits, "чужие домашние каталоги: %s" % hits


def test_no_old_tree_references():
    hits = scan(OLD_TREE)
    assert not hits, "ссылки на старую раскладку каталогов: %s" % hits


@pytest.mark.parametrize("path", shell_files(), ids=lambda p: p.name)
def test_no_self_referencing_defaults(path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    found = SELF_REF.findall(text)
    assert not found, "%s: самоссылка в значении по умолчанию (%s)" % (path.name, found)
