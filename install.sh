#!/bin/bash
# =============================================================================
#  Приставка STB — установка на чистую Debian 13 (trixie)
#
#  Запуск от root:   sudo bash install.sh
#
#  Параметры (необязательные, спросит по ходу):
#     STB_USER=stbuser STB_TV_IP=192.168.1.199 STB_TV_MAC=A8:23:FE:5A:B4:37 \
#     STB_TV_MAC_ALT=00:51:ED:2C:72:60 bash install.sh
#
#  Сеть телевизора: приставка выдаёт ему постоянный адрес через dnsmasq
#  и держит на своём интерфейсе адрес STB_TV_IF_ADDR (по умолчанию — как
#  у приставки: последний октет телевизора, но 198). Шлюз и DNS берутся из
#  системы, если не заданы STB_GW и STB_DNS.
#
#  Проверка архива без установки:  bash install.sh --check
#
#  Установщик обязан доводить чистую систему до рабочего состояния: если
#  какой-то шаг не выполнился — установка падает с ошибкой, а не пишет «✓».
# =============================================================================
set -euo pipefail
trap 'printf "\n\033[1;31mОШИБКА:\033[0m не удалось выполнить команду на строке %s\n" "$LINENO" >&2' ERR

SRC="$(cd "$(dirname "$0")" && pwd)"
DST=/opt/stb

# ---------------------------------------------------------------- проверка архива
if [ "${1:-}" = "--check" ]; then
    echo "== проверка архива (ничего не меняем) =="
    problems=0
    need="bin/stb bin/stb-watch bin/stb-wifi-remote bin/stb-tv-link \
lib/stbcommon.py lib/stbtvcmd.py lib/stbdesktop.py lib/stbactions.py lib/stbtv.py lib/stbgesture.py lib/stbtvlast.py lib/stbx11.py lib/stbconf.py lib/stbconf.sh lib/stbdiff.py lib/stbsvc.py lib/stbtabs.py lib/stbmarionette.py lib/stb4k.py \
lib/stbkeys.py lib/stbpointer.py lib/stbtext.py lib/stbws.py lib/tv_setting.py \
web/index.html web/stb-web.py config/stb.conf config/tiles.json \
README.md tests/run_tests.sh tests/test_docs.py \
system/etc/systemd/system/stb.target \
system/etc/dnsmasq.d/tv-lan.conf.template \
system/etc/network/interfaces.d/tv-lan.template \
home/.config/systemd/user/stb-browser.service \
home/.config/systemd/user/stb-web.service \
home/.config/systemd/user/stb-screensaver.service"
    for f in $need; do
        if [ -e "$SRC/$f" ]; then
            printf "   \033[32m·\033[0m %s\n" "$f"
        else
            printf "   \033[31mНЕТ\033[0m %s\n" "$f"
            problems=$((problems + 1))
        fi
    done
    for u in stb-web stb-browser stb-screensaver; do
        if [ -e "$SRC/home/.config/systemd/user/$u.service" ]; then
            printf "   \033[32m·\033[0m юнит %s\n" "$u"
        else
            printf "   \033[31mНЕТ\033[0m юнит %s\n" "$u"
            problems=$((problems + 1))
        fi
    done
    echo "== проверка пакетов =="
    for p in lightdm openbox xbindkeys firefox-esr xdotool wmctrl scrot \
             x11-xserver-utils xprintidle python3-xlib pipewire bluez \
             python3-evdev ethtool etherwake netcat-openbsd dnsmasq ifupdown \
             procps flatpak; do
        cand=$(apt-cache policy "$p" 2>/dev/null | awk '/Candidate:/ {print $2}')
        if [ -n "$cand" ] && [ "$cand" != "(none)" ]; then
            printf "   \033[32m·\033[0m %-20s %s\n" "$p" "$cand"
        else
            printf "   \033[31mНЕТ\033[0m %-20s\n" "$p"
            problems=$((problems + 1))
        fi
    done
    if [ "$problems" -ne 0 ]; then
        echo "== найдено проблем: $problems =="
        exit 1
    fi
    echo "== архив полный, пакеты доступны =="
    exit 0
