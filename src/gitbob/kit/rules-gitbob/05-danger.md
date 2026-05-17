# GitBob danger rules — make risk visible before acting

GitBob colour-codes every operation: 🟦 **safe**, 🟧 **history rewrite**
(recoverable via reflog, but collaborators diverge), 🟥 **destructive**
(can permanently lose work or rewrite shared history).

## Always preview risk before changing anything

Before you propose ANY `git_run`, call **`git_explain_risk`** with the
exact commands you intend to run. Then, in your reply:

1. State the level plainly: "🟥 This is **destructive**." /
   "🟧 This **rewrites history**." / "🟦 This is safe."
2. If the result has a non-empty `mermaid`, include that block
   **verbatim** (the whole ```mermaid ... ``` fence) — it shows the
   consequence in colour (orphaned work in dashed red). Don't describe
   it instead of showing it.
3. Say, bluntly and specifically, what the consequence is and whether
   it's reversible (use the `reversible` and `affects_others` fields).
   For force-push: name who loses work ("everyone who already pulled
   these commits").
4. Only then ask whether to proceed.

## Force-push and shared history

Treat anything that rewrites *shared* history (force-push,
`filter-branch`, force-push after rebase) as the highest concern. Show
the before/after diagram, and make sure the user understands that other
people's clones break — this is the whole point of the visual.

## Then follow the safety gate

For 🟥 destructive plans, after the user gives an explicit yes, proceed
through the normal confirm-token flow (see `02-safety.md`): `git_run`
returns `confirmation_required` (with this same risk card attached) —
re-call with the same commands plus the `confirm_token`.

🟧 caution plans don't need a token, but still show the risk card and
get a clear yes first. 🟦 safe plans: just proceed.

If `git_explain_risk` returns an empty `mermaid`, continue in words —
never block the real work on the picture.
