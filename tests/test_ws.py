"""WebSocket: кадры, сборка сообщений, обрыв посреди сообщения."""
import asyncio
import os
import struct

import pytest

from stbws import read_ws_frame, read_ws_message, ws_frame



def masked_frame(payload, opcode=0x1):
    """Кадр так, как его присылает приложение: с маской."""
    data = payload.encode() if isinstance(payload, str) else payload
    mask = os.urandom(4)
    head = bytearray([0x80 | opcode])
    n = len(data)
    if n < 126:
        head.append(0x80 | n)
    elif n < 65536:
        head.append(0x80 | 126)
        head += struct.pack(">H", n)
    else:
        head.append(0x80 | 127)
        head += struct.pack(">Q", n)
    body = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return bytes(head) + mask + body


def read(frame):
    async def scenario():
        reader = asyncio.StreamReader()
        reader.feed_data(frame)
        reader.feed_eof()
        return await read_ws_frame(reader)

    return asyncio.run(scenario())


def test_short_frame():
    opcode, payload = read(masked_frame("type:button\nname:UP\n"))
    assert opcode == 0x1
    assert payload == b"type:button\nname:UP\n"


def test_medium_frame():
    text = "x" * 1000
    opcode, payload = read(masked_frame(text))
    assert opcode == 0x1
    assert payload.decode() == text


def test_cyrillic_payload():
    opcode, payload = read(masked_frame("привет"))
    assert payload.decode("utf-8") == "привет"


def test_server_frame_header():
    frame = ws_frame("ok")
    assert frame[0] == 0x81
    assert frame[1] == 2


def test_pong_opcode():
    frame = ws_frame(b"pingdata", opcode=0xA)
    assert frame[0] == 0x8A
    assert frame.endswith(b"pingdata")


def test_handshake_key():
    from stbws import ws_accept

    assert ws_accept("dGhlIHNhbXBsZSBub25jZQ==") == \
        "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


def frame(payload, opcode=0x1, fin=True):
    """Кадр так, как его присылает приложение: с маской."""
    data = payload.encode() if isinstance(payload, str) else payload
    mask = os.urandom(4)
    head = bytearray([(0x80 if fin else 0) | opcode])
    n = len(data)
    if n < 126:
        head.append(0x80 | n)
    elif n < 65536:
        head.append(0x80 | 126)
        head += struct.pack(">H", n)
    else:
        head.append(0x80 | 127)
        head += struct.pack(">Q", n)
    body = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return bytes(head) + mask + body


def read_one(data, max_size=None):
    async def scenario():
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        reader.feed_eof()
        extra = {} if max_size is None else {"max_size": max_size}
        return await read_ws_message(reader, **extra)

    return asyncio.run(scenario())


def read_two(data):
    async def scenario():
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        reader.feed_eof()
        return await read_ws_message(reader), await read_ws_message(reader)

    return asyncio.run(scenario())


def test_two_fragments():
    opcode, payload = read_one(frame("type:button\n", fin=False)
                               + frame("name:UP\n", opcode=0x0))
    assert opcode == 0x1
    assert payload == b"type:button\nname:UP\n"


def test_ping_between_fragments():
    data = (frame("type:but", fin=False) + frame(b"", opcode=0x9)
            + frame("ton\nname:UP\n", opcode=0x0))
    (op1, pay1), (op2, pay2) = read_two(data)
    assert op1 == 0x9 and pay1 == b""
    assert op2 == 0x1 and pay2 == b"type:button\nname:UP\n"


def test_message_too_big():
    with pytest.raises(ValueError):
        read_one(frame("x" * 100, fin=False) + frame("y" * 100, opcode=0x0), max_size=120)


def test_unexpected_data_frame_inside_message():
    with pytest.raises(ValueError):
        read_one(frame("начало", fin=False) + frame("другое", opcode=0x1))


def test_continuation_without_start():
    with pytest.raises(ValueError):
        read_one(frame("хвост", opcode=0x0))


def test_close_inside_message():
    op, _pay = read_one(frame("начало", fin=False) + frame(b"", opcode=0x8))
    assert op == 0x8


def test_plain_message_still_works():
    text = "просто сообщение"
    opcode, payload = read_one(frame(text))
    assert opcode == 0x1 and payload == text.encode()


def test_ws_reader_forgotten_on_disconnect():
    import stbws

    async def scenario():
        reader = asyncio.StreamReader()
        # Начало сообщения и обрыв: продолжения не будет.
        reader.feed_data(frame("начало", fin=False))
        reader.feed_eof()
        with pytest.raises(asyncio.IncompleteReadError):
            await stbws.read_ws_message(reader)
        return dict(stbws._PENDING)

    assert asyncio.run(scenario()) == {}
