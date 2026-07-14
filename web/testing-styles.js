// Modal GPU — Tokenized Dark Design System
//
// This stylesheet centralizes all visual rules for the Modal GPU frontend.
// Every screen imports ensureTestingStyles() to inject these shared tokens
// and utility classes. No screen should define its own color/layout tokens.

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

.comfymodal-testing-modal {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  width: 1200px;
  height: 780px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: var(--color-text-primary);
  font-size: var(--font-size-base);
}

.comfymodal-testing-header {
  display: flex;
  align-items: center;
  padding: var(--space-md) var(--space-lg);
  border-bottom: 1px solid var(--color-border-default);
  flex-shrink: 0;
  background: var(--color-bg-toolbar);
}

.comfymodal-testing-header h2 {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  flex: 1;
  color: var(--color-text-primary);
  letter-spacing: 0.01em;
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

/* ── Tab Navigation ──────────────────────────────────────── */

.comfymodal-testing-nav {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--color-border-default);
  flex-shrink: 0;
  padding: 0 var(--space-md);
  background: var(--color-bg-base);
  min-height: var(--tab-height);
}

.comfymodal-testing-nav-btn {
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  padding: 10px 16px;
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  border-bottom: 2px solid transparent;
  transition: color var(--duration-fast) var(--ease-standard),
              background var(--duration-fast) var(--ease-standard),
              border-color var(--duration-fast) var(--ease-standard);
  position: relative;
}

.comfymodal-testing-nav-btn:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-hover);
}

.comfymodal-testing-nav-btn.active {
  color: var(--color-accent);
  border-bottom-color: var(--color-accent);
  font-weight: var(--font-weight-semibold);
}

.comfymodal-testing-nav-btn:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: -2px;
}

/* ── Body / Scroll ────────────────────────────────────────── */

.comfymodal-testing-body {
  flex: 1;
  overflow: hidden;
  min-height: 0;
  background: var(--color-bg-base);
}

/* Thin styled scrollbar */
.comfymodal-testing-body::-webkit-scrollbar {
  width: 6px;
}

.comfymodal-testing-body::-webkit-scrollbar-track {
  background: transparent;
}

.comfymodal-testing-body::-webkit-scrollbar-thumb {
  background: var(--color-border-default);
  border-radius: 3px;
}

.comfymodal-testing-body::-webkit-scrollbar-thumb:hover {
  background: var(--color-border-strong);
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

/* ── Loader & Error ──────────────────────────────────────── */

.comfymodal-testing-loader {
  padding: 20px;
  text-align: center;
  color: var(--color-text-muted);
  font-size: var(--font-size-base);
}

.comfymodal-testing-error {
  padding: 20px;
  text-align: center;
}

.comfymodal-testing-error p {
  color: var(--color-danger);
  margin: 0 0 12px;
  font-size: var(--font-size-base);
}

.comfymodal-testing-retry-btn {
  background: var(--color-bg-hover);
  border: 1px solid var(--color-border-default);
  color: var(--color-text-primary);
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: background var(--duration-fast) var(--ease-standard);
}

.comfymodal-testing-retry-btn:hover {
  background: var(--color-bg-raised);
}

.comfymodal-testing-retry-btn:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
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

/* ── Hero Card (blocked/unhealthy deploy state) ──────────── */

.comfymodal-hero {
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
  padding: var(--space-xl);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.comfymodal-hero h3 {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

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

/* ── Mode Badge (normalization / Legacy T2I) ────────────── */

.comfymodal-mode-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  line-height: var(--line-height-tight);
}

.comfymodal-mode-badge.norm {
  background: var(--color-info-bg);
  color: var(--color-accent);
}

.comfymodal-mode-badge.legacy {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

/* ── Status Badge ────────────────────────────────────────── */

.comfymodal-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  line-height: var(--line-height-tight);
}

.comfymodal-status-badge.success {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.comfymodal-status-badge.warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.comfymodal-status-badge.danger {
  background: var(--color-danger-bg);
  color: var(--color-danger);
}

.comfymodal-status-badge.info {
  background: var(--color-info-bg);
  color: var(--color-accent);
}

/* ── Input / Select / Textarea ──────────────────────────── */

.comfymodal-input,
.comfymodal-testing-input,
.testing-setup-input,
.testing-setup-textarea,
.testing-setup-select,
.testing-results-select {
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

.comfymodal-input:focus,
.comfymodal-testing-input:focus,
.testing-setup-input:focus,
.testing-setup-textarea:focus,
.testing-setup-select:focus,
.testing-results-select:focus {
  outline: none;
  border-color: var(--color-border-focus);
  box-shadow: 0 0 0 2px var(--color-focus-ring);
}

.comfymodal-input:hover,
.comfymodal-testing-input:hover,
.testing-setup-input:hover,
.testing-setup-textarea:hover,
.testing-setup-select:hover,
.testing-results-select:hover {
  border-color: var(--color-border-interactive);
}

.comfymodal-input.input-error,
.comfymodal-testing-input.input-error,
.testing-setup-input.input-error {
  border-color: var(--color-border-danger);
  box-shadow: 0 0 0 2px var(--color-danger-bg);
}

/* ── Focus-visible ring (global) ────────────────────────── */

:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
}

/* ── Progress Bar ────────────────────────────────────────── */

.comfymodal-progress-bar {
  width: 100%;
  height: 6px;
  background: var(--color-bg-input);
  border-radius: 3px;
  overflow: hidden;
}

.comfymodal-progress-bar .comfymodal-progress-fill {
  height: 100%;
  background: var(--color-accent);
  border-radius: 3px;
  transition: width var(--duration-normal) var(--ease-standard);
}

.comfymodal-progress-bar .comfymodal-progress-fill.success {
  background: var(--color-success);
}

.comfymodal-progress-bar .comfymodal-progress-fill.warning {
  background: var(--color-warning);
}

/* ── Section Card ────────────────────────────────────────── */

.comfymodal-section-card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.comfymodal-section-card-header {
  display: flex;
  align-items: center;
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-toolbar);
  border-bottom: 1px solid var(--color-border-default);
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}

.comfymodal-section-card-body {
  padding: var(--space-md);
}

/* ── Dashboard Cards ─────────────────────────────────────── */

.comfymodal-dashboard-card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  padding: var(--space-md);
}

.comfymodal-dashboard-card h3 {
  margin: 0 0 var(--space-sm);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

/* ── Utility Toolbar ─────────────────────────────────────── */

.comfymodal-utility-toolbar {
  display: flex;
  gap: var(--space-sm);
  flex-wrap: wrap;
  align-items: center;
}

.comfymodal-utility-toolbar .comfymodal-secondary-btn {
  padding: 6px 12px;
  font-size: var(--font-size-xs);
}

/* ── Deployment Strip ────────────────────────────────────── */

.comfymodal-deploy-strip {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

/* ── Settings Wrapper ────────────────────────────────────── */

.comfymodal-settings-wrapper {
  display: flex;
  gap: var(--space-lg);
  height: 100%;
}

.comfymodal-settings-wrapper .testing-settings-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 160px;
  flex-shrink: 0;
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  padding: var(--space-sm);
}

.comfymodal-settings-wrapper .testing-settings-nav .testing-settings-nav-btn {
  background: transparent;
  border: none;
  color: var(--color-text-secondary);
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  text-align: left;
  transition: background var(--duration-fast) var(--ease-standard),
              color var(--duration-fast) var(--ease-standard);
}

.comfymodal-settings-wrapper .testing-settings-nav .testing-settings-nav-btn:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.comfymodal-settings-wrapper .testing-settings-nav .testing-settings-nav-btn.active,
.comfymodal-settings-wrapper .testing-settings-nav .testing-settings-nav-btn.comfymodal-nav-btn-active {
  background: var(--color-selection);
  color: var(--color-accent);
  font-weight: var(--font-weight-semibold);
}

.comfymodal-settings-wrapper .testing-settings-body {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
}

/* ── History Row ─────────────────────────────────────────── */

.comfymodal-history-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard);
}