fi

STB_USER="${STB_USER:-stbuser}"
STB_HOME="/home/${STB_USER}"
STB_TV_IP="${STB_TV_IP:-}"
STB_TV_MAC="${STB_TV_MAC:-}"
STB_TV_MAC_ALT="${STB_TV_MAC_ALT:-}"
STB_TV_APP="${STB_TV_APP:-org.jellyfin.webos}"
STB_TV_INPUT="${STB_TV_INPUT:-HDMI_3}"
STB_LAN_IF="${STB_LAN_IF:-wlp2s0}"
STB_TV_IF="${STB_TV_IF:-enp0s25}"
STB_TV_IF_ADDR="${STB_TV_IF_ADDR:-}"   # адрес приставки в сети телевизора
STB_GW="${STB_GW:-}"                  # шлюз для телевизора (пусто — из системы)
STB_DNS="${STB_DNS:-}"                # DNS для телевизора (пусто — из системы)

say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '   \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31mОШИБКА:\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- 0. проверки
say "0. Проверка окружения"
[ "$(id -u)" -eq 0 ] || die "запускать от root: sudo bash install.sh"
. /etc/os-release
case "${VERSION_ID:-}" in
    13) ok "Debian 13 (trixie)" ;;
    *)  warn "система ${PRETTY_NAME:-неизвестна}, рассчитано на Debian 13" ;;
esac
[ -d "$SRC/bin" ] || die "рядом с install.sh нет каталога bin/ — распакуйте архив целиком"
[ -d "$SRC/system/etc" ] || die "нет дерева system/ — архив неполный"

if [ -z "$STB_TV_IP" ]; then
    read -rp "IP телевизора в сети: " STB_TV_IP
fi
[ -n "$STB_TV_IP" ] || die "без IP телевизора дальше нельзя"
if [ -z "$STB_TV_MAC" ]; then
    read -rp "MAC телевизора (для включения по сети): " STB_TV_MAC
fi
[ -n "$STB_TV_MAC" ] || die "без MAC телевизор не включить по сети"

# ---------------------------------------------------------------- 0a. пользователь
say "0a. Пользователь приставки: ${STB_USER}"
if id "$STB_USER" >/dev/null 2>&1; then
    ok "уже существует"
else
    useradd -m -s /bin/bash -c "STB user" "$STB_USER"
    passwd -d "$STB_USER" >/dev/null
    ok "создан"
fi
STB_HOME="$(getent passwd "$STB_USER" | cut -d: -f6)"
[ -n "$STB_HOME" ] || die "не удалось определить домашний каталог ${STB_USER}"
for g in video audio input render bluetooth netdev; do
    if getent group "$g" >/dev/null 2>&1; then
        usermod -aG "$g" "$STB_USER"
    fi
done
ok "группы добавлены"

install -d -o "$STB_USER" -g "$STB_USER" "$STB_HOME/.config"
if [ -f "$SRC/home/.config/user-dirs.dirs" ]; then
    install -o "$STB_USER" -g "$STB_USER" -m 644 \
        "$SRC/home/.config/user-dirs.dirs" "$STB_HOME/.config/user-dirs.dirs"
fi
for d in Desktop Documents Downloads Music Pictures Public Templates Videos; do
    if [ -d "$STB_HOME/$d" ]; then
        rmdir "$STB_HOME/$d" 2>/dev/null || true
    fi
done

# ---------------------------------------------------------------- 1. программы
say "1. Программы"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
    lightdm openbox xbindkeys firefox-esr python3-pytest python3-pyflakes shellcheck \
    xdotool wmctrl scrot x11-xserver-utils xprintidle python3-xlib \
    pipewire pipewire-pulse wireplumber \
    bluez bluetooth \
    python3 python3-evdev python3-dbus python3-gi python3-venv python3-pip \
    netcat-openbsd ethtool iw wpasupplicant network-manager etherwake \
    dnsmasq ifupdown procps \
    curl ca-certificates rsync util-linux sudo \
    fonts-dejavu fonts-noto-core adwaita-icon-theme dunst libnotify-bin
