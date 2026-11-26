#!/usr/bin/env python3
import sys
sys.path.insert(0, "/opt/stb/lib")
import stbconf  # noqa: E402
_stbconf = stbconf
STB_HOME = _stbconf.get("STB_HOME", "/home/stbuser")
STB_USER = _stbconf.get("STB_USER", "stbuser")

"""stb-web — домашняя сетка приставки и переходник «кнопка → команда».

Отдаёт на 127.0.0.1:8090:
  /                — страница сетки (index.html)
  /api/buttons     — плитки из tiles.json
  /run/<id>        — выполнить команду кнопки, вернуть {"ok":true,"msg":"..."}

Зависимостей нет — только стандартная библиотека. Логи в journal (stdout).
"""
import json
import os
import shlex
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, "/opt/stb/lib")


BASE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(BASE, "index.html")
BUTTONS = stbconf.get("STB_TILES") or os.path.join(
    stbconf.get("STB_CONFIG_DIR", "/opt/stb/config"), "tiles.json")
HOST, PORT = "127.0.0.1", int(stbconf.get("STB_WEB_PORT", "8090"))
RUN_TIMEOUT = 20


# ---------------------------------------------------------------- страница «Кнопки»
ACTION_DOC = {
    "ok": "выбор плитки под курсором · ENTER в телевизор",
    "up": "вверх по сетке · стрелка в ТВ",
    "down": "вниз по сетке · стрелка в ТВ",
    "left": "влево · стрелка в ТВ",
    "right": "вправо · стрелка в ТВ",
    "back": "назад в браузере · назад в меню ТВ",
    "tobox": "вернуться с телевизора на приставку",
    "home": "на сетку · меню телевизора",
    "menu": "Escape · меню телевизора",
    "volup": "громкость телевизора +",
    "voldown": "громкость телевизора −",
    "mute": "выключить/включить звук ТВ",
    "power": "выключить/включить телевизор",
    "chup": "канал + (только в режиме ТВ)",
    "chdown": "канал − (только в режиме ТВ)",
    "play": "выбор плитки · ENTER в ТВ",
    "playkey": "выбор плитки · PLAY в ТВ",
    "pausekey": "выбор плитки · PAUSE в ТВ",
    "prev": "влево · перемотка назад в ТВ",
    "next": "вправо · перемотка вперёд в ТВ",
    "red": "красная кнопка ТВ",
    "green": "зелёная кнопка ТВ",
    "yellow": "жёлтая кнопка ТВ",
    "blue": "синяя кнопка ТВ",
    "info": "информация о программе (режим ТВ)",
    "guide": "телегид (режим ТВ)",
    "cc": "субтитры (режим ТВ)",
    "exit": "выход (режим ТВ)",
}


def preprocess_json(text):
    """Убирает комментарии // и /* */ и висячие запятые, не трогая строки.

    Нужно, чтобы в tiles.json / картах можно было писать пояснения, а также
    чтобы обычный "http://..." внутри строки не считался комментарием.
    """
    out = []
    i = 0
    n = len(text)
    in_string = False
    escape = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1

    clean = "".join(out)
    # висячие запятые: {"a":1,} / [1,2,]
    import re
    return re.sub(r",(\s*[}\]])", r"\1", clean)


def load_json_file(path):
    """json с комментариями и висячими запятыми."""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    return json.loads(preprocess_json(raw))


def load_map(name):
    """Читает карту КЛЮЧ=ДЕЙСТВИЕ из каталога конфигов."""
    path = os.path.join(stbconf.get("STB_CONFIG_DIR", "/opt/stb/config"), name)
    pairs = []
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, action = line.split("=", 1)
                pairs.append((key.strip(), action.strip()))
    except OSError:
        pass
    return pairs