.comfymodal-history-row:hover {
  background: var(--color-bg-hover);
}

.comfymodal-history-row .testing-history-thumb {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-input);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  overflow: hidden;
}

.comfymodal-history-row .testing-history-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.comfymodal-history-row .testing-history-kind {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  flex-shrink: 0;
  min-width: 48px;
}

.comfymodal-history-row .testing-history-status {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  flex-shrink: 0;
  min-width: 60px;
}

.comfymodal-history-row .testing-history-status .status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.comfymodal-history-row .testing-history-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  flex-shrink: 0;
  min-width: 80px;
  font-variant-numeric: tabular-nums;
}

.comfymodal-history-row .testing-history-duration {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  flex-shrink: 0;
  min-width: 50px;
  font-variant-numeric: tabular-nums;
}

.comfymodal-history-row .testing-history-model {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  flex-shrink: 0;
  min-width: 60px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Results Layers ──────────────────────────────────────── */

.testing-results-root {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.testing-results-root [data-section="controls"] {
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
}

.testing-results-root [data-section="progress"] {
  padding: var(--space-md);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
}

.testing-results-root [data-section="grid"] {
  background: transparent;
}

/* ── Results: visual hierarchy improvements ──────────────── */

.testing-results-root [data-section="command-bar"] {
  padding: var(--space-md);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
  margin-bottom: var(--space-md);
}

.testing-results-root [data-section="summary"] {
  padding: var(--space-lg);
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
  margin-bottom: var(--space-md);
}

.testing-results-root [data-section="summary"] .testing-results-summary-card {
  gap: var(--space-xl);
  padding: 0;
  background: transparent;
  border: none;
}

.testing-results-root [data-section="summary"] .testing-results-summary-primary .summary-stat-value {
  font-size: 28px;
  font-weight: var(--font-weight-semibold);
}

.testing-results-root [data-section="summary"] .summary-stat-value {
  font-size: var(--font-size-xl);
}

.testing-results-root [data-section="summary"] .summary-stat-label {
  font-size: var(--font-size-sm);
  letter-spacing: 0.06em;
}

/* ── Setup: field grid utility ───────────────────────────── */

.testing-setup-field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-md);
}

/* ── Setup: finish zone ──────────────────────────────────── */

.testing-setup-finish-zone {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-lg);
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
}

/* ── Setup: contextual profile toolbar ───────────────────── */

.testing-setup-profile-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  align-items: center;
  margin-bottom: var(--space-sm);
}

/* ── Results: command bar groups ─────────────────────────── */

.testing-results-command-bar {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
}

.testing-results-command-main {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  align-items: center;
}

