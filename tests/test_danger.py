from pathlib import Path

from gitbob import danger


def test_safe_plan_blue_no_diagram(git_repo: Path):
    card = danger.risk_card(["git status", "git add -A"], str(git_repo))
    assert card["level"] == "safe"
    assert card["emoji"] == "🟦"
    assert card["mermaid"] == ""
    assert card["affects_others"] is False


def test_caution_plan_orange_with_rewrite_diagram(git_repo: Path):
    card = danger.risk_card(["git rebase -i HEAD~3"], str(git_repo))
    assert card["level"] == "caution"
    assert card["emoji"] == "🟧"
    assert "```mermaid" in card["mermaid"]
    assert "flowchart" in card["mermaid"]
    assert "classDef caution" in card["mermaid"]
    assert "reflog" in card["reversible"].lower()


def test_force_push_red_orphan_diagram(git_repo: Path):
    card = danger.risk_card(["git push --force origin main"], str(git_repo))
    assert card["level"] == "dangerous"
    assert card["emoji"] == "🟥"
    assert card["affects_others"] is True
    assert "not reversible" in card["reversible"].lower()
    m = card["mermaid"]
    assert "```mermaid" in m and "flowchart" in m
    assert "ghost" in m            # orphaned commits styled dashed-red
    assert "classDef danger" in m


def test_hard_reset_red_discarded_diagram(git_repo: Path):
    card = danger.risk_card(["git reset --hard HEAD~1"], str(git_repo))
    assert card["level"] == "dangerous"
    m = card["mermaid"]
    assert "```mermaid" in m
    assert "discarded" in m
    assert "reflog" in m.lower()


def test_per_command_breakdown_mixed(git_repo: Path):
    card = danger.risk_card(
        ["git add -A", "git rebase main", "git push --force"],
        str(git_repo))
    levels = {pc["command"]: pc["level"] for pc in card["per_command"]}
    assert levels["git add -A"] == "safe"
    assert levels["git rebase main"] == "caution"
    assert levels["git push --force"] == "dangerous"
    assert card["level"] == "dangerous"  # worst tier wins


def test_rejected_command_surfaced(git_repo: Path):
    card = danger.risk_card(["rm -rf /"], str(git_repo))
    assert card["rejected"] and card["rejected"][0]["command"] == "rm -rf /"
    assert card["per_command"] == []
    assert card["level"] == "safe"  # nothing runnable


def test_no_repo_safe_returns_no_exception(tmp_path: Path):
    card = danger.risk_card(["git status"], str(tmp_path / "nope"))
    assert card["level"] == "safe"
    assert card["mermaid"] == ""


def test_force_push_without_upstream_is_illustrative(git_repo: Path):
    # git_repo has no remote/upstream → illustrative diagram + note.
    card = danger.risk_card(["git push -f"], str(git_repo))
    assert "illustrative" in card["mermaid"]
    assert "```mermaid" in card["mermaid"]