def render_buttons():
    """Страница-памятка: обе карты кнопок и текущий режим."""
    try:
        with open("/run/stb/mode", encoding="utf-8") as f:
            mode = f.read().strip() or "nuc"
    except OSError:
        mode = "nuc"
    mode_text = "телевизор" if mode == "tv" else "приставка"

    def rows(pairs):
        out = []
        for key, action in pairs:
            out.append("<tr><td class=k>%s</td><td>%s</td></tr>"
                       % (key, ACTION_DOC.get(action, action)))
        return "".join(out)

    wifi = load_map("buttons-wifi.conf")
    bt = load_map("buttons-bt.conf")
    return """<!doctype html><html lang=ru><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Кнопки</title>
<style>
 body{background:#0d1117;color:#e6edf3;font-family:system-ui,sans-serif;margin:0;padding:28px 40px}
 h1{font-size:44px;margin:0 0 6px}
 .mode{font-size:26px;color:#8ad6a0;margin-bottom:24px}
 h2{font-size:32px;margin:28px 0 10px;color:#9fb3d1}
 table{border-collapse:collapse;width:100%%;font-size:26px}
 td{padding:8px 14px;border-bottom:1px solid #21262d;vertical-align:top}
 td.k{color:#ffd479;white-space:nowrap;font-weight:600;width:38%%}
 .hint{font-size:22px;color:#8b949e;margin-top:26px}
</style>
<h1>Кнопки</h1>
<div class=mode>сейчас пульт управляет: %s</div>
<h2>Пульт Wi-Fi (приложение)</h2>
<table>%s</table>
<h2>Пульт Bluetooth</h2>
<table>%s</table>
<div class=hint>Карты хранятся в /opt/stb/config: buttons-wifi.conf и buttons-bt.conf.
После правки: sudo systemctl restart stb-wifi-remote (Wi-Fi) или stb keys apply bt (BT).</div>
</html>""" % (mode_text, rows(wifi), rows(bt))


def load_buttons():
    return load_json_file(BUTTONS)


BLACK_PAGE = (
    "<!doctype html><html lang=ru><meta charset=utf-8><title>Заставка</title>"
    "<style>html,body{margin:0;height:100vh;background:#000;overflow:hidden;"
    "cursor:none}</style><body></body></html>"
)


