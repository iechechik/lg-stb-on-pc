#!/usr/bin/env python3
"""stb — одна команда для всего, что делает приставка.

Экран приставки: окна браузера и плеера, сетка, заставка и простой, вход в
приложения и возврат на сетку, раскладка клавиатуры. Выделено из bin/stb без
изменения поведения; телевизор — в lib/stbtvcmd.py, общее — в lib/stbcommon.py.
"""
import os
import subprocess
import sys
import time

import stbtvlast
import stbconf
from stbcommon import (GRID_TITLE,STB_HOME,as_user,is_browser,is_grid,is_ours,key_log,
                       log_to,mark_clear,mark_read,mark_set,mode_get,say,sink_mute,
                       sink_muted,splash_windows,tv_alive,user_env,user_uid,window_title,
                       xdo)
from stbcommon import SCREEN_FLAG  # noqa: E402
from stbtvcmd import cmd_tv  # noqa: E402
from stbtvcmd import tv_state  # noqa: E402
from stbcommon import idle_log  # noqa: E402
from stbtvcmd import tv_shows_own_app  # noqa: E402
from stbtvcmd import TV_APP  # noqa: E402
from stbtvcmd import TV_INPUT  # noqa: E402
from stbcommon import mode_set  # noqa: E402
from stbtvcmd import wake_tv  # noqa: E402


def mark_age(path):
    """Возраст отметки в секундах; None, если отметки нет."""
    try:
        return max(0, int(time.time() - os.path.getmtime(path)))
    except OSError:
        return None


def cmd_close(argv):
    """Закрыть окно активного приложения. Сетку и браузер не трогаем."""
    win = xdo("getactivewindow").stdout.strip()
    if not win:
        return 0
    if is_ours(xdo("getwindowname", win).stdout):
        return 0
    xdo("windowclose", win)
    return 0


def hidden_mark():
    """Отметка «приложение скрыто»: время из mtime, заголовок окна внутри."""
    return os.path.join(user_env()["XDG_RUNTIME_DIR"], "stb-app-hidden")


def cmd_hide(argv):
    """Убрать окно с экрана, не закрывая приложение: вернёмся — покажем."""
    env = user_env()
    win = subprocess.run(["xdotool", "getactivewindow"], env=env,
                         capture_output=True, text=True).stdout.strip()
    if not win:
        return 0
    name = (subprocess.run(["xdotool", "getwindowname", win], env=env,
                           capture_output=True, text=True).stdout or "").strip()
    if not name or is_ours(name) or "stb-web" in name:
        return 0                      # сетку и браузер не прячем
    hidden = subprocess.run(["wmctrl", "-i", "-r", win, "-b", "add,hidden"], env=env,
                            capture_output=True)
    if hidden.returncode != 0:
        key_log("окно (%s) не скрылось — приложение оставляю на экране" % name[:40])
        return 1
    try:
        with open(hidden_mark(), "w", encoding="utf-8") as f:
            f.write(name)
    except OSError:
        pass
    sink_mute(True)
    minutes = int(stbconf.get("APP_HIDE_MINUTES", "10") or 0)
    key_log("окно скрыто (%s) — вернусь или закрою через %d мин" % (name[:40], minutes))
    return 0


