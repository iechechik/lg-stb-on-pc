"""stbtabs — вкладки браузера через Marionette: учёт активности, уборка, автовход.

Снаружи браузер отдаёт только заголовок окна, поэтому «закрыть ненужные
вкладки» и «войти в службу» приходилось делать вслепую. Теперь есть Marionette:
можно спросить список вкладок с адресами и работать с формой входа по её полям.
"""
import json
import os
import time
import urllib.parse

import stbcommon
import stbconf
import stbmarionette

GRID = "127.0.0.1:8090"
ACTIVITY = "/run/stb/tab-activity.json"


def connect(timeout=6):
    return stbmarionette.Marionette(port=int(stbconf.get("MARIONETTE_PORT", "2828")),
                                    timeout=timeout)


def tiles():
    try:
        with open(os.path.join(stbconf.get("STB_CONFIG_DIR", "/opt/stb/config"),
                               "tiles.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def tile_for_url(url):
    """id плитки по адресу страницы: сверяем хост и порт с target из tiles.json."""
    try:
        here = urllib.parse.urlsplit(url or "")
    except ValueError:
        return ""
    if not here.hostname:
        return ""
    for tile in tiles():
        if tile.get("type") != "url" or not tile.get("target"):
            continue
        there = urllib.parse.urlsplit(str(tile["target"]))
        if there.hostname == here.hostname and (there.port or 80) == (here.port or 80):
            return str(tile.get("id") or "")
    return ""


def _load():
    try:
        with open(ACTIVITY, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(state):
    try:
        os.makedirs(os.path.dirname(ACTIVITY), exist_ok=True)
        with open(ACTIVITY, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError:
        pass


def activate_grid(conn=None):
    """Сделать активной вкладку сетки, ничего не переписывая.

    Раньше «уйти на сетку» означало загрузить адрес сетки в текущей вкладке — и
    вкладка службы превращалась в ещё одну сетку. Теперь просто выбираем вкладку
    сетки, а если её нет — открываем.
    """
    script = ("(() => {"
              "const want = %s;"
              "let found = null, count = 0;"
              "Array.from(gBrowser.tabs).forEach(t => {"
              "  const u = (t.linkedBrowser && t.linkedBrowser.currentURI) ? "
              "t.linkedBrowser.currentURI.spec : '';"
              "  if (u.indexOf(want) === 0 || u.includes(want)) { count++; if (!found) found = t; }});"
              "if (count > 1) {"
              "  let first = true;"
              "  Array.from(gBrowser.tabs).forEach(t => {"
              "    const u = (t.linkedBrowser && t.linkedBrowser.currentURI) ? "
              "t.linkedBrowser.currentURI.spec : '';"
              "    if (u.includes(want)) { if (first) { first = false; } else "
              "{ gBrowser.removeTab(t, {animate: false}); } }});"
              "  found = null;"
              "  Array.from(gBrowser.tabs).forEach(t => {"
              "    const u = (t.linkedBrowser && t.linkedBrowser.currentURI) ? "
              "t.linkedBrowser.currentURI.spec : '';"
              "    if (u.includes(want)) { found = t; }});"
              "}"
              "if (!found) {"
              "  const tab = gBrowser.addTab(want, {triggeringPrincipal: "
              "Services.scriptSecurityManager.getSystemPrincipal()});"
              "  found = tab;"
              "}"
              "gBrowser.selectedTab = found;"
              "return 1;})()" % json.dumps("http://" + GRID + "/"))
    if conn is None:
        with connect() as fresh:
            fresh.chrome()
            return fresh.js(script)
    conn.chrome()
    return conn.js(script)


def reset_cursor():
    """Курсор на первую плитку: после перезапуска интерфейса страница новая."""
    for _ in range(12):
        try:
            conn = connect()
            conn.connect()
            try:
                if conn.js("typeof window.stbResetCursor") == "function":
                    return bool(conn.js("window.stbResetCursor()"))
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.5)
    return False


def needs_refit(inner, screen):
    """Страница считает себя выше экрана — окно надо перевести в fullscreen заново.

    После смены разрешения (2160→1080) Firefox иногда сохраняет старую высоту
    области просмотра: страница рисуется выше экрана, шапка сетки уезжает за
    верхний край. Подталкивание размера окна не помогает, помогает только
    снятие и повторная установка fullscreen.
    """
    try:
        return int(inner) > int(screen) + 1
    except (TypeError, ValueError):
        return False


def _screen_height():
    """Высота экрана из xrandr (HDMI-1)."""
    out = stbcommon.as_user("xrandr").stdout or ""
    for line in out.splitlines():
        if line.startswith("HDMI-1"):
            for token in line.split():
                if "x" in token and "+" in token:
                    return int(token.split("+")[0].split("x")[1])
    return 0


def _grid_window():
    found = stbcommon.as_user("xdotool", "search", "--name", stbcommon.GRID_TITLE).stdout or ""
    ids = [w for w in found.split() if w.isdigit()]
    return ids[0] if ids else ""


def refit():
    """Вернуть окну сетки правильный размер страницы. True — пришлось чинить."""
    height = _screen_height()
    if not height:
        return False
    try:
        with connect() as conn:
            conn.content()
            inner = conn.js("window.innerHeight")
    except (OSError, stbmarionette.MarionetteError):
        return False
    if not needs_refit(inner, height):
        return False
    wid = _grid_window()
    if not wid:
        return False
    stbcommon.as_user("wmctrl", "-i", "-r", wid, "-b", "remove,fullscreen")
    time.sleep(0.4)
    stbcommon.as_user("wmctrl", "-i", "-r", wid, "-b", "add,fullscreen")
    stbcommon.log_to("system", "окно сетки: переставил fullscreen (%s → %s)" % (inner, height))
    return True


def select_tile(tile_id=None):
    """Поставить подсветку на плитку, с которой человек ушёл.

    Одно соединение на всё: Marionette пускает одного клиента, поэтому адрес
    плитки читаем из самой страницы, а не отдельным last_tile().
    """
    try:
        conn = connect()
        conn.connect()
        try:
            tid = tile_id or conn.js("localStorage.getItem('stb-last-tile')") or ""
            if not tid:
                return False
            script = '(() => { const f = window.stbSelectTile; return f ? f("%s") : false; })()' % tid
            return bool(conn.js(script))
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return False


def last_tile():
    """id плитки, которую открывали последней (её запоминает сама сетка)."""
    try:
        with connect() as conn:
            conn.content()
            return conn.js("localStorage.getItem('stb-last-tile')")
    except (OSError, stbmarionette.MarionetteError):
        return None


def grid_tile_center(tile_id=None):
    """Центр плитки на экране: по id, а если его нет — выбранной."""
    selector = ("a.tile[data-id=%s]" % json.dumps(tile_id)) if tile_id else "a.tile.sel"
    script = ("(() => {const el = document.querySelector(%s);"
              "if (!el) return null; const r = el.getBoundingClientRect();"
              "return [Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2)];})()"
              % json.dumps(selector))
    try:
        with connect() as conn:
            conn.content()
            return conn.js(script)
    except (OSError, stbmarionette.MarionetteError):
        return None


_bars = {}


def note(tabs):
    """Отметить время активности: выбранная вкладка — сейчас, новые — при первом виде."""
    now = time.time()
    state = _load()
    alive = set()
    for tab in tabs:
        url = tab.get("url") or ""
        if not url:
            continue
        alive.add(url)
        if tab.get("selected") or url not in state:
            state[url] = now
    _save({url: stamp for url, stamp in state.items() if url in alive})
    return state


def close_url(url, conn=None):
    """Закрыть вкладку по адресу (сетку закрывать нельзя).

    Можно передать уже открытое соединение: за цикл уборки их не нужно много.
    """
    if not url or GRID in url:
        return 0
    if conn is None:
        with connect() as fresh:
            return close_url(url, fresh)
    conn.chrome()
    script = ("(() => {const want = %s; let n = 0;"
              "Array.from(gBrowser.tabs).forEach(t => {"
              "  const u = (t.linkedBrowser && t.linkedBrowser.currentURI) ? "
              "t.linkedBrowser.currentURI.spec : '';"
              "  if (u === want) { gBrowser.removeTab(t, {animate: false}); n++; }});"
              "return n;})()" % json.dumps(url))
    return conn.js(script) or 0


def reap(minutes):
    """Закрыть вкладки, не активные дольше minutes. Возвращает число закрытых."""
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return 0
    if minutes <= 0:
        return 0
    try:
        with connect() as conn:
            tabs = conn.tabs()
            state = note(tabs)
            now = time.time()
            closed = 0
            for tab in tabs:
                url = tab.get("url") or ""
                if not url or GRID in url or tab.get("selected"):
                    continue
                if now - state.get(url, now) >= minutes * 60:
                    try:
                        done = close_url(url, conn)
                        closed += done
                        if done:
                            stbcommon.log_to("keys", "закрыл вкладку %s (неактивна %d мин)"
                                             % (url[:70], minutes))
                    except (OSError, stbmarionette.MarionetteError):
                        pass          # закрытие оборвало сессию — не беда
            return closed
    except (OSError, stbmarionette.MarionetteError):
        return 0


def fill_login(user, password):
    """Заполнить форму входа в открытой странице через Marionette."""
    with connect() as conn:
        return conn.fill_login(user, password)