ok "пакеты установлены"

# без этих программ приставка не работает — проверяем сразу
for c in etherwake xprintidle xset xrandr xdotool wmctrl nc ethtool; do
    command -v "$c" >/dev/null || die "не установилась программа: $c"
done
ok "обязательные программы на месте"
python3 -c "import Xlib.ext.xtest" \
    || die "нет python3-xlib — указатель не сможет работать без запуска процессов"
ok "указатель через XTest доступен"

say "1a. Плеер Jellyfin Desktop"
apt-get install -y --no-install-recommends flatpak
flatpak remote-add --if-not-exists flathub \
    https://dl.flathub.org/repo/flathub.flatpakrepo \
    || warn "не удалось подключить flathub — плеер поставим позже"
if flatpak install -y flathub org.jellyfin.JellyfinDesktop; then
    ok "Jellyfin Desktop установлен"
else
    warn "плеер не установился — позже: flatpak install flathub org.jellyfin.JellyfinDesktop"
fi

say "1b. Библиотека управления телевизором"
if [ ! -x "$STB_HOME/tvctl/bin/python" ]; then
    runuser -u "$STB_USER" -- python3 -m venv "$STB_HOME/tvctl"
fi
runuser -u "$STB_USER" -- "$STB_HOME/tvctl/bin/pip" install -q --upgrade pip
runuser -u "$STB_USER" -- "$STB_HOME/tvctl/bin/pip" install -q bscpylgtv==0.5.5
"$STB_HOME/tvctl/bin/python" -c "import bscpylgtv" \
    || die "bscpylgtv не установился — без него приставка не управляет телевизором"
install -o "$STB_USER" -g "$STB_USER" -m 644 \
    "$SRC/tvctl/nuc_manifest.json" "$STB_HOME/tvctl/nuc_manifest.json"
ok "bscpylgtv 0.5.5"

# ---------------------------------------------------------------- 2. файлы
say "2. Файлы приставки"
install -d -m 755 "$DST" /var/log/stb /var/lib/stb
for log in keys system tvwatch audio wol pair pointer extrakeys buttons idle \
           screensaver session openbox faketv tv tvdaemon; do
    touch "/var/log/stb/$log.log"
done
chown -R "$STB_USER:$STB_USER" /var/log/stb
install -d -o "$STB_USER" -g "$STB_USER" -m 775 /run/stb
if [ "$SRC" != "$DST" ]; then
    for d in bin web lib config docs tests system home tvctl; do
        [ -d "$SRC/$d" ] || continue
        install -d "$DST/$d"
        cp -a "$SRC/$d/." "$DST/$d/"
    done
    for f in install.sh makedist.sh setup.cfg README.md; do
        [ -e "$SRC/$f" ] && cp -a "$SRC/$f" "$DST/" && chmod 755 "$DST/$f"
    done
    ok "дерево скопировано в $DST"
else
    ok "установка из самого $DST — копировать нечего"
