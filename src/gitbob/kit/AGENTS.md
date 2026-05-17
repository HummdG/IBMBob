# Project context for Bob

## GitBob is installed in this repository

This repo ships **GitBob**, a natural-language Git copilot, as an MCP
server (see `.bob/mcp.json`) plus a custom Bob mode (see
`.bob/custom_modes.yaml`).

- For **any Git task expressed in natural language** — recovering from
  mistakes, writing commit messages, cleaning up branches, or
  explaining the repo's history/branch structure — switch to the
  **👷 GitBob** mode and let it handle the request.
- GitBob exposes safe git tools: `git_status`, `git_log`, `git_diff`,
  `git_branches`, `git_reflog`, `git_repo_overview` (read-only,
  auto-approved) and `git_run` (gated; destructive plans require
  explicit confirmation).
- Do not hand-run raw shell git for these tasks when GitBob mode can do
  it — GitBob inspects the real repository state and makes every change
  explained, confirmed, and reversible.
