# Testing Framework Enhancement

## Changes Made

### `backend/tests/conftest.py`
- Added `patch` to `unittest.mock` import.
- Added `from fastapi.testclient import TestClient` import.
- Added `_StubStaticFiles` class: a minimal ASGI stub that replaces `StaticFiles` during
  tests. A real subclassable class is required because `app.py` defines
  `class DevStaticFiles(StaticFiles)` — patching with a bare `MagicMock` would raise
  `TypeError` at class-definition time.
- Added `app_module` fixture (session-scoped): patches `RAGSystem` and `StaticFiles` only
  during the `import app` call, then releases the patches. The mock instance is stored on
  `app.rag_system` and shared across all API tests.
- Added `mock_rag` fixture (function-scoped): fully resets the `rag_system` mock between
  tests (including return values and side effects) and re-configures
  `add_course_folder.return_value = (0, 0)` so the startup event never tries to unpack a
  bare `MagicMock`.
- Added `api_client` fixture (function-scoped): creates a `TestClient` context around the
  FastAPI app; lists `mock_rag` first to ensure the mock is configured before the startup
  event fires.

### `backend/tests/test_api_endpoints.py` (new file)
API endpoint tests covering all three routes:

| Endpoint | Test |
|---|---|
| `POST /api/query` | Returns answer + sources in `QueryResponse` shape |
| `POST /api/query` | Creates a new session when none is provided |
| `POST /api/query` | Uses caller-supplied `session_id` without creating a new one |
| `POST /api/query` | Returns HTTP 500 when `rag_system.query` raises |
| `POST /api/query` | Returns HTTP 422 on missing required `query` field |
| `GET /api/courses` | Returns `CourseStats` with total count and titles |
| `GET /api/courses` | Returns HTTP 500 when `get_course_analytics` raises |
| `GET /` | Static route is mounted and reachable (stub returns 200, not 404) |
| `DELETE /api/session/{id}` | Returns `{"status": "ok"}` and calls `delete_session` |

## Design Decisions

- **Patches are released immediately after import** rather than held for the session scope.
  This avoids interfering with `test_rag_system.py` and `test_ai_generator.py`, which
  patch `RAGSystem` independently.
- **`_StubStaticFiles` is a real class** (not `MagicMock`) so that
  `class DevStaticFiles(StaticFiles)` in `app.py` can inherit from it without error.
- **`pytest.ini_options` was already present** in `pyproject.toml` (`pythonpath`,
  `testpaths`) — no changes needed there.
- **`httpx`** was already available as a transitive dependency — no new dev dependency
  required.

---

# Frontend Changes: Dark/Light Theme Toggle

## Files Modified

### `frontend/index.html`
- Added an inline `<script>` in `<head>` (before first paint) that reads `localStorage` and sets `data-theme="light"` on `<html>` immediately, preventing a flash of the wrong theme on reload.
- Added a fixed `<button id="themeToggleBtn" class="theme-toggle">` with a sun SVG icon (the default icon for dark mode) positioned in the top-right corner. The button has `aria-label="Switch to light theme"` for accessibility.
- Bumped stylesheet cache-bust version to `style.css?v=12` and script version to `script.js?v=11`.

### `frontend/style.css`
- Added `[data-theme="light"]` block after `:root` that overrides the following CSS variables:
  - `--background`: `#f8fafc` (light gray-white)
  - `--surface`: `#ffffff` (white)
  - `--surface-hover`: `#f1f5f9`
  - `--text-primary`: `#0f172a` (near-black)
  - `--text-secondary`: `#64748b` (medium gray)
  - `--border-color`: `#e2e8f0` (light gray)
  - `--assistant-message`: `#f1f5f9`
  - `--shadow`: lighter drop shadow
  - `--welcome-bg`: `#eff6ff` (light blue tint)
- Added a global `*, *::before, *::after { transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease; }` rule for smooth theme switching. Scoped to only these three properties to avoid fighting existing `transform`/`opacity` animations.
- Added `.theme-toggle` button styles: fixed position top-right, 40×40px circle, uses surface/border CSS variables, with hover and focus ring states.
- Added `[data-theme="light"]` overrides for elements with hardcoded colors:
  - `.source-tag` and `.source-tag:hover`: changed text from light blue `#93c5fd` to dark blue `#1d4ed8` for contrast on white backgrounds.
  - `.message-content code` and `.message-content pre`: reduced background opacity from `0.2` to `0.06` for readability on light backgrounds.

### `frontend/script.js`
- Added `themeToggleBtn` to the DOM element declarations.
- Added `SUN_ICON` and `MOON_ICON` SVG string constants using `stroke="currentColor"` to inherit color from the button.
- Added `setupThemeToggle()` function that attaches a click listener to the toggle button; on each click it toggles `data-theme="light"` on `document.documentElement` and syncs the preference to `localStorage`.
- Added `updateThemeToggleIcon()` helper that sets the correct SVG (sun when dark, moon when light) and updates `aria-label` accordingly.
- `setupThemeToggle()` is called in `DOMContentLoaded` after `setupEventListeners()`.

## Behavior

- **Default**: dark theme (`:root` variables, no `data-theme` attribute).
- **Toggle**: clicking the button in the top-right switches between themes with a 0.3s smooth color transition.
- **Persistence**: preference is saved to `localStorage` under the key `"theme"` and restored on page load without a flash.
- **Accessibility**: the toggle is a native `<button>` (keyboard focusable), has a visible focus ring via `--focus-ring`, and carries an `aria-label` that reflects the action ("Switch to light/dark theme"). SVG icons use `aria-hidden="true"`.

---

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
