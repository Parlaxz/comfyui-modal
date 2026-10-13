// Modal Studio — Shell
//
// Owns Studio app state and page switching. Renders the top nav with
// Playground, History, Workflows, Backend, and Settings. Mounts the active
// page into rootEl. Receives only stable context from modal-testing.js and
// augments it with shell actions (setPage).
//
// Avoids nested containers: the shell's page
// container uses a distinct class (comfymodal-studio-pagecontainer).
//
// Routing (I9): the shell is the single navigation authority. Page changes
// serialize to the frozen hash contract (#comfymodal=<page>[&focus=<id>])
// via history.pushState/replaceState — hash only, host pathname/search are
// preserved. Back/Forward is honored through hashchange using the same
// setPage/applyRoute authority, so mounted page, .active and aria-current
// can never diverge from the routed state. Each render owns a navigation
// generation: stale async page work captured from a superseded mount can no
// longer become the active page (late Playground responses cannot overwrite
// History after setPage moved elsewhere).

import { renderPlayground } from "./studio-playground.js";
import { renderHistoryV2, requestHistoryRecordFocus } from "./studio-history-v2.js";
import { renderWorkflows } from "./studio-workflows.js";
import { renderBackend } from "./studio-backend.js";
import { renderSettings } from "./studio-settings.js";
import { el } from "./studio-ui.js";
import {
  parseStudioHash,
  serializeStudioHash,
  routeHistoryAction,
  isCanonicalPage,
} from "./studio-routing.js";

const PAGES = {
  playground: { label: "Playground", render: renderPlayground },
  history:    { label: "History",    render: renderHistoryV2 },
  workflows:  { label: "Workflows",  render: renderWorkflows },
  backend:    { label: "Manage Modal", render: renderBackend },
  settings:   { label: "Settings",   render: renderSettings },
};