fi
chmod 755 "$DST"/bin/*
chown -R "$STB_USER:$STB_USER" "$DST"
chmod 644 "$DST"/web/*.html "$DST"/web/*.py
ln -sfn "$DST/bin/stb" /usr/local/bin/tv
ok "ссылка /usr/local/bin/tv"

# ---------------------------------------------------------------- 3. настройки
say "3. Настройки системы"
CONF="$DST/config/stb.conf"
sed -i \
    -e "s|^STB_USER=.*|STB_USER=\"${STB_USER}\"|" \
    -e "s|^STB_HOME=.*|STB_HOME=\"${STB_HOME}\"|" \
    -e "s|^TV_IP=.*|TV_IP=\"${STB_TV_IP}\"|" \
    -e "s|^TV_MAC=.*|TV_MAC=\"${STB_TV_MAC}\"|" \
    -e "s|^TV_INPUT_ID=.*|TV_INPUT_ID=\"${STB_TV_INPUT}\"|" \
    -e "s|^TV_APP_ID=.*|TV_APP_ID=\"${STB_TV_APP}\"|" \
    -e "s|^LAN_IF=.*|LAN_IF=\"${STB_LAN_IF}\"|" \
    -e "s|^TV_IF=.*|TV_IF=\"${STB_TV_IF}\"|" "$CONF"
if [ -n "$STB_TV_MAC_ALT" ]; then
    sed -i "s|^TV_MAC_ALT=.*|TV_MAC_ALT=\"${STB_TV_MAC_ALT}\"|" "$CONF"
fi
ok "параметры в $CONF"

# наш идентификатор в SSDP: придумываем один раз, если поле пустое
if ! grep -qE '^WF_UUID="[^"]+"' "$CONF"; then
    NEW_UUID="uuid:$(python3 -c 'import uuid; print(uuid.uuid4())')"
    sed -i "s|^WF_UUID=.*|WF_UUID=\"${NEW_UUID}\"|" "$CONF"
    ok "WF_UUID придуман: $NEW_UUID"
fi

install -d -m 755 /etc/stb
ln -sfn "$CONF" /etc/stb/config

# внешние файлы: единственное дерево system/ повторяет настоящие пути
cp -a "$SRC/system/etc/." /etc/
cp -a "$SRC/system/usr/." /usr/
printf 'd /run/stb 0775 %s %s -\n' "$STB_USER" "$STB_USER" > /etc/tmpfiles.d/stb.conf
sed -i -e "s/stbuser/${STB_USER}/g" -e "s#/home/stbuser#${STB_HOME}#g" \
    /etc/lightdm/lightdm.conf.d/50-stb.conf
/usr/sbin/sysctl --system >/dev/null
ok "файлы /etc и /usr из system/"

# bluetooth: только наши две строки
if [ -f "$SRC/system/etc/bluetooth/main.conf.stb" ]; then
    while IFS= read -r line; do
        key="${line%%=*}"
        key="$(printf '%s' "$key" | tr -d ' ')"
        sed -i "/^[[:space:]]*${key}[[:space:]]*=/d" /etc/bluetooth/main.conf
        printf '%s\n' "$line" >> /etc/bluetooth/main.conf
    done < "$SRC/system/etc/bluetooth/main.conf.stb"
    ok "bluetooth: имя и FastConnectable"
fi

say "3d. Сеть телевизора"
# Адрес приставки в сети телевизора: если не задан — берём последний октет IP
# телевизора и подставляем 198 (как на нашей машине), иначе спрашиваем.
if [ -z "$STB_TV_IF_ADDR" ]; then
    STB_TV_IF_ADDR="${STB_TV_IP%.*}.198"
    warn "адрес приставки в сети телевизора не задан, беру ${STB_TV_IF_ADDR}"
fi
if [ -z "$STB_GW" ]; then
    STB_GW="$(ip route show default 2>/dev/null | awk '/default/ {print $3; exit}')"
fi
if [ -z "$STB_DNS" ]; then
    STB_DNS="$(awk '/^nameserver/ {print $2; exit}' /etc/resolv.conf 2>/dev/null)"
fi
[ -n "$STB_GW" ] || die "не удалось определить шлюз для телевизора (параметр STB_GW)"
[ -n "$STB_DNS" ] || STB_DNS="$STB_GW"

install -d /etc/network/interfaces.d /etc/dnsmasq.d
sed -e "s|@TV_IF@|${STB_TV_IF}|g" \
    -e "s|@ADDR@|${STB_TV_IF_ADDR}|g" \
    -e "s|@TV_IP@|${STB_TV_IP}|g" \
    "$SRC/system/etc/network/interfaces.d/tv-lan.template" \
    > /etc/network/interfaces.d/tv-lan

sed -e "s|@TV_IF@|${STB_TV_IF}|g" \
    -e "s|@TV_MAC@|${STB_TV_MAC}|g" \
    -e "s|@TV_IP@|${STB_TV_IP}|g" \
    -e "s|@GW@|${STB_GW}|g" \
    -e "s|@DNS@|${STB_DNS}|g" \
    "$SRC/system/etc/dnsmasq.d/tv-lan.conf.template" \
    > /etc/dnsmasq.d/tv-lan.conf

systemctl enable dnsmasq
if systemctl is-active --quiet networking; then
    ifup "$STB_TV_IF" 2>/dev/null || ifreload -a 2>/dev/null || true
fi
# Без телевизора (виртуалка, другой корпус) интерфейса может не быть: dnsmasq
# тогда не поднимется, но установка обязана дойти до конца.
if systemctl restart dnsmasq; then
    ok "телевизор получит ${STB_TV_IP} на ${STB_TV_IF} (адрес приставки ${STB_TV_IF_ADDR})"
else
    warn "dnsmasq не поднялся: нет интерфейса ${STB_TV_IF}? Проверьте после подключения телевизора"
fi

say "3a. Службы"
install -d /etc/systemd/system
for f in "$SRC"/system/etc/systemd/system/stb-*; do
    [ -e "$f" ] || continue
    cp -a "$f" /etc/systemd/system/
done
install -d -o "$STB_USER" -g "$STB_USER" "$STB_HOME/.config/systemd/user"
for f in "$SRC"/home/.config/systemd/user/stb-*.service; do
    [ -e "$f" ] || continue
    sed -e "s#/home/stbuser#${STB_HOME}#g" -e "s/stbuser/${STB_USER}/g" \
        "$f" > "$STB_HOME/.config/systemd/user/$(basename "$f")"
done
chown -R "$STB_USER:$STB_USER" "$STB_HOME/.config/systemd"
systemctl daemon-reload
ok "юниты на месте"

say "3b. Файлы пользователя"
install -d -o "$STB_USER" -g "$STB_USER" \
    "$STB_HOME/.config/openbox" "$STB_HOME/.config/dunst"
for f in .Xresources .xprofile; do
    [ -e "$SRC/home/$f" ] && install -o "$STB_USER" -g "$STB_USER" -m 644 \
        "$SRC/home/$f" "$STB_HOME/$f"
done
for f in .config/openbox/rc.xml .config/dunst/dunstrc; do
    [ -e "$SRC/home/$f" ] && install -o "$STB_USER" -g "$STB_USER" -m 644 \
        "$SRC/home/$f" "$STB_HOME/$f"
done
install -d -o "$STB_USER" -g "$STB_USER" "$STB_HOME/.mozilla/stb"
for f in user.js content-prefs.sqlite; do
    [ -e "$SRC/home/.mozilla/stb/$f" ] && install -o "$STB_USER" -g "$STB_USER" -m 644 \
        "$SRC/home/.mozilla/stb/$f" "$STB_HOME/.mozilla/stb/$f"
done
if [ -d "$SRC/home/.mozilla/stb/chrome" ]; then
    cp -a "$SRC/home/.mozilla/stb/chrome" "$STB_HOME/.mozilla/stb/"
fi
if [ -e "$SRC/home/.aiopylgtv.sqlite" ]; then
    install -o "$STB_USER" -g "$STB_USER" -m 600 \
        "$SRC/home/.aiopylgtv.sqlite" "$STB_HOME/.aiopylgtv.sqlite"
fi
chown -R "$STB_USER:$STB_USER" "$STB_HOME/.mozilla"
ok "профиль браузера, openbox, уведомления"

say "3c. Узкое sudo"
cat > "/etc/sudoers.d/stb-${STB_USER}" <<EOF
${STB_USER} ALL=(root) NOPASSWD: /usr/sbin/systemctl poweroff, /usr/bin/systemctl poweroff
${STB_USER} ALL=(root) NOPASSWD: /usr/sbin/systemctl reboot, /usr/bin/systemctl reboot
${STB_USER} ALL=(root) NOPASSWD: /usr/sbin/etherwake, /usr/bin/etherwake
${STB_USER} ALL=(root) NOPASSWD: /usr/sbin/ethtool, /usr/bin/ethtool
EOF
chmod 440 "/etc/sudoers.d/stb-${STB_USER}"
visudo -c -f "/etc/sudoers.d/stb-${STB_USER}" >/dev/null \
    || die "правило sudo не прошло проверку"
ok "правила sudo"

# ---------------------------------------------------------------- 4. включение
say "4. Службы и привязки"
systemctl daemon-reload
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
install -d -m 775 -o "$STB_USER" -g "$STB_USER" /var/log/stb
chown -R "$STB_USER:$STB_USER" /var/log/stb
# Хук выключения включаем явно, а не только через Wants= у stb.target: если
# stb.target не поднимется, приставка останется без гашения телевизора на
# выключении — а это ровно тот случай, когда телевизор будит её обратно.
systemctl enable stb.target stb-nic-watch.timer stb-tv-shutdown.service
ok "stb.target, сторож сети и хук выключения включены"

# Включить мало: на свежей системе службы ещё ни разу не запускались.
# Графическая сессия тоже должна подниматься сама.
systemctl set-default graphical.target >/dev/null 2>&1 || warn "не смог поставить graphical.target"
systemctl enable lightdm >/dev/null 2>&1 || warn "lightdm не включился"
systemctl start stb.target || warn "stb.target не запустился"
sleep 5
systemctl restart lightdm >/dev/null 2>&1 || warn "lightdm не перезапустился"
sleep 4
if systemctl is-active --quiet lightdm; then
    ok "графическая сессия запущена"
else
    warn "lightdm не стартовал — сессия появится после перезагрузки"
fi

# Пользовательские службы включаем ссылками в default.target.wants:
# на свежей системе графической сессии ещё нет, и systemctl --user не работает.
WANTS="$STB_HOME/.config/systemd/user/default.target.wants"
install -d -o "$STB_USER" -g "$STB_USER" "$WANTS"
for u in stb-web stb-browser stb-screensaver; do
    UNIT="$STB_HOME/.config/systemd/user/$u.service"
    if [ -e "$UNIT" ]; then
        ln -sfn "$UNIT" "$WANTS/$u.service"
        printf '   · %s\n' "$u"
    else
        warn "нет юнита $u — служба не включена"
    fi
done
chown -R "$STB_USER:$STB_USER" "$STB_HOME/.config/systemd"
"$DST/bin/stb" keys apply bt >/dev/null 2>&1 || warn "привязки BT соберутся при первом входе в сессию"
ok "пользовательские службы включены"

# ---------------------------------------------------------------- 5. проверка
say "5. Проверка установки"
problem=0
check() {  # check <что> <проверка...>
    local what="$1"; shift
    if "$@" >/dev/null 2>&1; then ok "$what"; else warn "НЕ ГОТОВО: $what"; problem=1; fi
}
check "конфиг на месте"            test -r /etc/stb/config
check "ссылка tv"                  test -x /usr/local/bin/tv
check "внешние юниты"              test -f /etc/systemd/system/stb.target
check "юнит заставки (пользователь)" test -f "$STB_HOME/.config/systemd/user/stb-screensaver.service"
check "профиль браузера"           test -f "$STB_HOME/.mozilla/stb/user.js"
check "библиотека телевизора"      "$STB_HOME/tvctl/bin/python" -c "import bscpylgtv"
check "stb.target включён"         systemctl is-enabled stb.target
check "хук выключения включён"    systemctl is-enabled stb-tv-shutdown.service
check "графическая цель"          test "$(systemctl get-default)" = graphical.target
check "сторож работает"           systemctl is-active stb-watch
check "приёмник пульта работает"  systemctl is-active stb-wifi-remote
check "связь с телевизором"       systemctl is-active stb-tv-link
check "страница отвечает"         curl -sf -m 5 -o /dev/null http://127.0.0.1:8090/

if [ "$problem" -ne 0 ]; then
    die "установка неполная — смотри предупреждения выше"
fi

# ---------------------------------------------------------------- 6. итог
say "6. Готово"
cat <<EOF
   1) Перезагрузка:                sudo reboot
   2) Регистрация телевизора:      sudo $DST/bin/stb tv register
      (на экране телевизора подтвердить запрос)
   3) Подключение телефона:        sudo $DST/bin/stb pair
   4) Проверка телевизора:         stb tv powerstate
   5) Состояние служб:             sudo $DST/bin/stb ctl status

   Документация: $DST/docs (начать с README.md)
EOF
