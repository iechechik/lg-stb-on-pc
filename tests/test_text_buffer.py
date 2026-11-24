"""Буфер текста: кумулятивная диктовка, повторы, удаления."""
import asyncio

from stbtext import TextBuffer


class Harness:
    """Буфер с перехваченными вызовами вместо xdotool."""

    def __init__(self, mode="nuc"):
        self.calls = []
        self.buf = TextBuffer(delay=0, run=self._run, mode=lambda: mode)

    async def _run(self, cmd, timeout=25):
        self.calls.append(list(cmd))
        return True

    def feed_all(self, texts):
        async def scenario():
            for text in texts:
                self.buf.feed(text)
            if self.buf.task:
                self.buf.task.cancel()
                self.buf.task = None
            await self.buf.flush()

        asyncio.run(scenario())

    def typed(self):
        return [c[-1] for c in self.calls if "type" in c]


def test_cumulative_dictation_types_once():
    h = Harness()
    h.feed_all(["сериал", "сериал про", "сериал про тупиц"])
    assert h.typed() == ["сериал про тупиц"]


def test_same_piece_twice_is_ignored():
    h = Harness()
    h.feed_all(["молоко", "молоко"])
    assert h.typed() == ["молоко"]


def test_shrinking_text_deletes_tail():
    h = Harness()
    h.feed_all(["сериал про", "сериал"])
    assert [c for c in h.calls if "BackSpace" in c or "Delete" in c], h.calls


def test_empty_text_does_nothing():
    h = Harness()
    h.feed_all([""])
    assert h.calls == []


def test_tv_mode_goes_through_tv_text():
    """В режиме телевизора текст печатает tv-text, а не xdotool."""
    h = Harness(mode="tv")
    h.feed_all(["молоко"])
    assert any(("tv-text" in " ".join(c))
               or ("stb" in " ".join(c) and "text" in " ".join(c))
               for c in h.calls), h.calls
