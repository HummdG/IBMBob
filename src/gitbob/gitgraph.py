"""Render the *real* repository topology as a Mermaid ``gitGraph``.

Bob's chat webview bundles Mermaid (incl. the ``gitGraph`` diagram type),
so returning a fenced ```mermaid block makes Bob draw a live git timeline
inside the chat — the branch "splits" and merges "converge" visually.

This is deliberately best-effort: Mermaid's ``gitGraph`` is opinionated
and cannot express every DAG. We render the common shapes well (linear
trunk + feature branches + merges, and the post-reset "commit moved to a
branch" shape) and degrade gracefully. **Any failure returns ``""`` so
callers never break git.**
"""

from __future__ import annotations

from .gitproc import is_git_repo, run_git

_US = "\x1f"  # unit separator (safe inside commit subjects)


class _Inconsistent(Exception):
    """Raised by the strict builder to trigger the simple fallback."""


# Branded "corporate Memphis" palette for the git timeline. Pure data —
# tweak hex values here; nothing else changes. ``git0`` is the trunk lane
# (signature yellow); ``git1..`` are feature lanes.
_PALETTE: dict[str, str] = {
    "git0": "#F5C518",          # trunk lane — signature yellow
    "git1": "#1F2A44",          # ink navy
    "git2": "#3D7DCA",          # corporate blue
    "git3": "#E8833A",          # warm orange accent
    "git4": "#5B8C5A",          # muted green
    "git5": "#8E6FB6",          # muted violet
    "git6": "#C1573E",          # brick
    "git7": "#4C4C4C",          # graphite
    "gitBranchLabel0": "#1F2A44",
    "gitBranchLabel1": "#FFFFFF",
    "gitBranchLabel2": "#FFFFFF",
    "gitBranchLabel3": "#FFFFFF",
    "gitBranchLabel4": "#FFFFFF",
    "gitBranchLabel5": "#FFFFFF",
    "gitBranchLabel6": "#FFFFFF",
    "gitBranchLabel7": "#FFFFFF",
    "commitLabelColor": "#1F2A44",
    "commitLabelBackground": "#FFF8E1",
    "commitLabelFontSize": "12px",
    "tagLabelColor": "#1F2A44",
    "tagLabelBackground": "#F5C518",
    "tagLabelBorder": "#1F2A44",
}


def _init_directive(trunk: str) -> str:
    """ONE valid single-line Mermaid ``%%{init: {...}}%%`` directive that
    themes the gitGraph (yellow trunk + branded palette) and, only when the
    trunk is not Mermaid's default ``main``, renames the main branch.

    Pure string assembly: no I/O, no imports, cannot raise on normal input.
    Rendered client-side by Mermaid in Bob's webview, so it can never affect
    the MCP server process.
    """
    vars_body = ",".join(f"'{k}':'{v}'" for k, v in _PALETTE.items())
    git_opts = "'showCommitLabel': true, 'rotateCommitLabel': true"
    if trunk != "main":
        safe_trunk = trunk.replace("'", "")   # single-quote guard
        git_opts += f", 'mainBranchName': '{safe_trunk}'"
    # Literal braces live only in plain "..." fragments (NOT f-strings), so
    # no brace-doubling is needed (avoids the old ``}}}}`` escaping trap).
    return (
        "%%{init: {'theme':'base','themeVariables': {"
        + vars_body
        + "}, 'gitGraph': {"
        + git_opts
        + "}}}%%"
    )


def _git(args: list[str], repo: str | None) -> str:
    res = run_git(args, repo, timeout=20)
    if not res.ok:
        raise _Inconsistent(f"git {' '.join(args)} failed: {res.stderr[:120]}")
    return res.stdout


def _trunk(repo: str | None) -> str:
    for name in ("main", "master"):
        if run_git(["show-ref", "--verify", "--quiet",
                    f"refs/heads/{name}"], repo).ok:
            return name
    cur = run_git(["branch", "--show-current"], repo).stdout.strip()
    if cur:
        return cur
    first = run_git(["for-each-ref", "--format", "%(refname:short)",
                     "refs/heads"], repo).stdout.splitlines()
    if not first:
        raise _Inconsistent("no branches")
    return first[0].strip()


def _sanitize_branch(name: str, used: dict[str, str]) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in name).strip("_")
    if not safe or not safe[0].isalpha():
        safe = f"b_{safe}"
    base, i = safe, 2
    while safe in used and used[safe] != name:
        safe, i = f"{base}_{i}", i + 1
    used[safe] = name
    return safe


def _label(short: str, subject: str) -> str:
    clean = "".join(
        c for c in subject if c.isalnum() or c in " ._-"
    ).strip()
    clean = " ".join(clean.split())[:22]
    return f'{short} {clean}'.strip()


