// Modal Studio — reusable, fixed field blocks.
//
// Blocks own rendering and value parsing for the small set of input kinds the
// Studio wrapper supports.  They are intentionally not extensible at runtime:
// product code adds a catalog entry/block when a new capability is approved.

import { el } from "./studio-ui.js";
import { openHistoryPicker } from "./studio-history-picker.js";

export const INTEGER_RULES = Object.freeze({
  seed: Object.freeze({ minimum: null, maximum: null, step: 1, allowNegative: true }),
  nonNegative: Object.freeze({ minimum: 0, maximum: null, step: 1, allowNegative: false }),
});

function controlProps(props, kind) {
  const inputProps = props || {};
  const result = {
    class: "comfymodal-input comfymodal-studio-field-block",
    "data-field-kind": kind,
  };
  if (inputProps.testid) result["data-testid"] = inputProps.testid;
  return result;
}

function attachChange(input, props, readValue, eventName) {
  if (props && typeof props.onChange === "function") {
    input.addEventListener(eventName || "input", () => props.onChange(readValue(input)));
  }
  return input;
}

function setValue(input, value) {
  if (value !== undefined && value !== null) input.value = String(value);
  return input;
}

export function renderMultilineBlock(props = {}) {
  const input = el("textarea", {
    ...controlProps(props, "multiline"),
    placeholder: props.placeholder || "",
    rows: props.rows || 3,
  });
  setValue(input, props.value);
  return attachChange(input, props, (node) => node.value, "input");
}

export function renderIntegerBlock(props = {}) {
  const rules = props.rules || INTEGER_RULES.nonNegative;
  const input = el("input", {
    ...controlProps(props, "integer"),
    type: "number",
    step: String(rules.step == null ? 1 : rules.step),
  });
  if (rules.minimum != null) input.setAttribute("min", String(rules.minimum));
  if (rules.maximum != null) input.setAttribute("max", String(rules.maximum));
  setValue(input, props.value);
  return attachChange(input, props, (node) => {
    if (node.value === "") return "";
    const value = Number(node.value);
    return Number.isInteger(value) ? value : node.value;
  }, "input");
}

export function renderFloatBlock(props = {}) {
  const rules = props.rules || {};
  const input = el("input", {
    ...controlProps(props, "float"),
    type: "number",
    step: String(rules.step == null ? "any" : rules.step),
  });
  if (rules.minimum != null) input.setAttribute("min", String(rules.minimum));
  if (rules.maximum != null) input.setAttribute("max", String(rules.maximum));
  setValue(input, props.value);
  return attachChange(input, props, (node) => {
    if (node.value === "") return "";
    const value = Number(node.value);
    return Number.isFinite(value) ? value : node.value;
  }, "input");
}

function optionValue(option) {
  if (option && typeof option === "object") {
    if (option.value !== undefined) return option.value;
    if (option.name !== undefined) return option.name;
    if (option.label !== undefined) return option.label;
    if (option.filename !== undefined) return option.filename;
    return option.id;
  }
  return option;
}

function optionLabel(option, value) {
  if (option && typeof option === "object") {
    return option.label !== undefined
      ? option.label
      : (option.display_name !== undefined ? option.display_name : value);
  }
  return value;
}

export function renderDropdownBlock(props = {}) {
  const input = el("select", controlProps(props, "dropdown"));
  (props.options || []).forEach((option) => {
    const value = optionValue(option);
    if (value === undefined || value === null) return;
    input.appendChild(el("option", { value: String(value), text: String(optionLabel(option, value)) }));
  });
  setValue(input, props.value);
  return attachChange(input, props, (node) => node.value, "change");
}

export function renderModelPickerBlock(props = {}) {
  const input = el("select", {
    ...controlProps(props, "model"),
    "aria-label": props.label || "Model",
  });
  (props.models || props.options || []).forEach((model) => {
    const value = optionValue(model);
    if (value === undefined || value === null) return;
    input.appendChild(el("option", { value: String(value), text: String(optionLabel(model, value)) }));
  });
  setValue(input, props.value);
  return attachChange(input, props, (node) => node.value, "change");
}

