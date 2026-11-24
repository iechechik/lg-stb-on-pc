"""Поиск оставшегося хардкода: адреса, версии Python, чужие домашние каталоги."""
import pathlib
import re

ROOT = pathlib.Path("/opt/stb")

ALLOWED_IPS = {"239.255.255.250"}   # multicast SSDP, адрес стандарта
IP = re.compile(r"\b(?!127\.0\.0\.1|0\.0\.0\.0)(?:\d{1,3}\.){3}\d{1,3}\b")
PY_VERSION = re.compile(r"python3\.\d+")
FOREIGN_HOME = re.compile(r"/home/(?!stbuser|\{|\$)[a-z_]")
OLD_TREE = re.compile(r"stb-dist|usr-local-bin|systemd/user")


def code_files():
    files = list((ROOT / "bin").glob("*"))
    files += [p for p in (ROOT / "lib").glob("*") if p.is_file()]
    files += list((ROOT / "web").glob("*.py"))
    return [f for f in files if f.is_file()]


def scan(pattern, skip_docstring=True):
    found = {}
    for path in code_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        hits = []
        for no, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped.startswith(chr(34)):
                continue
            if any(ip in line for ip in ALLOWED_IPS):
                continue
            if pattern.search(line):
                hits.append("%s:%d: %s" % (path.name, no, line.strip()[:80]))
        if hits:
            found[path.name] = hits
    return found


def test_no_hardcoded_addresses():
    found = scan(IP)
    assert not found, "в коде остались адреса: %s" % found


def test_no_pinned_python_version():
    found = scan(PY_VERSION)
    assert not found, "в коде прибита версия Python: %s" % found


def test_no_foreign_home_paths():
    found = scan(FOREIGN_HOME)
    assert not found, "в коде чужие домашние каталоги: %s" % found


def test_no_old_tree_references():
    found = scan(OLD_TREE)
    assert not found, "в коде ссылки на старые деревья: %s" % found
