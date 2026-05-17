"""Safe execution of git commands proposed by Bob.

The confirmation model has two gates:

  1. Bob's own UI gate — `git_run` is deliberately NOT in the mcp.json
     `alwaysAllow` list, so Bob shows the call and the user must approve it.
  2. GitBob's destructive gate — if the plan contains a dangerous command
     (history rewrite, hard reset, force push, file deletion, ...), the
     first call does NOT execute. It returns a `confirmation_required`
     payload with a `confirm_token`. The command only runs when Bob calls
     again with that exact token, which Bob is instructed to do only after
     the human explicitly says yes.

The token is derived from the exact command plan, so Bob cannot get a
"yes" for one plan and silently execute a different one.
"""

from __future__ import annotations

import hashlib
import shlex

from . import danger
from .gitproc import is_git_repo, run_git, truncate
from .safety import LEVEL_DANGEROUS, classify_all


def _token(commands: list[str]) -> str:
    """Stable token bound to this exact ordered plan."""
    digest = hashlib.sha256("\n".join(commands).encode("utf-8")).hexdigest()
    return f"gitbob-{digest[:16]}"


def run(
    commands: list[str],
    confirm_token: str | None = None,
    repo_path: str | None = None,
) -> dict:
    """Validate, gate, then execute an ordered list of git commands.

    Stops at the first command that fails and reports what happened, plus a
    fresh status snapshot so Bob can verify the outcome.
    """
    if not commands:
        return {"status": "error", "message": "No commands provided."}
    if not is_git_repo(repo_path):
        return {"status": "error",
                "message": "This directory is not inside a git repository."}

    classifications = classify_all(commands)

    rejected = [c for c in classifications if c.rejected]
    if rejected:
        return {
            "status": "rejected",
            "message": "One or more commands are not safe to run.",
            "details": [{"command": c.raw, "reason": c.reason} for c in rejected],
        }

    dangerous = [c for c in classifications if c.level == LEVEL_DANGEROUS]
    expected = _token(commands)

    if dangerous and confirm_token != expected:
        payload = {
            "status": "confirmation_required",
            "message": (
                "This plan contains destructive git operations. Show the "
                "user the risk assessment (include its `mermaid` diagram "
                "verbatim if present), get an explicit yes, then call "
                "git_run again with the same commands plus confirm_token."
            ),
            "dangerous": [
                {"command": c.raw, "risk": c.reason} for c in dangerous
            ],
            "plan": commands,
            "confirm_token": expected,
        }
        try:  # best-effort colour-coded consequence visual
            payload["risk"] = danger.risk_card(commands, repo_path)
        except Exception:
            pass
        return payload

    results = []
    aborted = False
    for cmd in commands:
        # Re-validated above; split is safe (no shell, no metachars).
        # safety.classify guarantees tokens[0] == "git"; run_git prepends
        # the git executable itself, so pass only the arguments.
        tokens = shlex.split(cmd, posix=True)
        res = run_git(tokens[1:], repo_path)
        results.append({
            "command": cmd,
            "exit_code": res.returncode,
            "ok": res.ok,
            "output": truncate(res.output, 3000),
        })
        if not res.ok:
            aborted = True
            break

    snapshot = run_git(
        ["status", "--short", "--branch"], repo_path
    ).stdout
    return {
        "status": "completed" if not aborted else "failed",
        "executed": results,
        "aborted_on_error": aborted,
        "repo_status_after": truncate(snapshot, 2000),
        "hint": (
            "A command failed. Read its output, explain the cause to the "
            "user in plain language, and propose a recovery plan."
            if aborted else
            "All commands succeeded. Confirm the outcome to the user."
        ),
    }