class Handler(BaseHTTPRequestHandler):
    server_version = "stb-web/1.0"

    def log_message(self, fmt, *args):  # pylint: disable=arguments-differ  # pylint: disable=arguments-differ
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))
        sys.stdout.flush()

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self):
        # Страница и плитки меняются на ходу: без этого браузер держит старую
        # версию и правки «не доезжают» до экрана.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        path = unquote(urlparse(self.path).path or "/")
        if path in ("/search", "/search.html"):
            try:
                with open(os.path.join(BASE, "search.html"), encoding="utf-8") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError as e:
                self._json(500, {"ok": False, "msg": str(e)})
        elif path in ("/black", "/black.html"):
            self._send(200, BLACK_PAGE, "text/html; charset=utf-8")
        elif path in ("/buttons", "/buttons.html"):
            self._send(200, render_buttons(), "text/html; charset=utf-8")
        elif path in ("/", "/index.html"):
            try:
                with open(INDEX, encoding="utf-8") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError as e:
                self._json(500, {"ok": False, "msg": str(e)})
        elif path in ("/lang/status", "/lang/ru", "/lang/en", "/lang/toggle"):
            code = path.rsplit("/", 1)[-1]
            if code == "toggle":
                try:
                    with open("/run/stb/lang", encoding="utf-8") as f:
                        cur = f.read().strip()
                except OSError:
                    cur = "us"
                code = "en" if cur == "ru" else "ru"
            if code == "status":
                try:
                    with open("/run/stb/lang", encoding="utf-8") as f:
                        cur = f.read().strip() or "us"
                except OSError:
                    cur = "us"
                self._json(200, {"ok": True, "layout": cur})
            else:
                lay = "ru" if code == "ru" else "us"
                rc = subprocess.run(["/opt/stb/bin/stb", "lang", code], capture_output=True, timeout=15)
                self._json(200 if rc.returncode == 0 else 500,
                           {"ok": rc.returncode == 0, "layout": lay,
                            "msg": (rc.stdout or rc.stderr).decode("utf-8", "replace")[-120:]})
        elif path in ("/tvtype", "/tvtype.html"):
            try:
                with open(os.path.join(BASE, "tvtype.html"), encoding="utf-8") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError as e:
                self._json(500, {"ok": False, "msg": str(e)})
        elif path == "/tv/text":
            q = parse_qs(urlparse(self.path).query)
            text = (q.get("t") or [""])[0]
            enter = (q.get("enter") or ["0"])[0] in ("1", "true", "yes")
            cmd = ["/opt/stb/bin/stb", "tv", "text"]
            if text:
                cmd.append("--")     # дальше — сам текст, даже если он с дефиса
                cmd.append(text)
            if enter:
                cmd.append("--enter")
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=25,
                                   env={**os.environ, "HOME": STB_HOME})
                out = (r.stdout or b"").decode("utf-8", "replace").strip()
                try:
                    obj = json.loads(out.splitlines()[-1]) if out else {"ok": False, "msg": "нет ответа"}
                except ValueError:
                    obj = {"ok": r.returncode == 0, "msg": out[-200:] or "нет ответа"}
                self._json(200 if obj.get("ok") else 500, obj)
            except subprocess.TimeoutExpired:
                self._json(504, {"ok": False, "msg": "телевизор не ответил"})
        elif path == "/api/lastkey":
            try:
                with open("/run/stb/lastkey", encoding="utf-8") as f:
                    line = f.read().strip()
                ts = os.path.getmtime("/run/stb/lastkey")
                self._json(200, {"ok": True, "line": line, "ts": ts})
            except OSError:
                self._json(200, {"ok": True, "line": "", "ts": 0})
        elif path == "/api/buttons":
            try:
                self._json(200, [b for b in load_buttons() if b.get("type") != "command"
                                 or b.get("show", True)])
            except Exception as e:  # noqa: BLE001
                self._json(500, {"ok": False, "msg": str(e)})
        elif path == "/pointer/warp":
            # Стрелки двигают выбор; курсор ставим на ту же плитку, иначе
            # подсветка и настоящий курсор живут отдельно и «прыгают».
            query = parse_qs(urlparse(self.path).query)
            try:
                x = int(float(query.get("x", [""])[0]))
                y = int(float(query.get("y", [""])[0]))
            except (TypeError, ValueError):
                self._json(400, {"ok": False, "msg": "нужны x и y"})
            else:
                r = subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)],
                                   capture_output=True, timeout=5, text=True)
                if r.returncode:
                    self._json(500, {"ok": False, "msg": (r.stderr or "").strip()[:200]})
                else:
                    self._json(200, {"ok": True})
        elif path == "/sound/on":
            # Плитки-сайты открываются ссылкой: страница просит включить звук,
            # прежде чем уйти на YouTube и подобное. Сетка звук глушит.
            subprocess.run(["/opt/stb/bin/stb", "sound", "on"],
                           capture_output=True, timeout=10)
            self._json({"ok": True})
        elif path.startswith("/run/"):
            self._run(path[len("/run/"):].strip("/"))
        elif path.startswith("/icons/"):
            self._static(path.lstrip("/"))
        else:
            self._json(404, {"ok": False, "msg": "not found"})

    def _static(self, rel):
        icons = os.path.realpath(os.path.join(BASE, "icons"))
        full = os.path.realpath(os.path.join(BASE, rel))
        try:
            inside = os.path.commonpath([icons, full]) == icons
        except ValueError:
            inside = False
        if not inside:
            return self._json(403, {"ok": False, "msg": "forbidden"})
        ext = os.path.splitext(full)[1].lower()
        ctype = {".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon",
                 ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".webp": "image/webp"}.get(ext, "application/octet-stream")
        try:
            with open(full, "rb") as f:
                self._send(200, f.read(), ctype)
        except (OSError, ValueError):
            self._json(404, {"ok": False, "msg": "нет файла " + rel})

    def _run(self, btn_id):
        try:
            buttons = load_buttons()
        except Exception as e:  # noqa: BLE001
            return self._json(500, {"ok": False, "msg": "tiles.json: %s" % e})
        btn = next((b for b in buttons if b.get("id") == btn_id), None)
        if btn is None:
            return self._json(404, {"ok": False, "msg": "нет кнопки %s" % btn_id})
        target = btn.get("target", "")
        if btn.get("type") != "command" or not target:
            return self._json(400, {"ok": False, "msg": "кнопка не команда"})
        try:
            proc = subprocess.run(shlex.split(target), capture_output=True, text=True,
                                  timeout=RUN_TIMEOUT)
        except FileNotFoundError:
            return self._json(500, {"ok": False, "msg": "команда не найдена: %s" % target})
        except subprocess.TimeoutExpired:
            return self._json(504, {"ok": False, "msg": "команда не ответила за %ds" % RUN_TIMEOUT})
        out = (proc.stdout or proc.stderr or "").strip().splitlines()
        msg = out[-1] if out else ("код " + str(proc.returncode))
        self._json(200 if proc.returncode == 0 else 500,
                   {"ok": proc.returncode == 0, "msg": msg})


def main():
    os.chdir(BASE)
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print("stb-web: http://%s:%d (кнопок: %d)" % (HOST, PORT, len(load_buttons())), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