.testing-results-command-danger {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  align-items: center;
  padding-top: var(--space-xs);
  border-top: 1px solid var(--color-border-default);
}

/* ── Results: summary card ───────────────────────────────── */

.testing-results-summary-card {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-md);
  padding: var(--space-md);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
  font-size: var(--font-size-sm);
}

.testing-results-summary-card .summary-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.testing-results-summary-card .summary-stat-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-weight: var(--font-weight-medium);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.testing-results-summary-card .summary-stat-value {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.testing-results-summary-card .summary-stat-value.completed {
  color: var(--color-success);
}

.testing-results-summary-card .summary-stat-value.failed {
  color: var(--color-danger);
}

.testing-results-summary-card .summary-stat-value.skipped {
  color: var(--color-text-muted);
}

/* ── Results: gallery ────────────────────────────────────── */

.testing-results-gallery {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* ── Results: empty state ────────────────────────────────── */

.testing-results-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-2xl) var(--space-lg);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  text-align: center;
  border: 1px dashed var(--color-border-default);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
}

/* ── Page-level surface primitives ───────────────────────── */

.testing-dashboard-page,
.testing-setup-page,
.testing-profiles-page,
.testing-results-page,
.testing-history-page,
.testing-settings-page {
  height: 100%;
  overflow-y: auto;
  padding: var(--space-xl);
  box-sizing: border-box;
}

/* ── Settings: root layout ────────────────────────────────── */

.testing-settings-root {
  height: 100%;
  overflow: hidden;
}

.testing-settings-root .comfymodal-settings-wrapper {
  height: 100%;
}

.testing-settings-root .testing-settings-nav {
  overflow-y: auto;
  max-height: 100%;
}

.testing-settings-root .testing-settings-body {
  overflow-y: auto;
  max-height: 100%;
  padding: var(--space-sm);
}

/* ── Profiles: workspace ─────────────────────────────────── */

.testing-profiles-root {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  height: 100%;
}

.testing-profiles-create-card,
.testing-profiles-list,
.testing-profiles-editor {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  padding: var(--space-md);
}

.testing-profiles-workspace {
  display: grid;
  grid-template-columns: minmax(300px, 360px) minmax(0, 1fr);
  gap: var(--space-md);
  min-height: 0;
  flex: 1;
}

.testing-profiles-list,
.testing-profiles-editor {
  min-height: 0;
  overflow-y: auto;
}

.testing-profiles-pane-title,
.testing-profiles-section-title,
.testing-profiles-editor-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.testing-profiles-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.testing-profiles-field-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.testing-profiles-inline-actions,
.testing-profiles-row-actions {
  display: flex;
  gap: var(--space-xs);
  flex-wrap: wrap;
}

.testing-profiles-list-rows {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin-top: var(--space-sm);
}

.testing-profiles-row {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  padding: var(--space-sm);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-raised);
}

.testing-profiles-row-active {
  border-color: var(--color-accent);
}

.testing-profiles-row-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
}

.testing-profiles-row-name {
  background: transparent;
  border: none;
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  text-align: left;
  cursor: pointer;
  padding: 0;
}

.testing-profiles-row-summary,
.testing-profiles-editor-summary,
.testing-profiles-section-help,
.testing-profiles-status,
.testing-profiles-empty-state,
.testing-profiles-warning-box,
.testing-profiles-error-box {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.testing-profiles-warning-box {
  color: var(--color-warning);
}

.testing-profiles-error-box {
  color: var(--color-danger);
}

.testing-profiles-model-section,
.testing-profiles-mapping-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin-top: var(--space-md);
  padding-top: var(--space-md);
  border-top: 1px solid var(--color-border-default);
}

.testing-profiles-model-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-sm);
}

.testing-profiles-mapping-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.testing-profiles-mapping-row {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: var(--space-sm);
  align-items: center;
}

.testing-profiles-slot-label {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
}

@media (max-width: 900px) {
  .testing-profiles-workspace {
    grid-template-columns: 1fr;
  }

  .testing-profiles-model-grid,
  .testing-profiles-mapping-row {
    grid-template-columns: 1fr;
  }
}

/* ── Dashboard: primary actions group ────────────────────── */

.testing-dashboard-primary-actions {
  display: flex;
  align-items: center;
  gap: var(--space-lg);
  margin-bottom: var(--space-lg);
}

.testing-dashboard-primary-actions .testing-dashboard-cta-main {
  padding: 12px 28px;
  font-size: var(--font-size-lg);
}

.testing-dashboard-secondary-actions {
  display: flex;
  gap: var(--space-sm);
}

/* ── Dashboard: utility toolbar (subordinate) ────────────── */

.testing-dashboard-utility-toolbar {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
  opacity: 0.75;
  transition: opacity var(--duration-fast) var(--ease-standard);
}

.testing-dashboard-utility-toolbar:hover {
  opacity: 1;
}

/* ── Dashboard: metrics hierarchy ────────────────────────── */

.testing-dashboard-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-md);
}

.testing-dashboard-metric {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  padding: var(--space-md);
}

