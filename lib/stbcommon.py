#!/usr/bin/env python3
"""stbcommon — общие помощники приставки: метки в /run/stb, журналы, пользователь
сессии, режим пульта, имена окон, вызов демона и библиотеки телевизора.

Выделено из bin/stb без изменения поведения; зависит только от stdlib
и lib/stbconf.py, lib/stbtv.py."""
import os
import subprocess
import sys
import time
import stbconf


STB_HOME = stbconf.get("STB_HOME", "/home/stbuser")
STB_USER = stbconf.get("STB_USER", "stbuser")
TV = stbconf.get("TV_IP", "")
TV_PORT = stbconf.get("TV_PORT", "3000")

# Путь к bin/stb для самоперезапуска (команды зовут сами себя с другими
# аргументами). bin/stb уточняет его при старте через __file__; в тестах
# остаётся sys.argv[0], и это ожидаемо.
SELF = sys.argv[0]

MODE_FILE = "/run/stb/mode"
SCREEN_FLAG = "/run/stb/screensaver"
LOGS = {
    "tv": "/var/log/stb/tv.log",
    "system": "/var/log/stb/system.log",
    "keys": "/var/log/stb/keys.log",
    "idle": "/var/log/stb/idle.log",
    "pair": "/var/log/stb/pair.log",
    "audio": "/var/log/stb/audio.log",
}


def mark_set(path, value=""):
    """Поставить отметку: файл с необязательным содержимым. False — не удалось."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(value)
        return True
    except OSError:
        return False


def mark_clear(*paths):
    """Снять отметки. Отсутствие файла ошибкой не считается."""
    for path in paths:
        try:
            os.remove(path)
        except OSError:
            pass


def mark_read(path, default=""):
    """Содержимое отметки или значение по умолчанию."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or default
    except OSError:
        return default


def log_to(section, msg, echo=False):
    """Строка в журнал раздела.

    Формат: «дата время.мс [режим] текст». Миллисекунды и режим пишутся только
    в keys.log — по нему меряют темп двойных нажатий; остальные разделы
    обходятся секундами. Возвращает записанную строку.
    """
    stamp = time.strftime("%F %T")
    if section == "keys":
        stamp = "%s.%03d [%s]" % (stamp, int(time.time() * 1000) % 1000, mode_get())
    line = "%s %s" % (stamp, msg)
    try:
        with open(LOGS[section], "a", buffering=1, encoding="utf-8") as f:
            f.write(line + "\n")
    except (OSError, KeyError):
        pass
    if echo:
        print(line, flush=True)
    return line


TVCTL = os.path.join(STB_HOME, "tvctl")
# ключ доступа обязателен: без него библиотека считает приставку новой
# и уходит регистрироваться — из-под root это выглядело как зависание
CLI = [os.path.join(TVCTL, "bin", "bscpylgtvcommand"),
       "-m", os.path.join(TVCTL, "nuc_manifest.json"),
       "-p", os.path.join(STB_HOME, ".aiopylgtv.sqlite")]
PY = os.path.join(TVCTL, "bin", "python")


def say(msg):
    """Короткая отметка о действии приставки — в журнал телевизора."""
    log_to("tv", msg)


def daemon():
    """Клиент демона телевизора.

    Импорт внутри: `stbtv` тянет asyncio, а это около 145 мс на каждый запуск.
    Платить их за кнопку пульта незачем — asyncio нужен только тем командам,
    что разговаривают с телевизором.
    """
    from stbtv import TvDaemon  # noqa: PLC0415

    return TvDaemon()


def user_uid():
    """UID пользователя приставки — один источник для всех, кому он нужен."""
    import pwd
    return pwd.getpwnam(STB_USER).pw_uid


def user_gid():
    import pwd
    return pwd.getpwnam(STB_USER).pw_gid


