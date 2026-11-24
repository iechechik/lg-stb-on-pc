"""Документ команд не должен расходиться с самой программой."""
import pathlib
import subprocess

ROOT = pathlib.Path("/opt/stb")


def test_commands_doc_is_fresh():
    generated = subprocess.run([str(ROOT / "bin/stb"), "help", "--markdown"],
                               capture_output=True, text=True, timeout=30).stdout
    saved = (ROOT / "docs/COMMANDS.md").read_text(encoding="utf-8")
    assert generated.strip() == saved.strip(), (
        "docs/COMMANDS.md устарел — пересоберите: stb help --markdown > docs/COMMANDS.md")
