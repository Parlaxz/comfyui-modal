const PREFIX = "[comfymodal.testing]";

export function assetUrl(apiBase, assetId) {
  if (!assetId) return null;
  return `${apiBase || "/comfymodal"}/assets/${encodeURIComponent(assetId)}`;
}

export async function fetchJson(path, options = {}) {
  const res = await fetch(path, options);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
  if (!res.ok) {
    const msg = (data && data.message) || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

export async function getExperiments(apiBase) {
  return fetchJson(`${apiBase || "/comfymodal"}/experiments`);
}

export async function getExperiment(apiBase, id) {
  return fetchJson(`${apiBase || "/comfymodal"}/experiments/${encodeURIComponent(id)}`);
}

export async function createExperiment(apiBase, payload) {
  return fetchJson(`${apiBase || "/comfymodal"}/experiments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getDeployStatus(apiBase) {
  try {
    return await fetchJson(`${apiBase || "/comfymodal"}/deploy/status`);
  } catch { return null; }
}

export async function getExperimentHistory(apiBase) {
  try {
    return await fetchJson(`${apiBase || "/comfymodal"}/run-history?limit=20`);
  } catch { return null; }
}

// ── Normalized-draft API helpers ────────────────────────────────────────
//
// These helpers send normalized drafts to the backend compile/create/start
// routes. The frontend must NOT construct final compiler-schema fragments;
// use these helpers to send normalized_draft payloads to the backend.

/**
 * Preview (compile) a normalized draft without creating an experiment.
 * POST /experiments/compile with { normalized_draft: draft }.
 */
export async function previewDraft(apiBase, draft) {
  return fetchJson(`${apiBase || "/comfymodal"}/experiments/compile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
}

/**
 * Create an experiment from a normalized draft payload
 * ({ normalized_draft: ..., max_containers: N }).
 */
export async function createFromDraft(apiBase, payload) {
  return fetchJson(`${apiBase || "/comfymodal"}/experiments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

/**
 * Create from draft + start the experiment in one flow.
 * Returns { created, started } so the caller can inspect both responses.
 */
export async function runFromDraft(apiBase, createPayload, startPayload) {
  const created = await createFromDraft(apiBase, createPayload);
  const expId = created && created.experiment_id;
  if (!expId) throw new Error("Create did not return an experiment_id");

  const startResult = await fetchJson(
    `${apiBase || "/comfymodal"}/experiments/${encodeURIComponent(expId)}/start`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(startPayload || {}),
    }
  );
  if (startResult && (startResult.error || startResult.status === "error")) {
    throw new Error(
      (startResult.message || startResult.error || "Start returned an error") +
        " \u2014 experiment was created but not started"
    );
  }
  return { created, started: startResult };
}

export function bootstrapLoader(container, loadFn) {
  const loadEl = document.createElement("div");
  loadEl.className = "comfymodal-testing-loader";
  loadEl.textContent = "Loading...";
  container.appendChild(loadEl);

  async function attempt() {
    loadEl.textContent = "Loading...";
    loadEl.className = "comfymodal-testing-loader";
    try {
      await loadFn();
      if (loadEl.parentNode) loadEl.remove();
    } catch (e) {
      console.warn(PREFIX, "load failed:", e);
      loadEl.className = "comfymodal-testing-error";
      loadEl.innerHTML = "";
      const msg = document.createElement("p");
      msg.textContent = "Failed to load: " + (e.message || e);
      loadEl.appendChild(msg);
      const retry = document.createElement("button");
      retry.className = "comfymodal-testing-retry-btn";
      retry.textContent = "Retry";
      retry.onclick = attempt;
      loadEl.appendChild(retry);
    }
  }

  return { attempt, element: loadEl };
}
