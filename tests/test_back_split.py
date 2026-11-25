"""Back разделён: распознавание двойного — в одном месте, смысл — в обработчиках."""
import io
import os

ROOT = os.environ.get("STB_ROOT", "/opt/stb")


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding="utf-8").read()


def func(name):
    """Текст функции из bin/stb по имени (до следующего определения)."""
    s = read("bin/stb")
    start = s.index("def %s(" % name)
    end = s.find("\ndef ", start + 5)
    return s[start:] if end == -1 else s[start:end]


def test_two_handlers_exist():
    s = read("bin/stb")
    assert "def key_back():" in s
    assert "def key_back_double():" in s


def test_single_back_keeps_its_specifics():
    """Одиночный Back: приложение, браузер с историей, сетка, прочее окно."""
    text = func("key_back")
    assert "alt+Left" in text, "приложение и браузер получают свой шаг назад"
    assert "is_app(title)" in text
    assert "is_browser(title)" in text
    assert "ctrl+w" in text, "пустая история в браузере закрывает вкладку"
    assert "cmd_hide" in text, "прочее окно прячется"


def test_single_back_no_longer_recognises_double():
    """Своего распознавания у диспетчера больше нет."""
    text = func("key_back")
    assert "back-gate" not in text
    assert "DOUBLE_BACK" not in text


def test_double_back_keeps_its_specifics():
    """Двойной Back: приставка в ТВ, сетка из браузера, спрятать приложение."""
    text = func("key_back_double")
    assert 'cmd_key(["tobox"])' in text
    assert "cmd_grid" in text
    assert "cmd_hide" in text


def test_dispatcher_knows_double_action():
    s = read("bin/stb")
    assert 'if act == "back-double":' in s
    assert (s.index('if act == "back-double":')
            < s.index("if act not in KEY_ACTIONS:")), "двойное до проверки имён"


def test_receiver_uses_one_layer():
    s = read("bin/stb-wifi-remote")
    assert "import stbgesture" in s
    assert "BackGate" not in s, "свой распознаватель должен уйти"
    assert "if name in GESTURES:" in s


def test_other_keys_are_not_delayed():
    """Придержка — только внутри ветки GESTURES; остальные кнопки идут сразу."""
    s = read("bin/stb-wifi-remote")
    gate = s.index("if name in GESTURES:")
    hold = [i for i in range(len(s)) if s.startswith("_hold_single(name, gest)", i)]
    assert len(hold) == 2, "определение и ровно один вызов"
    assert hold[1] > gate, "придержка — внутри ветки GESTURES"
    assert s.index("await do_action(name)") > gate, "общий путь ниже и без ожидания"