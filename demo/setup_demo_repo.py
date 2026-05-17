"""Build the GitBob demo repository in a deliberately messy state that
exercises all three flagship scenarios in one repo:

  1. Rescue    — a commit landed on `main` that belongs on a branch.
  2. Automation — uncommitted working changes needing a commit message.
  3. Onboarding — a mix of merged / active / stale branches to explain.

Idempotent: deletes and recreates <project>/demo-repo each run. The
generated .bob/mcp.json uses an ABSOLUTE path to this venv's `gitbob`
so IBM Bob can spawn the server regardless of system PATH.

Run:  .venv/Scripts/python.exe demo/setup_demo_repo.py
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path


def _force_rmtree(path: Path) -> None:
    """rmtree that survives Windows read-only git objects."""
    def _on_error(func, p, _exc):  # noqa: ANN001
        os.chmod(p, stat.S_IWRITE)
        func(p)

    if path.exists():
        shutil.rmtree(path, onexc=lambda f, p, e: _on_error(f, p, e))


def _clean_contents(path: Path) -> None:
    """Empty a directory IN PLACE without removing the dir itself.

    The top-level demo-repo may be held open by IBM Bob (cwd lock), so it
    cannot be deleted/recreated — but its contents can be cleared and
    rebuilt. This makes the script safe to re-run while Bob is open.
    """
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_dir():
            _force_rmtree(child)
        else:
            try:
                child.chmod(stat.S_IWRITE)
            except OSError:
                pass
            child.unlink(missing_ok=True)

PROJECT = Path(__file__).resolve().parents[1]
DEMO = PROJECT / "demo-repo"


def git(*args: str, cwd: Path = DEMO) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                    text=True)


def commit(msg: str, *, env_date: str | None = None) -> None:
    env = os.environ.copy()
    if env_date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = env_date
    subprocess.run(["git", "commit", "-m", msg], cwd=DEMO, check=True,
                    capture_output=True, text=True, env=env)


def write(rel: str, content: str) -> None:
    p = DEMO / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def install_kit() -> None:
    """Copy the kit, then reuse gitbob's OWN PATH-proof mcp.json writer
    (single source of truth — no divergent copy of that logic here), and
    pin ``cwd`` to the absolute demo path so the recording never depends
    on Bob expanding ``${workspaceFolder}``.
    """
    sys.path.insert(0, str(PROJECT / "src"))
    from gitbob.cli import _copy_kit, _write_mcp_json  # noqa: WPS433

    for line in _copy_kit(str(DEMO), force=True):
        print(f"  {line}")

    cmd = _write_mcp_json(str(DEMO))

    mcp_path = DEMO / ".bob" / "mcp.json"
    cfg = json.loads(mcp_path.read_text(encoding="utf-8"))
    cfg["mcpServers"]["gitbob"]["cwd"] = str(DEMO)
    mcp_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"  wired: .bob/mcp.json -> {cmd}")
    print(f"          cwd -> {DEMO}")


ORIGIN = PROJECT / "demo-origin.git"
TEAMMATE = PROJECT / ".demo-teammate"


def _setup_remote_divergence() -> None:
    """Give the demo a real `origin` where a teammate has pushed commits
    we don't have locally — so `git push --force main` would orphan their
    *actual* work and GitBob's danger diagram shows real lost commits.

    State after this:
      origin/main : ... ─ accidental ─ T1 ─ T2   (teammate's commits)
      local  main : ... ─ accidental             (behind by T1, T2)
    A force-push of local main would delete T1, T2 for everyone.
    """
    _force_rmtree(ORIGIN)
    _force_rmtree(TEAMMATE)
    git("init", "-q", "--bare", "-b", "main", str(ORIGIN), cwd=PROJECT)

    git("remote", "add", "origin", ORIGIN.as_posix())
    git("push", "-q", "-u", "origin", "main")

    # A teammate clones, pushes two commits we never pulled.
    git("clone", "-q", str(ORIGIN), str(TEAMMATE), cwd=PROJECT)
    git("config", "user.email", "priya@example.com", cwd=TEAMMATE)
    git("config", "user.name", "Priya (teammate)", cwd=TEAMMATE)
    (TEAMMATE / "auth.py").write_text(
        "def login(user):\n    # SECURITY: validate CSRF token\n"
        "    return f'hi {user}'\n", encoding="utf-8")
    git("add", "-A", cwd=TEAMMATE)
    git("-c", "user.name=Priya (teammate)",
        "-c", "user.email=priya@example.com",
        "commit", "-q", "-m", "fix: patch login CSRF hole", cwd=TEAMMATE)
    (TEAMMATE / "ratelimit.py").write_text(
        "WINDOW = 60\nMAX = 100\n", encoding="utf-8")
    git("add", "-A", cwd=TEAMMATE)
    git("-c", "user.name=Priya (teammate)",
        "-c", "user.email=priya@example.com",
        "commit", "-q", "-m", "feat: rate-limit the API", cwd=TEAMMATE)
    git("push", "-q", "origin", "main", cwd=TEAMMATE)

    # We only FETCH (never pull) — local main stays behind origin/main.
    git("fetch", "-q", "origin")
    _force_rmtree(TEAMMATE)


def build() -> None:
    _clean_contents(DEMO)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "dev@example.com")
    git("config", "user.name", "Demo Dev")

    # --- main history -----------------------------------------------------
    write("README.md", "# Todo API\n\nA tiny todo service.\n")
    write("requirements.txt", "flask==3.0.0\n")
    git("add", "-A")
    commit("chore: initialize project", env_date="2026-05-01T09:00:00")

    write("app.py", "from flask import Flask\n\napp = Flask(__name__)\n")
    git("add", "-A")
    commit("feat: add app skeleton", env_date="2026-05-02T10:00:00")

    # --- feature/login: merged (safe to delete) ---------------------------
    git("checkout", "-q", "-b", "feature/login")
    write("auth.py", "def login(user):\n    return f'hi {user}'\n")
    git("add", "-A")
    commit("feat: add login", env_date="2026-05-03T11:00:00")
    git("checkout", "-q", "main")
    git("merge", "-q", "--no-ff", "feature/login", "-m",
        "merge: feature/login")

    # --- GitBob kit committed as part of the repo (clean baseline) --------
    install_kit()
    git("add", ".bob", "AGENTS.md")
    commit("chore: add GitBob kit", env_date="2026-05-05T09:00:00")

    # --- feature/payments: active, unmerged (NOT safe to delete) ----------
    git("checkout", "-q", "-b", "feature/payments")
    write("payments.py", "def charge(amount):\n    return amount  # TODO\n")
    git("add", "-A")
    commit("feat: start payments", env_date="2026-05-08T14:00:00")
    write("payments.py",
          "def charge(amount):\n    if amount <= 0:\n        raise ValueError\n"
          "    return amount\n")
    git("add", "-A")
    commit("feat: validate charge amount", env_date="2026-05-09T15:00:00")

    # --- experiment/spike: stale, unmerged --------------------------------
    git("checkout", "-q", "main")
    git("checkout", "-q", "-b", "experiment/spike")
    write("spike.txt", "throwaway idea\n")
    git("add", "-A")
    commit("chore: random spike", env_date="2026-04-10T08:00:00")

    # --- the "accident": a real commit on main that belongs on a branch ---
    git("checkout", "-q", "main")
    write("logging_config.py",
          "import logging\n\nlogging.basicConfig(level=logging.INFO)\n")
    git("add", "-A")
    commit("feat: add logging config", env_date="2026-05-12T16:00:00")

    _setup_remote_divergence()

    # --- uncommitted working changes (scenario 2) -------------------------
    # Only the app change is left dirty, so the commit-message demo is crisp.
    write("app.py",
          "from flask import Flask\n\napp = Flask(__name__)\n\n\n"
          "@app.get('/health')\ndef health():\n    return {'ok': True}\n")
    write("NOTES.md", "- remember to add tests for /health\n")


def summary() -> None:
    print("\nDemo repo ready at:", DEMO)
    print("\nStarting state:")
    print("  - main TIP is an ACCIDENTAL commit: 'feat: add logging config'")
    print("    (scenario 1: should be moved to its own branch)")
    print("  - Uncommitted: app.py modified + NOTES.md new")
    print("    (scenario 2: ask GitBob to commit with a good message)")
    print("  - Branches: feature/login (merged), feature/payments (active),")
    print("    experiment/spike (stale) (scenario 3: what's safe to delete)")
    print("  - origin/main is AHEAD by 2 real teammate commits (Priya);")
    print("    local main is behind. `git push --force` would orphan them")
    print("    (danger demo: 'what would force-pushing main do here?')")
    print("\nNext: open this folder in IBM Bob, reload window,"
          " pick the GitBob mode.")


if __name__ == "__main__":
    build()
    summary()