def hidden_check():
    """Погасить приложение, которое слишком долго висит скрытым."""
    mark = hidden_mark()
    try:
        age = time.time() - os.path.getmtime(mark)
    except OSError:
        return 0
    minutes = int(stbconf.get("APP_HIDE_MINUTES", "10") or 0)
    if minutes <= 0 or age < minutes * 60:
        return 0
    title = ""
    try:
        with open(mark, encoding="utf-8") as f:
            title = f.read().strip()
    except OSError:
        pass
    env = user_env()
    # Окно могли вернуть мимо плитки (оконный менеджер, alt-tab). Тогда возраст
    # отметки уже ничего не значит: человек смотрит, гасить нельзя.
    found = (subprocess.run(["xdotool", "search", "--name", title], env=env,
                            capture_output=True, text=True)
             if title else None)
    # xdotool: 0 — окна есть, 1 — нет подходящих, больше — сам не смог
    # (нет X, сломан DISPLAY). В последнем случае состояние неизвестно:
    # закрывать приложение нельзя, человек может его смотреть.
    if found is not None and found.returncode > 1:
        say("окно (%s) проверить не удалось (xdotool код %d) — приложение оставляю"
            % (title[:40], found.returncode))
        return 0
    wins = found.stdout.split() if found is not None else []
    unverified = 0
    for wid in wins:
        if not wid.isdigit():
            continue
        info = subprocess.run(["xwininfo", "-id", wid], env=env,
                              capture_output=True, text=True)
        if info.returncode == 0 and "IsViewable" in info.stdout:
            mark_clear(mark)
            say("окно (%s) снова на экране — таймер снят" % title[:40])
            return 0
        if info.returncode != 0:
            # Окно могло исчезнуть между поиском и проверкой — это не «не смог
            # проверить». Всё остальное считаем неизвестностью.
            gone = "No such window" in (info.stderr or "") or "BadWindow" in (info.stderr or "")
            if not gone:
                unverified += 1
    if unverified:
        # Достаточно одного непроверенного окна: смешанный результат — это
        # неизвестность, приложение не трогаем.
        say("окно (%s): проверить не удалось (%d из %d) — приложение оставляю"
            % (title[:40], unverified, len([w for w in wins if w.isdigit()])))
        return 0
    if "jellyfin" in title.lower():
        jelly_kill(env, "скрыто дольше %d мин" % minutes)
    elif title:
        subprocess.run(["wmctrl", "-c", title], env=env, capture_output=True)
    mark_clear(mark)
    say("скрытое окно (%s) висело %d мин — приложение закрыто" % (title[:40], minutes))
    return 0