function _imagePreviewSrc(value, previewUrl) {
  if (previewUrl) return previewUrl;
  if (!value) return "";
  const v = String(value);
  if (/^(blob:|data:|https?:\/\/|\/)/.test(v)) return v;
  // Annotated workspace references ("name [output]") keep their directory:
  // preview from the matching /view type instead of a 404 bare filename.
  const m = v.match(/^(.*) \[(input|output|temp)\]$/);
  if (m) return "/view?filename=" + encodeURIComponent(m[1]) + "&type=" + m[2];
  return "/view?filename=" + encodeURIComponent(v) + "&type=input";
}

export function uniqueImageName(prefix) {
  const safe = String(prefix || "studio").replace(/[^a-z0-9_-]+/gi, "-").slice(0, 24) || "studio";
  let rand = "";
  try {
    const buf = new Uint32Array(2);
    crypto.getRandomValues(buf);
    rand = Array.from(buf).map((n) => n.toString(36)).join("").slice(0, 8);
  } catch (_e) {
    rand = Math.floor(Math.random() * 36 ** 8).toString(36);
  }
  return safe + "-" + Date.now().toString(36) + "-" + rand + ".png";
}

export async function uploadImageBlob(blob, filename) {
  const form = new FormData();
  form.append("image", blob, filename || uniqueImageName("studio-image"));
  form.append("overwrite", "false");
  let res = null;
  try {
    res = await fetch("/upload/image", { method: "POST", body: form });
  } catch (err) {
    throw new Error("Image upload request failed: " + (err && err.message ? err.message : err));
  }
  if (!res || !res.ok) throw new Error("Image upload failed (HTTP " + (res && res.status) + ")");
  let data = null;
  try { data = await res.json(); } catch (_e) { data = null; }
  const name = (data && (data.name || (data.files && data.files[0]))) || filename || "";
  if (!name) throw new Error("Image upload returned no filename");
  return String(name);
}

// Single-select History gallery for image inputs: the shared
// openHistoryPicker in single mode (click highlights, then Use image
// applies). Picking hands the record URL to onPickHistory (fetch → upload
// → bind as a real mapped filename) via Confirm; Escape/backdrop closes.
function _openHistoryBrowser(props) {
  const p = props || {};
  openHistoryPicker({
    mode: "single",
    testid: p.testid || "shelf-image",
    apiBase: p.apiBase,
    historyItems: p.historyItems,
    onConfirm: function (pick) {
      if (pick && pick.url && typeof p.onPickHistory === "function") {
        try { p.onPickHistory(pick.url); } catch (_e) { /* caller handles */ }
      }
    },
  });
}

