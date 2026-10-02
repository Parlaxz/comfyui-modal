// Modal GPU — Tokenized Dark Design System
//
// This stylesheet centralizes the shared design tokens and utility classes
// for the Modal GPU frontend. ensureTestingStyles() injects them once for
// the Studio shell; studio-styles.js layers the Studio-specific rules on top.
//
// H18 Wave G: all legacy testing-{setup,profiles,results,settings,dashboard,
// history}-* sections retired with their modules. Only the tokens and the
// shared components consumed by live Studio surfaces remain.

const STYLE_ID = "comfymodal-testing-styles";

const CSS = `
/* ── Design Tokens ─────────────────────────────────────────── */

:root {
  /* Surface tokens */
  --color-bg-base: #181822;
  --color-bg-toolbar: #1b1b27;
  --color-bg-surface: #20202c;
  --color-bg-raised: #252532;
  --color-bg-overlay: rgba(0, 0, 0, 0.72);
  --color-bg-input: #171723;
  --color-bg-hover: #2a2a38;
  --color-bg-selected: #242c3d;

  /* Border tokens */
  --color-border-default: #2d2d3a;
  --color-border-strong: #353545;
  --color-border-interactive: #454559;
  --color-border-focus: #5a7fdb;
  --color-border-danger: #ef4444;

  /* Text tokens */
  --color-text-primary: #e1e4ea;
  --color-text-secondary: #9aa3b2;
  --color-text-muted: #6f7785;

  /* Accent tokens */
  --color-accent: #5a7fdb;
  --color-accent-hover: #6a8ceb;
  --color-accent-active: #4d6fbe;
  --color-accent-muted: rgba(90, 127, 219, 0.18);
  --color-focus-ring: rgba(90, 127, 219, 0.24);
  --color-selection: rgba(90, 127, 219, 0.14);

  /* Semantic tokens */
  --color-success: #4ade80;
  --color-success-bg: rgba(74, 222, 128, 0.12);
  --color-warning: #f59e0b;
  --color-warning-bg: rgba(245, 158, 11, 0.12);
  --color-danger: #ef4444;
  --color-danger-bg: rgba(239, 68, 68, 0.12);
  --color-info-bg: rgba(90, 127, 219, 0.12);

  /* Disabled tokens */
  --color-disabled-bg: #1c1c28;
  --color-disabled-text: #616877;

  /* Spacing tokens */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 12px;
  --space-lg: 16px;
  --space-xl: 20px;
  --space-2xl: 24px;

  /* Radius tokens */
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;

  /* Typography tokens */
  --font-size-xs: 11px;
  --font-size-sm: 12px;
  --font-size-base: 13px;
  --font-size-lg: 14px;
  --font-size-xl: 16px;
  --font-weight-normal: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;
  --line-height-tight: 1.25;
  --line-height-base: 1.45;

  /* Dimension tokens */
  --control-height-sm: 28px;
  --control-height-md: 36px;
  --header-height: 52px;
  --tab-height: 40px;
  --sidebar-width: 188px;
  --modal-max-width: 1240px;
  --modal-height: 90vh;

  /* Motion tokens */
  --duration-fast: 120ms;
  --duration-normal: 180ms;
  --ease-standard: cubic-bezier(0.2, 0, 0, 1);
}

/* ── Shared Surface Classes ──────────────────────────────── */

.comfymodal-testing-overlay {
  position: fixed;
  inset: 0;
  background: var(--color-bg-overlay);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Thin styled scrollbar on the overlay host */
.comfymodal-testing-overlay::-webkit-scrollbar {
  width: 6px;
}

.comfymodal-testing-overlay::-webkit-scrollbar-track {
  background: transparent;
}

.comfymodal-testing-overlay::-webkit-scrollbar-thumb {
  background: var(--color-border-default);
  border-radius: 3px;
}

.comfymodal-testing-overlay::-webkit-scrollbar-thumb:hover {
  background: var(--color-border-strong);
}

.comfymodal-testing-close {
  background: transparent;
  border: 1px solid var(--color-border-interactive);
  color: var(--color-text-secondary);
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--duration-fast) var(--ease-standard),
              color var(--duration-fast) var(--ease-standard);
}

.comfymodal-testing-close:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.comfymodal-testing-close:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
}

/* ── Sidebar Panel ───────────────────────────────────────── */

.comfymodal-testing-sidebar-panel {
  padding: var(--space-sm) var(--space-md);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.comfymodal-testing-sidebar-panel button {
  background: var(--color-accent);
  border: 1px solid var(--color-accent-hover);
  color: #fff;
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  width: 100%;
  transition: background var(--duration-fast) var(--ease-standard);
}

.comfymodal-testing-sidebar-panel button:hover {
  background: var(--color-accent-hover);
}

.comfymodal-testing-sidebar-panel button:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
}

.comfymodal-testing-sidebar-panel .status-row {
  display: flex;
  justify-content: space-between;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  padding: 2px 0;
}

/* ── Fallback Launcher ────────────────────────────────────── */

.comfymodal-testing-fallback {
  position: fixed;
  right: 8px;
  bottom: 8px;
  z-index: 10000;
}

.comfymodal-testing-fallback button {
  background: var(--color-accent);
  border: 1px solid var(--color-accent-hover);
  color: #fff;
  padding: 8px 16px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  transition: background var(--duration-fast) var(--ease-standard);
}

.comfymodal-testing-fallback button:hover {
  background: var(--color-accent-hover);
}

.comfymodal-testing-fallback button:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
}

/* ═══════════════════════════════════════════════════════════ */
/* SHARED VISUAL COMPONENTS                                     */
/* ═══════════════════════════════════════════════════════════ */

/* ── Button Variants ─────────────────────────────────────── */

.comfymodal-primary-btn {
  background: var(--color-accent);
  border: 1px solid var(--color-accent);
  color: #fff;
  padding: 8px 16px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  transition: background var(--duration-fast) var(--ease-standard),
              border-color var(--duration-fast) var(--ease-standard);
}

.comfymodal-primary-btn:hover {
  background: var(--color-accent-hover);
  border-color: var(--color-accent-hover);
}

.comfymodal-primary-btn:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

.comfymodal-primary-btn:disabled {
  background: var(--color-disabled-bg);
  border-color: var(--color-border-default);
  color: var(--color-disabled-text);
  cursor: not-allowed;
}

.comfymodal-secondary-btn {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-interactive);
  color: var(--color-text-secondary);
  padding: 8px 16px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  transition: background var(--duration-fast) var(--ease-standard),
              border-color var(--duration-fast) var(--ease-standard),
              color var(--duration-fast) var(--ease-standard);
}

.comfymodal-secondary-btn:hover {
  background: var(--color-bg-hover);
  border-color: var(--color-border-strong);
  color: var(--color-text-primary);
}

.comfymodal-secondary-btn:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

.comfymodal-secondary-btn:disabled {
  background: var(--color-disabled-bg);
  border-color: var(--color-border-default);
  color: var(--color-disabled-text);
  cursor: not-allowed;
}

.comfymodal-destructive-btn {
  background: transparent;
  border: 1px solid var(--color-danger);
  color: var(--color-danger);
  padding: 8px 16px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  transition: background var(--duration-fast) var(--ease-standard),
              color var(--duration-fast) var(--ease-standard);
}

.comfymodal-destructive-btn:hover {
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.comfymodal-destructive-btn:focus-visible {
  outline: 2px solid var(--color-danger);
  outline-offset: 2px;
}

.comfymodal-destructive-btn:disabled {
  border-color: var(--color-border-default);
  color: var(--color-disabled-text);
  background: var(--color-disabled-bg);
  cursor: not-allowed;
}

/* ── Input / Select / Textarea ──────────────────────────── */

.comfymodal-input {
  background: var(--color-bg-input);
  border: 1px solid var(--color-border-default);
  color: var(--color-text-primary);
  padding: 6px 10px;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  line-height: var(--line-height-base);
  transition: border-color var(--duration-fast) var(--ease-standard),
              box-shadow var(--duration-fast) var(--ease-standard);
}

.comfymodal-input:focus {
  outline: none;
  border-color: var(--color-border-focus);
  box-shadow: 0 0 0 2px var(--color-focus-ring);
}

.comfymodal-input:hover {
  border-color: var(--color-border-interactive);
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
`;

export function ensureTestingStyles() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = CSS;
  document.head.appendChild(style);
}