def user_env():
    uid = user_uid()
    return dict(os.environ, HOME=STB_HOME, DISPLAY=":0",
                XAUTHORITY=os.path.join(STB_HOME, ".Xauthority"),
                XDG_RUNTIME_DIR="/run/user/%d" % uid,
                DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/%d/bus" % uid)


def as_user(*args, **kwargs):
    """Выполнить от имени пользователя приставки (если мы root)."""
    if os.getuid() == 0:
        return subprocess.run(["sudo", "-n", "-u", STB_USER, "env"] +
                              ["%s=%s" % (k, v) for k, v in user_env().items()
                               if k in ("HOME", "DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR",
                                        "DBUS_SESSION_BUS_ADDRESS")] + list(args),
                              capture_output=True, text=True, timeout=kwargs.get("timeout", 40))
    return subprocess.run(list(args), env=user_env(),
                          capture_output=True, text=True, timeout=kwargs.get("timeout", 40))


def tv_alive():
    import socket
    try:
        with socket.create_connection((TV, int(TV_PORT)), timeout=1):
            return True
    except OSError:
        return False


def need_tv():
    if not tv_alive():
        print("телевизор %s не отвечает (выключен или потерял сеть)" % TV, file=sys.stderr)
        sys.exit(1)


def cli_call(*args, timeout=12):
    """Прямой вызов библиотеки телевизора. Недоступна — пустой ответ, без падения."""
    env = dict(os.environ, HOME=STB_HOME)
    try:
        # cwd важен: sqlitedict открывает ключ телевизора относительно каталога,
        # и из недоступного каталога падает «unable to open database file».
        return subprocess.run(CLI + [TV] + list(args), capture_output=True, cwd=STB_HOME,
                              text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        print("телевизор не ответил за %d с" % timeout, file=sys.stderr)
        return subprocess.CompletedProcess(CLI, 1, stdout="", stderr="timeout")
    except (OSError, subprocess.SubprocessError) as exc:
        print("библиотека телевизора недоступна: %s" % exc, file=sys.stderr)
        return subprocess.CompletedProcess(CLI, 1, stdout="", stderr=str(exc))


def mode_get():
    """Режим пульта: «nuc» — управляем приставкой, «tv» — телевизором."""
    return mark_read(MODE_FILE, "nuc")


def mode_set(new):
    """Переключить режим пульта: в режиме приставки работает заставка."""
    os.makedirs(os.path.dirname(MODE_FILE), exist_ok=True)
    mark_set(MODE_FILE, new + "\n")
    try:
        with open(SCREEN_FLAG, "w", encoding="utf-8") as f:
            f.write("on\n" if new != "tv" else "off\n")
    except OSError:
        pass
    return new


def current_app():
    """Что сейчас на экране телевизора, одной строкой."""
    try:
        app = (daemon().ask({"cmd": "state"}, timeout=3).get("state") or {}).get("app")
    except Exception:  # noqa: BLE001
        app = None
    if app:
        return str(app)
    return cli_call("get_current_app").stdout.strip().splitlines()[-1] if tv_alive() else ""


def sink_mute(on):
    """Заглушить или вернуть звук приставки: он уходит в телевизор по HDMI.

    На сетке и в скрытом приложении звук не нужен — иначе фильм продолжает
    играть за кадром. В системе есть wireplumber (wpctl), pactl нет.
    """
    as_user("wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1" if on else "0")
    # Кто именно тронул звук: без этого в журнале видно только «заглушён/включён»,
    # и непонятно, кто из десятка мест снял глушилку после сетки.
    try:
        where = sys._getframe(1).f_code.co_name
    except Exception:  # noqa: BLE001
        where = "?"
    log_to("audio", "звук приставки %s (%s)" % ("заглушён" if on else "включён", where))


def sink_muted():
    """Заглушён ли звук приставки прямо сейчас."""
    try:
        out = as_user("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@").stdout or ""
    except Exception:  # noqa: BLE001
        return True          # не смогли спросить — не дёргаем
    return "MUTED" in out.upper()


def idle_log(msg):
    """Лёгкий режим: общий журнал для cmd_idle и подъёма окна."""
    log_to("idle", msg)


def splash_windows():
    """Окна с чёрной заставкой (это вкладка в окне Firefox, не отдельное окно)."""
    out = as_user("xdotool", "search", "--name", "Заставка").stdout.split()
    return [w for w in out if w.isdigit()]


def key_log(msg):
    """Кнопка пульта в keys.log; последняя строка доступна через /run/stb/lastkey."""
    line = log_to("keys", msg)
    try:
        with open("/run/stb/lastkey", "w", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def xdo(*args):
    """xdotool от имени пользователя приставки: окна, ввод, клики."""
    return as_user("xdotool", *args, timeout=20)


def window_title():
    return xdo("getactivewindow", "getwindowname").stdout.strip()


GRID_TITLE = "Приставка"

BROWSER_TITLE = "Mozilla"


def is_grid(title=None):
    """Активное окно — наша сетка."""
    return GRID_TITLE in (window_title() if title is None else title)


def is_browser(title=None):
    """Активное окно — браузер: в нём живёт и сетка, и сайты во вкладках."""
    return BROWSER_TITLE in (window_title() if title is None else title)


def is_ours(title=None):
    """Окно наше: сетка или браузер с вкладками."""
    text = window_title() if title is None else title
    return GRID_TITLE in text or BROWSER_TITLE in text


def is_app(title=None):
    """Окно приложения (Jellyfin и подобные): заголовок есть и он не наш."""
    text = window_title() if title is None else title
    return bool(text) and not is_ours(text)
