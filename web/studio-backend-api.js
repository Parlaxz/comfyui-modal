// Modal Studio — Backend API Layer
//
// All API communication for snapshots, presets, and backend discovery.
// No rendering logic — only fetch/response helpers.

// ── Internal fetch helper ─────────────────────────────────────────────────

let _backendCache = null;

async function apiFetch(apiBase, path, options) {
  try {
    const res = await fetch(`${apiBase}${path}`, options || {});
    if (!res.ok) return null;
    return await res.json();
  } catch { return null; }
}

// ── Legacy Backend Discovery API ──────────────────────────────────────────

export async function getBackends(context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  try {
    const res = await fetch(`${apiBase}/studio/backends`);
    if (!res.ok) return [];
    const data = await res.json();
    _backendCache = (data && data.backends) || [];
    return _backendCache;
  } catch {
    return [];
  }
}

export async function getCompareBackends(context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  try {
    const res = await fetch(`${apiBase}/studio/backends?kind=comparable`);
    if (!res.ok) return [];
    const data = await res.json();
    return (data && data.backends) || [];
  } catch {
    return [];
  }
}

// ── Snapshots API ─────────────────────────────────────────────────────────

export async function listSnapshots(apiBase) {
  const data = await apiFetch(apiBase, "/studio/snapshots");
  return (data && data.snapshots) || [];
}

export async function createSnapshot(apiBase, payload) {
  return apiFetch(apiBase, "/studio/snapshots", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updateSnapshot(apiBase, id, payload) {
  return apiFetch(apiBase, `/studio/snapshots/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function duplicateSnapshot(apiBase, id) {
  return apiFetch(apiBase, `/studio/snapshots/${encodeURIComponent(id)}/duplicate`, {
    method: "POST",
  });
}

export async function archiveSnapshot(apiBase, id) {
  return apiFetch(apiBase, `/studio/snapshots/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// ── Backend Presets API ───────────────────────────────────────────────────

export async function listPresets(apiBase) {
  const data = await apiFetch(apiBase, "/studio/presets");
  return (data && data.presets) || [];
}

export async function createPreset(apiBase, payload) {
  return apiFetch(apiBase, "/studio/presets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updatePreset(apiBase, id, payload) {
  return apiFetch(apiBase, `/studio/presets/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function duplicatePreset(apiBase, id) {
  return apiFetch(apiBase, `/studio/presets/${encodeURIComponent(id)}/duplicate`, {
    method: "POST",
  });
}

export async function archivePreset(apiBase, id) {
  return apiFetch(apiBase, `/studio/presets/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}
