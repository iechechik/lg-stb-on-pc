#!/bin/sh
# stbconf.sh — общие функции приставки: чтение конфига и вычисление адресов.
#
# Подключается так:   . /opt/stb/lib/stbconf.sh
# После этого доступны TV_IP, LAN_IF, TV_IF и функции stb_ip / stb_bcast.
#
# Правило: ни один скрипт не хранит адреса и имена у себя — только берёт отсюда.

: "${STB_CONFIG_DIR:=/opt/stb/config}"
: "${STB_CONFIG:=$STB_CONFIG_DIR/stb.conf}"
# shellcheck source=/dev/null
[ -r "$STB_CONFIG" ] && . "$STB_CONFIG"

# значения по умолчанию, если в конфиге пусто
: "${LAN_IF:=wlp2s0}"
: "${TV_IF:=enp0s25}"
: "${TV_PORT:=3000}"
: "${STB_WEB_PORT:=8090}"
: "${TV_APP_ID:=org.jellyfin.webos}"
: "${TV_INPUT_ID:=HDMI_3}"
: "${TV_WAKE_CMD:=tv on}"

# ---------------------------------------------------------------- адреса
# Текущий адрес интерфейса домашней сети в виде адрес/маска (192.168.1.34/24)
stb_cidr() {
    ip -4 -o addr show dev "$LAN_IF" 2>/dev/null | awk '{print $4}' | head -1
}

# Адрес приставки в домашней сети: из конфига, иначе вычисляется
stb_ip() {
    if [ -n "${STB_IP:-}" ]; then
        printf '%s\n' "$STB_IP"
        return 0
    fi
    cidr=$(stb_cidr)
    [ -n "$cidr" ] || return 1
    printf '%s\n' "${cidr%%/*}"
}

# Широковещательный адрес: из конфига, иначе считается по маске
stb_bcast() {
    if [ -n "${STB_BCAST:-}" ]; then
        printf '%s\n' "$STB_BCAST"
        return 0
    fi
    cidr=$(stb_cidr)
    [ -n "$cidr" ] || return 1
    python3 - "$cidr" <<'PY'
import ipaddress
import sys
print(ipaddress.IPv4Interface(sys.argv[1]).network.broadcast_address)
PY
}

# Адрес интерфейса, в который включён телевизор (для магических пакетов)
stb_tv_if_ip() {
    ip -4 -o addr show dev "$TV_IF" 2>/dev/null | awk '{print $4}' | head -1 | cut -d/ -f1
}
