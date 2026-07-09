// Modal Studio — History
//
// Real top-level page backed by existing run/experiment data.
// Uses existing /comfymodal/run-history endpoint.
// Shows truthful empty state if no data and visible error state
// with retry on failure.
//
// SAFETY: All user/run data is rendered via DOM node creation
// and textContent — no unsafe innerHTML for dynamic data.
// Experiments are minimally grouped by experiment_id if present.

export function renderHistory(state, context) {
  const container = document.createElement("div");
  container.className = "comfymodal-studio-history";

  const apiBase = (context && context.apiBase) || "/comfymodal";

  // Show loading state
  const loadingCard = document.createElement("div");
  loadingCard.className = "comfymodal-studio-card";
  loadingCard.textContent = "Loading history...";
  container.appendChild(loadingCard);

  function fetchAndRender() {
    // Replace loading state with fresh fetch attempt
    while (container.firstChild) container.removeChild(container.firstChild);

    const fetchCard = document.createElement("div");
    fetchCard.className = "comfymodal-studio-card";
    fetchCard.textContent = "Loading history...";
    container.appendChild(fetchCard);

    fetch(`${apiBase}/run-history?limit=50`)
      .then((res) => {
        if (!res.ok) throw new Error(`History request failed: ${res.status}`);
        return res.json();
      })
      .then((data) => {
        while (container.firstChild) container.removeChild(container.firstChild);

        // Handle various API response shapes
        const runs =
          data.runs || data.run_history || (Array.isArray(data) ? data : null);

        if (!runs || (Array.isArray(runs) && runs.length === 0)) {
          // Truthful empty state
          const emptyCard = document.createElement("div");
          emptyCard.className = "comfymodal-studio-card";
          emptyCard.textContent =
            "No run history yet. Runs will appear here once you create experiments.";
          container.appendChild(emptyCard);
          return;
        }

        const runList = Array.isArray(runs) ? runs : [];

        // Minimally group by experiment_id if present
        const grouped = {};
        const ungrouped = [];

        runList.forEach((run) => {
          const expId = run.experiment_id || run.experimentId || null;
          if (expId) {
            if (!grouped[expId]) grouped[expId] = [];
            grouped[expId].push(run);
          } else {
            ungrouped.push(run);
          }
        });

        // Render grouped experiments
        Object.entries(grouped).forEach(([expId, groupRuns]) => {
          const groupCard = document.createElement("div");
          groupCard.className = "comfymodal-studio-card";
          groupCard.style.marginBottom = "var(--space-md)";

          const groupHeader = document.createElement("div");
          groupHeader.style.display = "flex";
          groupHeader.style.justifyContent = "space-between";
          groupHeader.style.alignItems = "center";
          groupHeader.style.marginBottom = "var(--space-sm)";

          const groupTitle = document.createElement("strong");
          groupTitle.textContent = `Experiment: ${expId}`;
          groupHeader.appendChild(groupTitle);

          const groupCount = document.createElement("span");
          groupCount.style.fontSize = "var(--font-size-xs)";
          groupCount.style.color = "var(--color-text-muted)";
          groupCount.textContent = `${groupRuns.length} run(s)`;
          groupHeader.appendChild(groupCount);

          groupCard.appendChild(groupHeader);

          // Render runs within group
          groupRuns.forEach((run) => renderRunRow(groupCard, run));
          container.appendChild(groupCard);
        });

        // Render ungrouped runs
        ungrouped.forEach((run) => {
          const card = document.createElement("div");
          card.className = "comfymodal-studio-card";
          card.style.marginBottom = "var(--space-sm)";
          renderRunRow(card, run);
          container.appendChild(card);
        });
      })
      .catch((err) => {
        while (container.firstChild) container.removeChild(container.firstChild);

        // Error state with retry
        const errorCard = document.createElement("div");
        errorCard.className = "comfymodal-studio-card";

        const errorMsg = document.createElement("p");
        errorMsg.style.color = "var(--color-danger)";
        errorMsg.textContent = `Failed to load history: ${err.message}`;
        errorCard.appendChild(errorMsg);

        const retryBtn = document.createElement("button");
        retryBtn.className = "comfymodal-secondary-btn";
        retryBtn.textContent = "Retry";
        retryBtn.style.marginTop = "8px";
        retryBtn.addEventListener("click", fetchAndRender);
        errorCard.appendChild(retryBtn);

        container.appendChild(errorCard);
      });
  }

  fetchAndRender();
  return container;
}

function renderRunRow(card, run) {
  const rid = run.id || run.run_id || run.experiment_id || "unknown";
  const status = run.status || run.state || "unknown";
  const promptText = (
    run.prompt || (run.params && run.params.prompt) || rid
  ).substring(0, 120);
  const time = run.created_at || run.timestamp || run.created || "";
  const dur = run.duration || "";

  const row = document.createElement("div");
  row.className = "testing-history-row";
  row.style.display = "flex";
  row.style.gap = "var(--space-sm)";
  row.style.alignItems = "center";

  // Status badge
  const statusSpan = document.createElement("span");
  statusSpan.className = "testing-history-status";
  statusSpan.textContent = status;
  row.appendChild(statusSpan);

  // Prompt/description
  const promptSpan = document.createElement("span");
  promptSpan.className = "testing-history-row-main";
  promptSpan.textContent = promptText;
  row.appendChild(promptSpan);

  // Timestamp
  if (time) {
    const timeSpan = document.createElement("span");
    timeSpan.className = "testing-history-time";
    timeSpan.textContent = time;
    row.appendChild(timeSpan);
  }

  // Duration
  if (dur) {
    const durSpan = document.createElement("span");
    durSpan.className = "testing-history-duration";
    durSpan.textContent = dur;
    row.appendChild(durSpan);
  }

  card.appendChild(row);
}
