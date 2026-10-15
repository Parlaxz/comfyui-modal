// Modal Studio — cross-tab invalidation messages.
//
// Messages carry no application state. They only tell another Studio mount
// that its server-backed view should be read again.
//
// Sync vocabulary (three distinct "syncs" — do not conflate):
//   A. Volume-diff sync (legacy): GET/POST /sync/status|/sync/models|
//      /sync/custom-nodes — local-vs-remote inventory diff, shell banner.
//   B. Publisher sync (Backend page): /studio/custom-nodes/sync-status|
//      /sync|/sync/rebuild-dependencies|/sync/status/{sync_id} — push
//      plugins (FAST) vs rebuild dependencies (SLOW).
//   C. THIS module: cross-tab invalidation only (BroadcastChannel). Kinds
//      below are the wire protocol — renaming them breaks cross-tab mounts
//      and studio_phase_i10_cross_tab_sync_unit.mjs.

export const STUDIO_SYNC_CHANNEL = "comfymodal-studio";
export const STUDIO_SYNC_KINDS = Object.freeze([
  "settings",
  "workspace",
  "history",
  "workflows",
]);

const VALID_KINDS = new Set(STUDIO_SYNC_KINDS);
const listeners = new Map();
let channel = null;

export function isStudioSyncKind(kind) {
  return typeof kind === "string" && VALID_KINDS.has(kind);
}

export function isStudioSyncMessage(message) {
  return !!(
    message &&
    typeof message === "object" &&
    isStudioSyncKind(message.kind) &&
    Number.isInteger(message.at) &&
    message.at >= 0
  );
}

function dispatch(message) {
  if (!isStudioSyncMessage(message)) return;
  const subscribed = listeners.get(message.kind);
  if (!subscribed) return;
  for (const listener of Array.from(subscribed)) {
    try { listener(message); } catch (_) { /* one page cannot break another */ }
  }
}

function ensureChannel() {
  if (channel) return channel;
  if (typeof globalThis.BroadcastChannel !== "function") return null;
  try {
    channel = new globalThis.BroadcastChannel(STUDIO_SYNC_CHANNEL);
    // Node's BroadcastChannel otherwise keeps standalone unit-test processes alive.
    if (typeof channel.unref === "function") channel.unref();
    channel.onmessage = (event) => dispatch(event && event.data);
    return channel;
  } catch (_) {
    channel = null;
    return null;
  }
}

export function publishStudioSync(kind) {
  if (!isStudioSyncKind(kind)) return false;
  const target = ensureChannel();
  if (!target) return false;
  try {
    target.postMessage({ kind, at: Date.now() });
    return true;
  } catch (_) {
    return false;
  }
}

export function subscribeStudioSync(kind, listener) {
  if (!isStudioSyncKind(kind) || typeof listener !== "function") return () => {};
  if (!ensureChannel()) return () => {};
  let subscribed = listeners.get(kind);
  if (!subscribed) {
    subscribed = new Set();
    listeners.set(kind, subscribed);
  }
  subscribed.add(listener);
  return () => {
    subscribed.delete(listener);
    if (subscribed.size === 0) listeners.delete(kind);
  };
}

// ── Immediate recent-runs deletion bus ──────────────────────────────────
//
// Same-tab, id-carrying companion to the stateless "history" kind above.
// The kind channel intentionally never delivers back to the publishing tab
// (see studio_phase_i10_cross_tab_sync_unit.mjs), so History delete paths
// publish the deleted generation/experiment ids here so the Playground
// carousel can evict them from its cache synchronously — no server
// round-trip, no manual refresh. Cross-tab mounts still converge through
// the "history" kind refetch; this bus is intentionally in-memory only
// (no BroadcastChannel payload contract change).
const recentRunsDeletedListeners = new Set();

function _normalizeDeletedIds(ids) {
  const input = Array.isArray(ids) ? ids : (ids == null ? [] : [ids]);
  const out = [];
  const seen = new Set();
  for (const raw of input) {
    if (raw == null || raw === "") continue;
    const key = String(raw);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(key);
  }
  return out;
}

export function notifyRecentRunsDeleted(ids) {
  const normalized = _normalizeDeletedIds(ids);
  if (normalized.length === 0) return 0;
  for (const listener of Array.from(recentRunsDeletedListeners)) {
    try { listener(normalized); } catch (_) { /* one page cannot break another */ }
  }
  return normalized.length;
}

export function subscribeRecentRunsDeleted(listener) {
  if (typeof listener !== "function") return () => {};
  recentRunsDeletedListeners.add(listener);
  return () => {
    recentRunsDeletedListeners.delete(listener);
  };
}
