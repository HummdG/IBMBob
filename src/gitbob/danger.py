"""Risk visualization — make the danger of an operation *visible*.

Bob's chat renders Mermaid `flowchart` with real per-node colours
(`classDef`), so we can draw the *consequence* of a risky command:
safe = blue, history-rewrite = orange, destructive = red, and work that
would be orphaned in dashed dark-red.

`risk_card()` is best-effort: building the diagram is wrapped so any
failure just drops `mermaid` (the text fields still explain the risk).
This never blocks git.
"""

from __future__ import annotations

import re

from .gitproc import is_git_repo, run_git
from .safety import (
    LEVEL_CAUTION,
    LEVEL_DANGEROUS,
    LEVEL_SAFE,
    classify_all,
    overall_level,
)

_TIER = {
    LEVEL_SAFE: ("blue", "🟦", "SAFE"),
    LEVEL_CAUTION: ("orange", "🟧", "HISTORY REWRITE"),
    LEVEL_DANGEROUS: ("red", "🟥", "DESTRUCTIVE"),
}

_CLASSDEFS = (
    "classDef safe fill:#1f6feb,stroke:#0b3d91,color:#fff;\n"
    "classDef caution fill:#fb8500,stroke:#a85700,color:#fff;\n"
    "classDef danger fill:#d00000,stroke:#7f0000,color:#fff;\n"
    "classDef ghost fill:#6a040f,stroke:#d00000,color:#fff,"
    "stroke-dasharray:6 4;"
)


def _safe_label(text: str, limit: int = 40) -> str:
    """Mermaid-safe node label: strip parser-hostile chars, and clip on a
    word boundary (never mid-word) so labels read like plain English."""
    clean = re.sub(r'[\"\[\]{}()<>:;|#`\n\r]', " ", text)
    clean = " ".join(clean.split())
    if len(clean) > limit:
        clean = clean[:limit].rsplit(" ", 1)[0].rstrip() + "..."
    return clean or " "


def _humanize(subject: str) -> str:
    """Turn a commit subject into a plain phrase: drop the Conventional
    Commits prefix (`feat:`, `fix(api)!:`) and capitalise."""
    s = re.sub(r"^\s*[a-z]+(\([^)]*\))?!?:\s*", "", subject.strip(),
               flags=re.IGNORECASE)
    s = s.strip() or subject.strip()
    return (s[0].upper() + s[1:]) if s else s


def _is(pat: str, cmds: list[str]) -> bool:
    return any(re.search(pat, c) for c in cmds)


def _affects_others(cmds: list[str]) -> bool:
    return _is(r"\bpush\b.*(--force|--force-with-lease|\s-f\b|--delete|\s:\S)",
               cmds) or _is(r"\bfilter-(branch|repo)\b", cmds)


def _reversible(level: str, cmds: list[str]) -> str:
    if level == LEVEL_SAFE:
        return "Yes — nothing is lost."
    if level == LEVEL_CAUTION:
        return ("Recoverable via the reflog for ~30 days, but anyone who "
                "already pulled these commits keeps the old ones.")
    if _is(r"\breset\s+.*--hard\b", cmds):
        return ("Committed work is recoverable via the reflog (~30 days); "
                "UNCOMMITTED changes are NOT recoverable.")
    if _is(r"\bpush\b.*(--force|--force-with-lease|\s-f\b)", cmds):
        return ("NOT reversible for collaborators — whoever pulled the "
                "overwritten commits now has broken history.")
    return "Likely NOT reversible — this destroys data."


# --- diagram builders -------------------------------------------------

def _commits(repo: str | None, rng: str,
             limit: int = 6) -> list[tuple[str, str]]:
    """(short hash, plain-English subject) for `rng`, oldest -> newest."""
    out = run_git(["log", f"-{limit}", "--pretty=tformat:%h%x1f%s",
                    rng], repo).stdout
    rows: list[tuple[str, str]] = []
    for ln in out.splitlines():
        if "\x1f" in ln:
            h, s = ln.split("\x1f", 1)
            rows.append((h.strip(), _humanize(s)))
    return rows[::-1]


