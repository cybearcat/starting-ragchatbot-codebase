---
name: ship
description: Stage all changes, commit with a generated message, push to origin, and open a PR against cybearcat/starting-ragchatbot-codebase:main. Use when the user says "ship", "commit and push", "open a PR", or "create a PR".
user-invocable: true
allowed-tools:
  - Bash(git *)
  - Bash(gh *)
---

# /ship — Commit, Push, and Open a PR

Stage changed files, write a commit, push to `origin`, and create a PR against `cybearcat/starting-ragchatbot-codebase:main` in one pass.

Arguments passed: `$ARGUMENTS`

---

## Steps

1. **Inspect state** — run these in parallel:
   - `git status` to list modified/untracked files
   - `git diff` to see all unstaged changes
   - `git log --oneline -5` to read recent commit style

2. **Stage files** — add every modified tracked file. Do not use `git add .` or `git add -A`; add files by name to avoid accidentally staging `.env` or large binaries.

3. **Write the commit message** following the project convention:
   - Short subject line (imperative, ≤72 chars)
   - Blank line
   - One bullet point per logical change
   - End with: `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
   - Pass via HEREDOC to avoid shell quoting issues

4. **Push** to `origin` with `-u` if the branch has no upstream yet, otherwise plain `git push origin HEAD`.

5. **Create the PR** targeting `cybearcat/starting-ragchatbot-codebase:main`:
   ```
   gh pr create \
     --repo cybearcat/starting-ragchatbot-codebase \
     --base main \
     --title "<title>" \
     --body "$(cat <<'EOF'
   ## Summary
   - <bullet points>

   ## Test plan
   - [ ] <what to verify>

   🤖 Generated with [Claude Code](https://claude.com/claude-code)
   EOF
   )"
   ```

6. **Report** — print the PR URL so the user can open it directly.

---

## Notes

- If there are no staged or unstaged changes, say so and stop — do not create an empty commit.
- If the current branch is `main`, warn the user and stop — changes should be on a feature branch.
- Never use `--no-verify` or `--force`.
- If `$ARGUMENTS` contains a commit message hint, use it as the subject line rather than generating one.
