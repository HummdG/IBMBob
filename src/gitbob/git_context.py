"""Read-only git introspection.

These functions feed Bob the *real* state of the repository so it reasons
about the user's actual situation, not a guess. Outputs are compact on
purpose (Bobcoins are finite); large blobs are truncated.
"""

from __future__ import annotations

from .gitproc import is_git_repo, run_git, truncate

_NOT_A_REPO = {"error": "not_a_git_repo",
               "message": "This directory is not inside a git repository."}


def _guard(repo_path: str | None) -> dict | None:
    return None if is_git_repo(repo_path) else dict(_NOT_A_REPO)


def status(repo_path: str | None = None) -> dict:
    """Working-tree status: branch, upstream, ahead/behind, staged/unstaged."""
    if (g := _guard(repo_path)) is not None:
        return g
    branch = run_git(["branch", "--show-current"], repo_path).stdout.strip()
    porcelain = run_git(["status", "--porcelain=v1", "--branch"], repo_path).stdout
    ahead = behind = 0
    for line in porcelain.splitlines():
        if line.startswith("##") and "[" in line:
            seg = line[line.index("[") + 1 : line.index("]")]
            for part in seg.split(","):
                part = part.strip()
                if part.startswith("ahead "):
                    ahead = int(part.split()[1])
                elif part.startswith("behind "):
                    behind = int(part.split()[1])
    entries = [ln for ln in porcelain.splitlines() if not ln.startswith("##")]
    staged = [e for e in entries if e[:1] not in (" ", "?")]
    unstaged = [e for e in entries if e[1:2] not in (" ",) and e[:1] != "?"]
    untracked = [e for e in entries if e.startswith("??")]
    return {
        "branch": branch or "(detached HEAD)",
        "ahead": ahead,
        "behind": behind,
        "staged_count": len(staged),
        "unstaged_count": len(unstaged),
        "untracked_count": len(untracked),
        "clean": not entries,
        "porcelain": truncate(porcelain, 4000),
    }


def log(repo_path: str | None = None, count: int = 20) -> dict:
    """Recent commit history as a graph (oneline)."""
    if (g := _guard(repo_path)) is not None:
        return g
    count = max(1, min(count, 100))
    res = run_git(
        ["log", f"-{count}", "--graph", "--oneline", "--decorate", "--all"],
        repo_path,
    )
    return {"count": count, "graph": truncate(res.output, 6000)}


def diff(
    repo_path: str | None = None,
    staged: bool = False,
    path: str | None = None,
    max_chars: int = 8000,
) -> dict:
    """Diff of working changes (or staged changes if `staged=True`)."""
    if (g := _guard(repo_path)) is not None:
        return g
    args = ["diff"]
    if staged:
        args.append("--staged")
    if path:
        args += ["--", path]
    stat = run_git(["diff", *(["--staged"] if staged else []), "--stat"], repo_path)
    body = run_git(args, repo_path)
    return {
        "staged": staged,
        "stat": truncate(stat.stdout, 2000),
        "patch": truncate(body.stdout, max_chars),
        "empty": not body.stdout.strip(),
    }


def branches(repo_path: str | None = None) -> dict:
    """Local branches with upstream tracking and merged-into-HEAD status."""
    if (g := _guard(repo_path)) is not None:
        return g
    fmt = "%(refname:short)%09%(upstream:short)%09%(upstream:track)"
    res = run_git(["for-each-ref", "--format", fmt, "refs/heads"], repo_path)
    merged = {
        b.strip().lstrip("* ").strip()
        for b in run_git(["branch", "--merged"], repo_path).stdout.splitlines()
    }
    current = run_git(["branch", "--show-current"], repo_path).stdout.strip()
    out = []
    for line in res.stdout.splitlines():
        name, _, rest = line.partition("\t")
        upstream, _, track = rest.partition("\t")
        out.append({
            "name": name,
            "upstream": upstream or None,
            "track": track.strip("[]") or "up to date" if upstream else None,
            "merged_into_head": name in merged,
            "current": name == current,
        })
    return {"current": current, "branches": out}


def reflog(repo_path: str | None = None, count: int = 30) -> dict:
    """Recent HEAD movements — the key to rescuing 'lost' work."""
    if (g := _guard(repo_path)) is not None:
        return g
    count = max(1, min(count, 100))
    res = run_git(["reflog", f"-{count}", "--date=relative"], repo_path)
    return {"count": count, "reflog": truncate(res.output, 5000)}


def repo_overview(repo_path: str | None = None) -> dict:
    """One composite snapshot: everything Bob should know to onboard fast.

    Prefer this over many small calls — it is the most token-efficient way
    to give Bob situational awareness (great for the onboarding scenario).
    """
    if (g := _guard(repo_path)) is not None:
        return g
    st = status(repo_path)
    remotes = run_git(["remote", "-v"], repo_path).stdout
    stash = run_git(["stash", "list"], repo_path).stdout
    last = run_git(
        ["log", "-5", "--pretty=format:%h %an %ar  %s"], repo_path
    ).output
    return {
        "status": st,
        "branches": branches(repo_path)["branches"],
        "recent_commits": truncate(last, 1500),
        "remotes": truncate(remotes, 600),
        "stash_count": len([s for s in stash.splitlines() if s.strip()]),
    }
