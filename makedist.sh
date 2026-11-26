#!/bin/bash
# makedist.sh — собрать дистрибутив из живой системы.
#
#   sudo /opt/stb/makedist.sh                     обновить дерево (system/, home/)
#   sudo /opt/stb/makedist.sh /tmp/stb.tar.gz     обновить и упаковать
#   sudo /opt/stb/makedist.sh --to-misc           упаковать и положить на misc
#
# Ключи:
#   --no-tests    не прогонять тесты перед сборкой (по умолчанию прогоняются)
#   --with-key    включить в архив ключ доступа к телевизору (.aiopylgtv.sqlite);
#                 по умолчанию он остаётся в системе, но в архив не попадает
#
# Скрипты, конфиги, страницы и документация лежат в /opt/stb постоянно:
# они и есть рабочая версия. Отсюда обновляются только копии того, что живёт
# вне каталога: system/ (системные файлы) и home/ (файлы пользователя).
set -eu

ROOT=/opt/stb
USER_NAME="${STB_USER:-stbuser}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
MISC_HOST="${STB_MISC:-hermes@misc.chech}"
MISC_DIR="${STB_MISC_DIR:-/home/hermes}"
WITH_KEY=0
RUN_TESTS=1
TARGET=""

say() { printf '  %s\n' "$*"; }

for arg in "$@"; do
    case "$arg" in
        --with-key) WITH_KEY=1 ;;
        --no-tests) RUN_TESTS=0 ;;
        --to-misc)  TARGET="misc" ;;
        -h|--help)  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)          TARGET="$arg" ;;
    esac
done

[ "$(id -u)" = 0 ] || { echo "нужен root" >&2; exit 1; }
[ -d "$USER_HOME" ] || { echo "нет домашнего каталога $USER_HOME" >&2; exit 1; }

say "1. системные файлы (system/)"
"$ROOT/system/collect.sh"

say "2. файлы пользователя (home/)"
rm -rf "${ROOT:?}/home"
mkdir -p "$ROOT/home/.config/openbox" "$ROOT/home/.config/dunst" \
         "$ROOT/home/.config/systemd/user"
for f in .xbindkeysrc .Xresources .xprofile; do
    [ -e "$USER_HOME/$f" ] && cp -a "$USER_HOME/$f" "$ROOT/home/"
done
for f in .config/openbox/rc.xml .config/user-dirs.dirs .config/dunst/dunstrc; do
    [ -e "$USER_HOME/$f" ] && cp -a "$USER_HOME/$f" "$ROOT/home/$f"
done
# службы пользователя: браузер, веб-сервер сетки, сторож заставки
for f in "$USER_HOME"/.config/systemd/user/stb-*.service; do
    [ -e "$f" ] && cp -a "$f" "$ROOT/home/.config/systemd/user/"
done
# профиль браузера: настройки и главный экран без верхних строк
mkdir -p "$ROOT/home/.mozilla/stb"
for f in user.js content-prefs.sqlite; do
    [ -e "$USER_HOME/.mozilla/stb/$f" ] && cp -a "$USER_HOME/.mozilla/stb/$f" "$ROOT/home/.mozilla/stb/"
done
if [ -d "$USER_HOME/.mozilla/stb/chrome" ]; then
    cp -a "$USER_HOME/.mozilla/stb/chrome" "$ROOT/home/.mozilla/stb/"
fi

# ключ доступа к телевизору: нужен, чтобы после переустановки не подтверждать заново.
# Это секрет — по умолчанию он в архив не попадает.
if [ "$WITH_KEY" = 1 ] && [ -e "$USER_HOME/.aiopylgtv.sqlite" ]; then
    cp -a "$USER_HOME/.aiopylgtv.sqlite" "$ROOT/home/"
    say "   ключ телевизора добавлен в home/ (--with-key)"
else
    rm -f "$ROOT/home/.aiopylgtv.sqlite"
    say "   ключ телевизора в архив не включён (нужен --with-key)"
fi
say "   файлов: $(find "$ROOT/home" -type f | wc -l)"

