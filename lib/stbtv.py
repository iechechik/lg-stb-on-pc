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

        Ответ с `ok: False` и без признака `transport` — отказ телевизора,
        повторять нельзя. `transport: True` значит «до демона не достучались»,
        и вместе с ним идёт `sent`:

          * `sent: False` — соединения не было, запрос точно не ушёл;
          * `sent: True` — запрос мог дойти до телевизора, судьба неизвестна
            (тогда же стоит `unknown: True`), повторять нельзя.

        Разница принципиальная: громкость и Back не идемпотентны, и повтор
        после неизвестного исхода даёт двойное срабатывание.
        """
        deadline = time.monotonic() + timeout
        s = None
        sent = False
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(max(0.05, deadline - time.monotonic()))
            s.connect(self.path)
            s.sendall((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
            sent = True
            data = b""
            while not data.endswith(b"\n"):
                rest = deadline - time.monotonic()
                if rest <= 0:
                    raise socket.timeout("срок ответа вышел")
                s.settimeout(rest)
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
            if not data.strip():
                raise ConnectionError("демон закрыл соединение без ответа")
            return json.loads(data.decode("utf-8", "replace"))
        except (OSError, ValueError) as exc:
            answer = {"ok": False, "transport": True, "sent": sent,
                      "msg": "демон не ответил (%s)" % type(exc).__name__}
            if sent:
                answer["unknown"] = True
            return answer
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
        """Асинхронный запрос: один срок на всё — соединение, отправку и ответ.

        Признак `sent` считается так же, как в `ask()`: после записи в сокет
        исход уже неизвестен, и повторять команду нельзя.
        """
        deadline = time.monotonic() + timeout
        writer = None
        sent = False

        def left():
            return deadline - time.monotonic()

        async def bounded(coro):
            rest = left()
            if rest <= 0:
                raise asyncio.TimeoutError("срок ответа вышел")
            return await asyncio.wait_for(coro, timeout=rest)

        try:
            reader, writer = await bounded(asyncio.open_unix_connection(self.path))
            writer.write((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
            sent = True
            await bounded(writer.drain())
            line = await bounded(reader.readline())
            if not line.strip():
                raise ConnectionError("демон закрыл соединение без ответа")
            return json.loads(line.decode("utf-8", "replace"))
        except (OSError, ValueError, asyncio.TimeoutError) as exc:
            answer = {"ok": False, "transport": True, "sent": sent,
                      "msg": "демон не ответил (%s)" % type(exc).__name__}
            if sent:
                answer["unknown"] = True
            return answer
        finally:
            if writer is not None:
                try:
                    writer.close()
                    await asyncio.wait_for(writer.wait_closed(), timeout=0.5)
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
