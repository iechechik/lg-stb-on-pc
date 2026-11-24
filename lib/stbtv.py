#!/usr/bin/env python3
"""stbtv — общий клиент демона телевизора для всех частей приставки.

Демон (stb-tv-link) держит одно соединение с телевизором; все остальные
ходят к нему через сокет /run/stb/tv.sock. Так нажатие занимает десятки
миллисекунд вместо запуска отдельного процесса с WebSocket-рукопожатием.

    tv = TvDaemon()
    tv.ask({"cmd": "state"})            синхронно
    await tv.key("UP")                  асинхронно
"""
import asyncio
import json
import os
import socket
import time

SOCK = os.environ.get("STB_TV_SOCK", "/run/stb/tv.sock")

# Клиент ждёт дольше, чем демон тратит на команду (6 с): иначе пульт считает
# нажатие неудачным и повторяет его, а демон ещё выполняет первое.
DEFAULT_TIMEOUT = 8.0


class TvDaemon:
    def __init__(self, path=SOCK):
        self.path = path

    # ------------------------------------------------------------ синхронно
    def ask(self, req, timeout=DEFAULT_TIMEOUT):
        """Запрос к демону.

        `transport: True` в ответе значит «до демона не достучались» — только
        тогда имеет смысл прямое подключение к телевизору. Ответ демона с
        `ok: False` без этого признака — отказ телевизора, повторять нельзя.
        """
        s = None
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect(self.path)
            s.sendall((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
            return json.loads(data.decode("utf-8", "replace") or "{}")
        except (OSError, ValueError) as exc:
            return {"ok": False, "transport": True,
                    "msg": "демон не ответил (%s)" % type(exc).__name__}
        finally:
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass

    def state(self):
        return (self.ask({"cmd": "state"}).get("state") or {})

    def power(self):
        return self.state().get("power") or ""

    # ------------------------------------------------------------ асинхронно
    async def aask(self, req, timeout=DEFAULT_TIMEOUT):
        """Асинхронный запрос: один срок на всё — соединение, отправку и ответ."""
        deadline = time.monotonic() + timeout
        writer = None
        try:
            left = max(0.1, deadline - time.monotonic())
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(self.path), timeout=left)
            writer.write((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
            await asyncio.wait_for(writer.drain(), timeout=max(0.1, deadline - time.monotonic()))
            line = await asyncio.wait_for(reader.readline(),
                                          timeout=max(0.1, deadline - time.monotonic()))
            return json.loads(line.decode("utf-8", "replace") or "{}")
        except (OSError, ValueError, asyncio.TimeoutError) as exc:
            return {"ok": False, "transport": True,
                    "msg": "демон не ответил (%s)" % type(exc).__name__}
        finally:
            if writer is not None:
                try:
                    writer.close()
                except Exception:  # noqa: BLE001
                    pass

    async def key(self, name):
        return await self.aask({"cmd": "key", "name": str(name).upper()})

    async def move(self, dx, dy):
        return await self.aask({"cmd": "move", "dx": int(dx), "dy": int(dy)}, timeout=3)

    async def click(self):
        return await self.aask({"cmd": "click"}, timeout=3)

    async def scroll(self, dx, dy):
        return await self.aask({"cmd": "scroll", "dy": int(dy)}, timeout=3)

    async def vol(self, direction):
        return await self.aask({"cmd": "vol", "dir": direction})

    async def speaker(self, name):
        return await self.aask({"cmd": "speaker", "id": name})
