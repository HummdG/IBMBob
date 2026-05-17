from pathlib import Path

from gitbob import git_exec
from gitbob.gitproc import run_git


def test_empty_plan(git_repo: Path):
    assert git_exec.run([], None, str(git_repo))["status"] == "error"


def test_not_a_repo(empty_dir: Path):
    assert git_exec.run(["git status"], None, str(empty_dir))["status"] == "error"


def test_non_git_rejected(git_repo: Path):
    r = git_exec.run(["rm -rf /"], None, str(git_repo))
    assert r["status"] == "rejected"
    assert r["details"][0]["command"] == "rm -rf /"


def test_safe_plan_executes(git_repo: Path):
    r = git_exec.run(["git add -A", "git commit -m 'feat: add app'"],
                      None, str(git_repo))
    assert r["status"] == "completed", r
    assert all(step["ok"] for step in r["executed"])
    assert "feat: add app" in run_git(["log", "-1", "--pretty=%s"],
                                      str(git_repo)).stdout


def test_dangerous_requires_confirmation(git_repo: Path):
    plan = ["git reset --hard HEAD"]
    r = git_exec.run(plan, None, str(git_repo))
    assert r["status"] == "confirmation_required"
    assert r["confirm_token"].startswith("gitbob-")
    assert r["dangerous"][0]["command"] == "git reset --hard HEAD"
    # Enriched with the colour-coded risk card.
    assert r["risk"]["level"] == "dangerous"
    assert r["risk"]["emoji"] == "🟥"


def test_dangerous_runs_with_valid_token(git_repo: Path):
    plan = ["git reset --hard HEAD"]
    token = git_exec.run(plan, None, str(git_repo))["confirm_token"]
    r = git_exec.run(plan, token, str(git_repo))
    assert r["status"] == "completed", r


def test_wrong_token_does_not_execute(git_repo: Path):
    r = git_exec.run(["git reset --hard HEAD"], "gitbob-bogus", str(git_repo))
    assert r["status"] == "confirmation_required"


def test_failure_aborts_and_reports(git_repo: Path):
    r = git_exec.run(["git checkout does-not-exist"], None, str(git_repo))
    assert r["status"] == "failed"
    assert r["aborted_on_error"] is True
