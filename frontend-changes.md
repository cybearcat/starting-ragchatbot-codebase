# Frontend Code Quality Changes

## Overview

Added frontend code quality tooling using **Prettier** — the JavaScript/CSS/HTML equivalent of black.

> Note: The feature request named `black`, which is Python-only. Since the task scope is front-end only, Prettier was used instead. It provides the same automated, opinionated formatting guarantee for JS/CSS/HTML that black provides for Python.

## Files Added

| File | Purpose |
|------|---------|
| `frontend/package.json` | npm project config; declares Prettier as a dev dependency and exposes `format` / `check` npm scripts |
| `frontend/.prettierrc` | Prettier config: 4-space indentation, single quotes, 100-char line width, LF line endings |
| `frontend/node_modules/` | Installed Prettier package (excluded from git via `.gitignore`) |
| `check-frontend.sh` | Root-level shell script (matches `run.sh` convention) that runs `prettier --check` and exits non-zero on any formatting violation |

## Files Modified

| File | Change |
|------|--------|
| `.gitignore` | Added `frontend/node_modules/` entry |
| `frontend/script.js` | Reformatted by Prettier (quote style, indentation, line breaks) |
| `frontend/style.css` | Reformatted by Prettier (property spacing, blank lines) |
| `frontend/index.html` | Reformatted by Prettier (indentation, attribute formatting) |

## Developer Workflow

**Install dependencies (one-time):**
```bash
cd frontend && npm install
```

**Check formatting (CI / pre-commit):**
```bash
./check-frontend.sh
```

**Auto-format all frontend files:**
```bash
cd frontend && npm run format
```

**Check only (no writes):**
```bash
cd frontend && npm run check
```
