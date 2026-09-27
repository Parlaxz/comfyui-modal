// Modal Studio — reusable, fixed field blocks.
//
// Blocks own rendering and value parsing for the small set of input kinds the
// Studio wrapper supports.  They are intentionally not extensible at runtime:
// product code adds a catalog entry/block when a new capability is approved.

import { el } from "./studio-ui.js";

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
