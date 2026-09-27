// Modal Studio — Backend Credentials Section (H6 re-home)
//
// Modern Backend home for account/credential state, consuming the SAME
// routes as the legacy settings panel (/auth/status, /hf-token,
// /civitai-token).
//
// Secret policy (hard):
//  - Saved credentials are NEVER echoed. The GET responses may carry a
//    masked prefix; credentialConfigured() deliberately discards it and the
//    UI renders only configured / not-configured status.
//  - Token inputs use password semantics; values live in memory only until
//    submit and are never written into datasets, error text, or logs.
//  - No new storage authority: saves go through the existing server routes.

import { el, statusBadge } from "./studio-ui.js";
import {
  getAuthStatus,
  getCredentialStatus,
  saveCredentialToken,
  credentialConfigured,
} from "./studio-backend-api.js";

export function renderCredentialsSection(container, apiBase) {
  const root = el("div", { class: "comfymodal-studio-backend-detail", "data-testid": "backend-credentials" });

  // ── Modal account connection ────────────────────────────────────────────
  const modalCard = el("div", { class: "comfymodal-studio-backend-detail-card", style: "margin-bottom:8px;" });
  modalCard.appendChild(el("div", { text: "Modal Account", style: "font-weight:600;font-size:12px;margin-bottom:6px;" }));
  const modalStatusRow = el("div", { "data-testid": "backend-auth-status", style: "display:flex;align-items:center;gap:8px;" });
  modalStatusRow.appendChild(el("span", { text: "Connection:", style: "font-size:11px;color:#888;" }));
  const modalBadgeWrap = el("span", { "data-testid": "backend-auth-badge" });
  modalStatusRow.appendChild(modalBadgeWrap);
  modalCard.appendChild(modalStatusRow);
  modalCard.appendChild(el("div", {
    text: "Modal tokens are stored per workspace \u2014 add or edit them in the Workspaces tab.",
    style: "font-size:11px;color:#666;margin-top:6px;",
  }));

  // ── Credential blocks (HF / Civitai) ────────────────────────────────────
  function credentialBlock(kind, title, hint, placeholder, testid) {
    const card = el("div", { class: "comfymodal-studio-backend-detail-card", style: "margin-bottom:8px;" });
    card.appendChild(el("div", { text: title, style: "font-weight:600;font-size:12px;margin-bottom:4px;" }));
    card.appendChild(el("div", { text: hint, style: "font-size:11px;color:#888;margin-bottom:8px;" }));

    const badgeWrap = el("span", { "data-testid": `${testid}-state` });
    const statusRow = el("div", { style: "display:flex;align-items:center;gap:8px;margin-bottom:8px;" }, [
      el("span", { text: "Status:", style: "font-size:11px;color:#888;" }),
      badgeWrap,
    ]);
    card.appendChild(statusRow);

    const input = el("input", {
      type: "password",
      placeholder,
      "data-testid": `${testid}-input`,
      style: "flex:1;width:auto;min-width:0;background:#0a0a0a;border:1px solid #2a2a2a;color:#d0d0d0;padding:5px 8px;font-size:12px;border-radius:2px;",
    });
    const saveBtn = el("button", {
      type: "button", class: "comfymodal-primary-btn", text: "Save",
      "data-testid": `${testid}-save`,
      style: "width:auto;padding:5px 14px;font-size:11px;",
    });
    const clearNote = el("span", { text: "Save with an empty field to clear.", style: "font-size:10px;color:#555;" });
    card.appendChild(el("div", { style: "display:flex;gap:6px;align-items:center;" }, [input, saveBtn]));
    card.appendChild(el("div", { style: "margin-top:4px;" }, [clearNote]));

    const resultLine = el("div", { "data-testid": `${testid}-result`, style: "font-size:11px;color:#aaa;min-height:14px;margin-top:6px;", text: "" });
    card.appendChild(resultLine);

    async function readState() {
      let data = null;
      try { data = await getCredentialStatus(apiBase, kind); } catch { data = null; }
      renderConfigured(badgeWrap, credentialConfigured(data));
    }

    saveBtn.addEventListener("click", async () => {
      const token = input.value.trim();
      saveBtn.disabled = true;
      resultLine.textContent = "";
      let resp = null;
      try { resp = await saveCredentialToken(apiBase, kind, token); } catch { resp = null; }
      saveBtn.disabled = false;
      if (resp && resp.status === "ok") {
        input.value = "";
        resultLine.textContent = token ? "Saved." : "Cleared.";
        resultLine.style.color = "#7ed321";
        await readState();
      } else {
        // Bounded failure: server message only — the token value is never
        // included in error output.
        resultLine.textContent = (resp && (resp.message || resp.error)) || "Save failed.";
        resultLine.style.color = "#e05050";
      }
    });

    readState();
    return card;
  }

  function renderConfigured(wrap, configured) {
    while (wrap.firstChild) wrap.removeChild(wrap.firstChild);
    wrap.appendChild(configured
      ? statusBadge("CONFIGURED", "ok")
      : statusBadge("NOT CONFIGURED", "neutral"));
  }

  root.appendChild(modalCard);
  root.appendChild(credentialBlock(
    "hf",
    "\uD83E\uDD17 HuggingFace Token",
    "Required only for gated/private models on HuggingFace. Get a token at huggingface.co/settings/tokens.",
    "hf_...",
    "backend-cred-hf",
  ));
  root.appendChild(credentialBlock(
    "civitai",
    "\uD83C\uDFF0 Civitai API Key",
    "Required for gated/private/purchased models on Civitai. Get a key at civitai.com/user/account.",
    "Civitai API Key",
    "backend-cred-civitai",
  ));

  // Mount performs READ-ONLY status fetches only.
  (async () => {
    let data = null;
    try { data = await getAuthStatus(apiBase); } catch { data = null; }
    const connected = !!(data && data.connected === true);
    while (modalBadgeWrap.firstChild) modalBadgeWrap.removeChild(modalBadgeWrap.firstChild);
    modalBadgeWrap.appendChild(connected
      ? statusBadge("CONNECTED", "ok")
      : statusBadge("NOT CONFIGURED", "neutral"));
  })();

  container.appendChild(root);
  return root;
}
