"""Препроцессор плиток: комментарии разрешены, результат — обычный JSON."""
import json


def test_line_comments(stbweb):
    raw = '{"a": 1, // пояснение\n "b": 2}'
    assert json.loads(stbweb.preprocess_json(raw)) == {"a": 1, "b": 2}


def test_block_comments(stbweb):
    raw = '{"a": 1, /* многострочное\n пояснение */ "b": 2}'
    assert json.loads(stbweb.preprocess_json(raw)) == {"a": 1, "b": 2}


def test_trailing_commas(stbweb):
    raw = '{"a": [1, 2,], "b": 3,}'
    assert json.loads(stbweb.preprocess_json(raw)) == {"a": [1, 2], "b": 3}


def test_url_inside_string_is_not_comment(stbweb):
    raw = '{"url": "http://127.0.0.1:8090/", "x": 1}'
    assert json.loads(stbweb.preprocess_json(raw)) == {"url": "http://127.0.0.1:8090/", "x": 1}


def test_real_tiles_file(stbweb):
    """Настоящий файл плиток должен читаться и содержать плитки."""
    items = stbweb.load_tiles() if hasattr(stbweb, "load_tiles") else None
    if items is None:
        import io
        items = json.loads(stbweb.preprocess_json(
            io.open("/opt/stb/config/tiles.json", encoding="utf-8").read()))
    assert isinstance(items, list) and len(items) >= 10
