// Modal Studio — History
//
// Real top-level page backed by existing run/experiment data.
// Uses existing /comfymodal/run-history endpoint. Shows truthful empty
// state if no data and visible error state on failure.

export function renderHistory(state, context) {
  const container = document.createElement("div");
  container.className = "comfymodal-studio-history";

  const apiBase = (context && context.apiBase) || "/comfymodal";

  // Show loading state
  container.innerHTML = `<div class="comfymodal-studio-card"><p>Loading history...</p></div>`;

  // Fetch real data from the run-history endpoint
  fetch(`${apiBase}/run-history?limit=50`)
    .then((res) => {
      if (!res.ok) throw new Error(`History request failed: ${res.status}`);
      return res.json();
    })
    .then((data) => {
      // Handle various API response shapes
      const runs =
        data.runs || data.run_history || (Array.isArray(data) ? data : null);
      if (!runs || (Array.isArray(runs) && runs.length === 0)) {
        container.innerHTML = `
          <div class="comfymodal-studio-card">
            <p>No run history yet. Runs will appear here once you create experiments.</p>
          </div>
        `;
        return;
      }
      // Render history entries as cards
      const html = (Array.isArray(runs) ? runs : [])
        .map((run) => {
          const rid =
            run.id || run.run_id || run.experiment_id || "unknown";
          const status = run.status || run.state || "unknown";
          const prompt = (
            run.prompt || (run.params && run.params.prompt) || rid
          ).substring(0, 120);
          const time =
            run.created_at || run.timestamp || run.created || "";
          const dur = run.duration || "";
          return `<div class="comfymodal-studio-card" style="margin-bottom:var(--space-sm)">
            <div class="testing-history-row" style="display:flex;gap:var(--space-sm);align-items:center;">
              <span class="testing-history-status">${status}</span>
              <span class="testing-history-row-main">${prompt}</span>
              <span class="testing-history-time">${time}</span>
              <span class="testing-history-duration">${dur}</span>
            </div>
          </div>`;
        })
        .join("");
      container.innerHTML = html;
    })
    .catch((err) => {
      container.innerHTML = `
        <div class="comfymodal-studio-card">
          <p style="color:var(--color-danger)">Failed to load history: ${err.message}</p>
        </div>
      `;
    });

  return container;
}
