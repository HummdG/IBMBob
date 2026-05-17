"""Low-level git invocation. No shell, ever — args are passed as a list.

Every git call in GitBob funnels through `run_git` so behaviour (timeouts,
encoding, "is this a repo" checks) is consistent and testable.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

DEFAULT_TIMEOUT = 120

# When GitBob runs inside Bob, the server's stdin/stdout are the MCP stdio
# pipes. A naive subprocess inherits stdin and git blocks forever waiting on
# it (and could pop a pager or credential prompt). This env + stdin=DEVNULL
# keeps every git call strictly non-interactive.
_GIT_ENV = {
    "GIT_TERMINAL_PROMPT": "0",   # never prompt for credentials
    "GIT_PAGER": "cat",           # never launch a pager
    "GIT_OPTIONAL_LOCKS": "0",    # don't block on optional locks
    "GIT_CONFIG_NOSYSTEM": "0",
}


@dataclass
class GitResult:
    """Outcome of a single git invocation."""

    ok: bool
    returncode: int
    stdout: str
    stderr: str
    args: list[str]

    @property
    def output(self) -> str:
        """stdout, falling back to stderr (git writes some info there)."""
        return self.stdout if self.stdout.strip() else self.stderr


def run_git(
    args: list[str],
    repo_path: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> GitResult:
    """Run `git <args>` in `repo_path` (default: cwd). Never uses a shell."""
    cwd = repo_path or os.getcwd()
    try:
        proc = subprocess.run(
            ["git", "--no-pager", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            stdin=subprocess.DEVNULL,
            env={**os.environ, **_GIT_ENV},
        )
        return GitResult(
            ok=proc.returncode == 0,
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            args=args,
        )
    except subprocess.TimeoutExpired:
        return GitResult(False, 124, "", f"git timed out after {timeout}s", args)
    except OSError as exc:
        # Missing git executable, or an invalid/missing cwd
        # (FileNotFoundError / NotADirectoryError). Never propagate.
        return GitResult(False, 127, "", f"git could not run: {exc}", args)


def is_git_repo(repo_path: str | None = None) -> bool:
    """True if `repo_path` is inside a git working tree."""
    res = run_git(["rev-parse", "--is-inside-work-tree"], repo_path, timeout=15)
    return res.ok and res.stdout.strip() == "true"


def truncate(text: str, max_chars: int) -> str:
    """Clip large output so we stay token-frugal (Bobcoins are finite)."""
    if len(text) <= max_chars:
        return text
    head = text[:max_chars]
    omitted = len(text) - max_chars
    return f"{head}\n\n... [truncated {omitted} more characters] ..."
