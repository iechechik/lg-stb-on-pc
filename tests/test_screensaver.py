"""Сторож тишины: сравнение кадров и один цикл на все случаи.

Правило одно: чёрный экран, если нет ввода и не меняется картинка. Картинку
спрашиваем у самого телевизора, поэтому оно работает и на приставке, и в его
приложениях.
"""
import io
import os
import pathlib
import re

import stbdiff

ROOT = pathlib.Path(os.environ.get("STB_ROOT", "/opt/stb"))


def src(rel):
    return io.open(str(ROOT / rel), encoding="utf-8").read()


def jpeg(color=(0, 0, 0), size=(320, 180), box=None):
    """Кадр в том же виде, в каком его отдаёт телевизор."""
    from PIL import Image

    img = Image.new("RGB", size, color)
    if box:
        for x in range(box[0], box[2]):
            for y in range(box[1], box[3]):
                img.putpixel((x, y), (255, 255, 255))
    out = io.BytesIO()
    img.save(out, "JPEG")
    return out.getvalue()


def test_same_picture_is_quiet():
    sig, _ = stbdiff.signature(jpeg((20, 40, 60)))
    again, _ = stbdiff.signature(jpeg((20, 40, 60)))
    assert stbdiff.diff_percent(sig, again) == 0.0


def test_changed_picture_is_alive():
    sig, _ = stbdiff.signature(jpeg((20, 40, 60)))
    other, _ = stbdiff.signature(jpeg((200, 210, 220)))
    assert stbdiff.diff_percent(sig, other) > 50


def test_small_change_stays_below_threshold():
    """Часы и мелкая подсветка не должны считаться «идёт кино»."""
    sig, _ = stbdiff.signature(jpeg((20, 40, 60)))
    spottish, _ = stbdiff.signature(jpeg((20, 40, 60), box=(10, 10, 20, 16)))
    assert stbdiff.diff_percent(sig, spottish) < 2


def test_black_frame_is_recognised():
    _, black = stbdiff.signature(jpeg((0, 0, 0)))
    assert black > 99


def test_light_frame_is_not_black():
    _, black = stbdiff.signature(jpeg((120, 130, 140)))
    assert black < 1


def test_diff_handles_missing_frame():
    assert stbdiff.diff_percent(None, b"\x00" * 10) is None


def test_old_grid_screensaver_is_gone():
    """Старый сторож «только на сетке» заменён одним правилом."""
    desk = src("lib/stbdesktop.py")
    assert "def watching" not in desk
    assert "def tv_frame" in desk
    assert "tv_shows_own_app" not in desk.split("def cmd_screensaver")[1]


def conf_value(name):
    m = re.search(r'(?m)^%s="([^"]*)"' % name, src("config/stb.conf"))
    assert m, "в конфиге нет %s" % name
    return m.group(1)


def test_thresholds_are_sane():
    """Пороги можно менять, но соотношения между ними должны держаться.

    Точные числа не фиксируем: стенд то и дело ставит короткие пороги для
    проверок. Проверяем смысл — иначе тест придётся править вместе с конфигом.
    """
    screen = int(conf_value("SCREENSAVER_MINUTES"))
    sleep_after = int(conf_value("STB_TV_SLEEP_AFTER"))
    every = int(conf_value("SHOT_EVERY"))
    diff = float(conf_value("SHOT_DIFF_PERCENT"))
    hide = int(conf_value("APP_HIDE_MINUTES"))

    assert screen >= 1, "порог заставки — хотя бы минута"
    assert 0 <= sleep_after <= 120, "стендбай после 0..120 минут"
    assert 5 <= every <= 600, "кадр чаще 5 с — лишняя нагрузка на телевизор"
    assert 0 < diff < 100, "доля изменившихся точек — в процентах"
    assert hide == 0 or hide > screen, "брошенное приложение живёт дольше заставки"


def test_daemon_can_show_and_darken_screen():
    link = src("bin/stb-tv-link")
    assert 'cmd == "shot"' in link
    assert 'cmd == "screen"' in link
    # turnOffScreen на этой прошивке не поддержан: панель гасим заставкой.
    assert "show_screen_saver" in link


def test_tv_off_cleans_up_at_once():
    """Выключение телевизора само закрывает лишнее — не ждём включения."""
    desk = src("lib/stbdesktop.py")
    body = desk.split('say_idle("ТВ выключен → powersave сразу")')[1].split("\ndef ")[0]
    assert "finish_all()" in body


def test_cleaner_runs_only_with_tv_on():
    watch = src("bin/stb-watch")
    assert "if known:" in watch
    assert "jelly_cleanup(jelly_misses)" in watch


def test_hide_outlives_screensaver():
    """Правка в коде, а не в конфиге: таймер скрытия не может опередить заставку."""
    desk = src("lib/stbdesktop.py")
    assert "def hide_minutes():" in desk
    body = desk.split("def hide_minutes():")[1].split("\ndef ")[0]
    assert "max(minutes, screen + 1)" in body
    # таймер не стоит на паузе в темноте: брошенное приложение умирает всегда
    check = desk.split("def hidden_check():")[1].split("\ndef ")[0]
    assert "stb-screenblank" not in check


def test_service_command_is_wired():
    """`stb service` должен уметь и системные, и пользовательские службы."""
    stb = src("bin/stb")
    assert "from stbsvc import cmd_service" in stb
    assert '"service": cmd_service,' in stb
    svc = src("lib/stbsvc.py")
    assert "def user_units(" in svc
    assert '"--user"' in svc


def test_mode_does_not_disable_screensaver():
    """Смена режима пульта не должна гасить сторожа: иначе нет ни салюта, ни сна."""
    body = src("lib/stbcommon.py").split("def mode_set(new):")[1].split("\ndef ")[0]
    assert "SCREEN_FLAG" not in body, "режим снова выключает заставку"
