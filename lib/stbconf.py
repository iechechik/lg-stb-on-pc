#!/usr/bin/env python3
"""stbconf — чтение /etc/stb/config и вычисление адресов для python-служб.

    import sys; sys.path.insert(0, "/opt/stb/lib")
    import stbconf
    stbconf.get("TV_IP")          # значение из конфига
    stbconf.own_ip()              # адрес приставки в домашней сети
    stbconf.broadcast()           # широковещательный адрес
"""
import ipaddress
import os
import subprocess

CONFIG_DIR = os.environ.get("STB_CONFIG_DIR", "/opt/stb/config")
CONFIG = os.environ.get("STB_CONFIG", os.path.join(CONFIG_DIR, "stb.conf"))


def _clean(line):
    """Убирает комментарий в конце строки, не трогая кавычки."""
    out = []
    quote = None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out).strip()


def load(path=None):
    """Читает файл вида VAR="значение" и возвращает словарь."""
    path = path or CONFIG
    data = {}
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = _clean(raw)
                if not line or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                if key:
                    data[key] = value
    except OSError:
        pass
    return data


CFG = load()


def get(key, default=""):
    value = CFG.get(key, default)
    return default if value in (None, "") else value


def lan_cidr(iface=None):
    """Адрес интерфейса в виде 192.168.1.34/24 (или пустая строка)."""
    iface = iface or get("LAN_IF", "wlp2s0")
    try:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show", "dev", iface],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return ""
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            return parts[3]
    return ""


def own_ip(iface=None):
    """Адрес приставки в домашней сети: из конфига, иначе вычисляется."""
    fixed = CFG.get("STB_IP", "")
    if fixed:
        return fixed
    return lan_cidr(iface).split("/")[0]


def broadcast(iface=None):
    """Широковещательный адрес домашней сети."""
    fixed = CFG.get("STB_BCAST", "")
    if fixed:
        return fixed
    cidr = lan_cidr(iface)
    if not cidr:
        return ""
    try:
        return str(ipaddress.IPv4Interface(cidr).network.broadcast_address)
    except Exception:  # noqa: BLE001
        return ""
