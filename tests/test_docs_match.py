"""Документация должна соответствовать системе: пути, команды, юниты, параметры."""
import glob
import io
import os
import re
import subprocess

ROOT = os.environ.get("STB_ROOT", "/opt/stb")
CFG = io.open(os.path.join(ROOT, "config/stb.conf"), encoding="utf-8").read()
KEYS = set(re.findall(r"^([A-Z][A-Z0-9_]+)=", CFG, re.M))

KEYS_NAMES = {"BACK", "BLUE", "CHANNELDOWN", "CHANNELUP", "DOWN", "ENTER", "EXIT",
              "FASTFORWARD", "GREEN", "GUIDE", "INFO", "LEFT", "MENU", "MUTE",
              "PAUSE", "PLAY", "RED", "REWIND", "RIGHT", "SUBTITLE", "VOLUMEDOWN",
              "VOLUMEUP", "YELLOW", "HOME", "OK", "CC", "PYTHONPATH", "DISPLAY",
              "XDG_RUNTIME_DIR", "UUID", "TV", "STB", "LG", "SSDP", "HDMI_3", "API",
              "URL", "JSON", "CPU", "MAC", "IP", "HDMI", "SSAP", "ID",
              "STB_DNS", "STB_GW", "STB_TV_IF_ADDR"}


def docs():
    found = sorted(glob.glob(os.path.join(ROOT, "docs/*.md")))
    root_readme = os.path.join(ROOT, "README.md")
    if os.path.exists(root_readme):
        found.append(root_readme)
    return found


def topics():
    out = subprocess.run([os.path.join(ROOT, "bin/stb"), "help"],
                         capture_output=True, text=True, timeout=30).stdout
    return {line.split()[0] for line in out.splitlines()
            if line.startswith("  ") and not line.startswith("   ") and line.split()}


def units():
    out = subprocess.run(["systemctl", "list-unit-files", "stb*", "--no-pager",
                          "--no-legend"], capture_output=True, text=True, timeout=30).stdout
    return {line.split()[0] for line in out.splitlines() if line.strip()}


def test_docs_match_system():
    known_topics, known_units = topics(), units()
    problems = []

    for doc in docs():
        text = io.open(doc, encoding="utf-8").read()

        for path in set(re.findall(r"(/opt/stb/[\w./-]+|/home/stbuser/[\w./-]+)", text)):
            clean = path.rstrip(".,)`»")
            if "*" in clean:
                if clean.startswith("/opt/stb"):
                    rest = clean[len("/opt/stb"):].lstrip("/")
                    clean = os.path.join(ROOT, rest)
                if not glob.glob(clean):
                    problems.append("%s: путь %s" % (os.path.basename(doc), clean))
                continue
            # документация описывает пути установки; при прогоне из другого
            # каталога (/opt/stb заменяется на STB_ROOT) проверяем то же место
            if clean.startswith("/opt/stb"):
                rest = clean[len("/opt/stb"):].lstrip("/")
                clean = os.path.join(ROOT, rest) if rest else ROOT
            if not os.path.exists(clean):
                problems.append("%s: путь %s" % (os.path.basename(doc), clean))

        for unit in set(re.findall(r"\b(stb-[\w-]+\.(?:service|timer))\b", text)):
            if unit not in known_units:
                problems.append("%s: юнит %s" % (os.path.basename(doc), unit))

        for topic in set(re.findall(r"\bstb ([\w-]+)", text)):
            if topic not in known_topics and not topic.isdigit():
                problems.append("%s: команда stb %s" % (os.path.basename(doc), topic))

        for key in set(re.findall(r"`([A-Z][A-Z0-9_]{2,})`", text)):
            if key not in KEYS and key not in KEYS_NAMES:
                problems.append("%s: параметр %s" % (os.path.basename(doc), key))

        for log in set(re.findall(r"/var/log/stb/([\w.-]+\.log)", text)):
            if not os.path.exists("/var/log/stb/" + log):
                problems.append("%s: журнал %s" % (os.path.basename(doc), log))

    assert not problems, "документация разошлась с системой:\n  " + "\n  ".join(sorted(set(problems)))
