"""Разбор аргументов ввода текста: текст с дефисов не должен стать опцией."""
import pytest


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
