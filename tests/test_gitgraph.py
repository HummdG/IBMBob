import subprocess
from pathlib import Path

import pytest

from gitbob import gitgraph
from gitbob.gitproc import GitResult


def _g(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True,
                    capture_output=True, text=True)


@pytest.fixture
def rich_repo(tmp_path: Path) -> Path:
    """main with history, a MERGED feature/login, an UNMERGED
    feature/payments, and a branch created at a commit that main then
    reset away (the C1 'commit moved to a branch' shape)."""
    r = tmp_path / "rich"
    r.mkdir()
    _g(r, "init", "-q", "-b", "main")
    _g(r, "config", "user.email", "t@e.com")
    _g(r, "config", "user.name", "T")
    (r / "a.txt").write_text("1\n")
    _g(r, "add", "-A")
    _g(r, "commit", "-qm", "chore: init")
    (r / "b.txt").write_text("2\n")
    _g(r, "add", "-A")
    _g(r, "commit", "-qm", "feat: b")

    _g(r, "checkout", "-q", "-b", "feature/login")
    (r / "login.txt").write_text("login\n")
    _g(r, "add", "-A")
    _g(r, "commit", "-qm", "feat: add login")
    _g(r, "checkout", "-q", "main")
    _g(r, "merge", "-q", "--no-ff", "feature/login", "-m",
       "merge: feature/login")

    _g(r, "checkout", "-q", "-b", "feature/payments")
    (r / "pay.txt").write_text("pay\n")
    _g(r, "add", "-A")
    _g(r, "commit", "-qm", "feat: payments")

    # Accidental commit on main, then branch it off and reset main.
    _g(r, "checkout", "-q", "main")
    (r / "oops.txt").write_text("oops\n")
    _g(r, "add", "-A")
    _g(r, "commit", "-qm", "feat: accidental")
    _g(r, "branch", "feature/logging")
    _g(r, "reset", "-q", "--hard", "HEAD~1")
    return r


def test_returns_fenced_mermaid_gitgraph(rich_repo: Path):
    out = gitgraph.to_mermaid(str(rich_repo))
    assert out.startswith("```mermaid\n")
    assert out.rstrip().endswith("```")
    assert "gitGraph" in out


def test_branches_and_merge_present(rich_repo: Path):
    out = gitgraph.to_mermaid(str(rich_repo))
    # branch names are sanitized: feature/login -> feature_login
    assert "feature_login" in out
    assert "feature_payments" in out
    assert "feature/login" not in out          # raw slash never emitted
    assert "branch feature_payments" in out
    assert "merge feature_login" in out        # merged branch converges


def test_reset_commit_now_lives_on_branch(rich_repo: Path):
    out = gitgraph.to_mermaid(str(rich_repo))
    # The accidental commit was reset off main but kept on feature/logging
    assert "feature_logging" in out
    assert "branch feature_logging" in out


def test_head_highlighted(rich_repo: Path):
    out = gitgraph.to_mermaid(str(rich_repo))
    assert "type: HIGHLIGHT" in out


def test_non_repo_returns_empty(empty_dir: Path):
    assert gitgraph.to_mermaid(str(empty_dir)) == ""


def test_failure_returns_empty_not_exception(rich_repo: Path, monkeypatch):
    def boom(*_a, **_k):
        return GitResult(False, 1, "", "forced failure", [])

    monkeypatch.setattr(gitgraph, "run_git", boom)
    # is_git_repo also uses run_git via the real module; force True so we
    # exercise the builders failing internally.
    monkeypatch.setattr(gitgraph, "is_git_repo", lambda *_a, **_k: True)
    assert gitgraph.to_mermaid(str(rich_repo)) == ""


def test_respects_commit_cap(rich_repo: Path):
    out = gitgraph.to_mermaid(str(rich_repo), max_commits=3)
    assert "gitGraph" in out  # still valid, just windowed


# --- Branded "corporate Memphis" timeline styling -------------------------
#
# The timeline is themed via a single pure-string Mermaid `%%{init: ...}%%`
# directive (rendered client-side in Bob's webview). These tests pin the
# directive's presence, shape and palette, and prove BOTH the strict and the
# simple builder carry it, without disturbing the existing topology contract.


@pytest.fixture
def renamed_trunk_repo(tmp_path: Path) -> Path:
    """A repo whose trunk is `develop` (not Mermaid's default `main`) —
    exercises the `mainBranchName` arm of the init directive."""
    r = tmp_path / "dev"
    r.mkdir()
    _g(r, "init", "-q", "-b", "develop")
    _g(r, "config", "user.email", "t@e.com")
    _g(r, "config", "user.name", "T")
    (r / "a.txt").write_text("1\n")
    _g(r, "add", "-A")
    _g(r, "commit", "-qm", "chore: init")
    (r / "b.txt").write_text("2\n")
    _g(r, "add", "-A")
    _g(r, "commit", "-qm", "feat: b")
    return r


def test_init_directive_present_and_wellformed(rich_repo: Path):
    out = gitgraph.to_mermaid(str(rich_repo))
    assert out.startswith("```mermaid\n")
    assert out.rstrip().endswith("```")
    assert "gitGraph" in out
    assert out.count("%%{init:") == 1          # exactly one directive
    line = out.split("\n")[1]                   # 0 = ```mermaid, 1 = directive
    assert line.startswith("%%{init:")
    assert line.endswith("}%%")
    assert line.count("{") == line.count("}")   # balanced braces, one line


def test_init_directive_has_theme_and_yellow_trunk(rich_repo: Path):
    out = gitgraph.to_mermaid(str(rich_repo))
    assert "'theme':'base'" in out
    assert "themeVariables" in out
    assert "'git0':'#F5C518'" in out            # trunk lane = signature yellow
    assert "rotateCommitLabel" in out


def test_init_directive_main_trunk_omits_mainbranchname(rich_repo: Path):
    out = gitgraph.to_mermaid(str(rich_repo))
    assert "%%{init:" in out                    # directive IS emitted...
    assert "'theme':'base'" in out
    assert "mainBranchName" not in out          # ...but not for default main


def test_init_directive_renamed_trunk_sets_mainbranchname(
    renamed_trunk_repo: Path,
):
    out = gitgraph.to_mermaid(str(renamed_trunk_repo))
    assert "%%{init:" in out
    assert "'mainBranchName': 'develop'" in out
    assert "'theme':'base'" in out              # theming still applied
    assert "'git0':'#F5C518'" in out


def test_init_directive_present_in_simple_fallback(
    rich_repo: Path, monkeypatch
):
    def boom(*_a, **_k):
        raise gitgraph._Inconsistent("forced strict failure")

    monkeypatch.setattr(gitgraph, "_build_strict", boom)
    out = gitgraph.to_mermaid(str(rich_repo))
    assert out.startswith("```mermaid\n")
    assert "%%{init:" in out
    assert "'theme':'base'" in out
    assert "gitGraph" in out