export function renderImageBlock(props = {}) {  const wrap = el("div", { ...controlProps(props, "image"), "data-testid": props.testid || "shelf-image-block" });
  wrap.style.display = "flex";
  wrap.style.flexDirection = "column";
  wrap.style.gap = "6px";
  const current = props.value != null ? String(props.value) : "";
  const previewSrc = _imagePreviewSrc(current, props.previewUrl);
  if (previewSrc) {
    const img = el("img", {
      src: previewSrc,
      alt: props.label || "Selected image",
      "data-testid": (props.testid || "shelf-image") + "-preview",
    });
    img.style.maxWidth = "100%";
    img.style.maxHeight = "160px";
    img.style.objectFit = "contain";
    img.style.borderRadius = "6px";
    wrap.appendChild(img);
  } else {
    wrap.appendChild(el("p", {
      class: "comfymodal-studio-control-note",
      text: "No image selected.",
      "data-testid": (props.testid || "shelf-image") + "-empty",
    }));
  }
  const row = el("div", {});
  row.style.display = "flex";
  row.style.gap = "6px";
  row.style.flexWrap = "wrap";
  const file = el("input", {
    type: "file",
    accept: "image/*",
    class: "comfymodal-input",
    "data-testid": (props.testid || "shelf-image") + "-file",
    "aria-label": props.label || "Choose image",
  });
  file.addEventListener("change", async () => {
    const f = file.files && file.files[0];
    if (!f || typeof props.onChange !== "function") return;
    try {
      const name = await uploadImageBlob(f, f.name);
      props.onChange(name);
    } catch (_e) { /* caller surfaces errors via run gating; keep prior value */ }
  });
  row.appendChild(file);
  const ingestFile = async (f) => {
    if (!f || typeof props.onChange !== "function") return;
    try {
      const name = await uploadImageBlob(f, f.name);
      props.onChange(name);
    } catch (_e) { /* keep prior value, same as file handler */ }
  };
  wrap.setAttribute("tabindex", "0");
  wrap.addEventListener("dragover", (ev) => {
    ev.preventDefault();
    wrap.style.outline = "1px dashed #888";
  });
  wrap.addEventListener("dragleave", () => { wrap.style.outline = ""; });
  wrap.addEventListener("drop", (ev) => {
    ev.preventDefault();
    wrap.style.outline = "";
    const f = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
    if (f && (!f.type || f.type.indexOf("image/") === 0)) ingestFile(f);
  });
  wrap.addEventListener("paste", (ev) => {
    const items = ev.clipboardData && ev.clipboardData.items;
    if (!items) return;
    for (const item of items) {
      if (item.type && item.type.indexOf("image/") === 0) {
        ev.preventDefault();
        ingestFile(item.getAsFile());
        break;
      }
    }
  });
  if (typeof props.onToggleLink === "function") {
    // A checkmark, not an action button: it shows whether this input is
    // currently bound to the canvas image, and (un)checking (un)binds it.
    // While a link is in flight the box disables so a second click cannot
    // start a competing upload.
    const linkLabel = el("label", {
      style: "display:flex;align-items:center;gap:4px;font-size:11px;color:#aaa;cursor:pointer;",
    });
    const linkBox = el("input", {
      type: "checkbox",
      "data-testid": (props.testid || "shelf-image") + "-use-current",
      "aria-label": "Use the current canvas image",
    });
    linkBox.checked = props.canvasLinked === true;
    if (props.linkBusy) {
      linkBox.disabled = true;
      linkBox.title = "Linking canvas image…";
    }
    linkBox.addEventListener("change", () => props.onToggleLink(linkBox.checked));
    linkLabel.appendChild(linkBox);
    linkLabel.appendChild(el("span", { text: "Canvas" }));
    row.appendChild(linkLabel);
  } else if (typeof props.onUseCurrent === "function") {
    const useBtn = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn",
      text: "Use current",
      "data-testid": (props.testid || "shelf-image") + "-use-current",
    });
    useBtn.addEventListener("click", () => props.onUseCurrent());
    row.appendChild(useBtn);
  }
  if (typeof props.onPickHistory === "function"
    && Array.isArray(props.historyItems) && props.historyItems.length) {
    const browseBtn = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn",
      text: "Browse history…",
      "data-testid": (props.testid || "shelf-image") + "-history-browse",
    });
    browseBtn.addEventListener("click", () => {
      _openHistoryBrowser(props);
    });
    row.appendChild(browseBtn);
  }
  if (current && typeof props.onChange === "function") {
    const clearBtn = el("button", {
      type: "button",
      class: "comfymodal-secondary-btn",
      text: "Clear",
      "data-testid": (props.testid || "shelf-image") + "-clear",
    });
    clearBtn.addEventListener("click", () => props.onChange(""));
    row.appendChild(clearBtn);
  }
  wrap.appendChild(row);
  if (props.linkError) {
    wrap.appendChild(el("p", {
      class: "comfymodal-studio-control-note",
      text: String(props.linkError),
      style: "color:#f87171;",
      "data-testid": (props.testid || "shelf-image") + "-link-error",
    }));
  }
  return wrap;
}

export const FIELD_BLOCKS = Object.freeze({
  multiline: Object.freeze({
    kind: "multiline",
    inputKind: "multiline",
    render: renderMultilineBlock,
  }),
  integer: Object.freeze({
    kind: "integer",
    inputKind: "integer",
    render: renderIntegerBlock,
  }),
  float: Object.freeze({
    kind: "float",
    inputKind: "float",
    render: renderFloatBlock,
  }),
  dropdown: Object.freeze({
    kind: "dropdown",
    inputKind: "dropdown",
    render: renderDropdownBlock,
  }),
  "model-picker": Object.freeze({
    kind: "model-picker",
    inputKind: "model",
    render: renderModelPickerBlock,
  }),
  image: Object.freeze({
    kind: "image",
    inputKind: "image",
    render: renderImageBlock,
  }),
});

export const BLOCK_DEFINITIONS = FIELD_BLOCKS;

export function getFieldBlock(kind) {
  return FIELD_BLOCKS[kind] || null;
}

export function renderFieldBlock(kind, props = {}) {
  const block = getFieldBlock(kind);
  if (!block) throw new TypeError("Unknown Studio field block: " + kind);
  return block.render(props);
}
