"""`gitbob` command-line entry point.

  gitbob serve    Run the MCP server over stdio (this is what Bob launches).
  gitbob init     Drop the .bob/ GitBob kit into the current repo.
  gitbob doctor   Check the environment is ready.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from importlib import resources

from .gitproc import is_git_repo, run_git

_KIT_DIRNAME = "kit"

# Explicit, predictable mapping: packaged kit file -> path inside the repo.
# (Templates avoid a leading-dot directory so packaging never drops them;
# init writes them to the real .bob/ locations Bob expects.)
_KIT_MANIFEST: list[tuple[str, str]] = [
    ("mcp.json", ".bob/mcp.json"),
    ("custom_modes.yaml", ".bob/custom_modes.yaml"),
    ("rules-gitbob/01-workflow.md", ".bob/rules-gitbob/01-workflow.md"),
    ("rules-gitbob/02-safety.md", ".bob/rules-gitbob/02-safety.md"),
    ("rules-gitbob/03-onboarding.md", ".bob/rules-gitbob/03-onboarding.md"),
    ("rules-gitbob/04-timeline.md", ".bob/rules-gitbob/04-timeline.md"),
    ("rules-gitbob/05-danger.md", ".bob/rules-gitbob/05-danger.md"),
    ("AGENTS.md", "AGENTS.md"),
]

# The 8 read/visual tools Bob may auto-approve. Kept in sync with the
# packaged kit's mcp.json; used only as a fallback if that file is
# missing/unparseable when we rewrite it.
_READ_TOOLS = [
    "git_status", "git_log", "git_diff", "git_branches",
    "git_reflog", "git_repo_overview", "git_timeline", "git_explain_risk",
]


def _server_command() -> tuple[str, list[str]]:
    """The command Bob should use to spawn the server, chosen so it
    resolves on the *target* machine.

    1. **Portable (every machine):** if ``gitbob`` is on PATH — a real
       ``pipx``/``pip`` install — return the bare command. Bob spawns
       with the system environment, so this is exactly what Bob resolves
       too, on any machine, in any cwd, and it is safe to commit.
    2. **Raw dev checkout** (a virtualenv whose ``Scripts``/``bin`` is
       not on PATH — the classic "0 tools" case): the absolute path to
       *this* interpreter's ``gitbob`` console script.
    3. **Last resort:** run the module with this exact interpreter.
    """
    if shutil.which("gitbob"):
        return "gitbob", ["serve"]
    scripts = os.path.dirname(sys.executable)
    exe = os.path.join(
        scripts, "gitbob.exe" if os.name == "nt" else "gitbob")
    if os.path.isfile(exe):
        return exe, ["serve"]
    return sys.executable, ["-m", "gitbob", "serve"]


def _write_mcp_json(dest_root: str) -> str:
    """Rewrite ``<dest_root>/.bob/mcp.json`` so Bob can actually spawn
    the server: an absolute, PATH-independent command. Preserves the
    rest of the file (alwaysAllow, timeout, cwd). Returns the command.
    """
    path = os.path.join(dest_root, ".bob", "mcp.json")
    cmd, args = _server_command()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    server = data.setdefault("mcpServers", {}).setdefault("gitbob", {})
    server["command"] = cmd
    server["args"] = args
    server.setdefault("cwd", "${workspaceFolder}")
    server.setdefault("timeout", 60)
    server.setdefault("alwaysAllow", list(_READ_TOOLS))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    return cmd


def _cmd_serve(_args: argparse.Namespace) -> int:
    from .server import serve

    serve()
    return 0


def _copy_kit(dest_root: str, force: bool) -> list[str]:
    """Install the packaged kit into dest_root per _KIT_MANIFEST."""
    written: list[str] = []
    kit = resources.files("gitbob").joinpath(_KIT_DIRNAME)
    for src_rel, dest_rel in _KIT_MANIFEST:
        target = os.path.join(dest_root, *dest_rel.split("/"))
        if os.path.exists(target) and not force:
            written.append(f"skip (exists): {dest_rel}")
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        src = kit.joinpath(*src_rel.split("/"))
        with resources.as_file(src) as src_path:
            shutil.copyfile(src_path, target)
        written.append(f"wrote: {dest_rel}")
    return written


def _cmd_init(args: argparse.Namespace) -> int:
    root = os.path.abspath(args.path)
    if not is_git_repo(root):
        print(f"! {root} is not a git repository. Run `git init` first.",
              file=sys.stderr)
        return 1
    print(f"Installing GitBob kit into {root} ...")
    for line in _copy_kit(root, force=args.force):
        print(f"  {line}")
    server_cmd = _write_mcp_json(root)
    print(f"  wired: .bob/mcp.json -> {server_cmd}")
    print(
        "\nDone. Open this folder in IBM Bob, reload the window, then pick the "
        "'GitBob' mode and ask in plain English (e.g. \"what's safe to "
        "delete here?\")."
    )
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    root = os.path.abspath(args.path)
    ok = True

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and passed
        print(f"  [{'OK' if passed else 'XX'}] {label}"
              f"{f' - {detail}' if detail else ''}")

    print("GitBob doctor:")
    git = run_git(["--version"])
    check("git available", git.ok, git.output.strip())
    check("inside a git repo", is_git_repo(root), root)
    try:
        import mcp  # noqa: F401

        check("mcp SDK importable", True)
    except Exception as exc:  # pragma: no cover - env dependent
        check("mcp SDK importable", False, str(exc))
    check("Python >= 3.10", sys.version_info >= (3, 10),
          sys.version.split()[0])

    cmd, _cmd_args = _server_command()
    launchable = (os.path.isfile(cmd)
                  or shutil.which(cmd) is not None
                  or cmd == sys.executable)
    check("server launch command resolvable", launchable, cmd)

    mcp_path = os.path.join(root, ".bob", "mcp.json")
    if os.path.isfile(mcp_path):
        try:
            with open(mcp_path, encoding="utf-8") as fh:
                cfg_cmd = json.load(fh)["mcpServers"]["gitbob"]["command"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            check("Bob can spawn server from .bob/mcp.json", False,
                  f"unreadable: {exc}")
        else:
            resolves = (os.path.isfile(cfg_cmd)
                        or shutil.which(cfg_cmd) is not None)
            check(
                "Bob can spawn server from .bob/mcp.json",
                resolves,
                cfg_cmd if resolves else
                f"'{cfg_cmd}' not found by Bob - re-run `gitbob init` "
                f"(writes an absolute path) or set command to: {cmd}",
            )

    print("\nResult:", "ready" if ok else "NOT ready")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gitbob", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="run the MCP server (stdio)").set_defaults(
        func=_cmd_serve
    )

    p_init = sub.add_parser("init", help="install the .bob/ GitBob kit")
    p_init.add_argument("path", nargs="?", default=".", help="repo path")
    p_init.add_argument("--force", action="store_true",
                        help="overwrite existing kit files")
    p_init.set_defaults(func=_cmd_init)

    p_doc = sub.add_parser("doctor", help="check the environment")
    p_doc.add_argument("path", nargs="?", default=".", help="repo path")
    p_doc.set_defaults(func=_cmd_doctor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
