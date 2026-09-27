// Modal Studio — cross-tab invalidation messages.
//
// Messages carry no application state. They only tell another Studio mount
// that its server-backed view should be read again.

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
