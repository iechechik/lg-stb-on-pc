#!/bin/bash
# collect.sh — собрать /opt/stb/system: копии всего, что живёт вне /opt/stb.
# Здесь единственное место для системных файлов: дерево повторяет настоящие
# пути (/etc/..., /usr/share/...), поэтому установка = копирование в корень.
set -eu

S="/opt/stb/system"
install -d "$S/etc/systemd/system" "$S/etc/systemd/logind.conf.d" \
           "$S/etc/sysctl.d" "$S/etc/tmpfiles.d" "$S/etc/lightdm/lightdm.conf.d" \
           "$S/etc/bluetooth" "$S/etc/NetworkManager/conf.d" \
           "$S/usr/share/xsessions"

# --- юниты комплекса (вместе с переопределениями PartOf)
cp -f /etc/systemd/system/stb.target "$S/etc/systemd/system/"
for f in /etc/systemd/system/stb-*.service /etc/systemd/system/stb-*.timer; do
    [ -e "$f" ] && cp -f "$f" "$S/etc/systemd/system/"
done
for d in /etc/systemd/system/stb-*.service.d; do
    [ -d "$d" ] || continue
    install -d "$S/etc/systemd/system/$(basename "$d")"
    cp -f "$d"/*.conf "$S/etc/systemd/system/$(basename "$d")/"
done

# --- настройки системы
cp -f /etc/tmpfiles.d/stb.conf                      "$S/etc/tmpfiles.d/"
cp -f /etc/sysctl.d/90-tv-proxyarp.conf             "$S/etc/sysctl.d/"
cp -f /etc/systemd/logind.conf.d/10-powerkey.conf   "$S/etc/systemd/logind.conf.d/"
cp -f /etc/lightdm/lightdm.conf.d/50-stb.conf       "$S/etc/lightdm/lightdm.conf.d/"
cp -f /etc/NetworkManager/conf.d/wifi-no-rand-mac.conf "$S/etc/NetworkManager/conf.d/"
cp -f /usr/share/xsessions/stb.desktop              "$S/usr/share/xsessions/"
cp -f /etc/machine-info                             "$S/etc/" 2>/dev/null || true

# bluetooth: чужой файл целиком не копируем — только наши строки
grep -E "^(Name|FastConnectable) *=" /etc/bluetooth/main.conf > "$S/etc/bluetooth/main.conf.stb" || true

chmod -R u+rwX,go+rX "$S"
find "$S" -type f -exec chmod 644 {} +
chmod 755 "$S/collect.sh"   # сам сборщик остаётся исполняемым
chown -R stbuser:stbuser "$S"
echo "  файлов в system/: $(find "$S" -type f | wc -l)"
