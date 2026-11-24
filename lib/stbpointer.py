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
                 click_gap=0.35, on_grid=None):
        self.run = run
        self.mode = mode
        self.tv = tv
        self.x11 = x11
        self.log = log or (lambda msg: None)
        self.send_hz = send_hz
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

    async def flush_loop(self):
        interval = 1.0 / self.send_hz
        while True:
            await asyncio.sleep(interval)
            if not (self.dx or self.dy):
                continue
            dx, dy = self.dx + self.rx, self.dy + self.ry
            self.dx = self.dy = 0.0
            self.rx, self.ry = dx - int(dx), dy - int(dy)
            dx, dy = int(dx), int(dy)
            if not (dx or dy):
                continue
            if self.mode() == "tv":
                client = await self.tv_client()
                if client is None:
                    continue
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

    async def click(self):
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
            if self.x11 is not None:
                self.x11.click(1)
            else:
                await self.run(["xdotool", "click", "1"], timeout=5)
            self.log("  клик → приставка")

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
