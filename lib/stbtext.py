#!/usr/bin/env python3
"""stbtext — буфер текста с телефона.

Диктовка приходит кумулятивно («сериал», «сериал про», «сериал про тупиц»),
ручной набор — по символу. Здесь решается, что допечатать и сколько стереть.
Отправка и режим передаются снаружи: run(cmd) и mode().
"""
import asyncio


class TextBuffer:
    """Приложение присылает текст по-разному:

    * ручной набор — по одному символу (это готовая добавка);
    * диктовка — КУМУЛЯТИВНО: «сериал», «сериал про», «сериал про тупиц»,
      то есть каждый раз весь текст заново.

    Держим то, что уже напечатано (typed), и считаем разницу. Печатаем пачкой,
    чтобы быстрые интерфейсы (Sonarr) не теряли символы.
    """

    def __init__(self, delay=0.25, run=None, mode=None, log=None):
        self.run = run                # чем отправлять (async)
        self.mode = mode or (lambda: "nuc")
        self.log = log or (lambda msg: None)
        self.delay = delay
        self.last = ""       # последний присланный кусок
        self.dels = 0        # сколько символов стереть
        self.pending = ""    # что осталось допечатать
        self.task = None

    def feed(self, text):
        """Куски текста только прибавляются. Повтор того же куска — пропуск,
        кусок длиннее предыдущего — дописываем только хвост."""
        if not text:
            return
        if text == self.last:
            self.log("ТЕКСТ: повтор куска, пропускаю")
            return
        if self.last and text.startswith(self.last):
            delta = text[len(self.last):]
            self.last = text
            self.pending += delta
        elif self.last and self.last.startswith(text) and len(text) < len(self.last):
            self.schedule()
            n = len(self.last) - len(text)
            self.last = text
            self._backspace(n)
            return
        else:
            self.last = text
            self.pending += text
        self.schedule()

    def schedule(self):
        if self.task:
            self.task.cancel()
        self.task = asyncio.create_task(self._later())

    async def _later(self):
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            return
        await self.flush()

    async def flush(self):
        if self.dels:
            n, self.dels = self.dels, 0
            if self.mode() == "tv":
                await self.run(["/opt/stb/bin/stb", "tv", "text", "--delete", str(n)])
            elif n >= 3:
                # много удалений подряд — чистим поле целиком, так не теряются
                await self.run(["xdotool", "key", "--clearmodifiers", "ctrl+a"], timeout=5)
                await self.run(["xdotool", "key", "--clearmodifiers", "Delete"], timeout=5)
            else:
                await self.run(["xdotool", "key", "--clearmodifiers",
                                "--repeat", str(n), "BackSpace"], timeout=5)
            self.log(f"ТЕКСТ: стёрено {n} симв.")

        chunk, self.pending = self.pending, ""
        if not chunk:
            return
        if self.mode() == "tv":
            await self.run(["/opt/stb/bin/stb", "tv", "text", "--", chunk])
        else:
            await self.run(["xdotool", "type", "--clearmodifiers", "--delay", "80", chunk], timeout=30)
        self.log(f"ТЕКСТ: допечатал {chunk!r}")

    def _backspace(self, count):
        """Удаления копим: по одному нажатию запускать xdotool накладно."""
        if count <= 0:
            return
        self.dels += int(count)
        self.schedule()

    async def _replace_all(self, text):
        if self.mode() == "tv":
            await self.run(["/opt/stb/bin/stb", "tv", "text", "--delete", str(len(self.last) or 1)])
            await self.run(["/opt/stb/bin/stb", "tv", "text", "--", text])
        else:
            await self.run(["xdotool", "key", "--clearmodifiers", "ctrl+a"], timeout=5)
            await self.run(["xdotool", "type", "--clearmodifiers", "--delay", "80", text], timeout=30)
        self.log(f"ТЕКСТ: заменил всё на {text!r}")
