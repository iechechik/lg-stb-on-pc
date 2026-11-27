"""Службы комплекса: systemctl с поправкой на пользовательский менеджер.

Часть служб приставки живёт в менеджере stbuser (`systemctl --user`), часть — в
обычном. Из-под root пользовательским нужен адрес шины сеанса, и это как раз то,
что невозможно запомнить. Помнить должна команда, а не человек:

    stb service list                     — что есть и в каком состоянии
    stb service restart stb-screensaver  — перезапустить (сама найдёт менеджер)
"""
import subprocess
import sys

from stbcommon import as_user


def _norm(unit):
    return unit if "." in unit else unit + ".service"


def user_units():
    """Службы, которые stbuser держит в своём менеджере."""
    out = as_user("systemctl", "--user", "list-unit-files", "stb*",
                  "--no-legend", "--plain")
    return {line.split()[0] for line in out.stdout.splitlines() if line.strip()}


def _systemctl(unit, action, user):
    args = ["systemctl"] + (["--user"] if user else []) + [action, unit]
    if user:
        return as_user(*args, timeout=60)
    return subprocess.run(args, capture_output=True, text=True, timeout=60)


def _state(unit, user):
    return (_systemctl(unit, "is-active", user).stdout or "").strip() or "?"


def cmd_service(argv):
    """Службы комплекса: stb service list | status|restart|start|stop <служба>."""
    action = (argv[0] if argv else "list").lstrip("-")

    if action in ("list", "ls"):
        users = user_units()
        print("пользовательские (менеджер stbuser):")
        for unit in sorted(users):
            print("  %-28s %s" % (unit, _state(unit, True)))
        out = subprocess.run(["systemctl", "list-unit-files", "stb*", "--no-legend", "--plain"],
                             capture_output=True, text=True)
        system = {line.split()[0] for line in out.stdout.splitlines() if line.strip()}
        if system - users:
            print("системные:")
            for unit in sorted(system - users):
                print("  %-28s %s" % (unit, _state(unit, False)))
        return 0

    if action not in ("status", "restart", "start", "stop", "logs"):
        print("usage: stb service list | status|restart|start|stop|logs <служба>", file=sys.stderr)
        return 2
    if len(argv) < 2 or not argv[1].strip():
        print("не названа служба", file=sys.stderr)
        return 2

    unit = _norm(argv[1].strip())
    user = unit in user_units()
    if not user and not _systemctl(unit, "cat", False).returncode == 0:
        print("такой службы нет: %s (см. stb service list)" % unit, file=sys.stderr)
        return 1

    if action == "logs":
        args = (["journalctl", "--user-unit=" + unit] if user
                else ["journalctl", "-u", unit])
        args += ["-n", "40", "--no-pager", "-o", "short-iso"]
        res = as_user(*args, timeout=60) if user else subprocess.run(
            args, capture_output=True, text=True, timeout=60)
        print(((res.stdout or "") + (res.stderr or "")).rstrip())
        return res.returncode

    res = _systemctl(unit, action, user)
    text = ((res.stdout or "") + (res.stderr or "")).strip()
    if action == "status":
        print(text or "нет данных")
        return res.returncode
    if res.returncode == 0:
        state = _state(unit, user) if action in ("restart", "start") else ""
        print("%s (%s): %s%s" % (unit, "пользовательская" if user else "системная",
                                 action, " → " + state if state else ""))
        return 0

    print("%s %s — не вышло (%d)" % (unit, action, res.returncode), file=sys.stderr)
    if text:
        print(text[:400], file=sys.stderr)
    return 1
