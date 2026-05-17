"""CLI behaviour — the GitBob<->Bob integration boundary.

History: `.bob/mcp.json` shipped `"command": "gitbob"`, but Bob spawns
MCP servers with the *system* environment where a virtualenv's `gitbob`
is not on PATH -> "0 tools". Fix: `gitbob init` writes a command that
resolves on the **target** machine — bare `gitbob` when it is installed
on PATH (portable, works on every machine), else an absolute fallback
for a raw dev checkout. `gitbob doctor` actively catches an unspawnable
config. These tests pin that contract deterministically (PATH lookup is
stubbed so the suite is hermetic across machines).
"""

import argparse
import json
import os
from pathlib import Path

from gitbob import cli


def _server_cfg(repo: Path) -> dict:
    data = json.loads((repo / ".bob" / "mcp.json").read_text(encoding="utf-8"))
    return data["mcpServers"]["gitbob"]


def _on_path(monkeypatch):
    monkeypatch.setattr(
        cli.shutil, "which",
        lambda name, *a, **k: r"C:\tools\gitbob.exe" if name == "gitbob"
        else None)


def _not_on_path(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda *a, **k: None)


def test_server_command_prefers_gitbob_on_path(monkeypatch):
    _on_path(monkeypatch)
    assert cli._server_command() == ("gitbob", ["serve"])


def test_server_command_falls_back_to_venv_exe(tmp_path, monkeypatch):
    _not_on_path(monkeypatch)
    bin_dir = tmp_path / "Scripts"
    bin_dir.mkdir()
    exe = bin_dir / ("gitbob.exe" if os.name == "nt" else "gitbob")
    exe.write_text("")
    monkeypatch.setattr(cli.sys, "executable", str(bin_dir / "python.exe"))

    assert cli._server_command() == (str(exe), ["serve"])


def test_server_command_falls_back_to_module(tmp_path, monkeypatch):
    _not_on_path(monkeypatch)
    empty = tmp_path / "nogitbob"
    empty.mkdir()
    fake_py = empty / "python.exe"
    fake_py.write_text("")
    monkeypatch.setattr(cli.sys, "executable", str(fake_py))

    assert cli._server_command() == (str(fake_py), ["-m", "gitbob", "serve"])


def test_init_writes_bare_gitbob_when_on_path(git_repo: Path, monkeypatch):
    _on_path(monkeypatch)

    assert cli.main(["init", str(git_repo)]) == 0
    srv = _server_cfg(git_repo)
    assert srv["command"] == "gitbob"            # portable: every machine
    assert srv["args"][-1] == "serve"
    assert srv["cwd"] == "${workspaceFolder}"    # follows the opened repo
    assert len(srv["alwaysAllow"]) == 8


def test_init_writes_absolute_fallback_without_path_install(
    git_repo: Path, monkeypatch
):
    _not_on_path(monkeypatch)

    assert cli.main(["init", str(git_repo)]) == 0
    srv = _server_cfg(git_repo)
    assert srv["command"] != "gitbob"            # no PATH install -> absolute
    assert os.path.isabs(srv["command"])
    assert os.path.isfile(srv["command"])        # and it really exists
    assert srv["args"][-1] == "serve"


def test_doctor_flags_unresolvable_mcp_command(git_repo: Path, capsys):
    bob = git_repo / ".bob"
    bob.mkdir(parents=True, exist_ok=True)
    (bob / "mcp.json").write_text(json.dumps({
        "mcpServers": {"gitbob": {
            "command": "gitbob-not-a-real-binary-xyz", "args": ["serve"]}}
    }), encoding="utf-8")

    rc = cli._cmd_doctor(argparse.Namespace(path=str(git_repo)))
    out = capsys.readouterr().out

    assert rc != 0
    assert "gitbob-not-a-real-binary-xyz" in out
    assert "not ready" in out.lower()


def test_doctor_passes_after_init(git_repo: Path, capsys):
    cli.main(["init", str(git_repo)])
    capsys.readouterr()

    rc = cli._cmd_doctor(argparse.Namespace(path=str(git_repo)))
    out = capsys.readouterr().out

    assert rc == 0
    assert "spawn" in out.lower()                # the launchability check ran
    assert "[XX]" not in out
