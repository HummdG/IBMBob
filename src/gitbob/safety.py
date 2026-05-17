"""Command safety policy.

GitBob never blocks git outright — Bob legitimately needs `reset --hard`
for rescue work. Instead it *classifies* commands so dangerous ones are
forced through an explicit, human-confirmed gate (see git_exec.py).

Two layers of defence:
  1. The command must actually be `git` (no shell injection / arbitrary exec).
  2. Destructive subcommands are flagged "dangerous" and require a token
     that is only issued after a human says yes.

Three risk tiers (used for the colour-coded danger visuals):
  * safe      (blue)   — read-only or additive; no data loss.
  * caution   (orange) — rewrites/moves history; recoverable via reflog,
                          but anyone who already has the commits diverges.
  * dangerous (red)    — destroys work or rewrites *shared* history;
                          the confirm-token gate applies to this tier.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

# Substrings that would let a single "command" smuggle in a second one.
# We never use a shell, but reject these anyway as defence-in-depth.
_SHELL_METACHARS = (";", "|", "&", "`", "$(", ">", "<", "\n", "\r")

LEVEL_SAFE = "safe"
LEVEL_CAUTION = "caution"
LEVEL_DANGEROUS = "dangerous"

# Severity order, lowest → highest. Used to take the worst tier of a plan.
_ORDER = {LEVEL_SAFE: 0, LEVEL_CAUTION: 1, LEVEL_DANGEROUS: 2}

# DANGEROUS (red): destroys work or rewrites *shared* history. Checked
# first, so e.g. `reset --hard` lands here, not in the caution `reset`.
# (regex over the normalized command, human reason). Order = priority.
_DANGEROUS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\breset\s+.*--hard\b"),
     "discards uncommitted work and moves HEAD"),
    (re.compile(r"\bpush\b.*(--force\b|--force-with-lease\b|\s-f\b)"),
     "force-pushes — can overwrite remote history for everyone"),
    (re.compile(r"\bpush\b.*(--delete\b|\s:\S)"), "deletes a remote branch"),
    (re.compile(r"\bbranch\b.*\s-D\b"),
     "force-deletes a branch even if unmerged — commits may be lost"),
    (re.compile(r"\bclean\b.*-[a-z]*[dfx]"),
     "permanently deletes untracked files"),
    (re.compile(r"\bcheckout\s+(--\s+\.|--\s+\S|\.\s*$)"),
     "discards changes in working files"),
    (re.compile(r"\brestore\b(?!.*--staged\b.*--source)"),
     "discards changes in working files"),
    (re.compile(r"\bswitch\b.*--discard-changes\b"),
     "discards working changes"),
    (re.compile(r"\breflog\s+(delete|expire)\b"),
     "deletes reflog entries — undo history becomes unrecoverable"),
    (re.compile(r"\bgc\b.*--prune"),
     "prunes unreachable objects — lost work becomes unrecoverable"),
    (re.compile(r"\bfilter-(branch|repo)\b"),
     "rewrites entire repository history"),
    (re.compile(r"\bupdate-ref\s+-d\b"), "deletes a ref directly"),
    (re.compile(r"\bstash\s+(drop|clear)\b"),
     "permanently drops stashed work"),
    (re.compile(r"\bworktree\s+remove\b.*--force\b"),
     "force-removes a worktree"),
    (re.compile(r"\brm\b.*\s-f"), "force-removes tracked files"),
]

# CAUTION (orange): rewrites/moves history but recoverable via reflog,
# or a local ref deletion. Anyone who already has the commits diverges.
_CAUTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brebase\b"),
     "rewrites commit history — recoverable via reflog, but anyone who "
     "already has these commits will diverge"),
    (re.compile(r"\bcommit\b.*--amend\b"),
     "rewrites the last commit — its hash changes, so collaborators who "
     "have it will diverge"),
    (re.compile(r"\bcherry-pick\b"),
     "replays a commit here — can cause conflicts or duplicate history"),
    (re.compile(r"\bbranch\b.*\s-d\b(?!.*-D)"),
     "deletes a branch (git refuses unless it is merged)"),
    (re.compile(r"\btag\s+-d\b"), "deletes a local tag"),
    (re.compile(r"\breset\b(?!.*--soft)"),
     "moves HEAD and unstages changes — your edits stay in the working "
     "tree and the old position is recoverable via reflog"),
    (re.compile(r"\breset\s+--soft\b"),
     "moves HEAD only — staged changes and working tree are kept"),
]


@dataclass
class Classification:
    """Result of inspecting one proposed command string."""

    raw: str
    is_git: bool
    level: str  # LEVEL_SAFE | LEVEL_CAUTION | LEVEL_DANGEROUS
    reason: str  # why it's risky / why it was rejected ("" if safe git)

    @property
    def rejected(self) -> bool:
        """True when the command isn't a runnable git command at all."""
        return not self.is_git


def classify(command: str) -> Classification:
    """Classify a single command string.

    Rejected (is_git=False) if it isn't a plain `git ...` invocation or
    contains shell metacharacters. Otherwise SAFE, CAUTION, or DANGEROUS
    with a plain-English reason. Dangerous patterns win over caution.
    """
    cmd = command.strip()
    if not cmd:
        return Classification(command, False, LEVEL_SAFE, "empty command")

    if any(mc in cmd for mc in _SHELL_METACHARS):
        return Classification(
            command, False, LEVEL_SAFE,
            "contains shell metacharacters; only a single plain git command "
            "is allowed (no pipes, redirection, or chaining)",
        )

    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError as exc:
        return Classification(command, False, LEVEL_SAFE, f"unparseable: {exc}")

    if not tokens or tokens[0] != "git":
        return Classification(
            command, False, LEVEL_SAFE,
            "not a git command — GitBob only runs `git ...`",
        )

    normalized = " ".join(tokens)
    for pattern, reason in _DANGEROUS_PATTERNS:
        if pattern.search(normalized):
            return Classification(command, True, LEVEL_DANGEROUS, reason)
    for pattern, reason in _CAUTION_PATTERNS:
        if pattern.search(normalized):
            return Classification(command, True, LEVEL_CAUTION, reason)

    return Classification(command, True, LEVEL_SAFE, "")


def classify_all(commands: list[str]) -> list[Classification]:
    """Classify each command in an ordered plan."""
    return [classify(c) for c in commands]


def overall_level(classifications: list[Classification]) -> str:
    """The worst (highest) tier across a plan. Empty → safe."""
    return max(
        (c.level for c in classifications),
        key=lambda lvl: _ORDER.get(lvl, 0),
        default=LEVEL_SAFE,
    )
