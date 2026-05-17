"""Stdio MCP smoke test: spawn the GitBob server like Bob would, list its
tools, and exercise a read tool plus the destructive-confirmation gate.

Run: .venv/Scripts/python.exe scripts/smoke_client.py
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def result_payload(call_result) -> dict:
    """Tool return as a dict, whichever way the SDK surfaced it."""
    sc = call_result.structuredContent
    if isinstance(sc, dict):
        return sc.get("result", sc)
    return json.loads(call_result.content[0].text)


def _make_repo() -> str:
    d = tempfile.mkdtemp(prefix="gitbob-smoke-")
    run = lambda *a: subprocess.run(["git", *a], cwd=d, check=True,
                                    capture_output=True)
    run("init", "-b", "main")
    run("config", "user.email", "smoke@example.com")
    run("config", "user.name", "Smoke")
    with open(os.path.join(d, "README.md"), "w") as fh:
        fh.write("# smoke\n")
    run("add", "-A")
    run("commit", "-m", "chore: initial")
    return d


async def main() -> int:
    repo = _make_repo()
    src = os.path.join(os.path.dirname(__file__), "..", "src")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "gitbob.server"],
        env={**os.environ, "PYTHONPATH": os.path.abspath(src)},
        cwd=repo,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print("TOOLS:", names)
            assert len(names) == 9, f"expected 9 tools, got {names}"
            assert {"git_timeline", "git_explain_risk"} <= set(names), names

            st = result_payload(
                await session.call_tool("git_status", {"repo_path": repo}))
            print("git_status -> branch:", st["branch"], "clean:", st["clean"])
            assert st["branch"] == "main", st

            ov = result_payload(
                await session.call_tool("git_repo_overview",
                                        {"repo_path": repo}))
            print("git_repo_overview -> branch:", ov["status"]["branch"])
            assert ov["status"]["branch"] == "main", ov

            # Destructive gate: first call must NOT execute.
            r1 = result_payload(await session.call_tool(
                "git_run",
                {"commands": ["git reset --hard HEAD"], "repo_path": repo}))
            print("git_run (no token) ->", r1["status"])
            assert r1["status"] == "confirmation_required", r1
            assert r1["risk"]["level"] == "dangerous", r1["risk"]

            # Second call with the issued token executes.
            r2 = result_payload(await session.call_tool(
                "git_run",
                {"commands": ["git reset --hard HEAD"],
                 "confirm_token": r1["confirm_token"], "repo_path": repo}))
            print("git_run (with token) ->", r2["status"])
            assert r2["status"] == "completed", r2
            assert "```mermaid" in r2.get("timeline", ""), \
                "git_run should attach a timeline on completion"

            tl = result_payload(await session.call_tool(
                "git_timeline", {"repo_path": repo}))
            print("git_timeline -> available:", tl.get("available"))
            assert tl["available"] is True, tl
            assert "```mermaid" in tl["mermaid"] and "gitGraph" in tl["mermaid"]

            rk = result_payload(await session.call_tool(
                "git_explain_risk",
                {"commands": ["git push --force origin main"],
                 "repo_path": repo}))
            print("git_explain_risk -> level:", rk["level"],
                  "affects_others:", rk["affects_others"])
            assert rk["level"] == "dangerous", rk
            assert rk["affects_others"] is True
            assert "```mermaid" in rk["mermaid"] and "flowchart" in rk["mermaid"]

    print("\nSMOKE OK — MCP stdio, 9 tools, gate+risk works, "
          "timeline+danger render.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