def cmd_browser(argv):
    """Запустить Firefox окном на весь экран (служба stb-browser)."""
    env = user_env()
    proc = subprocess.Popen(["/usr/bin/firefox-esr", "--no-remote",
                             "--profile", os.path.join(STB_HOME, ".mozilla/stb"),
                             "http://127.0.0.1:%s/" % stbconf.get("STB_WEB_PORT", "8090")],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        time.sleep(0.5)
        listing = subprocess.run(["wmctrl", "-l"], env=env, capture_output=True, text=True).stdout
        for line in listing.splitlines():
            if is_browser(line):
                wid = line.split()[0]
                subprocess.run(["wmctrl", "-i", "-r", wid, "-b", "add,maximized_vert,maximized_horz"],
                               env=env, capture_output=True)
                subprocess.run(["wmctrl", "-i", "-a", wid], env=env, capture_output=True)
                return proc.wait()
    return proc.wait()


JELLY_APP = "org.jellyfin.JellyfinDesktop"


def jelly_windows(env):
    """Окна плеера, которые реально видны (wmctrl перечисляет только показанные)."""
    listing = subprocess.run(["wmctrl", "-l", "-x"], env=env,
                             capture_output=True, text=True).stdout
    return [line for line in listing.splitlines() if "jellyfin-desktop" in line.lower()]


def jelly_running():
    """Есть ли процессы плеера (по полной командной строке)."""
    out = subprocess.run(["pgrep", "-f", "jellyfin-desktop"],
                         capture_output=True, text=True).stdout
    return [pid for pid in out.split() if pid]


def jelly_kill(env, why=""):
    """Погасить плеер целиком: flatpak, потом процессы, потом SIGKILL."""
    if jelly_running():
        say("плеер: гашу %s" % (why or "висящий экземпляр"))
    subprocess.run(["flatpak", "kill", JELLY_APP], env=env, capture_output=True)
    for _ in range(10):
        if not jelly_running():
            return True
        subprocess.run(["pkill", "-f", "jellyfin-desktop"], capture_output=True)
        time.sleep(0.5)
    for _ in range(6):
        if not jelly_running():
            return True
        subprocess.run(["pkill", "-9", "-f", "jellyfin-desktop"], capture_output=True)
        time.sleep(0.5)
    return not jelly_running()


def cmd_player(argv):
    """Jellyfin Desktop на приставке: показать окно или честно сказать, что не вышло."""
    env = user_env()
    # Плееру нужна сессионная шина: без неё он запускается и молча висит без окна.
    bus = "/run/user/%d/bus" % user_uid()
    if os.path.exists(bus) and not env.get("DBUS_SESSION_BUS_ADDRESS"):
        env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + bus

    if "--kill" in argv:
        jelly_kill(env, "по команде")
        return 0

    if "--status" in argv:
        print("окно: %s" % ("есть" if jelly_windows(env) else "нет"))
        print("процессы: %s" % (", ".join(jelly_running()) or "нет"))
        return 0

    def fullscreen(wid):
        if not wid:
            return
        geo = subprocess.run(["xdotool", "getdisplaygeometry"], env=env,
                             capture_output=True, text=True).stdout.split()
        subprocess.run(["wmctrl", "-i", "-r", wid, "-b", "remove,hidden"], env=env)
        subprocess.run(["wmctrl", "-i", "-a", wid], env=env)
        if len(geo) == 2:
            subprocess.run(["wmctrl", "-i", "-r", wid, "-e", "0,0,0,%s,%s" % (geo[0], geo[1])],
                           env=env)
        subprocess.run(["wmctrl", "-i", "-r", wid, "-b", "add,fullscreen"], env=env)

    windows = jelly_windows(env)
    if windows:
        wid = windows[0].split()[0]
        subprocess.run(["wmctrl", "-i", "-r", wid, "-b", "remove,hidden"], env=env, capture_output=True)
        fullscreen(wid)
        # Возврат в приложение: звук к этому моменту мог быть погашен лёгким режимом.
        for unit in ("pipewire.socket", "pipewire-pulse.socket", "wireplumber"):
            as_user("systemctl", "--user", "start", unit)
        sink_mute(False)
        mark_clear(hidden_mark())
        print("Jellyfin уже открыт")
        return 0

    # Процессы есть, окна нет — это и есть «висит ненужным»: гасим и запускаем заново.
    if jelly_running():
        jelly_kill(env, "висящий экземпляр без окна")
        time.sleep(1)

    # Пока flatpak-экземпляр числится живым, `flatpak run` не создаёт новое окно,
    # а «активирует» прежний. Ждём, пока он исчезнет из списка запущенных.
    for _ in range(20):
        listed = subprocess.run(["flatpak", "ps"], env=env, capture_output=True,
                                text=True).stdout.lower()
        if "jellyfin" not in listed:
            break
        subprocess.run(["flatpak", "kill", JELLY_APP], env=env, capture_output=True)
        time.sleep(0.5)

    try:
        player_log = open("/var/log/stb/jellyfin.log", "w", encoding="utf-8")
    except OSError:
        player_log = subprocess.DEVNULL
    subprocess.Popen(["flatpak", "run", JELLY_APP, "--tv", "--fullscreen"], env=env,
                     stdout=player_log, stderr=subprocess.STDOUT, start_new_session=True)

    # Приложение-пульт ждёт ответ 20 с: дольше держать бессмысленно, пользователь
    # уже увидел бы ошибку.
    for _ in range(20):
        time.sleep(1)
        windows = jelly_windows(env)
        if windows:
            time.sleep(1)
            fullscreen(windows[0].split()[0])
            sink_mute(False)      # окно на экране — звук должен быть слышен
            print("Jellyfin открыт")
            return 0

    # Окно не появилось — процесс бесполезен, убираем, чтобы не висел в фоне.
    jelly_kill(env, "окно не появилось за 20 с")
    print("Jellyfin не показал окно — процесс выключен, смотри /var/log/stb/jellyfin.log",
          file=sys.stderr)
    return 1


def show_browser():
    """Показать готовое окно браузера: развернуть и вывести вперёд.

    Возвращает True, если окно уже существует и показано.
    """
    windows = browser_windows()
    if not windows:
        return False
    wid = windows[0].split()[0]
    as_user("wmctrl", "-i", "-a", wid)
    as_user("wmctrl", "-i", "-r", wid, "-b", "add,maximized_vert,maximized_horz")
    as_user("xdotool", "windowactivate", "--sync", wid)
    return True


def browser_windows():
    """Есть ли окно браузера: список окон openbox."""
    out = as_user("wmctrl", "-l").stdout.strip()
    return [line for line in out.splitlines() if is_ours(line)]


def ensure_browser():
    """Гарантировать окно браузера.

    Прежний Firefox после остановки службы может ещё держать профиль;
    если запустить новый сразу, он молча выходит без окна. Поэтому:
    остановить, дождаться, пока процесс уйдёт, снять замки, запустить,
    проверить окно и повторить при неудаче.
    """
    # Сначала даём браузеру время: Firefox поднимает окно 10–20 с,
    # и перезапуск в это время только мешает.
    for _ in range(30):
        if browser_windows():
            return True
        time.sleep(1)
    for attempt in (1, 2, 3):
        if browser_windows():
            return True
        idle_log("окна браузера нет — перезапускаю (попытка %d)" % attempt)
        as_user("systemctl", "--user", "stop", "stb-browser")
        subprocess.run(["pkill", "-x", "firefox-esr"], capture_output=True)
        for _ in range(20):
            time.sleep(0.5)
            alive = subprocess.run(["pgrep", "-x", "firefox-esr"],
                                   capture_output=True).stdout.strip()
            if not alive:
                break
        profile = os.path.join(STB_HOME, ".mozilla", "stb")
        for name in ("lock", ".parentlock"):
            mark_clear(os.path.join(profile, name))
        as_user("systemctl", "--user", "reset-failed", "stb-browser")
        as_user("systemctl", "--user", "start", "stb-browser")
        for _ in range(20):
            time.sleep(1)
            if browser_windows():
                return True
    idle_log("окно браузера так и не появилось")
    return False


def cmd_idle(argv):
    """Телевизор выключен — лишние программы не нужны: stb idle on|off."""
    what = argv[0] if argv else ""
    if what not in ("on", "off"):
        print("usage: stb idle on|off", file=sys.stderr)
        return 2
    def say_idle(msg):
        idle_log(msg)

    def governor(name):
        import glob
        for path in glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"):
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(name)
            except OSError:
                pass

    if what == "on":
        say_idle("ТВ включён → поднимаю интерфейс")
        governor("schedutil")
        cmd_screen(["on"])
        # Отметка подъёма: xprintidle считает простой и при погашенном экране,
        # поэтому без неё заставка срабатывает сразу после включения.
        try:
            open(os.path.join(user_env()["XDG_RUNTIME_DIR"], "stb-wake"), "w",
                 encoding="utf-8").close()
        except OSError:
            pass
        for unit in ("pipewire.socket", "pipewire-pulse.socket", "wireplumber"):
            as_user("systemctl", "--user", "start", unit)
        if not show_browser():
            # окна нет совсем (первый запуск, падение) — поднимаем службу
            as_user("systemctl", "--user", "reset-failed", "stb-browser")
            as_user("systemctl", "--user", "start", "stb-browser")
            if tv_alive() and not ensure_browser():
                return 1
        # Firefox после перезапуска восстанавливает вкладки, и активной может
        # оказаться чёрная или страница подсказок — возвращаем сетку.
        cmd_grid([])
    else:
        say_idle("ТВ выключен → powersave сразу")
        governor("powersave")
        cmd_screen(["off"])
        for unit in ("wireplumber", "pipewire-pulse.socket", "pipewire.socket"):
            as_user("systemctl", "--user", "stop", unit)

        # Браузер не перезапускаем: холодный старт — до 20 с чёрного экрана.
        # Закрываем только окно плеера, оно держит экран и звук.
        say_idle("браузер оставляю в памяти — включение будет мгновенным")

        subprocess.run(["flatpak", "kill", "org.jellyfin.JellyfinDesktop"], capture_output=True)
        subprocess.run(["pkill", "-f", "jellyfin-desktop"], capture_output=True)

    try:
        with open("/run/stb/idle", "w", encoding="utf-8") as f:
            f.write(what + "\n")
    except OSError:
        pass
    return 0


def cmd_screen(argv):
    """Заставка: stb screen on|off|status."""
    what = argv[0] if argv else "status"
    minutes = stbconf.get("SCREENSAVER_MINUTES", "5")
    if what == "on":
        try:
            with open(SCREEN_FLAG, "w", encoding="utf-8") as f:
                f.write("on\n")
        except OSError:
            pass
        as_user("systemctl", "--user", "start", "stb-screensaver")
        print("заставка включена: %s мин" % minutes)
        return 0
    if what == "off":
        try:
            with open(SCREEN_FLAG, "w", encoding="utf-8") as f:
                f.write("off\n")
        except OSError:
            pass
        for marker in ("/run/stb/screenblank",
                       os.path.join(user_env()["XDG_RUNTIME_DIR"], "stb-screenblank")):
            mark_clear(marker)
        print("заставка выключена")
        return 0
    if what == "status":
        try:
            state = open(SCREEN_FLAG, encoding="utf-8").read().strip() or "off"
        except OSError:
            state = "off"
        idle = as_user("xprintidle").stdout.strip() or "?"
        blank = as_user("xdotool", "search", "--name", "Заставка").returncode == 0
        print("состояние: %s" % state)
        print("порог: %s мин" % minutes)
        print("простой: %s мс" % idle)
        print("чёрная вкладка: %s" % ("открыта" if blank else "нет"))
        return 0
    print("usage: stb screen on|off|status", file=sys.stderr)
    return 2


def grid_window():
    out = as_user("xdotool", "search", "--name", GRID_TITLE).stdout.split()
    return any(w.isdigit() for w in out)


def current_layout():
    """Текущая раскладка: 'ru', 'us' или ''."""
    out = as_user("setxkbmap", "-query").stdout
    for line in out.splitlines():
        if line.strip().startswith("layout:"):
            return line.split(":", 1)[1].strip()
    return ""


def type_url(url):
    """Набрать адрес так, чтобы раскладка не превратила его в мусор.

    В русской раскладке xdotool type выдаёт «h1t27p.0:/,/)1.217…», Firefox
    отправляет это в поиск, и на экране появляется страница с подсказками
    вместо сетки. Поэтому на время набора включаем us.
    """
    was = current_layout()
    if was and was != "us":
        as_user("setxkbmap", "us")
        time.sleep(0.2)
    try:
        as_user("xdotool", "key", "--clearmodifiers", "ctrl+l")
        time.sleep(0.2)
        as_user("xdotool", "type", "--delay", "25", url)
        time.sleep(0.3)
        as_user("xdotool", "key", "--clearmodifiers", "Return")
        time.sleep(1.0)
    finally:
        if was and was != "us":
            as_user("setxkbmap", was)


def firefox_windows(env):
    """Окна браузера. У Firefox есть служебные окна того же класса — берём
    те, в заголовке которых видно содержимое (сетка, заставка, обычная страница)."""
    out = as_user("xdotool", "search", "--class", "firefox-esr").stdout.split()
    wins = [w for w in out if w.isdigit()]
    real = []
    for wid in wins:
        title = as_user("xdotool", "getwindowname", wid).stdout
        if is_ours(title) or "Заставка" in title:
            real.append(wid)
    return real or wins


def cmd_grid(argv):
    """Показать сетку в окне браузера, в какой бы вкладке он ни оказался.

    Firefox после перезапуска восстанавливает прежние вкладки (чёрную заставку,
    новую вкладку с подсказками), и телевизор показывает не то. Закрывать их
    через ctrl+w опасно — можно закрыть саму сетку и получить моргание.
    Поэтому просто переводим активную вкладку на адрес сетки.
    """
    env = user_env()
    wins = firefox_windows(env)
    if not wins:
        if not ensure_browser():
            return 1
        wins = firefox_windows(env)
    if not wins:
        return 1
    wid = wins[0]
    as_user("xdotool", "windowactivate", "--sync", wid)
    title = as_user("xdotool", "getwindowname", wid).stdout
    if is_grid(title):
        sink_mute(True)       # на сетке звук всегда выключен
        return 0
    url = "http://127.0.0.1:%s/" % stbconf.get("STB_WEB_PORT", "8090")
    as_user("xdotool", "key", "--clearmodifiers", "Escape")
    type_url(url)
    sink_mute(True)           # на сетке звук всегда выключен
    return 0


def close_splash_now():
    """Закрыть заставку, не убивая окно сетки: гасим вкладку, а не окно."""
    runtime = user_env()["XDG_RUNTIME_DIR"]
    for name in ("stb-screenblank", "stb-tv-slept"):
        mark_clear(os.path.join(runtime, name))
    try:
        screen_on = open(SCREEN_FLAG, encoding="utf-8").read().strip() == "on"
    except OSError:
        screen_on = True
    # Возврат к экрану: показываем сетку в любом случае — она могла быть
    # перекрыта чёрной вкладкой или страницей подсказок.
    if screen_on and mode_get() == "nuc":
        cmd_grid([])
    return 0


def splash_present():
    """Открыта ли заставка (чёрная вкладка)."""
    return bool(splash_windows())


def splash_fullscreen():
    """Занимает ли заставка весь экран."""
    geo = as_user("xdotool", "getactivewindow", "getwindowgeometry", "--shell").stdout
    width = ""
    for line in geo.splitlines():
        if line.startswith("WIDTH="):
            width = line.split("=", 1)[1]
    display = as_user("xdotool", "getdisplaygeometry").stdout.split()
    return bool(width) and bool(display) and width == display[0]


def splash_open(port, opened_at):
    """Перевести текущую вкладку на чёрную страницу во весь экран.

    Новая вкладка не создаётся: она копила бы «Приставку» и включала верхние
    строки Firefox, которые прячутся только при одной вкладке.
    """
    url = "http://127.0.0.1:%s/black" % port
    as_user("xdotool", "key", "--clearmodifiers", "F11")
    time.sleep(0.6)
    type_url(url)
    if not splash_fullscreen():
        as_user("xdotool", "key", "--clearmodifiers", "F11")
        time.sleep(0.4)
    if not splash_present():
        type_url(url)
        as_user("xdotool", "key", "--clearmodifiers", "F11")
        time.sleep(0.4)
    mark_set(opened_at)


def idle_ms_capped(runtime):
    """Простой мыши в миллисекундах, но не больше времени с подъёма интерфейса.

    Экран мог быть погашен часами: тогда xprintidle показывает огромный простой
    и заставка открывается сразу после включения.
    """
    out = as_user("xprintidle").stdout.strip()
    idle = int(out) if out.isdigit() else 0
    try:
        since = int((time.time() - os.path.getmtime(
            os.path.join(runtime, "stb-wake"))) * 1000)
        idle = max(0, min(idle, since))
    except OSError:
        pass
    return idle


def tv_sleep_if_idle(age, sleep_after, slept_marker, log):
    """Тишина дольше порога: гасим телевизор либо отмечаем, что гасить нечего."""
    if mode_get() != "nuc" or tv_shows_own_app() is not False:
        return
    power = tv_state().get("power") or ""
    if not power:
        log("тишина %d с — состояние телевизора неизвестно, не гашу" % age)
        return
    if power == "Active":
        if cmd_tv(["off"]) == 0:
            mark_set(slept_marker)
            log("тишина %d с — гашу телевизор (порог %d мин)" % (age, sleep_after // 60))
        return
    mark_set(slept_marker)


def keep_display_awake():
    """Гашение экрана — дело сторожа, а не X: DPMS выключаем."""
    if "DPMS is Enabled" in as_user("xset", "q").stdout:
        as_user("xset", "-dpms")
        as_user("xset", "dpms", "0", "0", "0")
    as_user("xset", "s", "off")


def watching():
    """Человек смотрит, а не простаивает: виден плеер или открыт сайт.

    Простой считается только на сетке и в пустом браузере. Иначе поверх фильма
    открывалась чёрная вкладка (порог 5 минут), а через 10 минут гас телевизор:
    смотреть кино было невозможно.
    """
    env = user_env()
    try:
        if jelly_windows(env):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        for wid in firefox_windows(env):
            title = as_user("xdotool", "getwindowname", wid).stdout
            if title and not is_grid(title) and "Заставка" not in title:
                return True
    except Exception:  # noqa: BLE001
        pass
    return False


def cmd_screensaver(argv):
    """Сторож простоя: чёрная вкладка, затем гашение телевизора."""
    if argv and argv[0] == "close":
        return close_splash_now()
    import fcntl

    minutes = int(stbconf.get("SCREENSAVER_MINUTES", "5") or 5)
    limit_ms = minutes * 60 * 1000
    if limit_ms <= 0:
        return 0
    sleep_after = int(stbconf.get("STB_TV_SLEEP_AFTER", "10") or 0) * 60
    port = stbconf.get("STB_WEB_PORT", "8090")
    runtime = user_env()["XDG_RUNTIME_DIR"]
    opened_at = os.path.join(runtime, "stb-screenblank")
    slept_marker = os.path.join(runtime, "stb-tv-slept")

    lock = open(os.path.join(runtime, "stb-screensaver.lock"), "w", encoding="utf-8")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("сторож уже работает — выхожу")
        return 0

    def log(msg):
        log_to("system", msg, echo=True)

    mark_clear(slept_marker)
    log("сторож заставки: порог %d мин" % minutes)

    tick = 0
    watching_until = 0.0
    while True:
        screen = mark_read(SCREEN_FLAG, "on")
        own = tv_shows_own_app()

        # Телевизор наш или погашен: заставка не нужна.
        if screen != "on" or mode_get() != "nuc" or own is True:
            close_splash_now()
            time.sleep(5)
            continue

        # Чужой экран: новую заставку не открываем, уже открытую не трогаем —
        # короткий сбой связи не повод её закрывать.
        if own is None and not os.path.exists(opened_at):
            time.sleep(5)
            continue

        # Сетка на экране — приставка заглушена. Правило безусловное: неважно,
        # каким путём человек вернулся на сетку, звук не останется включённым.
        if mode_get() == "nuc" and not sink_muted() and is_grid(window_title()):
            sink_mute(True)

        # Кино или открытый сайт — это не простой. Заставку, если она успела
        # открыться, закрываем: фильм важнее.
        if watching():
            watching_until = time.monotonic()
            if os.path.exists(opened_at):
                close_splash_now()
            time.sleep(5)
            continue

        idle = idle_ms_capped(runtime)
        if watching_until:
            # xprintidle помнит всё время фильма; отсчёт ведём от конца просмотра.
            idle = min(idle, int((time.monotonic() - watching_until) * 1000))

        if os.path.exists(opened_at):
            age = mark_age(opened_at) or 0
            if age >= 10 and idle < 3000:
                close_splash_now()
                time.sleep(2)
                continue
            if sleep_after > 0 and age >= sleep_after and not os.path.exists(slept_marker):
                tv_sleep_if_idle(age, sleep_after, slept_marker, log)
            time.sleep(2)
            continue

        if idle >= limit_ms:
            # Отметка ставится до попытки открыть вкладку: без браузера
            # заставка не откроется, но отсчёт до гашения уже идёт.
            mark_set(opened_at)
            splash_open(port, opened_at)
            time.sleep(2)
            continue

        if splash_present() or not grid_window():
            cmd_grid([])
            time.sleep(2)
            continue

        tick += 1
        if tick >= 15:
            tick = 0
            keep_display_awake()
        time.sleep(10 if idle < limit_ms - 90000 else 2)


XDISPLAY = {"DISPLAY": ":0"}


BROWSER_WINDOW = "Mozilla Firefox"    # имя окна для wmctrl -a


def finish_all():
    """Home на сетке: убрать всё запущенное и оставить чистую сетку."""
    if jelly_running():
        key_log("home на сетке → закрываю плеер")
        cmd_player(["--kill"])
    listing = as_user("wmctrl", "-l").stdout
    for line in listing.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        wid, title = parts[0], parts[3]
        if is_ours(title):
            continue                      # браузер с сеткой не трогаем
        as_user("wmctrl", "-i", "-c", wid)
    sink_mute(True)           # на сетке звук всегда выключен
    mark_clear(hidden_mark())
    cmd_grid([])
    key_log("home на сетке → всё убрано")
    return 0


def finish_app():
    """Закрыть приложение насовсем: Home означает «закончил», а не «вернусь»."""
    sink_mute(True)           # после Home всегда сетка — звук приставки не нужен
    mark = hidden_mark()
    hidden_title = ""
    try:
        with open(mark, encoding="utf-8") as f:
            hidden_title = f.read().strip()
    except OSError:
        pass
    if "jellyfin" in hidden_title.lower():
        # Окно уже спрятано (Back), но Home означает «закончил» — гасим.
        key_log("home → закрываю скрытый плеер")
        cmd_player(["--kill"])
        mark_clear(mark)
        return 0
    title = window_title()
    if is_ours(title):
        # Сетка или браузер — приложений поверх нет, только снимаем отметку.
        mark_clear(mark)
        return 0
    if "jellyfin" in title.lower():
        key_log("home → закрываю плеер")
        cmd_player(["--kill"])
    else:
        key_log("home → закрываю окно (%s)" % title[:40])
        cmd_close([])
    mark_clear(mark)
    return 0


def cmd_ui(argv):
    """Перезапуск интерфейса: браузер заново, одна вкладка с сеткой.

    Нужен, когда надо начать с чистого листа (накопленные вкладки, странная
    страница). Ничего в системе не перезапускает — только окно браузера.
    """
    if not argv or argv[0] != "restart":
        print("usage: stb ui restart", file=sys.stderr)
        return 2
    say("интерфейс: перезапускаю браузер")
    as_user("systemctl", "--user", "reset-failed", "stb-browser")
    as_user("systemctl", "--user", "restart", "stb-browser")
    for _ in range(40):
        time.sleep(0.5)
        if grid_window():
            break
    cmd_grid([])
    say("интерфейс перезапущен")
    return 0


def cmd_mode(argv):
    if not argv:
        print(mode_get())
        return 0
    what = argv[0]
    if what not in ("nuc", "tv"):
        print("usage: stb mode [nuc|tv]", file=sys.stderr)
        return 2
    print(mode_set(what))
    return 0


def cmd_box(argv):
    """Вернуть вход приставки и режим nuc."""
    if TV_INPUT:
        cmd_tv(["setinput", TV_INPUT])
    mode_set("nuc")
    # На экране будет сетка: звук приставки глушим. Иначе спрятанный плеер
    # продолжает играть, и после «Телевизора» фильм слышно поверх сетки.
    sink_mute(True)
    print("приставка")
    return 0


def cmd_jelly(argv):
    """Запустить Jellyfin на телевизоре и перевести пульт в режим ТВ."""
    sink_mute(False)      # звук будет от телевизора

    if not wake_tv(45):
        say("jelly: телевизор не проснулся")
        print("телевизор не проснулся", file=sys.stderr)
        return 1
    cmd_tv(["app", TV_APP])
    time.sleep(2)
    mode_set("tv")
    cmd_tv(["speaker-auto"])
    say("jelly: запущено на телевизоре")
    print("Jellyfin на телевизоре")
    return 0


def cmd_live(argv):
    """Разбудить телевизор и перевести пульт в режим ТВ (источник не меняем)."""
    sink_mute(False)      # уходим в телевизор — звук приставки не глушим

    if not wake_tv(45):
        say("live: телевизор не проснулся")
        print("телевизор не проснулся", file=sys.stderr)
        return 1
    # Свой вход оставлять нельзя: после возврата в сетку источник — наш HDMI,
    # и «Телевизор» показывал бы ту же сетку. Открываем то, что смотрели
    # последним (сторож запоминает чужое приложение), иначе запасное.
    target = ""
    if str(stbconf.get("TV_RESTORE_LAST", "1")).strip().lower() in ("1", "on", "true", "yes"):
        target = stbtvlast.last(stbconf.get)
    if not target:
        target = str(stbconf.get("TV_FALLBACK_APP", "com.webos.app.home") or "")
    if target:
        say("live: открываю %s" % target)
        cmd_tv(["app", target])
    else:
        say("live: источник не меняю")
    mode_set("tv")
    cmd_tv(["speaker-auto"])
    print("перехожу на телевизор")
    return 0


def cmd_toggle(argv):
    if mode_get() == "tv":
        say("toggle: → приставка")
        cmd_box([])
        return 0
    say("toggle: → телевизор")
    cmd_jelly([])
    return 0


def cmd_sound(argv):
    """Звук приставки: stb sound on|off."""
    what = (argv[0] if argv else "").strip()
    if what not in ("on", "off"):
        print("usage: stb sound on|off", file=sys.stderr)
        return 2
    sink_mute(what == "off")
    key_log("звук %s" % ("включён" if what == "on" else "выключен"))
    return 0


def cmd_lang(argv):
    """Раскладка клавиатуры: stb lang [ru|en|toggle|status]."""
    what = argv[0] if argv else "status"
    current = current_layout

    if what == "status":
        print(current())
        return 0
    if what == "toggle":
        what = "us" if current() == "ru" else "ru"
    elif what == "en":
        what = "us"
    elif what == "ru":
        pass
    else:
        print("usage: stb lang [ru|en|toggle|status]", file=sys.stderr)
        return 2
    as_user("setxkbmap", what)
    print(what)
    return 0
