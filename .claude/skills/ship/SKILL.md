---
name: ship
description: Commit all changes on the current feature branch, push, open and merge a PR into main, pull main, then delete the branch. Use when the user says "ship", "commit and push", "open a PR", or "create a PR".
user-invocable: true
allowed-tools:
  - Bash(git *)
  - Bash(gh *)
---

# /ship — Commit, Merge, and Clean Up

Take all pending changes on the current feature branch through the full lifecycle: commit, push, open and merge a PR, then return main to a clean state.

Arguments passed: `$ARGUMENTS`

---

## Steps

### 1. Inspect state

Run in parallel:
- `git status` — list modified/untracked files
- `git diff` — see all unstaged changes
- `git log --oneline -5` — read recent commit style
- `git branch --show-current` — confirm the current branch name

If there are no staged or unstaged changes, say so and stop — do not create an empty commit.

If the current branch is `main`, stop and tell the user to create a feature branch first (via `/branch`).

### 2. Draft the commit message

Format:
```
<short subject line — imperative, ≤72 chars>

- <one bullet per logical change>
- <another change>
- ...

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

If `$ARGUMENTS` contains a hint, use it as the subject line.

### 3. Stage and commit

Add every modified tracked file by name — do not use `git add .` or `git add -A` to avoid accidentally staging `.env` or large binaries.

Commit using a HEREDOC to avoid shell quoting issues:
```bash
git commit -m "$(cat <<'EOF'
<subject line>

- <bullet>
- <bullet>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

### 4. Push the branch

```bash
git push -u origin HEAD
```

### 5. Open and merge the PR

Create the PR targeting `cybearcat/starting-ragchatbot-codebase:main`:
```bash
gh pr create \
  --repo cybearcat/starting-ragchatbot-codebase \
  --base main \
  --title "<subject line>" \
  --body "$(cat <<'EOF'
## Summary
- <bullet points matching the commit>

## Test plan
- [ ] <what to verify>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Then immediately merge it, passing `--repo` explicitly because `gh pr merge` without it can fail when the local branch tracks a fork:
```bash
gh pr merge <PR-number> --repo cybearcat/starting-ragchatbot-codebase --merge --delete-branch
```

The `--delete-branch` flag removes the remote branch on merge.

### 6. Return main to clean state

```bash
git checkout main
git pull origin main
```

### 7. Delete the local branch

```bash
git branch -d <branch-name>
```

### 8. Report

Print a one-line confirmation: the PR URL and the fact that `main` is now up to date.

---

## Notes

- Never use `--no-verify`, `--force`, or `--no-gpg-sign`.
- If the merge fails (e.g., CI required), report the PR URL and stop — do not force-merge.
- If `gh pr merge` deletes the remote branch, skip any manual `git push origin --delete` to avoid a redundant error.
