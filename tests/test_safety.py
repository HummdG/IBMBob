from gitbob.safety import (
    LEVEL_CAUTION,
    LEVEL_DANGEROUS,
    LEVEL_SAFE,
    classify,
    classify_all,
    overall_level,
)


def test_safe_commands():
    for cmd in ("git status", "git log --oneline", "git diff", "git add -A",
                "git commit -m 'feat: x'", "git checkout -b feature/new",
                "git fetch origin", "git stash push -m wip"):
        c = classify(cmd)
        assert c.is_git and c.level == LEVEL_SAFE, (cmd, c)


def test_dangerous_tier():
    cases = {
        "git reset --hard origin/main": "discards",
        "git push --force origin main": "force",
        "git push -f": "force",
        "git push origin --delete old": "remote branch",
        "git clean -fd": "untracked",
        "git branch -D feature/x": "force-delete",
        "git stash drop": "stashed",
        "git reflog expire --all": "reflog",
        "git gc --prune=now": "unrecoverable",
        "git filter-branch --tree-filter x HEAD": "entire repository",
    }
    for cmd, needle in cases.items():
        c = classify(cmd)
        assert c.is_git and c.level == LEVEL_DANGEROUS, (cmd, c)
        assert needle in c.reason.lower(), (cmd, c.reason)


def test_caution_tier_history_rewrite():
    cases = {
        "git rebase -i HEAD~3": "rewrites",
        "git commit --amend -m x": "last commit",
        "git reset HEAD~1": "moves head",
        "git reset --soft HEAD~1": "moves head only",
        "git cherry-pick abc123": "replays",
        "git branch -d merged-branch": "merged",
        "git tag -d v1.0": "local tag",
    }
    for cmd, needle in cases.items():
        c = classify(cmd)
        assert c.is_git and c.level == LEVEL_CAUTION, (cmd, c)
        assert needle in c.reason.lower(), (cmd, c.reason)


def test_hard_reset_beats_caution_reset():
    # `reset --hard` must be dangerous, not caught by the caution `reset`.
    assert classify("git reset --hard HEAD").level == LEVEL_DANGEROUS
    assert classify("git reset HEAD").level == LEVEL_CAUTION


def test_overall_level_is_worst_tier():
    assert overall_level(classify_all(["git status", "git log"])) == LEVEL_SAFE
    assert overall_level(
        classify_all(["git status", "git rebase main"])) == LEVEL_CAUTION
    assert overall_level(
        classify_all(["git add -A", "git rebase main",
                      "git push --force"])) == LEVEL_DANGEROUS
    assert overall_level([]) == LEVEL_SAFE


def test_non_git_rejected():
    for cmd in ("rm -rf /", "ls -la", "echo hi", "python evil.py", ""):
        c = classify(cmd)
        assert not c.is_git and c.rejected, (cmd, c)


def test_shell_injection_rejected():
    for cmd in ("git status; rm -rf /", "git log | sh", "git status && curl x",
                "git show > /etc/passwd", "git log `whoami`"):
        c = classify(cmd)
        assert not c.is_git, (cmd, c)
        assert "metacharacter" in c.reason
