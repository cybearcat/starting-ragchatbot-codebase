---
name: branch
description: Create a new feature branch off main. Use when the user says "create a branch", "new branch", "start a feature", or "make a branch".
user-invocable: true
allowed-tools:
  - Bash(git *)
---

# /branch — Create a Feature Branch

Create a new feature branch off an up-to-date `main` and switch to it, ready for development.

Arguments passed: `$ARGUMENTS`

---

## Steps

### 1. Ensure main is up to date

```bash
git checkout main
git pull origin main
```

### 2. Derive the branch name

If `$ARGUMENTS` is provided, derive the branch name from it: lowercase, spaces → hyphens, drop punctuation, max 40 chars.

If no arguments are provided, ask the user for a short description of what the branch is for, then derive the name from that.

### 3. Create and switch to the branch

```bash
git checkout -b <branch-name>
```

### 4. Report

Print one line: the branch name and confirmation that it diverges from `main`.

---

## Notes

- Never create a branch from a branch other than `main` unless the user explicitly asks.
- Do not stage, commit, or push anything — this skill only creates the branch.
