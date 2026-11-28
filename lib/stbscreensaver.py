#!/usr/bin/env python3
"""Заставка приставки: чёрный экран по тишине и гашение телевизора.

Тишина — это «нет ввода и не меняется картинка». Картинку спрашиваем у самого
телевизора, поэтому одно правило работает и на приставке, и в его приложениях:
играет кино или эфир — картинка живая, гасить нечего.

Отдельная тонкость: если кадр получить не удалось, это НЕ тишина. Отсчёт
гашения на такой сессии приостанавливается — иначе недоступная съёмка
приводила бы к выключению телевизора во время просмотра.
"""

import os
import time

import stbconf

from stbcommon import (SCREEN_FLAG, as_user, is_grid, log_to, mark_clear, mark_read,
                       mark_set, mode_get, screensaver_on, sink_mute, sink_muted,
                       tv_alive, user_env, window_title)
from stbtvcmd import cmd_tv, power_on, tv_state


def quiet_ms(now, alive_at, blind_since):
    """Сколько миллисекунд тишины насчитано.

    Пока картинка неизвестна (кадры не приходят), тишины нет: 0 — гасить
    не по чему.
    """
    if blind_since:
        return 0
    return int((now - alive_at) * 1000)


def mark_age(path):
    """Возраст отметки в секундах; None, если отметки нет."""
    try:
        return max(0, int(time.time() - os.path.getmtime(path)))
    except OSError:
        return None

def close_splash_now():
    """Снять заставку: вернуть яркость и панель. False — что-то не вернулось.

    Отметки снимаются только после удачного возврата: иначе система считает
    экран живым, хотя он остался погашенным.
    """
    runtime = user_env()["XDG_RUNTIME_DIR"]
    blanked_mark = os.path.join(runtime, "stb-tv-blanked")
    screen_mark = os.path.join(runtime, "stb-screenblank")
    ok = True
    if os.path.exists(blanked_mark):
        # Панель гасили мы сами — её и возвращаем.
        if tv_screen(True):
            log_to("system", "возвращаю панель телевизора", echo=True)
            mark_clear(blanked_mark)
        else:
            ok = False
            log_to("system", "панель не включилась — попробую ещё", echo=True)
    if os.path.exists(screen_mark):
        if screen_dim(False):
            mark_clear(screen_mark)
        else:
            ok = False
            log_to("system", "яркость не вернулась — попробую ещё", echo=True)
    mark_clear(os.path.join(runtime, "stb-tv-slept"))
    return ok

def splash_present():
    """Погашен ли экран по нашей воле (гашением выхода или панели)."""
    return screensaver_on()

def splash_open(port, opened_at):
    """Погасить экран: гасим сам выход, окна остаются на месте."""
    if not screen_dim(True):
        return False
    mark_set(opened_at)
    return True

def blank_choice(app, our_input):
    """Что гасить: "panel" (телевизор), "dim" (наш выход) или "none" (не знаю).

    Приложение телевизора неизвестно — не выбираем: гашение не того, что надо,
    человек видит как погасший экран во время просмотра.
    """
    if not app:
        return "none"
    return "panel" if app != our_input else "dim"


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
    power = tv_state().get("power") or ""
    if not power:
        log("тишина %d с — состояние телевизора неизвестно, не гашу" % age)
        return
    if power_on(power):
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

def screen_output():
    """Имя подключённого выхода X (HDMI-1 и подобное) — на нём и гасим."""
    for line in as_user("xrandr", "--current").stdout.splitlines():
        if " connected" in line:
            return line.split()[0]
    return ""

def screen_dim(on):
    """Погасить или вернуть экран на уровне видеовыхода.

    Окна не трогаются: ничего не сворачиваем и не перекрываем — поэтому после
    возврата на экране ровно тот же кадр, включая паузу в фильме. Телевизор
    продолжает получать сигнал, «нет сигнала» не появляется, возврат мгновенный.
    """
    output = screen_output()
    if not output:
        log_to("system", "не нашёл выход X — погасить экран нечем", echo=True)
        return False
    proc = as_user("xrandr", "--output", output, "--brightness", "0" if on else "1")
    if getattr(proc, "returncode", 1) != 0:
        log_to("system", "яркость %s не применилась: %s"
               % ("0" if on else "1", ((proc.stderr or "").strip()[:120] or "без текста")), echo=True)
        return False
    return True

