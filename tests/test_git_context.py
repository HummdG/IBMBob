from pathlib import Path

from gitbob import git_context


def test_status_reports_branch_and_dirty(git_repo: Path):
    st = git_context.status(str(git_repo))
    assert st["branch"] == "main"
    assert st["untracked_count"] == 1  # app.py
    assert st["clean"] is False


def test_log_has_initial_commit(git_repo: Path):
    out = git_context.log(str(git_repo))
    assert "initial commit" in out["graph"]


def test_diff_detects_changes(git_repo: Path):
    # app.py is untracked; stage it so it appears in a staged diff.
    from gitbob.gitproc import run_git

    run_git(["add", "app.py"], str(git_repo))
    d = git_context.diff(str(git_repo), staged=True)
    assert d["empty"] is False
    assert "app.py" in d["stat"]


def test_branches_lists_main(git_repo: Path):
    b = git_context.branches(str(git_repo))
    assert b["current"] == "main"
    assert any(x["name"] == "main" for x in b["branches"])


def test_repo_overview_composite(git_repo: Path):
    ov = git_context.repo_overview(str(git_repo))
    assert ov["status"]["branch"] == "main"
    assert "initial commit" in ov["recent_commits"]
    assert ov["stash_count"] == 0


def test_not_a_git_repo(empty_dir: Path):
    assert git_context.status(str(empty_dir))["error"] == "not_a_git_repo"
    assert git_context.repo_overview(str(empty_dir))["error"] == "not_a_git_repo"
