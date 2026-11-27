"""Сравнение кадров телевизора: шевельнулась ли картинка.

Кадр приходит JPEG-ом с самого телевизора (SSAP take_screenshot), поэтому
проверка работает и на нашем входе, и в его собственных приложениях. Сравнивать
файлы побайтно нельзя: телевизор кодирует один и тот же кадр по-разному, файлы
различаются даже на неподвижной картинке. Сравниваем прореженные пиксели с
допуском по яркости.
"""
import io

SIZE = (160, 90)          # прореживание: 14400 точек хватает, чтобы отличить
TOLERANCE = 8             # шум JPEG и лёгкая дрожь кодека
BLACK_LEVEL = 12          # темнее — считаем «чёрный» (защита контента)


def signature(data):
    """JPEG → (прореженные точки, доля чёрных точек в процентах)."""
    from PIL import Image

    img = Image.open(io.BytesIO(data)).convert("L").resize(SIZE, Image.BILINEAR)
    pixels = img.tobytes()
    black = 100.0 * sum(1 for value in pixels if value < BLACK_LEVEL) / len(pixels)
    return pixels, black


def diff_percent(old, new):
    """Сколько точек изменилось, %: 0 — картинка стоит, 100 — сменилась вся."""
    if not old or not new or len(old) != len(new):
        return None
    changed = sum(1 for a, b in zip(old, new) if abs(a - b) > TOLERANCE)
    return 100.0 * changed / len(new)
