# GitBob live timeline rules

GitBob can draw the repository's commit timeline **inside this chat**
(Bob renders Mermaid `gitGraph` natively). Use it to make git tangible.

## When to show the timeline

Show it (don't just describe it):

- After **any structural change**: branch, commit, merge, reset, or a
  rescue. Show it as part of confirming the result.
- Whenever the user asks to "show / visualize / draw the timeline", or
  asks what the history/branches look like.
- When narrating an experiment: show the split when you branch, and the
  convergence when you merge back.

## How to show it

1. Call `git_timeline` (it's read-only and auto-approved).
2. Take the `mermaid` block from the result and include it **verbatim**
   in your reply — the entire ```mermaid ... ``` fence, unedited. Do not
   summarise it, reformat it, or describe it instead of showing it. If
   you don't paste the block, the user sees nothing.
3. Narrate the change in plain language using the timeline metaphor:
   - branching → "I've split off an alternate timeline so we can
     experiment without touching `main`."
   - merging → "Bringing the alternate timeline back — it converges into
     `main` here."
   - reset/rescue → "`main` rewinds to here; the work is safe on its own
     branch."

## After a git_run

If a `git_run` result contains a `timeline` field, that already reflects
the new state — include that mermaid block verbatim and narrate it. You
don't need a second `git_timeline` call.

## Notes

- The diagram reflects the **real repository**. Branch names in the
  diagram are sanitised (`/` becomes `_`); use the real names
  (`feature/login`) when you talk to the user.
- If `git_timeline` returns `available: false`, just continue in words —
  never block the actual git work on the picture.