export function mountStudioShell(rootEl, context = {}, options = {}) {
  const state = {
    activePage: "playground",
    playground: {
      featureId: "txt2img",
      experimentMode: false,
      selectedBackendId: "",
      compareBackendIds: [],
      controls: {},
      experimentAxes: {},
    },
    history: {
      selectedRunId: "",
      filters: { query: "", kind: "all", status: "all" },
    },
    settings: {
      activeSection: "studio",
    },
  };

  // ── Routing state (I9) ──────────────────────────────────────────────────
  // Explicit caller intent (options.initialRoute) wins over an existing
  // location hash; absent both, today's Playground default applies.
  const initialRoute = _resolveInitialRoute(options.initialRoute, typeof window !== "undefined" ? window.location.hash : "");
  // Managed route mirrors what this shell believes the URL carries.
  let _managedRoute = { page: initialRoute.page, focus: initialRoute.focus };
  // Lazy seed: the current history entry is rewritten to the canonical hash
  // only when the first managed navigation happens, so open/close without
  // navigating leaves the host URL untouched.
  let _routeSeeded = false;
  // Navigation generation: bumped on every renderActivePage. Page-context
  // closures capture their generation and drop late async completions from
  // mounts that have been superseded.
  let _navGen = 0;

  function _resolveInitialRoute(explicit, locationHash) {
    if (explicit && isCanonicalPage(explicit.page)) {
      return {
        page: explicit.page,
        focus: typeof explicit.focus === "string" && explicit.focus ? explicit.focus : null,
      };
    }
    const parsed = parseStudioHash(locationHash);
    if (parsed.matched) return { page: parsed.page, focus: parsed.focus };
    return { page: "playground", focus: null };
  }

  // Build top nav — semantic <nav> so assistive tech can identify and
  // traverse primary Studio navigation. Page controls stay native buttons:
  // they switch an in-modal application view, not a document URL.
  const nav = el("nav", {
    class: "comfymodal-studio-topnav",
    "aria-label": "Studio pages",
  });

  // Build page container — use a distinct class to avoid
  // class-name collision with page-level containers
  const pageContainer = el("div", { class: "comfymodal-studio-pagecontainer", "data-testid": "studio-page" });

  // Dependency health belongs to the shell: a volume mismatch can affect
  // every Studio page, not just Settings or Backend.
  const syncNotice = el("div", { class: "comfymodal-studio-sync-notice-host", hidden: true });
  let syncPollTimer = null;
  let syncInFlight = false;
  let lastSyncResult = "";
  let lastSyncData = null;

  function shortHash(value) {
    return typeof value === "string" && value ? value.slice(0, 8) : "—";
  }

  function syncResultText(data, fallback) {
    if (data && data.status === "ok") return data.message || "Dependencies and custom nodes synced.";
    const error = data && (data.error || data.message || data.reason);
    if (typeof error === "string") return error;
    if (error && typeof error === "object") return error.detail || error.message || error.code || fallback;
    return fallback;
  }

  function renderSyncNotice(status) {
    const dependency = status && status.dependency;
    const pending = Array.isArray(status && status.custom_nodes && status.custom_nodes.pending)
      ? status.custom_nodes.pending : [];
    const mismatch = dependency && dependency.prepared === false;
    const hasResult = Boolean(lastSyncResult);
    while (syncNotice.firstChild) syncNotice.removeChild(syncNotice.firstChild);
    if (!mismatch && !pending.length && !hasResult) {
      syncNotice.hidden = true;
      return;
    }
    syncNotice.hidden = false;
    const banner = el("section", {
      class: `comfymodal-studio-sync-notice ${mismatch ? "mismatch" : pending.length ? "pending" : "result"}`,
      ...(mismatch ? { "data-testid": "dep-mismatch-banner", role: "alert", "aria-live": "polite" } : {}),
    });
    if (mismatch) {
      banner.appendChild(el("div", { class: "comfymodal-studio-sync-title", text: "Studio dependencies need syncing" }));
      banner.appendChild(el("div", { class: "comfymodal-studio-sync-copy", text: dependency.cause || "Dependency mismatch detected." }));
      banner.appendChild(el("div", { class: "comfymodal-studio-sync-copy", text: dependency.solution || "Sync dependencies and custom nodes to repair the volume." }));
      const names = [...(Array.isArray(dependency.changed_nodes) ? dependency.changed_nodes : []), ...(Array.isArray(dependency.missing_in_volume) ? dependency.missing_in_volume : [])]
        .filter((name, index, values) => name && values.indexOf(name) === index).slice(0, 5);
      const details = [dependency.reason, `baked ${shortHash(dependency.baked_hash)} / current ${shortHash(dependency.current_hash)}`, names.length ? names.join(", ") : "no affected nodes listed"]
        .filter(Boolean).join(" · ");
      banner.appendChild(el("div", { class: "comfymodal-studio-sync-detail", text: details }));
    } else if (pending.length) {
      banner.appendChild(el("div", { class: "comfymodal-studio-sync-copy", text: `${pending.length} custom node(s) not yet published to the volume` }));
    }
    const actions = el("div", { class: "comfymodal-studio-sync-actions" });
    actions.appendChild(el("button", {
      type: "button", class: "comfymodal-primary-btn",
      text: syncInFlight ? "Syncing…" : "Sync deps / custom nodes",
      "data-testid": "dep-sync-button", disabled: syncInFlight,
      onclick: function () { syncCustomNodes(); },
    }));
    banner.appendChild(actions);
    if (hasResult) banner.appendChild(el("div", { class: "comfymodal-studio-sync-result", "data-testid": "dep-sync-result", text: lastSyncResult, role: "status" }));
    const destructive = lastSyncData && lastSyncData.publication && lastSyncData.publication.reason === "destructive_custom_node_publication_blocked"
      ? (lastSyncData.publication.destructive || null) : null;
    const blockedPackages = destructive && Array.isArray(destructive.packages) ? destructive.packages : [];
    if (blockedPackages.length) {
      const lines = blockedPackages.slice(0, 5).map(function (pkg) {
        const name = pkg && pkg.package ? String(pkg.package) : "unknown package";
        const count = pkg && pkg.missing_count != null ? pkg.missing_count : "?";
        const paths = pkg && Array.isArray(pkg.missing_paths) ? pkg.missing_paths.slice(0, 3).join(", ") : "";
        return `${name}: ${count} file(s) only on the volume${paths ? ` (${paths}${pkg.missing_paths.length > 3 ? ", …" : ""})` : ""}`;
      });
      banner.appendChild(el("div", { class: "comfymodal-studio-sync-detail", "data-testid": "dep-blocked-detail", text: lines.join(" · ") }));
      const confirmActions = el("div", { class: "comfymodal-studio-sync-actions" });
      confirmActions.appendChild(el("button", {
        type: "button", class: "comfymodal-primary-btn",
        text: syncInFlight ? "Syncing…" : "Replace volume contents",
        title: "Publish the local tree, deleting volume files the local tree lacks",
        "data-testid": "dep-sync-confirm-button", disabled: syncInFlight,
        onclick: function () { syncCustomNodes({ allow_destructive: true }); },
      }));
      banner.appendChild(confirmActions);
    }
    syncNotice.appendChild(banner);
  }

  async function fetchSyncStatus() {
    try {
      const response = await fetch(`${context.apiBase}/sync/status`);
      const data = await response.json();
      if (response.ok) renderSyncNotice(data);
    } catch {
      // Keep the last known warning visible through transient poll failures.
    }
  }

  async function syncCustomNodes(requestBody) {
    if (syncInFlight) return;
    syncInFlight = true;
    lastSyncResult = "Syncing dependencies and custom nodes…";
    lastSyncData = null;
    renderSyncNotice({ dependency: null, custom_nodes: { pending: [] } });
    try {
      const request = requestBody
        ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(requestBody) }
        : { method: "POST" };
      const response = await fetch(`${context.apiBase}/sync/custom-nodes`, request);
      let data = null;
      try { data = await response.json(); } catch { /* show a result even for an empty response */ }
      lastSyncData = data;
      lastSyncResult = syncResultText(data, response.ok ? "Sync finished." : `Sync failed (HTTP ${response.status}).`);
    } catch {
      lastSyncData = null;
      lastSyncResult = "Sync failed: unable to reach the Studio sync service.";
    } finally {
      syncInFlight = false;
      await fetchSyncStatus();
      if (!syncNotice.firstChild) renderSyncNotice({ dependency: null, custom_nodes: { pending: [] } });
    }
  }

  // Deferred scroll restoration state — handles rapid successive re-renders
  // (e.g. rapid experiment checkbox toggles) by coalescing into one callback
  // that always uses the latest captured scroll values.
  let _pendingScrollRestore = null;
  let _scrollRestoreScheduled = false;

  function renderActivePage(preserveScroll = true) {
    const gen = ++_navGen;
    const pageScrollTop = preserveScroll ? pageContainer.scrollTop : 0;
    const controlPanelScrollTop = preserveScroll
      ? pageContainer.querySelector(".comfymodal-studio-control-panel")?.scrollTop
      : undefined;

    if (!state.playground._controlPanelScrollRestorePending) {
      const oldPanel = pageContainer.querySelector(".comfymodal-studio-control-panel");
      if (oldPanel) {
        state.playground._controlPanelScrollTop = oldPanel.scrollTop;
      }
    }

    // Clear page container
    while (pageContainer.firstChild) pageContainer.removeChild(pageContainer.firstChild);

    const pageDef = PAGES[state.activePage];
    if (!pageDef) {
      // Never leave the body empty (an empty dialog reads as a black
      // hang): render a truthful notice with a recovery action.
      const notice = el("div", {
        class: "comfymodal-studio-placeholder-notice",
        role: "alert",
      });
      notice.appendChild(el("p", { text: `Unknown page: ${state.activePage}` }));
      const backBtn = el("button", {
        type: "button",
        class: "comfymodal-secondary-btn",
        text: "Back to Playground",
        onclick: () => setPage("playground"),
      });
      notice.appendChild(backBtn);
      pageContainer.appendChild(notice);
      return;
    }

    // Augment context with shell actions so pages can trigger navigation
    // and state changes. The context's setPage carries the stale-navigation
    // guard: a superseded mount's late async work may still legitimately
    // refresh the CURRENT page (live run polling outlives incidental
    // re-renders), but it must never force a DIFFERENT page over the one
    // the user navigated to (a delayed recent-runs response re-rendering
    // Playground over active History).
    const pageContext = {
      ...context,
      setPage,
      clearRouteFocus,
      setRouteFocus,
      // Pages route through the shell's single authority so no page writes
      // history itself. Use this for deep links that carry a focus identity
      // (e.g. Settings → Manage Modal → Workspaces); plain page switches
      // should use setPage, which drops any previous focus.
      applyRoute,
    };
    const capturedGen = gen;
    pageContext.setPage = function staleGuardedSetPage(nextPage) {
      if (nextPage !== state.activePage && capturedGen !== _navGen) return;
      setPage(nextPage);
    };

    const content = pageDef.render(state, pageContext);
    if (content) pageContainer.appendChild(content);

    // Defer scroll restoration to a macrotask so it fires after all
    // setTimeout(0) callbacks scheduled during rendering (e.g. axis editor
    // insertion in enhanceControlWithAxisCheckbox). By that point the DOM
    // has been laid out and all deferred insertions have settled, making
    // scrollTop assignments effective.
    _pendingScrollRestore = { pageScrollTop, controlPanelScrollTop, pageContainer };
    if (!_scrollRestoreScheduled) {
      _scrollRestoreScheduled = true;
      setTimeout(() => {
        _scrollRestoreScheduled = false;
        const restore = _pendingScrollRestore;
        _pendingScrollRestore = null;
        if (!restore) return;

        restore.pageContainer.scrollTop = restore.pageScrollTop;
        const controlPanel = restore.pageContainer.querySelector(".comfymodal-studio-control-panel");
        if (controlPanel && restore.controlPanelScrollTop != null) {
          controlPanel.scrollTop = restore.controlPanelScrollTop;
          if (controlPanel.scrollTop !== restore.controlPanelScrollTop) {
            state.playground._controlPanelScrollRestorePending = true;
          }
        }
      }, 0);
    }
  }

  function updateNavActive() {
    // Single page-state authority: mounted page, .active, and aria-current
    // all derive from state.activePage so they can never diverge.
    nav.querySelectorAll("button").forEach((btn) => {
      const isActive = btn.dataset.page === state.activePage;
      btn.classList.toggle("active", isActive);
      if (isActive) {
        btn.setAttribute("aria-current", "page");
      } else {
        btn.removeAttribute("aria-current");
      }
    });
  }

  // Create nav buttons — user-driven navigation closes over the unguarded
  // setPage: explicit user intent always wins, only superseded MOUNTS are
  // stale-guarded through their own page-context closure.
  Object.entries(PAGES).forEach(([pageId, pageDef]) => {
    const btn = el("button", {
      "data-page": pageId,
      text: pageDef.label,
      onclick: () => {
        setPage(pageId);
      },
    });
    nav.appendChild(btn);
  });

  function setPage(nextPage) {
    const prevRoute = { page: _managedRoute.page, focus: _managedRoute.focus };
    const prevPage = state.activePage;
    state.activePage = nextPage;
    updateNavActive();
    renderActivePage(prevPage === nextPage);
    // Plain page switches carry no focus identity: a previous deep-link
    // focus belongs to the page it was routed for.
    _managedRoute = { page: nextPage, focus: null };
    _syncUrl(prevRoute, _managedRoute);
  }

  /**
   * Drop the focus identity from the managed route (I9A convergence).
   * Closing a focused record view rewrites the hash to the bare page route
   * through the same replace authority, so the URL never keeps claiming a
   * selection that no longer exists on screen — a cached reopen or reload
   * would otherwise resurrect the record the user just dismissed. The
   * current history entry is marked seeded: it now carries a managed route.
   */
  function clearRouteFocus() {
    if (!_managedRoute.focus) return;
    const prevRoute = { page: _managedRoute.page, focus: _managedRoute.focus };
    _managedRoute = { page: prevRoute.page, focus: null };
    _routeSeeded = true;
    _syncUrl(prevRoute, _managedRoute);
  }

  function setRouteFocus(focus) {
    const nextFocus = typeof focus === "string" && focus ? focus : null;
    const prevRoute = { page: _managedRoute.page, focus: _managedRoute.focus };
    if (prevRoute.focus === nextFocus) return;
    _managedRoute = { page: prevRoute.page, focus: nextFocus };
    _routeSeeded = true;
    _syncUrl(prevRoute, _managedRoute);
  }

  /**
   * Apply a parsed Studio route through the same single authority.
   * opts.passive — the browser already navigated (Back/Forward); do not
   *                write history, just adopt the entry as managed truth.
   * opts.rerender — also re-render when page+focus are unchanged.
   * Returns false when the route is not a canonical Studio page.
   */
  function applyRoute(route, opts = {}) {
    if (!isCanonicalPage(route && route.page)) return false;
    const page = route.page;
    const focus =
      route && typeof route.focus === "string" && route.focus ? route.focus : null;
    if (page === "settings" && focus) state.settings.activeSection = _settingsTabForFocus(focus);
    const prevRoute = { page: _managedRoute.page, focus: _managedRoute.focus };

    // Focus seams run BEFORE the page renders so mount-time consumers
    // (History V2 pending-record focus) observe them on THIS mount. Only
    // seams with a stable owner exist; other pages fail soft (§9 I9).
    if (focus && page === "history") {
      requestHistoryRecordFocus(focus, "generation");
    }

    const pageChanged = page !== state.activePage;
    const focusChanged = focus !== prevRoute.focus;
    if (pageChanged || focusChanged || opts.rerender) {
      state.activePage = page;
      updateNavActive();
      renderActivePage(false);
    }

    _managedRoute = { page, focus };
    if (opts.passive) {
      // The browser owns this history entry already.
      _routeSeeded = true;
    } else {
      _syncUrl(prevRoute, _managedRoute);
    }
    if (focus && page === "settings") _scheduleSettingsSectionFocus(focus);
    return true;
  }

  // ── URL sync ────────────────────────────────────────────────────────────
  // Hash-only writes: base URL (pathname+search) is always preserved. The
  // first managed navigation seeds the CURRENT entry with the previous
  // route via replaceState before pushing the new one, so Back from the
  // first pushed page stays inside Studio instead of leaving ComfyUI.

  function _syncUrl(prevRoute, nextRoute) {
    if (typeof window === "undefined" || !window.history) return;
    const hash = serializeStudioHash(nextRoute);
    if (!hash) return;
    if (window.location.hash === hash) return;
    const base = window.location.pathname + window.location.search;
    try {
      if (!_routeSeeded) {
        const seedHash = serializeStudioHash(prevRoute);
        if (seedHash && window.location.hash !== seedHash) {
          window.history.replaceState(window.history.state, "", base + seedHash);
        }
        _routeSeeded = true;
        // When the seed already produced the target hash (e.g. an explicit
        // opener landed on this exact route), pushing would create a
        // duplicate no-op entry — skip it.
        if (window.location.hash !== hash) {
          window.history.pushState(window.history.state, "", base + hash);
        }
      } else if (routeHistoryAction(prevRoute, nextRoute) === "push") {
        window.history.pushState(window.history.state, "", base + hash);
      } else {
        window.history.replaceState(window.history.state, "", base + hash);
      }
    } catch (_err) {
      // History API unavailable (sandboxed embeds) — navigation still works.
    }
  }

  // ── Back / Forward ──────────────────────────────────────────────────────
  // The shell writes routes exclusively through pushState/replaceState,
  // which never fire events, so every hashchange event originates from real
  // browser navigation (Back/Forward, manual hash edits). Matched routes
  // adopt the entry passively; unrelated host hashes are ignored.

  function _handleHashChange() {
    const parsed = parseStudioHash(window.location.hash);
    if (!parsed.matched) return;
    applyRoute({ page: parsed.page, focus: parsed.focus }, { passive: true });
  }

  if (typeof window !== "undefined") {
    window.addEventListener("hashchange", _handleHashChange);
  }

  // Settings section focus (deep links): same presentation behavior as the
  // comfymodal.open-section handler — scroll to [data-section] and flash a
  // short outline. Unknown ids resolve nothing: Settings opens normally.
  function _settingsTabForFocus(sectionId) {
    if (sectionId === "history") return "interface";
    if (["accounts", "account", "credentials", "tokens"].includes(sectionId)) return "accounts";
    if (["generation", "outputs", "interface", "advanced"].includes(sectionId)) return sectionId;
    if (["profile", "golden", "golden-profile", "golden_profile"].includes(sectionId)) return "generation";
    return "generation";
  }

  function _scheduleSettingsSectionFocus(sectionId) {
    const normalized = _settingsTabForFocus(sectionId);
    const tab = pageContainer.querySelector("#settings-tab-" + normalized);
    if (tab && typeof tab.click === "function") tab.click();
    {
      const sections = pageContainer.querySelectorAll("[data-section]");
      let sectionEl = null;
      for (let i = 0; i < sections.length; i++) {
        if (sections[i].getAttribute("data-section") === normalized || (normalized === "interface" && sectionId === "history" && sections[i].getAttribute("data-section") === "interface")) {
          sectionEl = sections[i];
          break;
        }
      }
      if (!sectionEl || typeof sectionEl.scrollIntoView !== "function") return;
      sectionEl.scrollIntoView({ behavior: "smooth", block: "start" });
      sectionEl.style.outline = "2px solid var(--color-accent)";
      setTimeout(function () {
        sectionEl.style.outline = "";
      }, 2000);
    }
  }

  // Assemble shell
  rootEl.appendChild(nav);
  rootEl.appendChild(syncNotice);
  rootEl.appendChild(pageContainer);

  // Initial render — honor the resolved initial route (explicit opener
  // intent or copied/reloaded URL hash) before first paint.
  state.activePage = initialRoute.page;
  if (initialRoute.page === "settings" && initialRoute.focus) state.settings.activeSection = _settingsTabForFocus(initialRoute.focus);
  if (initialRoute.focus && initialRoute.page === "history") {
    requestHistoryRecordFocus(initialRoute.focus, "generation");
  }
  updateNavActive();
  renderActivePage(false);
  if (initialRoute.focus && initialRoute.page === "settings") {
    _scheduleSettingsSectionFocus(initialRoute.focus);
  }
  fetchSyncStatus();
  syncPollTimer = setInterval(fetchSyncStatus, 15000);

  const shellApi = {
    nav,
    destroy() {
      if (syncPollTimer) {
        clearInterval(syncPollTimer);
        syncPollTimer = null;
      }
      if (typeof window !== "undefined") {
        window.removeEventListener("hashchange", _handleHashChange);
      }
      while (rootEl.firstChild) rootEl.removeChild(rootEl.firstChild);
    },
    setPage,
    /** Apply a parsed route ({page, focus}) through the single authority. */
    applyRoute,
    /** Drop the focus identity from the managed route (I9A). */
    clearRouteFocus,
    /** Update focus identity without remounting the current page. */
    setRouteFocus,
    /** Current managed route snapshot ({page, focus}). */
    getRoute() {
      return { page: _managedRoute.page, focus: _managedRoute.focus };
    },
    getState() {
      return state;
    },
  };

  return shellApi;
}
