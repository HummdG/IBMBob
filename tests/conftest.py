"""Shared fixtures: a throwaway git repo with a little history."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True,
                    capture_output=True, text=True)


@pytest.fixture(autouse=True)
def _git_ceiling(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Stop git from discovering an enclosing repo above the test sandbox.

    Developer/CI home directories are sometimes git repos, which would make
    a 'plain' temp dir look like it's inside a work tree. Pinning the
    ceiling to tmp_path keeps the non-repo tests honest while the fixture
    repo (which has its own .git) is found before the ceiling is hit.
    """
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A repo on `main` with one commit and an uncommitted modification."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "chore: initial commit")
    (repo / "app.py").write_text("print('hello')\n", encoding="utf-8")
    return repo


@pytest.fixture
def empty_dir(tmp_path: Path) -> Path:
    """A directory that is NOT a git repository."""
    d = tmp_path / "plain"
    d.mkdir()
    return d
