"""CLI behaviour — the GitBob<->Bob integration boundary.

The historical failure: `.bob/mcp.json` shipped `"command": "gitbob"`, but
Bob spawns MCP servers with the *system* environment where a virtualenv's
`gitbob` is not on PATH -> "0 tools". These tests pin that `gitbob init`
now writes a PATH-proof absolute command, and that `gitbob doctor`
actively catches an unspawnable config.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from gitbob import cli


def _server_cfg(repo: Path) -> dict:
    data = json.loads((repo / ".bob" / "mcp.json").read_text(encoding="utf-8"))
    return data["mcpServers"]["gitbob"]


def test_server_command_prefers_venv_executable(tmp_path, monkeypatch):
    bin_dir = tmp_path / "Scripts"
    bin_dir.mkdir()
    exe_name = "gitbob.exe" if os.name == "nt" else "gitbob"
    fake_exe = bin_dir / exe_name
    fake_exe.write_text("")
    monkeypatch.setattr(cli.sys, "executable", str(bin_dir / "python.exe"))

    cmd, args = cli._server_command()

    assert cmd == str(fake_exe)
    assert args == ["serve"]


def test_server_command_falls_back_to_module(tmp_path, monkeypatch):
    empty = tmp_path / "nogitbob"
    empty.mkdir()
    fake_py = empty / "python.exe"
    fake_py.write_text("")
    monkeypatch.setattr(cli.sys, "executable", str(fake_py))

    cmd, args = cli._server_command()

    assert cmd == str(fake_py)
    assert args == ["-m", "gitbob", "serve"]


def test_init_writes_path_proof_mcp_json(git_repo: Path):
    rc = cli.main(["init", str(git_repo)])

    assert rc == 0
    srv = _server_cfg(git_repo)
    assert srv["command"] != "gitbob"                  # the historical bug
    assert os.path.isabs(srv["command"])
    # The command Bob will spawn must actually exist on this machine.
    assert os.path.isfile(srv["command"])
    assert srv["args"][-1] == "serve"
    assert len(srv["alwaysAllow"]) == 8
    assert "git_status" in srv["alwaysAllow"]


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
    capsys.readouterr()  # discard init output

    rc = cli._cmd_doctor(argparse.Namespace(path=str(git_repo)))
    out = capsys.readouterr().out

    assert rc == 0
    assert "spawn" in out.lower()          # the new launchability check ran
    assert "[XX]" not in out
