#!/usr/bin/env python3
"""stbx11 — указатель на самом экране через XTest, без запуска процессов.

Раньше каждое движение указателя запускало xdotool: 25 процессов в секунду
на слабом i3. Здесь движение — один вызов библиотеки X11.

    p = LocalPointer()
    p.move(3.4, -1.2)      дробные доли не теряются
    p.click()              левая кнопка
    p.scroll(+1)           колесо
"""
import os


class LocalPointer:
    def __init__(self, dpy=None):
        from Xlib import display  # noqa: PLC0415

        self.d = display.Display(dpy or os.environ.get("DISPLAY", ":0"))
        self.root = self.d.screen().root
        self.rx = 0.0
        self.ry = 0.0

    def move(self, dx, dy):
        """Сдвиг указателя с накоплением долей: медленное движение не залипает."""
        self.rx += dx
        self.ry += dy
        ix, iy = int(self.rx), int(self.ry)
        if not (ix or iy):
            return
        self.rx -= ix
        self.ry -= iy
        from Xlib import X  # noqa: PLC0415
        from Xlib.ext import xtest  # noqa: PLC0415

        pos = self.root.query_pointer()
        xtest.fake_input(self.d, X.MotionNotify, x=pos.root_x + ix, y=pos.root_y + iy)
        self.d.sync()

    def click(self, button=1):
        from Xlib import X  # noqa: PLC0415
        from Xlib.ext import xtest  # noqa: PLC0415

        xtest.fake_input(self.d, X.ButtonPress, button)
        self.d.sync()
        xtest.fake_input(self.d, X.ButtonRelease, button)
        self.d.sync()

    def scroll(self, dy):
        button = 4 if dy > 0 else 5
        for _ in range(max(1, abs(int(dy)))):
            self.click(button)


def open_pointer():
    """Указатель XTest или None, если библиотеки нет (тогда зовём xdotool)."""
    try:
        return LocalPointer()
    except Exception:  # noqa: BLE001
        return None
