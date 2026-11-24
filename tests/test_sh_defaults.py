"""Самоссылки в значениях по умолчанию: ${X:=${X}} даёт пустое значение.

Такой шаблон появляется при механической замене путей и ломается молча:
переменная остаётся пустой, и программа ищет файлы в корне.
"""
import pathlib
import re

ROOT = pathlib.Path("/opt/stb")
SELF_REF = re.compile(r"\$\{(\w+):=\$\{\1\}\}")


def shell_files():
    files = list((ROOT / "bin").glob("*")) + list((ROOT / "lib").glob("*"))
    for path in files:
        if not path.is_file():
            continue
        try:
            first = path.open(encoding="utf-8", errors="ignore").readline()
        except OSError:
            continue
        if "sh" in first and "python" not in first:
            yield path


def test_no_self_referencing_defaults():
    bad = []
    for path in shell_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in SELF_REF.finditer(text):
            bad.append("%s: %s" % (path.name, match.group(0)))
    assert not bad, "самоссылки в значениях по умолчанию: %s" % bad
