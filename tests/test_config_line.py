"""Единый разбор строк конфигов."""
import os
import sys

ROOT = os.environ.get("STB_ROOT", "/opt/stb")
sys.path.insert(0, os.path.join(ROOT, "lib"))

import stbconf  # noqa: E402


def test_comment_after_value_is_dropped():
    assert stbconf.parse_line('BLUE=blue             # синяя: режим 4K') == ("BLUE", "blue")


def test_quoted_hash_survives():
    assert stbconf.parse_line('URL="http://host/#frag"') == ("URL", "http://host/#frag")


def test_plain_value_is_stripped():
    assert stbconf.parse_line("  KEY =  value  ") == ("KEY", "value")


def test_comment_only_and_blank_and_junk():
    assert stbconf.parse_line("# только комментарий") is None
    assert stbconf.parse_line("   ") is None
    assert stbconf.parse_line("без знака равно") is None
    assert stbconf.parse_line("=без ключа") is None


def test_single_quotes_are_unwrapped():
    assert stbconf.parse_line("A='x y'") == ("A", "x y")


def test_escaped_hash_stays_in_value():
    assert stbconf.parse_line("PASS=pa\\#ss") == ("PASS", "pa#ss")


def test_escaped_hash_and_trailing_comment():
    assert stbconf.parse_line("PASS=pa\\#ss   # пояснение") == ("PASS", "pa#ss")


def test_escaped_hash_inside_quotes():
    assert stbconf.parse_line('URL="http://h/#a\\#b"') == ("URL", "http://h/#a#b")


def test_escaped_quote_does_not_open_quotes():
    assert stbconf.parse_line("A=it\\'s # хвост") == ("A", "it's")
