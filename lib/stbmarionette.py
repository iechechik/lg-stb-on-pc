#!/usr/bin/env python3
"""stbmarionette — управление Firefox по встроенному каналу Marionette.

Зачем: снаружи браузер рассказывает только заголовок окна. Из-за этого нельзя
ни понять, какие вкладки открыты, ни найти поле логина — приходится угадывать
Tab'ами, и в формах логин с паролем попадают не туда. Marionette позволяет
спросить сам браузер: список вкладок, адреса, поля формы.

Протокол простой: TCP на 127.0.0.1:2828, кадр — "<длина>:<json>".
Включается в профиле: marionette.enabled=true, marionette.port=2828.
"""
import json
import socket
import time


class MarionetteError(RuntimeError):
    pass


class Marionette:
    """Короткое соединение на команду: держать открытым незачем."""

    def __init__(self, port=2828, host="127.0.0.1", timeout=10):
        self.port = port
        self.host = host
        self.timeout = timeout
        self.sock = None
        self.buf = b""
        self.next_id = 1

    # ---------------------------------------------------------------- транспорт
    def connect(self):
        # Сервер обрывает соединение, если предыдущая сессия ещё не закрыта,
        # поэтому пробуем несколько раз с короткой паузой.
        last = None
        for _ in range(4):
            try:
                self.sock = socket.create_connection((self.host, self.port),
                                                    timeout=self.timeout)
                self.sock.settimeout(self.timeout)
                self.buf = b""
                self._read()                      # приветствие сервера
                self.cmd("WebDriver:NewSession", {"capabilities": {}})
                return self
            except (OSError, MarionetteError) as err:
                last = err
                self.close()
                time.sleep(0.4)
        raise MarionetteError("не удалось подключиться: %s" % last)

    def close(self):
        if self.sock:
            try:
                # Сессию закрываем сами: иначе следующее подключение сервер рвёт.
                self._write([0, self.next_id, "WebDriver:DeleteSession", {}])
                self.next_id += 1
            except (OSError, MarionetteError, ValueError):
                pass
            try:
                self.sock.close()
            finally:
                self.sock = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        self.close()

    def _read(self):
        while b":" not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise MarionetteError("соединение закрыто")
            self.buf += chunk
        length, rest = self.buf.split(b":", 1)
        need = int(length)
        while len(rest) < need:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise MarionetteError("соединение закрыто на кадре")
            rest += chunk
        self.buf = rest[need:]
        return json.loads(rest[:need].decode("utf-8"))

    def _write(self, obj):
        data = json.dumps(obj).encode("utf-8")
        self.sock.sendall(str(len(data)).encode("ascii") + b":" + data)

    def cmd(self, name, params=None):
        mid = self.next_id
        self.next_id += 1
        self._write([0, mid, name, params or {}])
        while True:
            msg = self._read()
            if not isinstance(msg, list) or len(msg) < 4:
                continue
            if msg[0] == 1 and msg[1] == mid:      # ответ на нашу команду
                if msg[2]:
                    raise MarionetteError(str(msg[2].get("message") or msg[2])[:300])
                return msg[3]

    # ------------------------------------------------------------------ контекст
    def chrome(self):
        self.cmd("Marionette:SetContext", {"value": "chrome"})

    def content(self):
        self.cmd("Marionette:SetContext", {"value": "content"})

    def js(self, script):
        """Выполнить скрипт в текущем контексте и вернуть результат."""
        answer = self.cmd("WebDriver:ExecuteScript",
                          {"script": "return (%s);" % script, "args": [], "newSandbox": False})
        # значения приходят как {"value": ...} в разных версиях
        if isinstance(answer, dict) and "value" in answer:
            return answer["value"]
        return answer

    # -------------------------------------------------------------------- вкладки
    def tabs(self):
        """Список вкладок: адрес, заголовок, выбрана ли."""
        self.chrome()
        script = ("Array.from(gBrowser.tabs).map(t => ({"
                  "url: (t.linkedBrowser && t.linkedBrowser.currentURI ? "
                  "t.linkedBrowser.currentURI.spec : ''),"
                  "title: t.label || '',"
                  "selected: t.selected}))")
        return self.js(script) or []

    # -------------------------------------------------------------------- логин
    def fill_login(self, user, password):
        """Заполнить поля логина и пароля в открытой странице и отправить форму.

        Ищем не по порядку Tab, а по самим полям: сначала password, рядом с ним
        (перед ним) — логин. Значения ставим «по-настоящему», через сеттер,
        иначе React и подобные не замечают ввода.
        """
        self.content()
        script = ("(() => {"
                  "const pw = document.querySelector('input[type=password]');"
                  "if (!pw) return 'нет поля пароля';"
                  "const form = pw.form || document;"
                  "const inputs = Array.from(form.querySelectorAll('input'));"
                  "let userField = inputs.find(i => i.type === 'email') ||"
                  "  inputs.filter(i => i.type !== 'password' && i.type !== 'checkbox' &&"
                  "    i.type !== 'submit' && i.type !== 'hidden' && i.type !== 'button')"
                  "    .filter(i => inputs.indexOf(i) < inputs.indexOf(pw))[0];"
                  "const set = (el, v) => {"
                  "  const d = Object.getOwnPropertyDescriptor(el.constructor.prototype, 'value');"
                  "  d.set.call(el, v);"
                  "  el.dispatchEvent(new Event('input', {bubbles: true}));"
                  "  el.dispatchEvent(new Event('change', {bubbles: true}));"
                  "};"
                  "if (userField) set(userField, %s);"
                  "set(pw, %s);"
                  "const btn = form.querySelector('button[type=submit],input[type=submit],button');"
                  "if (btn) { btn.click(); return 'отправлено кнопкой'; }"
                  "if (form.requestSubmit) { form.requestSubmit(); return 'отправлено формой'; }"
                  "return 'нет кнопки отправки';})()" % (json.dumps(user), json.dumps(password)))
        return self.js(script)


def available(port=2828, host="127.0.0.1", timeout=3):
    """Отвечает ли Marionette (включён ли он в профиле)."""
    try:
        with Marionette(port=port, host=host, timeout=timeout):
            return True
    except (OSError, MarionetteError):
        return False