say "3. манифест телевизора"
mkdir -p "$ROOT/tvctl"
if [ -e "$USER_HOME/tvctl/nuc_manifest.json" ]; then
    cp -a "$USER_HOME/tvctl/nuc_manifest.json" "$ROOT/tvctl/"
    say "   nuc_manifest.json скопирован"
fi

say "4. чистка мусора"
find "$ROOT" \( -name '__pycache__' -o -name '.pytest_cache' \) -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$ROOT" \( -name '*.bak-*' -o -name '*.bak' -o -name '*.py-' -o -name '*.swp' \) -delete 2>/dev/null || true

say "5. проверки"
if [ "$RUN_TESTS" = 1 ]; then
    if PYTHONDONTWRITEBYTECODE=1 sh "$ROOT/tests/run_tests.sh" >/tmp/makedist-tests.log 2>&1; then
        say "   тесты: $(grep -E 'passed' /tmp/makedist-tests.log | tail -1 | tr -d '\n')"
    else
        echo "   тесты не прошли — архив не собираю (см. /tmp/makedist-tests.log)" >&2
        exit 1
    fi
else
    say "   тесты пропущены (--no-tests)"
fi
if bash "$ROOT/install.sh" --check >/tmp/makedist-check.log 2>&1; then
    say "   проверка архива: без замечаний"
else
    echo "   проверка архива не прошла (см. /tmp/makedist-check.log)" >&2
    exit 1
fi

# тесты и проверки могут снова создать кэш — убираем перед упаковкой
find "$ROOT" \( -name '__pycache__' -o -name '.pytest_cache' \) -type d -prune -exec rm -rf {} + 2>/dev/null || true

say "6. итог"
printf '   %-10s %s\n' "bin:"    "$(ls "$ROOT/bin" | wc -l) файлов: $(ls "$ROOT/bin" | tr '\n' ' ')"
printf '   %-10s %s\n' "web:"    "$(ls "$ROOT/web" | wc -l) файлов"
printf '   %-10s %s\n' "docs:"   "$(ls "$ROOT/docs" | wc -l) файлов"
printf '   %-10s %s\n' "tests:"  "$(ls "$ROOT/tests" | wc -l) файлов"
printf '   %-10s %s\n' "system:" "$(find "$ROOT/system" -type f | wc -l) файлов"
printf '   %-10s %s\n' "home:"   "$(find "$ROOT/home" -type f | wc -l) файлов"
printf '   %-10s %s\n' "размер:" "$(du -sh --exclude=.git "$ROOT" | cut -f1)"

[ -n "$TARGET" ] || exit 0

say "7. архив"
STAMP="$(date +%Y%m%d-%H%M)"
if [ "$TARGET" = "misc" ]; then
    NAME="stb-$STAMP.tar.gz"
    OUT="/tmp/$NAME"
else
    OUT="$TARGET"
    NAME="$(basename "$OUT")"
fi
tar czf "$OUT" --exclude="*/__pycache__" --exclude="*/.pytest_cache" --exclude="*/.git" -C /opt stb
chmod 644 "$OUT"
say "   $NAME  $(du -h "$OUT" | cut -f1)  sha256 $(sha256sum "$OUT" | cut -c1-16)…"

if [ "$TARGET" = "misc" ]; then
    # ключ ssh обычно у того, кто запустил sudo, а не у root
    SSH_USER="${SUDO_USER:-root}"
    chmod 644 "$OUT"
    if [ "$SSH_USER" = "root" ]; then
        scp -q "$OUT" "$MISC_HOST:$MISC_DIR/$NAME" 2>/dev/null
    else
        sudo -u "$SSH_USER" -H scp -q "$OUT" "$MISC_HOST:$MISC_DIR/$NAME" 2>/dev/null
    fi
    if [ $? -eq 0 ]; then
        say "   положен на misc: $MISC_DIR/$NAME"
    else
        say "   на misc не отправилось (нет ключа ssh у $SSH_USER)"
        say "   архив готов: $OUT — заберите вручную или задайте STB_MISC"
    fi
fi
