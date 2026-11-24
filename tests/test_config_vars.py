"""Согласованность кода и конфига: все переменные из кода есть в stb.conf."""
import pathlib
import re

ROOT = pathlib.Path("/opt/stb")

# переменные, которые задаются извне и в конфиге не нужны
ALLOWED = {"STB_CONFIG", "STB_CONFIG_DIR", "STB_ROOT", "STB_TV_SOCK"}


def conf_keys():
    text = (ROOT / "config/stb.conf").read_text(encoding="utf-8")
    return set(re.findall(r"^([A-Z][A-Z0-9_]*)=", text, re.M))


def code_files():
    files = list((ROOT / "bin").glob("*"))
    files += [p for p in (ROOT / "lib").glob("*") if p.is_file()]
    files += list((ROOT / "web").glob("*.py"))
    return [f for f in files if f.is_file()]


def used_keys():
    """Какие ключи код спрашивает у stbconf."""
    used = {}
    for path in code_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for key in re.findall(r'stbconf\.get\(\s*"([A-Z][A-Z0-9_]*)"', text):
            used.setdefault(key, set()).add(path.name)
    return used


def test_every_used_key_exists_in_config():
    known = conf_keys()
    missing = {k: sorted(v) for k, v in used_keys().items()
               if k not in known and k not in ALLOWED}
    assert not missing, "код спрашивает ключи, которых нет в stb.conf: %s" % missing


def test_config_has_no_duplicate_keys():
    text = (ROOT / "config/stb.conf").read_text(encoding="utf-8")
    keys = re.findall(r"^([A-Z][A-Z0-9_]*)=", text, re.M)
    duplicates = {k for k in keys if keys.count(k) > 1}
    assert not duplicates, "ключи повторяются в stb.conf: %s" % sorted(duplicates)
