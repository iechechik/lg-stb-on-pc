#!/usr/bin/env python3
"""stbtvlast — что телевизор показывал последним, кроме входа приставки.

После возврата в сетку телевизор стоит на нашем HDMI, поэтому плитка
«Телевизор» не может «оставить как было» — было наше. Запоминаем на диск
последнее чужое приложение: сторож и так спрашивает у демона текущее
приложение каждые несколько секунд, остаётся записать изменение.

    TV_INPUT_ID        вход, на котором сидит приставка (HDMI_3 → com.webos.app.hdmi3)
    STB_TV_LAST        файл памяти (по умолчанию /var/lib/stb/tv-last)
"""

DEFAULT_PATH = "/var/lib/stb/tv-last"


def path(getter=None):
    """Файл памяти: окружение (для проверок), конфиг, по умолчанию."""
    import os
    env = os.environ.get("STB_TV_LAST")
    if env:
        return env
    if getter is None:
        return DEFAULT_PATH
    return str(getter("STB_TV_LAST", DEFAULT_PATH) or DEFAULT_PATH)


def ours(getter):
    """appId нашего входа: HDMI_3 → com.webos.app.hdmi3."""
    inp = str(getter("TV_INPUT_ID", "") or "").strip()
    return ("com.webos.app." + inp.lower().replace("_", "")) if inp else ""


def is_foreign(app, getter):
    """Приложение чужое: непустое и это не наш вход."""
    app = str(app or "").strip()
    return bool(app) and app.lower() != ours(getter)


def last(getter=None):
    """Что запомнили; пусто, если ещё ничего не смотрели."""
    try:
        with open(path(getter), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def remember(app, getter):
    """Запомнить приложение, если оно не наше. True — файл переписан."""
    import os
    if not is_foreign(app, getter):
        return False
    app = str(app).strip()
    if last(getter) == app:
        return False
    target = path(getter)
    try:
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(app + "\n")
        return True
    except OSError:
        return False