.testing-dashboard-metric h3 {
  margin: 0 0 var(--space-sm);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.testing-dashboard-metric-primary {
  background: var(--color-bg-raised);
  border-color: var(--color-border-strong);
}

.testing-dashboard-metric-primary h3 {
  color: var(--color-text-primary);
}

/* ── Setup: collapsible section cards ────────────────────── */

.testing-setup-section-collapsible {
  transition: opacity var(--duration-normal) var(--ease-standard);
}

.testing-setup-section-collapsible[data-collapsed="true"] {
  opacity: 0.5;
}

.testing-setup-section-collapsible[data-collapsed="true"] .comfymodal-section-card-body {
  display: none;
}

.testing-setup-section-collapsible[data-collapsed="false"] {
  opacity: 1;
}

/* ── Setup: name/notes large inputs ────────────────────────── */

.testing-setup-name-input {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  padding: 10px 14px;
  min-height: 40px;
  width: 100%;
}

.testing-setup-notes-textarea {
  font-size: var(--font-size-base);
  padding: 10px 14px;
  min-height: 80px;
  width: 100%;
  resize: vertical;
  line-height: var(--line-height-base);
}

.testing-setup-field-large {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.testing-setup-field-large .testing-setup-field-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

/* ── Setup: experiment fields ──────────────────────────────── */

.testing-setup-experiment-fields {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* ── Setup: model profiles section ────────────────────────── */

.testing-setup-model-profiles {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.testing-setup-model-profile-entry {
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.testing-setup-model-profile-name {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-accent);
}

/* ── Setup: sampler grid with enable/disable ──────────────── */

.testing-setup-sampler-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-xs) var(--space-sm);
}

.testing-setup-sampler-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard);
}

.testing-setup-sampler-row:hover {
  background: var(--color-bg-hover);
}

.testing-setup-sampler-row.testing-setup-sampler-disabled {
  opacity: 0.45;
}

.testing-setup-sampler-row.testing-setup-sampler-enabled {
  opacity: 1;
}

.testing-setup-sampler-toggle {
  accent-color: var(--color-accent);
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.testing-setup-sampler-name {
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
}

.testing-setup-sampler-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.testing-setup-sampler-header {
  display: flex;
  align-items: baseline;
  gap: var(--space-sm);
}

.testing-setup-sampler-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-weight: var(--font-weight-normal);
}

/* ── Setup: prompt editor ──────────────────────────────────── */

.testing-setup-prompt-editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.testing-setup-prompt-textarea {
  min-height: 72px;
  width: 100%;
  resize: vertical;
  line-height: var(--line-height-base);
  font-size: var(--font-size-base);
}

/* ── Setup: preset bar ─────────────────────────────────────── */

.testing-setup-preset-bar {
  display: flex;
  gap: var(--space-sm);
  align-items: center;
  padding-top: var(--space-sm);
  border-top: 1px solid var(--color-border-default);
}

.testing-setup-preset-dropdown {
  flex: 1;
  min-width: 160px;
}

.testing-setup-save-preset-btn {
  flex-shrink: 0;
}

/* ── Setup: workflow profile rows ──────────────────────────── */

.testing-setup-create-row {
  display: flex;
  gap: var(--space-sm);
  align-items: center;
  margin-bottom: var(--space-sm);
}

.testing-setup-profiles {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.testing-setup-profile-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  transition: border-color var(--duration-fast) var(--ease-standard);
}

.testing-setup-profile-row.testing-setup-profile-selected {
  border-color: var(--color-accent);
  background: var(--color-accent-muted);
}

.testing-setup-profile-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.testing-setup-profile-name {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.testing-setup-profile-triple {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.testing-setup-profile-actions {
  display: flex;
  gap: var(--space-xs);
  flex-shrink: 0;
}

.testing-setup-profile-action-btn {
  padding: 4px 10px !important;
  font-size: var(--font-size-xs) !important;
}

/* ── Setup: sections container ─────────────────────────────── */

.testing-setup-sections {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* ── Setup: empty hints ────────────────────────────────────── */

.testing-setup-empty-hint {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  padding: var(--space-sm) 0;
}

/* ── Setup: tri-state generation type ────────────────────── */

.testing-setup-generation-type {
  display: flex;
  gap: var(--space-md);
}

.testing-setup-tri-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-xs);
  padding: var(--space-md);
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  flex: 1;
  transition: border-color var(--duration-fast) var(--ease-standard),
              background var(--duration-fast) var(--ease-standard);
}

.testing-setup-tri-state:hover {
  border-color: var(--color-border-interactive);
  background: var(--color-bg-hover);
}

.testing-setup-tri-state.testing-setup-tri-state-active {
  border-color: var(--color-accent);
  background: var(--color-accent-muted);
}

.testing-setup-tri-state input[type="radio"] {
  accent-color: var(--color-accent);
}

.testing-setup-tri-state-label {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.testing-setup-tri-state-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  text-align: center;
}

/* ── Setup: workflow-local config ────────────────────────── */

.testing-setup-workflow-local-config {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  margin-top: var(--space-sm);
}

.testing-setup-workflow-local-entry {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.testing-setup-workflow-local-entry summary {
  cursor: pointer;
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-toolbar);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  user-select: none;
}

.testing-setup-workflow-local-entry summary:hover {
  color: var(--color-accent);
}

.testing-setup-workflow-local-body {
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.testing-setup-section-subtitle {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-accent);
  margin: 0;
  padding: 0;
}

/* ── Setup: model stack ──────────────────────────────────── */

.testing-setup-model-stack {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

/* ── Setup: section divider ──────────────────────────────── */

.testing-setup-section-divider {
  height: 1px;
  background: var(--color-border-default);
  margin: var(--space-sm) 0;
}

/* ── Setup: test values ──────────────────────────────────── */

.testing-setup-test-values {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.testing-setup-test-values-group {
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--color-bg-raised);
}

.testing-setup-test-values-group summary {
  cursor: pointer;
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-toolbar);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  user-select: none;
}

.testing-setup-test-values-group summary:hover {
  color: var(--color-accent);
}

.testing-setup-test-values-group-body {
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* ── Setup: sticky summary ───────────────────────────────── */

.testing-setup-sticky-summary {
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-raised);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-sm);
}

