"""Кадры WebSocket: сборка ответа и чтение кадра от приложения."""
import asyncio
import os
import struct

from stbws import read_ws_frame, ws_frame


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
