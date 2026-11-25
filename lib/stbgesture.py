#!/usr/bin/env python3
"""stbgesture — кнопки с выдержкой: одиночное и двойное нажатие как два события.

Слой считает только время: склеивает повтор того же нажатия, придерживает
одиночное на окно и говорит, что пришло — «двойное» или «придержать». Что
делать в каждом случае, решает обработчик (`bin/stb`): там вся специфика —
приложение, браузер, сетка, режим телевизора.

Через слой идут только кнопки из `GESTURES` (по умолчанию одна — BACK).
Остальные кнопки слой не видит вовсе: они уходят сразу, без ожидания.

    GESTURES="BACK"     — какие кнопки распознавать (через пробел)
    DOUBLE_BACK="1.0"   — окно второго нажатия, секунды
    DUP_BACK="0.12"     — склейка повторов, секунды

Для новой кнопки достаточно дописать её имя в GESTURES: окно и склейка
берутся из DOUBLE_<ИМЯ> и DUP_<ИМЯ>, а без них — 1.0 и 0.12. Двойное
нажатие приходит обработчику как `<имя>-double`.
"""

DEFAULT_WINDOW = 1.0
DEFAULT_DUP_GAP = 0.12
DEFAULT_KEYS = "BACK"


class Gesture:
    """Состояние одной кнопки: склейка повторов и придержка одиночного."""

    def __init__(self, window=DEFAULT_WINDOW, dup_gap=DEFAULT_DUP_GAP):
        self.window = window
        self.dup_gap = dup_gap
        self.last_raw = 0.0
        self.pending = False

    def duplicate(self, now):
        """Повтор того же физического нажатия (приложение шлёт пару событий)."""
        if self.last_raw and now - self.last_raw <= self.dup_gap:
            self.last_raw = now
            return True
        self.last_raw = now
        return False

    def press(self):
        """`двойное` — второе нажатие в окне, `придержать` — ждём второго."""
        if self.pending:
            self.pending = False
            return "double"
        self.pending = True
        return "wait"

    def fired(self):
        """Придержанное нажатие ушло одиночным."""
        self.pending = False


def double_action(name):
    """Имя действия для двойного нажатия: BACK → back-double."""
    return "%s-double" % (name or "").strip().lower()


def load(getter):
    """Набор кнопок из конфига: имя → Gesture. `getter(имя, по умолчанию)`."""
    names = str(getter("GESTURES", DEFAULT_KEYS) or DEFAULT_KEYS).split()
    keys = {}
    for raw in names:
        name = raw.strip().upper()
        if not name:
            continue
        keys[name] = Gesture(_number(getter, "DOUBLE_" + name, DEFAULT_WINDOW),
                             _number(getter, "DUP_" + name, DEFAULT_DUP_GAP))
    return keys


def _number(getter, key, default):
    try:
        return float(getter(key, str(default)))
    except (TypeError, ValueError):
        return default