.testing-setup-sticky-summary-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-md);
  align-items: center;
}

.testing-setup-sticky-summary-item {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}

/* ── Setup: section status messages ────────────────────────── */

.testing-setup-section-status {
  font-size: var(--font-size-xs);
  padding: 4px 0;
  min-height: 20px;
}

.testing-setup-status-ok {
  color: var(--color-success);
}

.testing-setup-status-error {
  color: var(--color-danger);
}

.testing-setup-status-warn {
  color: var(--color-warning);
}

.testing-setup-status-info {
  color: var(--color-accent);
}

/* ── Setup: profile action menu ──────────────────────────── */

.testing-setup-profile-menu {
  display: inline-block;
  position: relative;
}

.testing-setup-profile-menu summary {
  cursor: pointer;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-default);
  user-select: none;
}

.testing-setup-profile-menu summary:hover {
  border-color: var(--color-border-interactive);
  color: var(--color-text-secondary);
}

.testing-setup-profile-menu[open] summary {
  border-color: var(--color-accent);
}

.testing-setup-profile-menu .profile-menu-body {
  position: absolute;
  top: 100%;
  right: 0;
  z-index: 20;
  min-width: 160px;
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  padding: var(--space-xs);
  display: flex;
  flex-direction: column;
  gap: 2px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}

/* ── Setup: advanced toggle ──────────────────────────────── */

.testing-setup-advanced-toggle {
  margin-top: var(--space-sm);
  border-top: 1px solid var(--color-border-default);
  padding-top: var(--space-sm);
}

.testing-setup-advanced-toggle summary {
  cursor: pointer;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-weight: var(--font-weight-medium);
  user-select: none;
}

.testing-setup-advanced-toggle summary:hover {
  color: var(--color-text-secondary);
}

.testing-setup-advanced-toggle .advanced-body {
  margin-top: var(--space-sm);
}

/* ── Setup: prominent finish zone ────────────────────────── */

.testing-setup-finish-zone-prominent {
  border: 2px solid var(--color-accent);
  background: var(--color-bg-raised);
}

/* ═══════════════════════════════════════════════════════════ */
/* SETUP: DEEPER WORKFLOW/MODEL-STACK/LORA SEMANTICS           */
/* ═══════════════════════════════════════════════════════════ */

/* ── Setup: generation type tiles (T2I vs I2I) ──────────── */

.testing-setup-generation-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-lg);
  background: var(--color-bg-raised);
  border: 2px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  cursor: pointer;
  flex: 1;
  transition: border-color var(--duration-fast) var(--ease-standard),
              background var(--duration-fast) var(--ease-standard),
              transform var(--duration-fast) var(--ease-standard);
  text-align: center;
}

.testing-setup-generation-tile:hover {
  border-color: var(--color-border-interactive);
  background: var(--color-bg-hover);
  transform: translateY(-1px);
}

.testing-setup-generation-tile.testing-setup-generation-tile-active {
  border-color: var(--color-accent);
  background: var(--color-accent-muted);
}

.testing-setup-generation-tile input[type="radio"] {
  accent-color: var(--color-accent);
  width: 18px;
  height: 18px;
}

.testing-setup-generation-tile-icon {
  font-size: 28px;
  line-height: 1;
}

.testing-setup-generation-tile-label {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.testing-setup-generation-tile-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  line-height: var(--line-height-base);
}

/* ── Setup: variable grid (What Changes?) ───────────────── */

.testing-setup-what-changes {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.testing-setup-variable-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-md);
}

@media (max-width: 1200px) {
  .testing-setup-variable-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .testing-setup-variable-grid {
    grid-template-columns: 1fr;
  }
}

.testing-setup-var-tile {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-md);
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  transition: border-color var(--duration-fast) var(--ease-standard),
              background var(--duration-fast) var(--ease-standard);
}

.testing-setup-var-tile:hover {
  border-color: var(--color-border-interactive);
}

/* Variable mode colors */
.testing-setup-var-tile.testing-setup-var-mode-default {
  border-color: var(--color-border-default);
}

.testing-setup-var-tile.testing-setup-var-mode-testing {
  border-color: var(--color-accent);
  background: linear-gradient(135deg, var(--color-bg-raised) 0%, var(--color-accent-muted) 100%);
}

.testing-setup-var-tile.testing-setup-var-mode-controlled {
  border-color: var(--color-warning);
  background: linear-gradient(135deg, var(--color-bg-raised) 0%, var(--color-warning-bg) 100%);
}

.testing-setup-var-tile.testing-setup-var-tile-disabled {
  opacity: 0.4;
  pointer-events: none;
}

.testing-setup-var-tile-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.testing-setup-var-tile-name {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.testing-setup-var-tile-actions {
  display: flex;
  gap: 2px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-input);
}

