# Внешние файлы приставки

Копии всего, что должно лежать в системе **вне** `/opt/stb`. Пути внутри повторяют
настоящие, поэтому применение — копирование дерева в корень.

## Как применить

```sh
rsync -a etc/ /etc/
mkdir -p /etc/stb
ln -sfn /opt/stb/config/stb.conf /etc/stb/config
ln -sf /opt/stb/bin/tv /usr/local/bin/tv
systemctl daemon-reload
systemctl enable --now stb.target stb-nic-watch.timer
```

Установщик `/opt/stb/install.sh` делает это сам (и подставляет своего пользователя
вместо `stbuser`).

## Что требует внимания

- `etc/bluetooth/main.conf.stb` — **не файл целиком**, а две строки (`Name`,
  `FastConnectable`): их нужно внести в `/etc/bluetooth/main.conf` вручную,
  иначе затрётся остальная настройка Bluetooth.
- В юнитах встречаются `/opt/stb` и `stbuser`. При других значениях заменить
  (установщик делает это через `sed`).
- Служебные файлы пользователя (`stb-browser`, `stb-web`, `stb-screensaver`) здесь
  отсутствуют: они живут в `~/.config/systemd/user`, копии — в `home/`.
- Симлинки `etc/stb/config` и `usr/local/bin/tv` в каталоге не хранятся —
  создаются командами выше.
- После копирования нужен `systemctl daemon-reload`, для части настроек
  (sysctl, logind, lightdm) — перезагрузка.

## Что здесь есть

| путь | назначение |
|---|---|
| `etc/systemd/system/stb.target` | единая цель комплекса |
| `etc/systemd/system/stb-*.service`, `.timer`, `.service.d/` | службы приставки и их привязка к цели |
| `etc/tmpfiles.d/stb.conf` | каталог `/run/stb` |
| `etc/sysctl.d/90-tv-proxyarp.conf` | `ip_forward`, `proxy_arp` |
| `etc/systemd/logind.conf.d/10-powerkey.conf` | поведение кнопки корпуса |
| `etc/lightdm/lightdm.conf.d/50-stb.conf` | автовход пользователя приставки |
| `etc/NetworkManager/conf.d/wifi-no-rand-mac.conf` | без случайного MAC при сканировании |
| `etc/bluetooth/main.conf.stb` | имя приставки и `FastConnectable` |
