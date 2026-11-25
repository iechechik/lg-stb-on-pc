"""Ввод текста на телевизор: разбор аргументов и буфер накопления."""
import asyncio

import pytest

from stbtext import TextBuffer



def test_plain_text(tvtext):
    assert tvtext.parse_args(["привет"]) == ("привет", False, 0)


def test_text_after_separator(tvtext):
    assert tvtext.parse_args(["--", "--delete молоко"]) == ("--delete молоко", False, 0)


def test_delete_count(tvtext):
    assert tvtext.parse_args(["--delete", "3"]) == (None, False, 3)


def test_enter_flag(tvtext):
    assert tvtext.parse_args(["--enter"]) == (None, True, 0)


def test_text_with_enter(tvtext):
    assert tvtext.parse_args(["--", "текст", "--enter"]) == ("текст", True, 0)


def test_unknown_option_rejected(tvtext):
    with pytest.raises(SystemExit):
        tvtext.parse_args(["--nope"])


def test_delete_without_count_rejected(tvtext):
    with pytest.raises(SystemExit):
        tvtext.parse_args(["--delete"])


class Harness:
    """Буфер с перехваченными вызовами вместо xdotool и ручными часами."""

    def __init__(self, mode="nuc"):
        self.calls = []
        self.logs = []
        self.now = 100.0
        self.buf = TextBuffer(delay=0, run=self._run, mode=lambda: mode,
                              clock=lambda: self.now, log=self.logs.append)

    async def _run(self, cmd, timeout=25):
        self.calls.append(list(cmd))
        return True

    def feed_all(self, texts, gap=0.2):
        async def scenario():
            for text in texts:
                self.now += gap
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


def test_repeated_letter_is_typed():
    """Ручной набор «ссс» больше не превращается в «с»."""
    h = Harness()
    h.feed_all(["с", "с", "с"], gap=0.2)
    assert h.typed() == ["ссс"]


def test_physical_duplicate_of_one_letter_glued():
    """Пара событий на одно нажатие (0,02 с) — один символ."""
    h = Harness()
    h.feed_all(["с", "с"], gap=0.02)
    assert h.typed() == ["с"]


def test_request_after_enter_is_not_skipped():
    """Тот же запрос после Enter уходит снова."""
    h = Harness()

    async def scenario():
        h.now += 0.2
        h.buf.feed("сериал")
        await h.buf.flush()
        h.buf.reset()          # Enter сбрасывает буфер
        h.now += 5.0
        h.buf.feed("сериал")
        await h.buf.flush()

    asyncio.run(scenario())
    assert h.typed() == ["сериал", "сериал"]


def test_duplicate_skip_is_logged_with_text_and_gap():
    """По журналу видно, что пропущено и с каким зазором."""
    h = Harness()
    h.feed_all(["молоко", "молоко"], gap=0.05)
    joined = " | ".join(h.logs)
    assert "пропуск 'молоко'" in joined, joined
    assert "0.05 с" in joined, joined
