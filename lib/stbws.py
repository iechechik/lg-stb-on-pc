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


# Незаконченные сообщения: ключ — id(reader), значение — состояние сборки.
# Держим и сам reader, чтобы его id не был переиспользован другим соединением.
_PENDING = {}


def _drop_pending(key):
    _PENDING.pop(key, None)


def forget_ws_reader(reader):
    """Забыть незавершённое сообщение этого соединения (зовётся при разрыве)."""
    _PENDING.pop(id(reader), None)


async def _read_message(reader, max_size=MAX_MESSAGE):
    """Сообщение целиком; управляющий кадр внутри сообщения не ломает сборку.

    Клиент вправе прислать PING между фрагментами (TEXT FIN=0, PING,
    CONTINUATION FIN=1). Тогда ping отдаётся вызывающему сразу, а сборка
    продолжается со следующего вызова: состояние лежит в `_PENDING`.
    """
    key = id(reader)
    state = _PENDING.get(key)

    if state is None:
        opcode, payload, fin = await _frame(reader, max_size)
        if opcode >= 0x8:            # ping/pong/close не фрагментируются
            return opcode, payload
        if opcode == 0x0:
            raise ValueError("продолжение без начала сообщения")
        if fin:
            return opcode, payload
        state = {"reader": reader, "opcode": opcode, "parts": [payload],
                 "size": len(payload)}
        _PENDING[key] = state

    while True:
        op, chunk, fin = await _frame(reader, max_size)
        if op >= 0x8:
            # Управляющий кадр: отдаём его, а сборку оставляем до следующего раза.
            if op == 0x8:            # close — сообщение уже не продолжится
                _drop_pending(key)
            return op, chunk
        if op != 0x0:
            _drop_pending(key)
            raise ValueError("неожиданный кадр %#x внутри сообщения" % op)
        state["size"] += len(chunk)
        if state["size"] > max_size:
            _drop_pending(key)
            raise ValueError("сообщение больше %d байт" % max_size)
        state["parts"].append(chunk)
        if fin:
            _drop_pending(key)
            return state["opcode"], b"".join(state["parts"])


async def read_ws_message(reader, max_size=MAX_MESSAGE):
    """Чтение с очисткой: оборванное сообщение не остаётся в памяти.

    Разрыв посреди фрагментированного сообщения поднимает исключение — без
    очистки состояние сборки (до 1 МиБ плюс сам reader) копилось бы на каждое
    такое подключение.
    """
    try:
        return await _read_message(reader, max_size)
    except Exception:
        forget_ws_reader(reader)
        raise
