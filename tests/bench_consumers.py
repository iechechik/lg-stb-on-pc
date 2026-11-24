#!/usr/bin/env python3
"""Замер стоимости опроса: CPU и запущенные процессы у сторожей.

    sudo /opt/stb/tests/bench_consumers.py [секунд]

Рядом поднимается поддельный телевизор (tests/fake_tv.py), поэтому настоящий
не участвует. Считаем: сколько запросов сделал сторож, сколько процессорного
времени потратил и какие процессы породил после запуска (первые секунды не
считаются: при старте сторож законно поднимает интерфейс и ставит вход).
"""
import os
import subprocess
import sys
import time

ROOT = os.environ.get("STB_ROOT", "/opt/stb")
SOCK = "/tmp/bench-tv.sock"
FLOG = "/tmp/bench-tv.log"
DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 30
WARMUP = 5.0


def proc_times(pid):
    try:
        with open("/proc/%d/stat" % pid, encoding="utf-8") as f:
            fields = f.read().split()
        return (int(fields[13]) + int(fields[14])) / os.sysconf("SC_CLK_TCK")
    except (OSError, IndexError, ValueError):
        return 0.0


def children_of(pid):
    """Дети процесса: множество pid (попадания в выборку не считаем)."""
    found = set()
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open("/proc/%s/stat" % entry, encoding="utf-8") as f:
                fields = f.read().split()
            if int(fields[3]) == pid:
                found.add(entry)
        except (OSError, IndexError, ValueError):
            continue
    return found


def cmdline(pid):
    try:
        with open("/proc/%s/cmdline" % pid, "rb") as f:
            return f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
    except OSError:
        return "?"


def requests_made():
    try:
        with open(FLOG, encoding="utf-8") as f:
            return len([line for line in f if line.strip()])
    except OSError:
        return 0


def run_consumer(name, command, env, seconds):
    before_req = requests_made()
    started = time.time()
    proc = subprocess.Popen(command, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cpu0 = proc_times(proc.pid)
    spawned = {}
    while time.time() - started < seconds and proc.poll() is None:
        if time.time() - started > WARMUP:
            for child in children_of(proc.pid):
                if child not in spawned:
                    spawned[child] = cmdline(child)
        time.sleep(0.1)
    cpu1 = proc_times(proc.pid)
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    return {"name": name, "cpu": cpu1 - cpu0,
            "requests": requests_made() - before_req,
            "children": list(spawned.values())}


def cli_cost(env, runs=5):
    started = time.time()
    for _ in range(runs):
        subprocess.run([sys.executable, os.path.join(ROOT, "bin/stb-tv-ask"), "state"],
                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return (time.time() - started) / runs


def main():
    fake = subprocess.Popen([sys.executable, os.path.join(ROOT, "tests/fake_tv.py"),
                             "--socket", SOCK, "--log", FLOG, "--delay", "0.02"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    env = dict(os.environ, STB_TV_SOCK=SOCK)

    rows = [
        run_consumer("сторожа (stb-watch all)",
                     [sys.executable, os.path.join(ROOT, "bin/stb-watch"), "all"], env, DURATION),
    ]
    one_call = cli_cost(env)

    fake.terminate()
    try:
        fake.wait(timeout=5)
    except subprocess.TimeoutExpired:
        fake.kill()

    print("\n  %-34s %9s %8s %10s" % ("кто", "запросов", "CPU, с", "процессов"))
    for r in rows:
        print("  %-34s %9d %8.3f %10d"
              % (r["name"], r["requests"], r["cpu"], len(r["children"])))
        for cmd in r["children"]:
            print("      процесс: %s" % cmd[:80])
    print("\n  наблюдение: %d с на каждого; первые %d с не считаются"
          % (DURATION, int(WARMUP)))
    print("  для сравнения: одна команда через отдельный процесс — %.0f мс" % (one_call * 1000))
    return 0


if __name__ == "__main__":
    sys.exit(main())
