"""The GitBob MCP server.

Bob is the agent. These tools are its hands. Tool docstrings ARE the
descriptions Bob reads to decide what to call, so they are written for an
agent audience: what it does, when to use it, what it returns.

Transport is stdio (Bob spawns this process per the repo's .bob/mcp.json).
The six read tools are safe and meant to be in `alwaysAllow`. `git_run`
is deliberately gated.
"""

from __future__ import annotations

import logging
import os

from mcp.server.fastmcp import FastMCP

from . import danger, git_context, git_exec, gitgraph

# The MCP SDK logs "Processing request of type ..." at INFO to stderr on
# every request. Bob's MCP panel flags ALL server stderr as "error", so
# those benign lines show up as scary (but harmless) errors. Keep the
# server silent on success; real exceptions still surface.
logging.getLogger("mcp").setLevel(logging.ERROR)

mcp = FastMCP("gitbob", log_level="ERROR")


def _repo(repo_path: str | None) -> str:
    return repo_path or os.getcwd()


@mcp.tool()
def git_status(repo_path: str | None = None) -> dict:
    """Current working-tree status: branch, upstream, ahead/behind counts,
    and how many files are staged / unstaged / untracked.

    Call this first for almost any git request — it grounds you in the
    user's actual situation. Read-only and safe."""
    return git_context.status(_repo(repo_path))


@mcp.tool()
def git_log(repo_path: str | None = None, count: int = 20) -> dict:
    """Recent commit history as an ASCII graph (oneline, all branches).
    Use to understand how branches diverged or what was committed
    recently. Read-only and safe."""
    return git_context.log(_repo(repo_path), count)


@mcp.tool()
def git_diff(
    repo_path: str | None = None,
    staged: bool = False,
    path: str | None = None,
) -> dict:
    """The actual code changes. `staged=False` shows working-tree changes;
    `staged=True` shows what is staged for commit. Use this before writing
    a commit message so the message reflects real changes. Read-only."""
    return git_context.diff(_repo(repo_path), staged=staged, path=path)


@mcp.tool()
def git_branches(repo_path: str | None = None) -> dict:
    """All local branches with upstream tracking and whether each is
    merged into the current HEAD. Use to advise what is safe to delete
    or how branches relate. Read-only and safe."""
    return git_context.branches(_repo(repo_path))


@mcp.tool()
def git_reflog(repo_path: str | None = None, count: int = 30) -> dict:
    """Recent HEAD movements (reflog). This is the key to RESCUING work
    that seems lost after a bad reset/rebase/checkout — the old commit is
    almost always still here. Read-only and safe."""
    return git_context.reflog(_repo(repo_path), count)


@mcp.tool()
def git_repo_overview(repo_path: str | None = None) -> dict:
    """One composite snapshot — status, branches, recent commits, remotes,
    stash count — in a single call. Prefer this for onboarding / "explain
    this repo" requests and to stay token-efficient. Read-only and safe."""
    return git_context.repo_overview(_repo(repo_path))


@mcp.tool()
def git_timeline(repo_path: str | None = None) -> dict:
    """A live visual of THIS repo's commit timeline as a Mermaid
    `gitGraph` (Bob's chat renders it natively). Branches show as lanes
    splitting off; merges show them converging back. The diagram uses
    GitBob's branded styling — a yellow trunk lane and a corporate
    palette — so the trunk is instantly recognisable; present it as-is.

    Call this after any branch / commit / merge / reset, and whenever the
    user asks to "show / visualize the timeline". Then SHOW it: include
    the `mermaid` block from the result **verbatim** in your reply and
    narrate the change as an alternate timeline splitting or converging.
    Read-only and safe."""
    diagram = gitgraph.to_mermaid(_repo(repo_path))
    if not diagram:
        return {"available": False,
                "message": "No timeline could be rendered for this repo."}
    return {
        "available": True,
        "mermaid": diagram,
        "instructions": (
            "Show the user the timeline: include the entire `mermaid` "
            "block above verbatim in your reply, then narrate what "
            "changed (a branch splitting off as an alternate timeline, "
            "or branches converging on a merge)."
        ),
    }


@mcp.tool()
def git_explain_risk(
    commands: list[str], repo_path: str | None = None
) -> dict:
    """Assess the RISK of a git plan BEFORE running it, with a
    colour-coded consequence diagram Bob's chat renders natively.

    Call this whenever you are about to propose a `git_run`, or when the
    user asks "is this safe?" / "what would <command> do?". Returns the
    risk level (🟦 safe / 🟧 history-rewrite / 🟥 destructive), a
    per-command breakdown, reversibility, whether it affects other
    people, and a `mermaid` flowchart of the consequence (e.g. for a
    force-push, which commits get orphaned). SHOW the user this: state
    the level and include the `mermaid` block verbatim if present, then
    explain the consequence in plain language. Read-only and safe."""
    return danger.risk_card(commands, _repo(repo_path))


@mcp.tool()
def git_run(
    commands: list[str],
    confirm_token: str | None = None,
    repo_path: str | None = None,
) -> dict:
    """Execute an ordered list of git commands (e.g.
    ["git add -A", "git commit -m \\"feat: ...\\""]). Stops on first error.

    Workflow you MUST follow:
      1. First gather context with the read tools.
      2. Propose the exact commands and a plain-English explanation + risk
         to the user, and wait for their approval.
      3. Call git_run with the commands.
      4. If the result status is `confirmation_required`, the plan is
         DESTRUCTIVE. Show the user each command and its risk, get an
         EXPLICIT yes, then call git_run again with the same commands and
         the returned `confirm_token`.
      5. If a command fails, read its output, explain the cause, and
         propose a recovery plan — do not silently retry.
      6. On success, if the result includes a `timeline`, SHOW it:
         include that `mermaid` block verbatim in your reply and narrate
         the timeline change.

    Only plain `git ...` commands are allowed (no shell, pipes, chaining)."""
    repo = _repo(repo_path)
    result = git_exec.run(commands, confirm_token, repo)
    # Best-effort: attach an updated timeline after a real execution so
    # Bob can show the before/after. Never let this break git_run.
    if isinstance(result, dict) and result.get("status") in (
        "completed", "failed",
    ):
        try:
            diagram = gitgraph.to_mermaid(repo)
            if diagram:
                result["timeline"] = diagram
        except Exception:
            pass
    return result


def serve() -> None:
    """Run the server over stdio (how Bob launches it)."""
    mcp.run()


if __name__ == "__main__":
    serve()