.testing-setup-var-mode-btn {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--color-text-secondary);
  padding: 4px 8px;
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard),
              color var(--duration-fast) var(--ease-standard);
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
}

.testing-setup-var-mode-btn:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.testing-setup-var-mode-btn.testing-setup-var-mode-btn-active {
  background: var(--color-accent);
  color: #fff;
  font-weight: var(--font-weight-semibold);
}

.testing-setup-var-mode-btn.testing-setup-var-mode-btn-testing.testing-setup-var-mode-btn-active {
  background: var(--color-accent);
}

.testing-setup-var-mode-btn.testing-setup-var-mode-btn-controlled.testing-setup-var-mode-btn-active {
  background: var(--color-warning);
  color: #000;
}

/* ── Setup: stack editor ────────────────────────────────── */

.testing-setup-stack-editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.testing-setup-stack-card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.testing-setup-stack-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
}

.testing-setup-stack-id {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-accent);
}

.testing-setup-stack-card-actions {
  display: flex;
  gap: var(--space-xs);
}

.testing-setup-stack-action-btn {
  padding: 3px 8px !important;
  font-size: var(--font-size-xs) !important;
}

/* ── Setup: LoRA scope row ───────────────────────────────── */

.testing-setup-lora-scope-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg-input);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-sm);
}

.testing-setup-lora-scope-btn {
  padding: 3px 10px !important;
  font-size: var(--font-size-xs) !important;
  min-width: 140px;
}

/* ── Setup: per-stack LoRA section ───────────────────────── */

.testing-setup-stack-loras {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding-top: var(--space-sm);
  border-top: 1px solid var(--color-border-default);
}

.testing-setup-workflow-heading {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  padding: var(--space-sm) 0;
}

.testing-setup-wf-lora-section {
  margin-top: var(--space-sm);
}

/* ── Setup: inactive test values group ───────────────────── */

.testing-setup-test-values-inactive {
  opacity: 0.45;
}

.testing-setup-test-values-inactive summary {
  color: var(--color-text-muted);
}

/* ── Results: command routine group ──────────────────────── */

.testing-results-command-routine {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  align-items: center;
}

/* ── Results: summary primary emphasis ───────────────────── */

.testing-results-summary-primary {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
  color: var(--color-success);
}

.testing-results-summary-primary .summary-stat-value {
  font-size: 24px;
}

/* ── History: two-line skim row ──────────────────────────── */

.testing-history-row-main {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  flex: 1;
  min-width: 0;
}

.testing-history-row-meta {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  flex-wrap: wrap;
}

/* ── Reduced Motion ──────────────────────────────────────── */

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}

/* ── Responsive helpers ─────────────────────────────────── */

/* ── Results: Matrix layout ──────────────────────────────── */

.testing-results-matrix-wrap {
  margin-bottom: var(--space-lg);
}

.testing-results-matrix-scroll {
  overflow: auto;
  max-height: 600px;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-surface);
}

.testing-results-matrix {
  border-collapse: separate;
  border-spacing: 0;
  min-width: 100%;
  font-size: var(--font-size-xs, 11px);
}

.testing-results-matrix th,
.testing-results-matrix td {
  padding: var(--space-xs);
  border-bottom: 1px solid var(--color-border-default);
  border-right: 1px solid var(--color-border-default);
  text-align: left;
  vertical-align: top;
}

