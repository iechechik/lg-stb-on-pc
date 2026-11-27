#!/usr/bin/env python3
"""stbtext — буфер текста с телефона.

Диктовка приходит кумулятивно («сериал», «сериал про», «сериал про тупиц»),
ручной набор — по символу. Здесь решается, что допечатать и сколько стереть.
Отправка и режим передаются снаружи: run(cmd) и mode().
"""
import asyncio
import subprocess
import time


def _layout():
    """Текущая раскладка X.

    В русской раскладке xdotool type молча теряет заглавные латинские: «Mam13Tan»
    печатается как «mam13Tan», и пароль не подходит. Поэтому перед набором
    включаем us, после — возвращаем прежнюю.
    """
    try:
        out = subprocess.run(["setxkbmap", "-query"], capture_output=True,
                             text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    for line in out.splitlines():
        if line.startswith("layout:"):
            return line.split(":", 1)[1].strip()
    return ""


class TextBuffer:
    """Буфер накопления текста перед отправкой.

    * ручной набор — по одному символу (это готовая добавка);
    * диктовка — КУМУЛЯТИВНО: «сериал», «сериал про», «сериал про тупиц»,
      то есть каждый раз весь текст заново.

    Держим то, что уже напечатано (typed), и считаем разницу. Печатаем пачкой,
    чтобы быстрые интерфейсы (Sonarr) не теряли символы.

    Повтор того же куска отсекается ТОЛЬКО по времени: приложение присылает одно
    событие дважды. Сравнивать содержимое нельзя — ручной набор «ссс» превращался
    в «с». Одиночный символ отсекается лишь на совсем близком повторе: две буквы
    за 60 мс человек не набирает, а пара событий на одно нажатие приходит именно
    так.
    """

    def __init__(self, delay=0.25, run=None, mode=None, log=None,
                 dup_gap=0.25, single_gap=0.06, clock=None):
        self.run = run                # чем отправлять (async)
        self.mode = mode or (lambda: "nuc")
        self.log = log or (lambda msg: None)
        self.delay = delay
        self.dup_gap = dup_gap        # окно повторного куска (диктовка)
        self.single_gap = single_gap  # окно повтора одиночного символа
        self.clock = clock or time.monotonic
        self.last = ""       # последний присланный кусок
        self.last_time = 0.0
        self.dels = 0        # сколько символов стереть
        self.pending = ""    # что осталось допечатать
        self.task = None

    def feed(self, text):
        """Кусок текста от приложения.

        Куски только прибавляются: длиннее предыдущего — дописываем хвост,
        короче — стираем разницу. Повтор отсекается по времени.
        """
        if not text:
            return
        now = self.clock()
        if self._duplicate(text, now):
            # В журнал — и текст, и зазор: по ним видно, был это дубль события
            # или второй одинаковый кусок диктовки.
            self.log("ТЕКСТ: пропуск %r (%.2f с) — повтор того же куска"
                     % (text, now - self.last_time))
            return
        self.last_time = now
        if self.last and text == self.last:
            # Новое нажатие с тем же текстом: дописываем целиком. Раньше такой
            # кусок считался «без хвоста», и вторая одинаковая буква пропадала.
            self.pending += text
        elif self.last and text.startswith(self.last):
            self.pending += text[len(self.last):]
        elif self.last and self.last.startswith(text) and len(text) < len(self.last):
            self.schedule()
            n = len(self.last) - len(text)
            self.last = text
            self._backspace(n)
            return
        else:
            self.pending += text
        self.last = text
        self.schedule()

    def _duplicate(self, text, now):
        """Тот же кусок, пришедший вторым событием того же нажатия."""
        if text != self.last:
            return False
        gap = now - self.last_time
        limit = self.single_gap if len(text) == 1 else self.dup_gap
        return gap <= limit

    async def _type(self, text):
        """Напечатать текст. Раскладка приставки всегда us.

        Переключений нет: us ставится один раз при старте. Здесь только страховка
        — если раскладку всё же сменили, вернуть us: в ru xdotool теряет латинские
        буквы (замерено: «Mam13Tan» → «13»), а кириллицу браузер принимает и в us.
        """
        if _layout().split(",")[0] != "us":
            await self.run(["setxkbmap", "us"], timeout=5)
        await self.run(["xdotool", "type", "--clearmodifiers", "--delay", "80", text],
                       timeout=30)

    def reset(self):
        """Enter или удаление: дальше считаем с чистого листа.

        Без этого тот же запрос, отправленный после Enter, молча пропускался:
        буфер считал его повтором предыдущего куска.
        """
        self.last = ""
        self.last_time = 0.0

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
            self.log(f"ТЕКСТ: стёрто {n} симв.")

        chunk, self.pending = self.pending, ""
        if not chunk:
            return
        if self.mode() == "tv":
            await self.run(["/opt/stb/bin/stb", "tv", "text", "--", chunk])
        else:
            await self._type(chunk)
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
            await self._type(text)
        self.log(f"ТЕКСТ: заменил всё на {text!r}")