def _force_push_diagram(repo: str | None) -> str:
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"],
                      repo).stdout.strip() or "your branch"
    up = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name",
                  "@{u}"], repo)
    lines = ["flowchart LR"]
    if up.ok and up.stdout.strip():
        upstream = up.stdout.strip()
        orphaned = _commits(repo, f"{branch}..{upstream}")
        rewrite = _commits(repo, f"{upstream}..{branch}")
        shown = orphaned[:5]

        lines.append('  subgraph SERVER["What is on the shared server now"]')
        lines.append('    s0["Shared starting point"]')
        prev = "s0"
        for i, (_h, subj) in enumerate(shown):
            nid = f"t{i}"
            lines.append(
                f'    {nid}["A teammate added - {_safe_label(subj, 32)}"]')
            lines.append(f"    {prev} --> {nid}")
            prev = nid
        if len(orphaned) > len(shown):
            lines.append(
                f'    tmore["plus {len(orphaned) - len(shown)} more"]')
            lines.append(f"    {prev} --> tmore")
        lines.append("  end")

        lines.append('  subgraph AFTER["What everyone gets after your '
                      'force-push"]')
        lines.append('    a0["Shared starting point"]')
        if rewrite:
            prev = "a0"
            ynodes = []
            for i, (_h, subj) in enumerate(rewrite[:5]):
                nid = f"y{i}"
                ynodes.append(nid)
                lines.append(
                    f'    {nid}["Your change - {_safe_label(subj, 32)}"]')
                lines.append(f"    {prev} --> {nid}")
                prev = nid
        else:
            ynodes = ["y0"]
            lines.append('    y0["Only your version - everything on the '
                         'left is gone"]')
            lines.append("    a0 --> y0")
        lines.append("  end")

        n = len(orphaned)
        if n:
            word = "commit" if n == 1 else "commits"
            lines.append(
                f'  LOSS["These {n} {word} are DELETED for everyone '
                'who pulled them - they cannot be recovered"]')
            last = f"t{len(shown) - 1}" if n <= len(shown) else "tmore"
            lines.append(f"  {last} -. deleted .-> LOSS")
            lines.append("  class " + ",".join(
                f"t{i}" for i in range(len(shown))) + " ghost")
            if n > len(shown):
                lines.append("  class tmore ghost")
            lines.append("  class LOSS ghost")
        else:
            lines.append('  OK0["Nothing on the server is deleted"]')
            lines.append("  class OK0 safe")
        lines.append("  class s0,a0 safe")
        lines.append("  class " + ",".join(ynodes) + " danger")
    else:
        lines += [
            '  subgraph SERVER["What is on the shared server (example)"]',
            '    e0["Shared start"] --> e1["A teammate added a fix"] --> '
            'e2["A teammate added a feature"]',
            "  end",
            '  subgraph AFTER["What everyone gets after your force-push"]',
            '    f0["Shared start"] --> f1["Only your version"]',
            "  end",
            '  LOSS["The teammate commits are DELETED for everyone - '
            'they cannot be recovered"]',
            "  e2 -. deleted .-> LOSS",
            '  NOTE["This repo has no shared server here - illustrative '
            'example"]',
            "  class e0,f0 safe",
            "  class f1 danger",
            "  class e1,e2,LOSS ghost",
            "  class NOTE caution",
        ]
    lines.append(_CLASSDEFS)
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def _hard_reset_diagram(repo: str | None, cmds: list[str]) -> str:
    target = "HEAD~1"
    for c in cmds:
        m = re.search(r"reset\s+.*--hard\s+(\S+)", c)
        if m:
            target = m.group(1)
            break
    discarded = _commits(repo, f"{target}..HEAD")
    lines = ["flowchart LR", '  H0["Where you are now"]']
    prev = "H0"
    for i, (_h, subj) in enumerate(discarded or [("", "your latest work")]):
        nid = f"d{i}"
        lines.append(
            f'  {nid}["Thrown away - {_safe_label(subj, 30)}"]')
        lines.append(f"  {prev} --> {nid}")
        prev = nid
    lines.append('  T["Your branch jumps back - those commits are '
                 'discarded"]')
    lines.append(f"  {prev} -. discarded .-> T")
    lines.append('  R["Saved commits are recoverable from the reflog for '
                 'about 30 days. UNSAVED edits are NOT recoverable."]')
    lines.append("  T --> R")
    lines.append("  class H0 safe")
    if discarded:
        lines.append("  class " + ",".join(
            f"d{i}" for i in range(len(discarded))) + " danger")
    lines.append("  class T danger")
    lines.append("  class R caution")
    lines.append(_CLASSDEFS)
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def _rewrite_diagram() -> str:
    return (
        "```mermaid\nflowchart LR\n"
        '  subgraph BEFORE["The history your teammates already have"]\n'
        '    A["Shared start"] --> B["A commit"] --> '
        'C["Another commit"]\n  end\n'
        '  subgraph AFTER["Your rewritten history - new, different '
        'commits"]\n'
        '    A2["Shared start"] --> B2["Rewritten commit"] --> '
        'C2["Rewritten commit"]\n  end\n'
        '  D["Anyone who had the old commits now has a conflicting copy. '
        'Recoverable from the reflog for about 30 days."]\n'
        "  C -. replaced .-> D\n"
        "  class A,A2 safe\n  class B2,C2 caution\n"
        "  class B,C,D caution\n" + _CLASSDEFS + "\n```"
    )