.testing-results-matrix th {
  background: var(--color-bg-toolbar);
  font-weight: var(--font-weight-semibold, 600);
  color: var(--color-text-secondary, #9aa3b2);
  white-space: nowrap;
}

/* Sticky headers */
.testing-results-matrix-corner {
  position: sticky;
  top: 0;
  left: 0;
  z-index: 3;
  background: var(--color-bg-raised, #252532);
  min-width: 80px;
  font-size: var(--font-size-xs, 11px);
  color: var(--color-text-muted, #6f7785);
}

.testing-results-matrix-col-header {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--color-bg-toolbar);
  min-width: 100px;
  padding: var(--space-sm) var(--space-xs) !important;
  font-size: var(--font-size-xs, 11px);
  color: var(--color-text-secondary, #9aa3b2);
  border-top: none;
}

.testing-results-matrix-row-header {
  position: sticky;
  left: 0;
  z-index: 1;
  background: var(--color-bg-toolbar);
  min-width: 80px;
  padding: var(--space-sm) var(--space-xs) !important;
  font-size: var(--font-size-xs, 11px);
  color: var(--color-text-secondary, #9aa3b2);
  border-left: none;
}

.testing-results-matrix th:first-child,
.testing-results-matrix td:first-child {
  border-left: none;
}

.testing-results-matrix thead tr:first-child th {
  border-top: none;
}

/* Matrix cell (compact card wrapper) */
.testing-results-matrix-cell {
  padding: 2px !important;
  min-width: 90px;
  min-height: 90px;
  vertical-align: middle;
}

.testing-results-matrix-empty {
  background: var(--color-bg-input, #171723);
}

/* ── Compact cell variant ────────────────────────────────── */

.testing-results-cell-compact {
  display: inline-block;
  width: 86px;
  border-radius: var(--radius-sm, 4px);
  overflow: hidden;
  cursor: pointer;
  background: var(--color-bg-raised, #252532);
  border: 1px solid var(--color-border-default, #2d2d3a);
  transition: border-color var(--duration-fast, 120ms) var(--ease-standard, cubic-bezier(0.2,0,0,1));
}

.testing-results-cell-compact:hover {
  border-color: var(--color-border-interactive, #454559);
}

.testing-results-cell-compact .testing-results-cell-thumb {
  width: 86px;
  height: 86px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  position: relative;
}

.testing-results-cell-compact .testing-results-cell-thumb img {
  width: 86px;
  height: 86px;
  object-fit: cover;
  display: block;
}

.testing-results-cell-compact .testing-results-cell-thumb-placeholder {
  width: 86px;
  height: 86px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xs, 11px);
  color: var(--color-text-muted, #6f7785);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.testing-results-cell-compact .testing-results-cell-attempt {
  position: absolute;
  bottom: 2px;
  right: 2px;
  background: rgba(0, 0, 0, 0.7);
  color: var(--color-text-primary, #e1e4ea);
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 2px;
  line-height: 1.2;
}

.testing-results-cell-compact .testing-results-cell-meta {
  display: none;
}

.testing-results-cell-compact .testing-results-cell-error {
  display: none;
}

/* Compact cell status borders */
.testing-results-cell-compact.testing-results-cell-completed {
  border-color: var(--color-success, #4ade80);
}

.testing-results-cell-compact.testing-results-cell-failed {
  border-color: var(--color-danger, #ef4444);
}

.testing-results-cell-compact.testing-results-cell-running {
  border-color: var(--color-accent, #5a7fdb);
}

.testing-results-cell-compact.testing-results-cell-pending {
  border-color: var(--color-border-default, #2d2d3a);
  opacity: 0.6;
}

/* ── Labeled sequence (1 axis) ────────────────────────────── */

.testing-results-axis-sequence {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.testing-results-axis-sequence-item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-md);
  padding: var(--space-sm);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  transition: border-color var(--duration-fast, 120ms) var(--ease-standard, cubic-bezier(0.2,0,0,1));
}

.testing-results-axis-sequence-item:hover {
  border-color: var(--color-border-interactive, #454559);
}

.testing-results-axis-label {
  flex-shrink: 0;
  min-width: 160px;
  font-size: var(--font-size-sm, 12px);
  font-weight: var(--font-weight-medium, 500);
  color: var(--color-accent, #5a7fdb);
  padding: var(--space-sm) 0;
  font-variant-numeric: tabular-nums;
}

@media (max-width: 700px) {
  .testing-results-axis-sequence-item {
    flex-direction: column;
    gap: var(--space-sm);
  }
  .testing-results-axis-label {
    min-width: unset;
  }
}

/* ── Group headers (3D / 4D) ─────────────────────────────── */

.testing-results-3d-wrapper,
.testing-results-4d-outer {
  display: flex;
  flex-direction: column;
  gap: var(--space-xl);
}

.testing-results-3d-group,
.testing-results-4d-group {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.testing-results-axis-group-header {
  margin: 0;
  padding: var(--space-md) var(--space-lg);
  font-size: var(--font-size-base, 13px);
  font-weight: var(--font-weight-semibold, 600);
  color: var(--color-text-primary, #e1e4ea);
  background: var(--color-bg-toolbar);
  border-bottom: 1px solid var(--color-border-default);
  letter-spacing: 0.01em;
}

.testing-results-4d-inner {
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.testing-results-4d-inner-group {
  background: var(--color-bg-raised);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.testing-results-axis-inner-header {
  margin: 0;
  padding: var(--space-sm) var(--space-md);
  font-size: var(--font-size-sm, 12px);
  font-weight: var(--font-weight-medium, 500);
  color: var(--color-accent, #5a7fdb);
  background: var(--color-bg-raised, #252532);
  border-bottom: 1px solid var(--color-border-default);
}

.testing-results-3d-group .testing-results-matrix-wrap,
.testing-results-4d-inner-group .testing-results-matrix-wrap {
  margin: var(--space-md);
}

/* ── Too many axes fallback ──────────────────────────────── */

.testing-results-too-many-axes {
  border-color: var(--color-warning, #f59e0b) !important;
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.12)) !important;
}

/* ── Responsive: matrices on small screens ────────────────── */

@media (max-width: 700px) {
  .testing-results-matrix-scroll {
    max-height: 400px;
  }
  .testing-results-matrix th,
  .testing-results-matrix td {
    padding: 2px;
  }
  .testing-results-matrix-cell {
    min-width: 70px;
    min-height: 70px;
  }
  .testing-results-cell-compact {
    width: 66px;
  }
  .testing-results-cell-compact .testing-results-cell-thumb,
  .testing-results-cell-compact .testing-results-cell-thumb img,
  .testing-results-cell-compact .testing-results-cell-thumb-placeholder {
    width: 66px;
    height: 66px;
  }
  .testing-results-matrix-col-header {
    min-width: 70px;
    font-size: 10px;
  }
  .testing-results-matrix-row-header {
    min-width: 60px;
    font-size: 10px;
  }
}

@media (max-width: 900px) {
  .comfymodal-settings-wrapper {
    flex-direction: column;
  }

  .comfymodal-settings-wrapper .testing-settings-nav {
    flex-direction: row;
    overflow-x: auto;
    min-width: unset;
  }

  .comfymodal-history-row {
    flex-wrap: wrap;
  }
}

/* ── Results: running spinner overlay ────────────────────── */

@keyframes testing-spinner-rotate {
  to { transform: rotate(360deg); }
}

.testing-results-running-spinner {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,0.35);
  z-index: 2;
}

.testing-results-running-spinner::after {
  content: "";
  width: 24px;
  height: 24px;
  border: 2px solid var(--color-border-interactive, #454559);
  border-top-color: var(--color-accent, #5a7fdb);
  border-radius: 50%;
  animation: testing-spinner-rotate 0.7s linear infinite;
}

.testing-results-cell-compact .testing-results-running-spinner::after {
  width: 18px;
  height: 18px;
}

/* ── Results: gallery layout with side panel ────────────── */

.testing-results-gallery-layout {
  display: flex;
  gap: var(--space-md);
  align-items: flex-start;
}

.testing-results-gallery-body-wrap {
  flex: 1;
  min-width: 0;
}

/* ── Results: side panel ────────────────────────────────── */

.testing-results-side-panel {
  width: 320px;
  flex-shrink: 0;
  background: var(--color-bg-raised, #252532);
  border: 1px solid var(--color-border-strong, #353545);
  border-radius: var(--radius-lg, 8px);
  overflow: hidden;
  transition: opacity var(--duration-normal, 180ms) var(--ease-standard, cubic-bezier(0.2,0,0,1)),
              transform var(--duration-normal, 180ms) var(--ease-standard, cubic-bezier(0.2,0,0,1));
}

.testing-results-side-panel-hidden {
  display: none;
}

.testing-results-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-sm, 8px) var(--space-md, 12px);
  background: var(--color-bg-toolbar, #1b1b27);
  border-bottom: 1px solid var(--color-border-default, #2d2d3a);
}

.testing-results-detail-title {
  font-size: var(--font-size-sm, 12px);
  font-weight: var(--font-weight-semibold, 600);
  color: var(--color-text-primary, #e1e4ea);
  letter-spacing: 0.02em;
}

.testing-results-detail-close {
  background: transparent;
  border: none;
  color: var(--color-text-muted, #6f7785);
  font-size: 16px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: var(--radius-sm, 4px);
  line-height: 1;
  transition: color var(--duration-fast, 120ms) var(--ease-standard, cubic-bezier(0.2,0,0,1)),
              background var(--duration-fast, 120ms) var(--ease-standard, cubic-bezier(0.2,0,0,1));
}

.testing-results-detail-close:hover {
  color: var(--color-text-primary, #e1e4ea);
  background: var(--color-bg-hover, #2a2a38);
}

.testing-results-detail-body {
  padding: var(--space-md, 12px);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm, 8px);
  max-height: 400px;
  overflow-y: auto;
}

.testing-results-detail-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--space-sm, 8px);
  padding: var(--space-xs, 4px) 0;
  border-bottom: 1px solid var(--color-border-default, #2d2d3a);
  font-size: var(--font-size-xs, 11px);
}

.testing-results-detail-row:last-child {
  border-bottom: none;
}

.testing-results-detail-label {
  color: var(--color-text-muted, #6f7785);
  font-weight: var(--font-weight-medium, 500);
  flex-shrink: 0;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.testing-results-detail-value {
  color: var(--color-text-primary, #e1e4ea);
  text-align: right;
  word-break: break-all;
  font-variant-numeric: tabular-nums;
}

/* Axis parameters in red */
.testing-results-detail-axis .testing-results-detail-label,
.testing-results-detail-axis .testing-results-detail-value {
  color: var(--color-danger, #ef4444);
}

/* ── Results: progress bars at grid bottom ──────────────── */

.testing-results-progress-bars {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm, 8px);
  padding: var(--space-md, 12px);
  background: var(--color-bg-surface, #20202c);
  border: 1px solid var(--color-border-default, #2d2d3a);
  border-radius: var(--radius-lg, 8px);
  margin-top: var(--space-md, 12px);
}

.testing-results-progress-bar-row {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs, 4px);
}

.testing-results-progress-bar-row:first-child {
  margin-bottom: var(--space-xs, 4px);
}

.testing-results-progress-bar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--font-size-xs, 11px);
  color: var(--color-text-secondary, #9aa3b2);
  font-weight: var(--font-weight-medium, 500);
}

.testing-results-progress-bar-pct {
  font-variant-numeric: tabular-nums;
  font-weight: var(--font-weight-semibold, 600);
  color: var(--color-text-primary, #e1e4ea);
}

.testing-results-progress-track {
  width: 100%;
  height: 6px;
  background: var(--color-bg-input, #171723);
  border-radius: 3px;
  overflow: hidden;
}

.testing-results-progress-fill {
  height: 100%;
  border-radius: 3px;
  transition: width var(--duration-normal, 180ms) var(--ease-standard, cubic-bezier(0.2,0,0,1));
}

.testing-results-progress-fill-image {
  background: var(--color-accent, #5a7fdb);
}

.testing-results-progress-fill-total {
  background: var(--color-success, #4ade80);
}

/* ── Responsive: side panel collapses on small screens ──── */

@media (max-width: 900px) {
  .testing-results-gallery-layout {
    flex-direction: column;
  }
  .testing-results-side-panel {
    width: 100%;
  }
  .testing-results-detail-body {
    max-height: 250px;
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

export function removeTestingStyles() {
  const el = document.getElementById(STYLE_ID);
  if (el) el.remove();
}
