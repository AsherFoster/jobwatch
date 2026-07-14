---
name: cleanup
description: Delete a merged worktree and its branch after verifying the branch is merged.
---

Worktrees live under `.claude/worktrees/<name>`, usually on a `worktree-<name>`
branch, and are typically locked.

1. Identify the target: `git worktree list`. If the user didn't name one, list
   the candidates and only clean up those that pass the checks below.

2. Verify the branch is merged into `main`:

```sh
git fetch origin main
git branch --merged origin/main
```

   If the branch isn't listed, it may have been squash-merged — confirm every
   commit is upstream (`git cherry origin/main <branch>` shows only `-` lines)
   or the diff is empty (`git diff origin/main...<branch>` produces nothing).
   If neither holds, **stop and report** — never delete unmerged work.

3. Check the worktree is clean: `git -C <path> status --porcelain` must be
   empty. Untracked or modified files mean stop and ask.

4. Remove the worktree first (a branch can't be deleted while checked out):

```sh
git worktree unlock <path>   # skip if not locked
git worktree remove <path>
git worktree prune
```

5. Delete the branch with `git branch -d <branch>`. If git refuses because the
   merge was a squash, `-D` is fine — but only after the step 2 verification
   passed.

Leave remote branches alone unless the user asks.
