#!/usr/bin/env python3
"""stbws — кадры WebSocket: рукопожатие, сборка ответа, чтение от клиента.

Выделено из приёмника пульта, чтобы протокол можно было проверять тестами
без запуска сервера.
"""
import base64
import hashlib
import struct

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def ws_accept(key):
    return base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
    ).decode()


def ws_frame(payload, opcode: int = 0x1) -> bytes:
    data = payload if isinstance(payload, bytes) else str(payload).encode()
    head = bytearray([0x80 | opcode])
    if len(data) < 126:
        head.append(len(data))
    elif len(data) < 65536:
        head.append(126)
        head += struct.pack(">H", len(data))
    else:
        head.append(127)
        head += struct.pack(">Q", len(data))
    return bytes(head) + data


MAX_MESSAGE = 1 << 20   # 1 МиБ: пульту столько не нужно, а память бережёт


async def _frame(reader, max_size=MAX_MESSAGE):
    """Один кадр: (opcode, payload, fin)."""
    b1 = await reader.readexactly(2)
    fin = bool(b1[0] & 0x80)
    opcode = b1[0] & 0x0F
    masked = b1[1] & 0x80
    length = b1[1] & 0x7F
    if length == 126:
        length = struct.unpack(">H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", await reader.readexactly(8))[0]
    if length > max_size:
        raise ValueError("кадр больше %d байт" % max_size)
    mask = await reader.readexactly(4) if masked else b""
    payload = await reader.readexactly(length) if length else b""
    if masked:
        payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
    return opcode, payload, fin


async def read_ws_frame(reader, max_size=MAX_MESSAGE):
    """Один кадр: (opcode, payload)."""
    opcode, payload, _fin = await _frame(reader, max_size)
    return opcode, payload


async def read_ws_message(reader, max_size=MAX_MESSAGE):
    """Сообщение целиком: фрагменты склеиваются, управляющие кадры — как есть."""
    opcode, payload, fin = await _frame(reader, max_size)
    if opcode >= 0x8:            # ping/pong/close не фрагментируются
        return opcode, payload
    parts = [payload]
    size = len(payload)
    while not fin:
        op, chunk, fin = await _frame(reader, max_size)
        if op != 0x0:            # новое сообщение вместо продолжения — отдаём как есть
            break
        size += len(chunk)
        if size > max_size:
            raise ValueError("сообщение больше %d байт" % max_size)
        parts.append(chunk)
    return opcode, b"".join(parts)
