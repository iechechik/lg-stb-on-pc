#!/bin/sh
# run_tests.sh — тесты и проверки качества кода приставки.
#
#   sudo /opt/stb/tests/run_tests.sh
#
# Тесты не трогают телевизор и X: проверяются разборы, кадры, буфер текста,
# логика Back, согласованность конфига и карт кнопок, отсутствие хардкода.
set -u
cd /opt/stb || exit 1
rc=0

python_files=""
shell_files=""
for f in bin/* lib/*.py web/*.py; do
    [ -f "$f" ] || continue
    case "$(head -1 "$f")" in
        *python*) python_files="$python_files $f" ;;
    esac
done
for f in bin/* lib/*.sh makedist.sh install.sh system/collect.sh; do
    [ -f "$f" ] || continue
    case "$(head -1 "$f")" in
        *sh*) shell_files="$shell_files $f" ;;
    esac
done

echo "== pytest -p no:cacheprovider =="
python3 -m pytest -p no:cacheprovider -q tests || rc=1

echo
echo "== pyflakes: неопределённое и неиспользуемое =="
if python3 -c "import pyflakes" 2>/dev/null; then
    python3 -m pyflakes $python_files 2>&1 | head -30
    echo "  замечаний: $(python3 -m pyflakes $python_files 2>&1 | grep -c ":" || true)"
else
    echo "  pyflakes не установлен — пропущено (apt install python3-pyflakes)"
fi

echo
echo "== shellcheck (warning и выше) =="
if command -v shellcheck >/dev/null 2>&1; then
    shellcheck -S warning $shell_files 2>&1 | head -40
    echo "  замечаний: $(shellcheck -S warning $shell_files 2>&1 | grep -c "^In \|SC[0-9]" || true)"
else
    echo "  shellcheck не установлен — пропущено (apt install shellcheck)"
fi

exit $rc
