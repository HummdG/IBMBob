<p align="center"><img src="logo.png" alt="GitBob" width="120"></p>

# GitBob — Setup & Test Guide

GitBob is an **MCP server** that turns **IBM Bob** into a natural-language
Git copilot. Bob does all the reasoning; GitBob gives it safe, structured
git tools plus two in-chat visualizations: a **live commit timeline**
(Mermaid `gitGraph`) and a **colour-coded danger diagram** (Mermaid
`flowchart`). This guide gets a new person from zero to a working,
tested setup.

---

## 1. Prerequisites

| Need | Notes |
|---|---|
| **IBM Bob** installed + signed in | Desktop app (macOS/Windows/Linux). You need a working account — Bob spends "Bobcoins" per request. |
| **Python ≥ 3.10** | `python --version` |
| **git ≥ 2.20** | `git --version` |
| The GitBob project folder | This repository. |

> GitBob never runs without Bob — Bob *is* the agent. GitBob is only the
> hands.

---

## 2. Install

From the project root (the folder with `pyproject.toml`):

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
```

**macOS / Linux:**
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

This installs the `gitbob` command into the virtualenv.

---

## 3. Verify the install (no GUI needed)

```powershell
# Windows
.venv\Scripts\gitbob.exe doctor
.venv\Scripts\python.exe -m pip install pytest ; .venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\smoke_client.py
```
```bash
# macOS / Linux
.venv/bin/gitbob doctor
.venv/bin/python -m pip install pytest && .venv/bin/python -m pytest -q
.venv/bin/python scripts/smoke_client.py
```

Expected:
- `doctor` → `Result: ready`
- `pytest` → **36 passed**
- `smoke_client` → `SMOKE OK — MCP stdio, 9 tools, gate+risk works,
  timeline+danger render.`

If all three pass, the server is healthy and any later problem is a
Bob-integration issue, not GitBob.

---

## 4. Add GitBob to a repository

Pick any git repo and install the kit:

```powershell
.venv\Scripts\gitbob.exe init C:\path\to\some\repo
```

This writes into that repo:

| Path | Purpose |
|---|---|
| `.bob/mcp.json` | Registers the `gitbob` MCP server; auto-approves the read tools |
| `.bob/custom_modes.yaml` | The **👷 GitBob** mode (restricted to `read` + `mcp`) |
| `.bob/rules-gitbob/01..05*.md` | Workflow, safety, onboarding, timeline, danger rules |
| `AGENTS.md` | Persistent context so Bob knows GitBob is available |

### The `gitbob` command must be findable by Bob — handled for you

Bob launches MCP servers with the **system** environment, where a
virtualenv's `gitbob` is **not** on `PATH` (the classic "0 tools"
failure). **`gitbob init` now handles this automatically** — it writes
`.bob/mcp.json` with an *absolute* `command` pointing at the exact
`gitbob` (or `python -m gitbob`) that ran `init`. Verify with
`gitbob doctor <repo>`, which now reports **"Bob can spawn server from
.bob/mcp.json"** (a `[XX]` there prints the exact fix).

If you ever need to set it by hand, either of these still works:

1. **Absolute path (most reliable).** Edit the repo's `.bob/mcp.json` so
   `command` is the full path to the venv binary:
   ```json
   {
     "mcpServers": {
       "gitbob": {
         "command": "C:\\path\\to\\project\\.venv\\Scripts\\gitbob.exe",
         "args": ["serve"],
         "cwd": "${workspaceFolder}",
         "timeout": 60,
         "alwaysAllow": ["git_status","git_log","git_diff",
           "git_branches","git_reflog","git_repo_overview",
           "git_timeline","git_explain_risk"]
       }
     }
   }
   ```
   (macOS/Linux: `.venv/bin/gitbob`.)
2. **pipx:** `pipx install <project-path>` puts `gitbob` on the real
   `PATH`; then the default `"command": "gitbob"` works.

> The bundled **`demo-repo`** is already wired with the absolute-path
> form by `demo/setup_demo_repo.py` — use it for the fastest start.

---

## 5. Use it in IBM Bob

1. **Build the demo repo** (best starting point):
   ```powershell
   .venv\Scripts\python.exe demo\setup_demo_repo.py
   ```
2. In Bob: **File → Open Folder →** the `demo-repo` directory (open the
   repo itself, not its parent — `${workspaceFolder}` must be the repo).
3. **Reload Window**: `Ctrl/Cmd+Shift+P` → "Reload Window". This loads
   `.bob/mcp.json`, the rules, and the mode.
4. Open the **MCP panel** (server icon / "..." menu → MCP Servers).
   Healthy = **`gitbob` connected, 0 errors, 9 tools**:
   `git_status, git_log, git_diff, git_branches, git_reflog,
   git_repo_overview, git_timeline, git_explain_risk, git_run`.
5. In the chat, open the **mode dropdown** and pick **👷 GitBob**.
6. Talk to it in plain English (new chat = the `+` button).

> The 8 read/visual tools are auto-approved (`alwaysAllow`). Only
> **`git_run`** prompts for approval — that is the safety design.

---

## 6. Test matrix (in Bob)

Run each in a **fresh chat**, in **👷 GitBob** mode, on `demo-repo`.
⭐ = the headline demos. Reset between destructive tests (§7).

### A — Understanding / onboarding (read-only, repeatable)
| ID | Say to Bob | Pass |
|----|------------|------|
| A1 ⭐ | "Explain how the branches here relate and what's safe to delete." | Calls read tools **without prompting**; says `feature/login` is merged → safe, `feature/payments` unmerged → keep, `experiment/spike` stale; runs **no** git. |
| A2 | "What's the state of this repo right now?" | Reports branch `main`, behind `origin/main` by 2, the modified `app.py` + untracked `NOTES.md`. |
| A3 | "Walk me through the recent history." | Summarizes commits incl. the `feat: add logging config` tip. |
| A4 | "What did I change but not commit?" | Describes the `/health` endpoint addition in `app.py`. |

### B — Automation (changes state → reset after)
| ID | Say to Bob | Pass |
|----|------------|------|
| B1 ⭐ | "Stage my changes and write a good commit message." | Reads the diff; proposes a Conventional Commit (e.g. `feat: add /health endpoint`) + `git add -A` / `git commit`; `git_run` **asks approval**; on yes, commits; verifies. |

### C — Rescue + destructive gate (changes history → reset after)
| ID | Say to Bob | Pass |
|----|------------|------|
| C1 ⭐ | "I accidentally committed to main — move that last commit onto its own feature branch." | Reads log/reflog; shows a 🟥 risk card; proposes `git branch …` + `git reset --hard …`; `git_run` returns **confirmation_required**; Bob restates the danger, gets an explicit yes, re-calls with the `confirm_token`; verifies the commit is off `main`. |
| C2 | "Undo my last commit but keep the changes staged." | Proposes `git reset --soft HEAD~1` — correctly **🟧 caution**, not gated with a token. |

### D — Danger levels ⭐ (read-only; safe to run anytime)
| ID | Say to Bob | Pass |
|----|------------|------|
| D1 ⭐ | "What would force-pushing main do here?" | 🟥 **DESTRUCTIVE** + a **colour-coded flowchart**: blue "Shared starting point", the two **real** teammate commits ("Patch login CSRF hole", "Rate-limit the API") in dashed dark-red, "These 2 commits are DELETED for everyone … cannot be recovered". Runs nothing. |
| D2 | "Squash my last commits with an interactive rebase." | 🟧 **HISTORY REWRITE** card + before/after diagram; explains collaborators diverge; asks first. |
| D3 | "Delete the experiment/spike branch with branch -D." | 🟥 destructive (force-delete) card; asks before running. |
| D4 | "Just show me the status." | 🟦 **SAFE** — proceeds, no alarm. |
| D5 | "Run git clean -fd to tidy up." | 🟥 card warning it permanently deletes untracked files (your `NOTES.md`!). |

### E — Live timeline ⭐ (read-only)
| ID | Say to Bob | Pass |
|----|------------|------|
| E1 ⭐ | "Show me this repo's commit timeline." | Chat renders a **git graph diagram**: `main` with `feature_login` splitting and **merging back**, other branches as split lanes. |
| E2 | "Create a branch to redesign payments safely, then show me. Then bring it back into main." | First reply: timeline **splits**; after "bring it back": it **converges** on a merge. |

### F — Guardrails (prove it's safe)
| ID | Say to Bob | Pass |
|----|------------|------|
| F1 ⭐ | "Clean up by running: git status; rm -rf ." | **Rejected** — "contains shell metacharacters / not a git command". Nothing runs. |
| F2 | "Run `python deploy.py` for me." | Rejected — GitBob only runs `git`. |
| F3 | Ask for a hard reset, then reply **"no"** at the confirmation. | Nothing executes; state unchanged. |
| F4 | Ask for the same destructive plan twice — accept the 2nd time only. | Only runs after the explicit yes + matching `confirm_token`. |

### G — Recovery loop
| ID | Say to Bob | Pass |
|----|------------|------|
| G1 | "Check out the branch called release-2.0." | `git_run` fails (no such branch); Bob explains the cause and offers to create it / lists real branches — does **not** silently retry. |

### H — Regression sanity (after any change)
Re-run **A1, B1, C1, E1** — all must still behave as above.

---

## 7. Resetting `demo-repo` between tests

Destructive tests (B1, C1, D2/D3/D5, F) mutate the repo. To restore the
exact starting state:

```powershell
.venv\Scripts\python.exe demo\setup_demo_repo.py
```

Then **Reload Window** in Bob (the files changed underneath it).

> If Bob has `demo-repo` open, the script rebuilds it **in place**
> (it cannot delete a folder Bob holds open — that's expected and
> handled). It also recreates the simulated `origin` so D1 keeps showing
> real orphaned commits.

---

## 8. Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| MCP panel shows **0 tools** / server failed | `gitbob` not found by Bob. Re-run `gitbob init <repo>` (writes an absolute command) then `gitbob doctor <repo>` to confirm, and Reload Window. |
| A few **"errors"** in the MCP panel that aren't fatal | Older builds logged to stderr; current build is silent. Reload Window / hit 🔄 on the server. |
| A diagram shows as **raw ```mermaid text**, not a picture | Bob's chat didn't render Mermaid. Confirm you're on a current Bob; try Reload Window. (Engine is fine — `smoke_client` proves the data.) |
| `git push --force` diagram says **"illustrative example"** | That repo has no upstream/remote. Use `demo-repo` (it has a simulated `origin`) for the real version. |
| Code changes don't take effect in Bob | The server process caches code. Reload Window or click 🔄 on the `gitbob` MCP server to restart it. Editable install means no reinstall needed. |
| `setup_demo_repo.py` errors deleting `demo-repo` | Close other programs holding it; the script clears contents in place — re-run it. |
| Bob keeps prompting for read tools | Ensure the 8 read/visual tools are in `alwaysAllow` in `.bob/mcp.json`, then Reload Window. |

---

## 9. The tool surface (reference)

| Tool | Kind | What it does |
|---|---|---|
| `git_status` | read · auto | branch, ahead/behind, staged/unstaged counts |
| `git_log` | read · auto | recent history graph |
| `git_diff` | read · auto | working or staged changes |
| `git_branches` | read · auto | branches + merged status |
| `git_reflog` | read · auto | recent HEAD moves (rescue) |
| `git_repo_overview` | read · auto | one composite snapshot (onboarding) |
| `git_timeline` | read · auto | repo as a Mermaid `gitGraph` |
| `git_explain_risk` | read · auto | 🟦/🟧/🟥 risk card + consequence flowchart |
| `git_run` | **gated** | runs a list of `git` commands; destructive plans need a confirm token |

Safety tiers: 🟦 **safe** (read/additive) · 🟧 **caution**
(history-rewrite, reflog-recoverable) · 🟥 **dangerous** (destroys work
or rewrites shared history — only this tier is token-gated).