def _build_strict(repo: str | None, max_commits: int) -> str:
    trunk = _trunk(repo)
    trunk_line = _git(
        ["rev-list", "--first-parent", "--reverse", trunk], repo
    ).split()
    if not trunk_line:
        raise _Inconsistent("empty trunk")

    # hash -> (parents, subject)
    meta: dict[str, tuple[list[str], str]] = {}
    for row in _git(["log", "--all", f"--pretty=tformat:%H{_US}%P{_US}%s"],
                     repo).split("\n"):
        if not row.strip():
            continue
        h, parents, subject = row.split(_US, 2)
        meta[h] = (parents.split(), subject)

    head = run_git(["rev-parse", "HEAD"], repo).stdout.strip()

    branches = [
        b.strip() for b in
        _git(["for-each-ref", "--format", "%(refname:short)",
              "refs/heads"], repo).splitlines()
        if b.strip() and b.strip() != trunk
    ]

    window = trunk_line[-max_commits:]
    win_set = set(window)
    win_idx = {h: i for i, h in enumerate(window)}
    used: dict[str, str] = {}

    opens: dict[str, list[dict]] = {}   # anchor trunk hash -> [descriptors]
    merge_at: dict[str, str] = {}       # trunk merge hash -> sanitized name

    for real in branches:
        tip = run_git(["rev-parse", real], repo).stdout.strip()
        if not tip:
            continue
        merged = run_git(
            ["merge-base", "--is-ancestor", tip, trunk], repo).ok

        if merged:
            # Reconstruct from the trunk merge commit whose 2nd parent is
            # this branch's tip (the common --no-ff case).
            m = next((th for th in window
                      if len(meta.get(th, ([], ""))[0]) >= 2
                      and meta[th][0][1] == tip), None)
            if m is None:
                continue
            p1, p2 = meta[m][0][0], meta[m][0][1]
            bp = run_git(["merge-base", p1, p2], repo).stdout.strip()
            lane = _git(["rev-list", "--reverse", p2, "--not", bp],
                        repo).split()
        else:
            bp = run_git(["merge-base", trunk, real], repo).stdout.strip()
            lane = _git(["rev-list", "--reverse", tip, "--not", bp],
                        repo).split()
            m = None

        if not lane:
            continue
        anchor = bp if bp in win_set else window[0]
        san = _sanitize_branch(real, used)
        # A merge can only be drawn if the branch is opened before it.
        if m is not None and win_idx.get(anchor, 0) < win_idx.get(m, -1):
            merge_at[m] = san
        opens.setdefault(anchor, []).append(
            {"san": san, "real": real, "lane": lane})

    out: list[str] = []
    out.append(_init_directive(trunk))
    out.append("gitGraph")

    def emit_commit(h: str, on_lane: bool = False) -> None:
        short = h[:7]
        subj = meta.get(h, ([], ""))[1]
        extra = " type: HIGHLIGHT" if h == head else ""
        out.append(f'   commit id: "{_label(short, subj)}"{extra}')

    for th in window:
        if th in merge_at:
            hi = " type: HIGHLIGHT" if th == head else ""
            out.append(f"   merge {merge_at[th]}{hi}")
        else:
            emit_commit(th)
        for desc in opens.get(th, []):
            out.append(f"   branch {desc['san']}")
            out.append(f"   checkout {desc['san']}")
            for c in desc["lane"]:
                emit_commit(c, on_lane=True)
            out.append(f"   checkout {trunk}")

    if len(out) <= 2:
        raise _Inconsistent("nothing rendered")
    return "```mermaid\n" + "\n".join(out) + "\n```"


def _build_simple(repo: str | None, max_commits: int) -> str:
    """Fallback: trunk line + each other branch as a split lane (no
    merge reconstruction). Still shows branches splitting off."""
    trunk = _trunk(repo)
    trunk_line = _git(
        ["rev-list", "--first-parent", "--reverse", trunk], repo
    ).split()[-max_commits:]
    if not trunk_line:
        raise _Inconsistent("empty trunk")
    subjects = {}
    for row in _git(["log", "--all", f"--pretty=tformat:%H{_US}%s"],
                     repo).split("\n"):
        if row.strip():
            h, s = row.split(_US, 1)
            subjects[h] = s

    out = []
    out.append(_init_directive(trunk))
    out.append("gitGraph")
    for h in trunk_line:
        out.append(f'   commit id: "{_label(h[:7], subjects.get(h, ""))}"')

    used: dict[str, str] = {}
    for b in _git(["for-each-ref", "--format", "%(refname:short)",
                   "refs/heads"], repo).splitlines():
        b = b.strip()
        if not b or b == trunk:
            continue
        tip = run_git(["rev-parse", b], repo).stdout.strip()
        bp = run_git(["merge-base", trunk, b], repo).stdout.strip()
        lane = run_git(["rev-list", "--reverse", tip, "--not", bp],
                       repo).stdout.split()
        if not lane:
            continue
        san = _sanitize_branch(b, used)
        out.append(f"   branch {san}")
        out.append(f"   checkout {san}")
        for c in lane[: max_commits]:
            out.append(f'   commit id: "{_label(c[:7], subjects.get(c, ""))}"')
        out.append(f"   checkout {trunk}")
    return "```mermaid\n" + "\n".join(out) + "\n```"


def to_mermaid(repo_path: str | None = None, max_commits: int = 25) -> str:
    """Real repo topology as a fenced Mermaid ``gitGraph`` block.

    Returns ``""`` for a non-repo or on ANY internal failure — callers
    must treat an empty string as "no diagram available".
    """
    try:
        if not is_git_repo(repo_path):
            return ""
        max_commits = max(3, min(max_commits, 60))
        try:
            return _build_strict(repo_path, max_commits)
        except _Inconsistent:
            return _build_simple(repo_path, max_commits)
    except Exception:
        return ""
