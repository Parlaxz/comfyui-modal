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
          const extra = getRunExtra(run);
          const expId = run.experiment_id || run.experimentId || extra.experiment_id || null;
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

          // Check for studio experiment metadata
          const firstRun = groupRuns[0] || {};
          const firstExtra = getRunExtra(firstRun);
          const studioMeta = firstRun.studio_meta || firstExtra.studio_meta || (firstRun.metadata && firstRun.metadata.studio_meta) || {};

          const groupTitle = document.createElement("strong");
          if (studioMeta.studio_feature_id || studioMeta.studio_preset_id) {
            const featureLabel = studioMeta.studio_feature_id || "studio";
            const presetLabel = studioMeta.studio_preset_id ? studioMeta.studio_preset_id.substring(0, 12) : "";
            groupTitle.textContent = `Studio ${featureLabel}${presetLabel ? " \u2014 " + presetLabel : ""}`;
          } else {
            groupTitle.textContent = `Experiment: ${expId}`;
          }
          groupHeader.appendChild(groupTitle);

          // Stats row
          const statsRow = document.createElement("div");
          statsRow.style.display = "flex";
          statsRow.style.gap = "8px";
          statsRow.style.fontSize = "var(--font-size-xs)";
          statsRow.style.color = "var(--color-text-muted)";

          const totalCells = firstRun.total_cells || firstExtra.total_cells || groupRuns.length;
          const completedCount = groupRuns.filter((r) => {
            const s = r.status || r.state || "";
            return s === "completed" || s === "success" || s === "done";
          }).length;
          const failedCount = groupRuns.filter((r) => {
            const s = r.status || r.state || "";
            return s === "failed" || s === "error";
          }).length;

          statsRow.appendChild(document.createTextNode(`${groupRuns.length} run(s)`));
          if (totalCells > 0) {
            statsRow.appendChild(document.createTextNode(`\u00b7 ${totalCells} total cells`));
          }
          if (completedCount > 0) {
            const completedSpan = document.createElement("span");
            completedSpan.style.color = "var(--color-success, #4ade80)";
            completedSpan.textContent = `\u00b7 ${completedCount} completed`;
            statsRow.appendChild(completedSpan);
          }
          if (failedCount > 0) {
            const failedSpan = document.createElement("span");
            failedSpan.style.color = "var(--color-danger, #f87171)";
            failedSpan.textContent = `\u00b7 ${failedCount} failed`;
            statsRow.appendChild(failedSpan);
          }
          groupHeader.appendChild(statsRow);

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

function getRunExtra(run) {
  return (run && run.extra) || {};
}

function renderRunRow(card, run) {
  const extra = getRunExtra(run);
  const rid = run.id || run.run_id || run.experiment_id || extra.experiment_id || "unknown";
  const status = run.status || run.state || "unknown";
  const promptText = (
    extra.prompt || run.prompt || (run.params && run.params.prompt) || rid
  ).substring(0, 120);
  const time = run.created_at || run.started_at || run.timestamp || run.created || "";
  const dur = run.duration || "";

  // Studio metadata
  const studioMeta = run.studio_meta || extra.studio_meta || (run.metadata && run.metadata.studio_meta) || {};

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

  // Studio feature badge (if available)
  if (studioMeta.studio_feature_id) {
    const featureBadge = document.createElement("span");
    featureBadge.className = "comfymodal-studio-history-feature";
    featureBadge.textContent = studioMeta.studio_feature_id;
    featureBadge.style.fontSize = "var(--font-size-xs)";
    featureBadge.style.color = "var(--color-accent)";
    featureBadge.style.border = "1px solid var(--color-accent)";
    featureBadge.style.borderRadius = "3px";
    featureBadge.style.padding = "0 4px";
    row.appendChild(featureBadge);
  }

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

  // Output thumbnail hint
  if (extra.primary_asset_id || run.asset_id || (run.outputs && run.outputs.length > 0)) {
    const thumbHint = document.createElement("span");
    thumbHint.textContent = "\u{1F5BC}";
    thumbHint.title = "Output available";
    thumbHint.style.fontSize = "12px";
    row.appendChild(thumbHint);
  }

  card.appendChild(row);
}