def _generic_diagram(level: str, per_cmd: list[dict]) -> str:
    cls = {"safe": "safe", "caution": "caution", "dangerous": "danger"}
    lines = ["flowchart TD"]
    for i, pc in enumerate(per_cmd):
        nid = f"c{i}"
        lines.append(f'  {nid}["{_safe_label(pc["command"], 34)}"]')
        lines.append(f"  class {nid} {cls.get(pc['level'], 'safe')}")
    lines.append(_CLASSDEFS)
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def _build_mermaid(level: str, cmds: list[str], per_cmd: list[dict],
                    repo: str | None) -> str:
    try:
        if _is(r"\bpush\b.*(--force|--force-with-lease|\s-f\b)", cmds):
            return _force_push_diagram(repo)
        if _is(r"\breset\s+.*--hard\b", cmds):
            return _hard_reset_diagram(repo, cmds)
        if _is(r"\b(rebase|commit\b.*--amend)\b", cmds):
            return _rewrite_diagram()
        if level != LEVEL_SAFE:
            return _generic_diagram(level, per_cmd)
        return ""
    except Exception:
        return ""


# --- public API -------------------------------------------------------

def risk_card(commands: list[str], repo_path: str | None = None) -> dict:
    """Colour-coded risk assessment + a Mermaid consequence diagram.

    Always returns the text fields; `mermaid` may be "" if it could not
    be built (callers must tolerate that). Never raises.
    """
    cls = classify_all(commands)
    rejected = [{"command": c.raw, "reason": c.reason}
                for c in cls if c.rejected]
    runnable = [c for c in cls if not c.rejected]
    level = overall_level(runnable) if runnable else LEVEL_SAFE
    color, emoji, word = _TIER[level]
    per_cmd = [{"command": c.raw, "level": c.level,
                "reason": c.reason or "no data loss"} for c in runnable]

    repo = repo_path
    in_repo = bool(repo) and is_git_repo(repo)
    mermaid = (_build_mermaid(level, [c.raw for c in runnable], per_cmd, repo)
               if in_repo or level != LEVEL_SAFE else "")

    summaries = {
        LEVEL_SAFE: "No data loss — these commands only read or add.",
        LEVEL_CAUTION: ("This rewrites or moves history. It's recoverable "
                        "via the reflog, but anyone who already has these "
                        "commits will diverge."),
        LEVEL_DANGEROUS: ("This can permanently lose work or rewrite "
                          "history that other people depend on."),
    }
    return {
        "level": level,
        "color": color,
        "emoji": emoji,
        "headline": f"{emoji} {word}",
        "summary": summaries[level],
        "per_command": per_cmd,
        "rejected": rejected,
        "reversible": _reversible(level, [c.raw for c in runnable]),
        "affects_others": _affects_others([c.raw for c in runnable]),
        "mermaid": mermaid,
        "instructions": (
            "Show the user this risk assessment: state the "
            f"{word} level, and if `mermaid` is non-empty include that "
            "block verbatim in your reply, then explain the consequence "
            "bluntly in plain language before doing anything."
        ),
    }