def tv_frame():
    """Кадр телевизора через демон: сколько изменилось и что за приложение.

    Спрашиваем сам телевизор — он отдаёт кадр своего экрана. Поэтому правило
    одно и для нашей приставки, и для его собственных приложений: идёт кино или
    эфир — картинка меняется; картинка встала — можно гасить.
    """
    try:
        import asyncio

        from stbtv import TvDaemon

        return asyncio.run(TvDaemon().shot())
    except Exception:  # noqa: BLE001
        return None

def tv_screen(on):
    """Погасить или включить панель телевизора, оставив его включённым."""
    try:
        import asyncio

        from stbtv import TvDaemon

        return asyncio.run(TvDaemon().screen(on))
    except Exception:  # noqa: BLE001
        return None

def cmd_screensaver(argv):
    """Сторож тишины: чёрный экран, затем гашение телевизора.

    Тишина — это «нет ввода и не меняется картинка». Картинку спрашиваем у
    самого телевизора, поэтому одно правило работает и на приставке, и в его
    приложениях: играет кино или эфир — картинка живая, гасить нечего.
    """
    if argv and argv[0] == "close":
        return close_splash_now()
    import fcntl

    minutes = int(stbconf.get("SCREENSAVER_MINUTES", "10") or 10)
    limit_ms = minutes * 60 * 1000
    if limit_ms <= 0:
        return 0
    sleep_after = int(stbconf.get("STB_TV_SLEEP_AFTER", "5") or 0) * 60
    shot_every = max(5, int(stbconf.get("SHOT_EVERY", "60") or 60))
    diff_limit = float(stbconf.get("SHOT_DIFF_PERCENT", "2") or 2)
    no_blank = [x.strip() for x in (stbconf.get("TV_NO_BLANK", "") or "").split(",") if x.strip()]
    our_input = stbconf.get("TV_INPUT", "com.webos.app.hdmi3")
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
    screen_dim(False)      # если прошлый раз экран остался погашенным
    log("сторож тишины: %d мин без ввода и без движения картинки, кадр раз в %d с"
        % (minutes, shot_every))

    alive_at = time.monotonic()    # когда картинка последний раз менялась
    blind_since = 0.0              # с какого момента кадры не приходят (0 — приходят)
    last_ok_at = alive_at          # время последнего удачного кадра
    blanked = None                 # "dim" — погашен выход, "screen" — панель
    blanked_at = 0.0               # когда погасили: свои же xdotool-нажатия при
                                   # открытии вкладки сбрасывают простой ввода
    app = ""                       # что телевизор показывал в последний раз
    next_shot = 0.0
    awake_tick = 0
    last_unknown_note = 0.0     # когда жаловались, что приложение неизвестно
    last_fail_note = 0.0        # когда жаловались на неудачное гашение
    while True:
        if mark_read(SCREEN_FLAG, "on") != "on":
            close_splash_now()
            blanked = None
            time.sleep(5)
            continue

        # Телевизор уже погашен (стендбай, «экран выключен»). Гасить нечего, и
        # чёрный слой держать нельзя: после включения человек видел бы чёрный
        # экран, а таймер досчитывал бы минуту и гасил телевизор повторно.
        power = (tv_state() or {}).get("power") or ""
        # Спящий телевизор вообще не отвечает, и power приходит пустым: поэтому
        # смотрим ещё и сеть — иначе чёрный слой оставался висеть.
        if power != "Active" and not tv_alive():
            if blanked is not None:
                close_splash_now()
                blanked = None
                log("телевизор погашен — снимаю заставку")
            alive_at = time.monotonic()
            time.sleep(10)
            continue

        # Салют уже на экране (остался с прошлого раза или телевизор включили в
        # него): это наше гашение, а не живая картинка. Без этого кадры салюта
        # выглядят как «смотрят» — фейерверк меняется каждую минуту — и сторож
        # не гасит телевизор по таймауту никогда.
        if blanked is None and power == "Screen Saver":
            blanked = "screen"
            blanked_at = time.monotonic()
            tv_blanked_mark = os.path.join(runtime, "stb-tv-blanked")
            if not os.path.exists(tv_blanked_mark):
                mark_set(tv_blanked_mark)
            log("салют уже на экране — считаю панель погашенной")

        # Сетка на экране — приставка заглушена. Правило прежнее и безусловное.
        if mode_get() == "nuc" and not sink_muted() and is_grid(window_title()):
            sink_mute(True)

        now = time.monotonic()
        if now >= next_shot:
            next_shot = now + shot_every
            answer = tv_frame()
            if answer and answer.get("ok"):
                if blind_since:
                    log("кадры снова приходят — возобновляю отсчёт тишины")
                    alive_at = time.monotonic()
                blind_since = 0.0
                last_ok_at = now
                app = str(answer.get("app") or "")
                diff = answer.get("diff")
                black = float(answer.get("black") or 0)
                if blanked == "screen":
                    # Панель погашена штатной заставкой телевизора: на чёрном там
                    # салют, и покадровое сравнение считало бы его живой картинкой.
                    # Признак возврата один: экран снова показывает не чёрное.
                    if black < 85:
                        blanked = None
                        alive_at = time.monotonic()
                        log("картинка вернулась — снимаю гашение")
                elif blanked == "dim":
                    # Экран погасили мы сами. Переход «картинка → чёрное» — это
                    # наше же гашение, поэтому сравнивать кадры тут бессмысленно:
                    # разница огромная, и сторож снимал гашение сразу после него.
                    if not splash_present():
                        blanked = None
                        alive_at = time.monotonic()
                        log("экран вернули мимо сторожа — снимаю отметку")
                else:
                    alive = False
                    if app in no_blank:
                        alive = True
                    elif diff is not None and diff >= diff_limit:
                        alive = True
                    elif black >= 99 and app and app != our_input:
                        # Так телевизор отдаёт защищённый контент: чёрный кадр при
                        # живом фильме. Не гасим, иначе выключим посреди просмотра.
                        alive = True
                    if alive:
                        alive_at = time.monotonic()
            else:
                # Кадр не получили: это НЕ «картинка не меняется». Считать такую
                # тишину нельзя — иначе при недоступной съёмке сторож погасит
                # телевизор посреди просмотра.
                if not blind_since:
                    blind_since = now
                    log("кадр не получен — отсчёт тишины приостановлен")
                elif int(now - blind_since) % 300 < shot_every:
                    log("кадры не приходят %.0f с (последний удачный %.0f с назад) — гашение не выполняется"
                        % (now - blind_since, now - last_ok_at))

        idle = idle_ms_capped(runtime)
        quiet = quiet_ms(time.monotonic(), alive_at, blind_since)

        if blanked is None:
            if idle >= limit_ms and quiet >= limit_ms:
                choice = blank_choice(app, our_input)
                if choice == "none":
                    # Приложение неизвестно: не гасим ни панель, ни выход.
                    if now - last_unknown_note > 300:
                        last_unknown_note = now
                        log("тишина есть, но приложение телевизора неизвестно — не гашу")
                elif choice == "panel":
                    if tv_screen(False):
                        mark_set(os.path.join(runtime, "stb-tv-blanked"))
                        blanked = "screen"
                        blanked_at = time.monotonic()
                        log("тишина %d мин — гашу панель телевизора (%s)" % (minutes, app))
                    elif now - last_fail_note > 60:
                        last_fail_note = now
                        log("панель не погасилась — повторю на следующем проходе")
                else:
                    if splash_open(port, opened_at):
                        blanked = "dim"
                        blanked_at = time.monotonic()
                        log("тишина %d мин — чёрный экран на приставке" % minutes)
                    elif now - last_fail_note > 60:
                        last_fail_note = now
                        log("выход не погас (xrandr) — повторю на следующем проходе")
                continue
        else:
            if idle < 3000 and time.monotonic() - blanked_at > 5:
                # Нажали наш пульт: экран возвращаем сразу, не дожидаясь кадра.
                # Первая пара секунд не в счёт: F11 и адрес при открытии чёрной
                # первые секунды не в счёт: наши же команды гашения сбрасывают
                # простой ввода (xrandr и правка яркости — не ввод человека).
                if not close_splash_now():
                    log("кнопка была, но экран не вернулся — повторю")
                    continue
                blanked = None
                alive_at = time.monotonic()
                log("кнопка — возвращаю экран")
                continue
            # Ветки ставят разные отметки: гашение выхода — stb-screenblank,
            # салют — stb-tv-blanked. Раньше возраст всегда спрашивали у первой,
            # и после салюта телевизор не уходил в стендбай никогда.
            mark = opened_at if blanked == "dim" else os.path.join(runtime, "stb-tv-blanked")
            age = mark_age(mark) or 0
            if sleep_after > 0 and age >= sleep_after and not os.path.exists(slept_marker):
                tv_sleep_if_idle(age, sleep_after, slept_marker, log)

        awake_tick += 1
        if awake_tick >= 30:
            awake_tick = 0
            keep_display_awake()
        time.sleep(10 if blanked is None else 5)
