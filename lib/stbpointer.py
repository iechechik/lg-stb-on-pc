#!/usr/bin/env python3
"""stbpointer — указатель приложения-пульта, вынесенный из приёмника.

Копит движение и отправляет его 25 раз в секунду: в режиме телевизора — через
демон, в режиме приставки — на самом экране через XTest (или xdotool, если
библиотеки X11 нет). Зависимости передаются снаружи: run() и mode().
"""
import asyncio
import time


class Pointer:
    def __init__(self, run, mode, tv, x11=None, log=None, send_hz=25,
                 click_gap=0.35, on_grid=None, speed=0.35):
        self.run = run
        self.mode = mode
        self.tv = tv
        self.x11 = x11
        self.log = log or (lambda msg: None)
        self.send_hz = send_hz
        self.speed = float(speed)   # чутьё точпада: приложение шлёт крупные шаги
        self.click_gap = click_gap
        self.on_grid = on_grid or (lambda: False)

        self.dx = 0.0
        self.dy = 0.0
        self.rx = 0.0   # остаток меньше пикселя: без него медленное движение залипало
        self.ry = 0.0
        self.last_click = 0.0
        self.client = None
        self.task = None

    def start(self):
        if self.task is None:
            self.task = asyncio.create_task(self.flush_loop())

    def add(self, dx, dy):
        self.dx += dx
        self.dy += dy

    async def tv_client(self):
        if self.client is None:
            self.client = self.tv
        return self.client

    async def apply_motion(self):
        """Отправить накопленное движение немедленно."""
        if not (self.dx or self.dy):
            return
        dx, dy = self.dx + self.rx, self.dy + self.ry
        self.dx = self.dy = 0.0
        self.rx, self.ry = dx - int(dx), dy - int(dy)
        dx, dy = int(dx * self.speed), int(dy * self.speed)
        if not (dx or dy):
            return
        if self.mode() == "tv":
            client = await self.tv_client()
            if client is None:
                return
            try:
                await client.move(dx, dy)
            except Exception as exc:  # noqa: BLE001
                self.log(f"  ошибка указателя в ТВ: {exc}")
                self.client = None
        elif self.x11 is not None:
            self.x11.move(dx, dy)
        else:
            await self.run(["xdotool", "mousemove_relative", "--",
                            str(dx), str(dy)], timeout=5)

    async def flush_loop(self):
        interval = 1.0 / self.send_hz
        while True:
            await asyncio.sleep(interval)
            await self.apply_motion()

    async def click(self):
        # Сначала доводим указатель до последнего положения: иначе нажатие
        # уходит по старому месту.
        await self.apply_motion()
        if self.mode() == "tv":
            client = await self.tv_client()
            if client is not None:
                try:
                    await client.click()
                    self.log("  клик → телевизор")
                except Exception as exc:  # noqa: BLE001
                    self.log(f"  ошибка клика в ТВ: {exc}")
                    self.client = None
        else:
            now = time.monotonic()
            if self.on_grid() and now - self.last_click <= self.click_gap:
                self.last_click = 0.0
                self.log("  клик → приставка (двойной склеен в один)")
                return
            self.last_click = now
            # Два полноэкранных окна (сетка и приложение) стоят друг на друге.
            # Клик уходит в верхнее, а оно может быть не тем, с которым человек
            # работает: нажатие в фильме открывало плитку сетки. Поднимаем
            # активное окно перед нажатием.
            try:
                act = await self.run(["xdotool", "getactivewindow"], timeout=3)
                act = str(act).strip().split()[-1]
                if act:
                    await self.run(["xdotool", "windowraise", act], timeout=3)
            except Exception:  # noqa: BLE001
                pass
            where = ""
            try:
                out = await self.run(["xdotool", "getmouselocation", "--shell"], timeout=3)
                xy = dict(part.split("=", 1) for part in str(out).split() if "=" in part)
                wid = xy.get("WINDOW", "")
                name = await self.run(["xdotool", "getwindowname", wid], timeout=3)
                where = " в (%s,%s) окно «%s»" % (
                    xy.get("X", "?"), xy.get("Y", "?"), str(name).strip()[:40])
            except Exception:  # noqa: BLE001
                where = ""
            if self.x11 is not None:
                self.x11.click(1)
            else:
                await self.run(["xdotool", "click", "1"], timeout=5)
            self.log("  клик → приставка" + where)

    async def scroll(self, dy):
        if self.mode() == "tv":
            client = await self.tv_client()
            if client is not None:
                try:
                    await client.scroll(0, dy)
                except Exception:  # noqa: BLE001
                    self.client = None
        elif self.x11 is not None:
            self.x11.scroll(dy)
        else:
            button = "4" if dy > 0 else "5"
            for _ in range(max(1, abs(int(dy)))):
                await self.run(["xdotool", "click", button], timeout=5)
