"""Установщик: полнота архива, шаблоны, привязка служб, режим проверки."""
import pathlib
import re
import subprocess

ROOT = pathlib.Path("/opt/stb")


OPTIONAL = {"home/.aiopylgtv.sqlite"}   # ключ телевизора — секрет, в архив по умолчанию не кладём


def test_every_archive_path_exists():
    """Всё, что установщик копирует из архива, должно в архиве быть."""
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    paths = set(re.findall(r"\$SRC/([A-Za-z0-9_./@-]+)", text))
    missing = sorted(p for p in paths
                     if not (ROOT / p).exists() and not p.endswith("/")
                     and p not in OPTIONAL)
    assert not missing, "установщик ждёт файлы, которых нет: %s" % missing


def test_templates_have_placeholders():
    for name in ("system/etc/dnsmasq.d/tv-lan.conf.template",
                 "system/etc/network/interfaces.d/tv-lan.template"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "@TV_IP@" in text, name
        assert "@TV_IF@" in text, name


def test_dnsmasq_template_binds_tv_by_mac():
    text = (ROOT / "system/etc/dnsmasq.d/tv-lan.conf.template").read_text(encoding="utf-8")
    assert "dhcp-host=@TV_MAC@" in text
    assert "port=0" in text          # свой DNS не поднимаем


def test_target_pulls_all_boot_units():
    text = (ROOT / "system/etc/systemd/system/stb.target").read_text(encoding="utf-8")
    for unit in ("stb-tv-link.service", "stb-tv-boot.service",
                 "stb-tv-shutdown.service", "stb-nic-tune.service",
                 "stb-nic-watch.timer"):
        assert unit in text, "в stb.target нет %s" % unit


def test_installer_check_mode_passes():
    result = subprocess.run(["bash", str(ROOT / "install.sh"), "--check"],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout[-800:]


def test_user_units_are_enabled_by_installer():
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    for unit in ("stb-web", "stb-browser", "stb-screensaver"):
        assert "for u in stb-web stb-browser stb-screensaver" in text or unit in text
