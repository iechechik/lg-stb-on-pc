#!/usr/bin/env python3
"""stbback — логика кнопки Back, вынесенная из приёмника пульта.

Приложение-пульт присылает одно нажатие дважды с разницей 0–200 мс, поэтому
события сначала склеиваются в «нажим». Два нажима подряд в режиме телевизора
означают возврат на приставку, причём первый Back в телевизор не уходит:
он придерживается и отменяется, если пришёл второй.
"""


class BackGate:
    def __init__(self, dup_gap=0.25):
        self.dup_gap = dup_gap
        self.last_raw = 0.0
        self.pending = False      # одиночный Back ждёт отправки в телевизор

    def duplicate(self, now):
        """Повтор того же физического нажатия (приложение шлёт пару событий)."""
        if self.last_raw and now - self.last_raw <= self.dup_gap:
            self.last_raw = now
            return True
        self.last_raw = now
        return False

    def press(self):
        """Новый нажим: 'tobox' — возврат на приставку, 'wait' — придержать."""
        if self.pending:
            self.pending = False
            return "tobox"
        self.pending = True
        return "wait"

    def fired(self):
        """Отложенный Back ушёл в телевизор."""
        self.pending = False

    def cancel(self):
        """Отложенный Back отменён (пришёл второй нажим)."""
        self.pending = False
