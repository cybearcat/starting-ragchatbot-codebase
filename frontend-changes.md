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
