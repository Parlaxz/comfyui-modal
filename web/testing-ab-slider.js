// web/testing-ab-slider.js
//
// Two-image A/B comparison slot with fullscreen viewer.
//
// Public API:
//   ab_slot_render(rootEl, options)
//   ab_slider_render(rootEl, options)
//   ab_slider_open_fullscreen(options)

function el(tag, props = {}, children = []) {
  const e = document.createElement(tag);
  for (const k in props) {
    if (k === "class") e.className = props[k];
    else if (k === "style") e.style.cssText = props[k];
    else if (k === "text") e.textContent = props[k];
    else if (k.startsWith("on") && typeof props[k] === "function") {
      e.addEventListener(k.slice(2).toLowerCase(), props[k]);
    } else if (k === "value") {
      e.value = props[k];
    } else {
      e.setAttribute(k, props[k]);
    }
  }
  for (const c of (Array.isArray(children) ? children : [children])) {
    if (c == null) continue;
    e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return e;
}

const SELECTION_LIMIT = 2;

export function ab_slot_render(rootEl, options = {}) {
  // The legacy entrypoint: build a slot that can hold up to
  // SELECTION_LIMIT images and render the A/B slider when two are
  // present.  The selection is held in the closure and exposed via
  // the returned object.
  const selection = [];
  const shell = el("div", { class: "testing-ab-slot", "data-testid": "ab-slot" });
  const render = () => {
    while (shell.firstChild) shell.removeChild(shell.firstChild);
    if (selection.length === 0) {
      shell.appendChild(el("p", { class: "testing-ab-empty",
        text: "Right-click two images to compare them here" }));
    } else if (selection.length === 1) {
      shell.appendChild(el("img", { src: selection[0].src, class: "testing-ab-preview" }));
      shell.appendChild(el("p", { class: "testing-ab-hint",
        text: "Right-click a second image to compare" }));
    } else {
      ab_slider_render(shell, {
        aSrc: selection[0].src,
        bSrc: selection[1].src,
        aLabel: selection[0].label || "A",
        bLabel: selection[1].label || "B",
      });
    }
  };
  render();
  rootEl.appendChild(shell);
  return {
    add(image) {
      if (!image || !image.src) return;
      if (selection.length >= SELECTION_LIMIT) selection.shift();
      selection.push(image);
      render();
    },
    remove(image) {
      const i = selection.findIndex((s) => s.src === image.src);
      if (i >= 0) { selection.splice(i, 1); render(); }
    },
    clear() { selection.length = 0; render(); },
    getSelection: () => selection.slice(),
  };
}

export function ab_slider_render(rootEl, options = {}) {
  if (!rootEl) throw new Error("ab_slider_render: rootEl is required");
  const aSrc = options.aSrc || "";
  const bSrc = options.bSrc || "";
  const aLabel = options.aLabel || "A";
  const bLabel = options.bLabel || "B";
  const wrap = el("div", { class: "testing-ab-slider", role: "slider",
    "aria-label": `A/B comparison: ${aLabel} vs ${bLabel}`,
    "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": "50",
    tabindex: "0" });
  const a = el("img", { src: aSrc, class: "testing-ab-side testing-ab-side-a", alt: aLabel });
  const b = el("img", { src: bSrc, class: "testing-ab-side testing-ab-side-b", alt: bLabel });
  const divider = el("div", { class: "testing-ab-divider" });
  wrap.appendChild(a);
  wrap.appendChild(b);
  wrap.appendChild(divider);
  const handle = el("div", { class: "testing-ab-handle" });
  wrap.appendChild(handle);
  wrap.appendChild(el("div", { class: "testing-ab-label testing-ab-label-a", text: aLabel }));
  wrap.appendChild(el("div", { class: "testing-ab-label testing-ab-label-b", text: bLabel }));

  let position = 50; // percent
  function setPosition(p) {
    position = Math.max(0, Math.min(100, p));
    divider.style.left = `${position}%`;
    handle.style.left = `${position}%`;
    b.style.clipPath = `inset(0 0 0 ${position}%)`;
    wrap.setAttribute("aria-valuenow", String(Math.round(position)));
  }
  setPosition(50);
  let dragging = false;
  const onMove = (ev) => {
    if (!dragging) return;
    const rect = wrap.getBoundingClientRect();
    const px = (ev.clientX || (ev.touches && ev.touches[0] && ev.touches[0].clientX) || 0) - rect.left;
    setPosition((px / rect.width) * 100);
  };
  wrap.addEventListener("mousedown", (ev) => { dragging = true; onMove(ev); });
  wrap.addEventListener("touchstart", (ev) => { dragging = true; onMove(ev); }, { passive: true });
  window.addEventListener("mousemove", onMove);
  window.addEventListener("touchmove", onMove, { passive: true });
  window.addEventListener("mouseup", () => { dragging = false; });
  window.addEventListener("touchend", () => { dragging = false; });
  wrap.addEventListener("keydown", (ev) => {
    const step = (ev.shiftKey ? 10 : 2);
    if (ev.key === "ArrowLeft") { setPosition(position - step); ev.preventDefault(); }
    else if (ev.key === "ArrowRight") { setPosition(position + step); ev.preventDefault(); }
    else if (ev.key === "Home") { setPosition(0); ev.preventDefault(); }
    else if (ev.key === "End") { setPosition(100); ev.preventDefault(); }
  });

  rootEl.appendChild(wrap);
  return {
    on_fullscreen: null,
    on_swap: null,
    set_position: setPosition,
  };
}

export function ab_slider_open_fullscreen(options = {}) {
  const overlay = el("div", { class: "testing-ab-fullscreen-overlay" });
  const stage = el("div", { class: "testing-ab-fullscreen-stage" });
  const a = el("img", { src: options.aSrc, class: "testing-ab-fullside testing-ab-fullside-a" });
  const b = el("img", { src: options.bSrc, class: "testing-ab-fullside testing-ab-fullside-b" });
  const divider = el("div", { class: "testing-ab-fulldivider" });
  stage.appendChild(a);
  stage.appendChild(b);
  stage.appendChild(divider);
  const handle = el("div", { class: "testing-ab-fullhandle" });
  stage.appendChild(handle);
  const aLabel = el("div", { class: "testing-ab-label testing-ab-label-a", text: options.aLabel || "A" });
  const bLabel = el("div", { class: "testing-ab-label testing-ab-label-b", text: options.bLabel || "B" });
  stage.appendChild(aLabel);
  stage.appendChild(bLabel);
  const toolbar = el("div", { class: "testing-ab-fulltoolbar" });
  const fitBtn = el("button", { class: "testing-results-btn", text: "Fit" });
  const actualBtn = el("button", { class: "testing-results-btn", text: "Actual" });
  const zoomInBtn = el("button", { class: "testing-results-btn", text: "Zoom +" });
  const zoomOutBtn = el("button", { class: "testing-results-btn", text: "Zoom -" });
  const swapBtn = el("button", { class: "testing-results-btn", text: "Swap" });
  const closeBtn = el("button", { class: "testing-results-btn", text: "Close" });
  toolbar.appendChild(fitBtn);
  toolbar.appendChild(actualBtn);
  toolbar.appendChild(zoomInBtn);
  toolbar.appendChild(zoomOutBtn);
  toolbar.appendChild(swapBtn);
  toolbar.appendChild(closeBtn);
  overlay.appendChild(stage);
  overlay.appendChild(toolbar);
  document.body.appendChild(overlay);

  // Slider behavior
  let position = 50;
  function setPos(p) {
    position = Math.max(0, Math.min(100, p));
    divider.style.left = `${position}%`;
    handle.style.left = `${position}%`;
    b.style.clipPath = `inset(0 0 0 ${position}%)`;
  }
  setPos(50);
  let dragging = false;
  const onMove = (ev) => {
    if (!dragging) return;
    const rect = stage.getBoundingClientRect();
    const px = (ev.clientX || 0) - rect.left;
    setPos((px / rect.width) * 100);
  };
  stage.addEventListener("mousedown", (ev) => { dragging = true; onMove(ev); });
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", () => { dragging = false; });

  // Pan / zoom
  let scale = 1;
  let panX = 0;
  let panY = 0;
  let isPanning = false;
  let panStart = { x: 0, y: 0 };
  function applyTransform() {
    a.style.transformOrigin = "0 0";
    b.style.transformOrigin = "0 0";
    a.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
    b.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
  }
  function fit() { scale = 1; panX = 0; panY = 0; applyTransform(); }
  // Actual size: show the image at its native pixel resolution (1 device
  // pixel = 1 image pixel) inside the viewport, with letterboxing if
  // larger than the stage.
  function actual() {
    const rect = stage.getBoundingClientRect();
    const aw = (a.naturalWidth || 1);
    const ah = (a.naturalHeight || 1);
    const sX = rect.width / aw;
    const sY = rect.height / ah;
    scale = Math.min(sX, sY, 1); // never upscale beyond 1:1 native pixels
    panX = (rect.width - aw * scale) / 2;
    panY = (rect.height - ah * scale) / 2;
    applyTransform();
  }
  function zoomIn() { scale = Math.min(8, scale * 1.25); applyTransform(); }
  function zoomOut() { scale = Math.max(0.1, scale / 1.25); applyTransform(); }
  function swap() {
    const tmpSrc = a.src;
    a.src = b.src;
    b.src = tmpSrc;
    const tmpLabel = aLabel.textContent;
    aLabel.textContent = bLabel.textContent;
    bLabel.textContent = tmpLabel;
  }
  function close() {
    overlay.remove();
    window.removeEventListener("keydown", onKey);
  }
  fitBtn.addEventListener("click", fit);
  actualBtn.addEventListener("click", actual);
  zoomInBtn.addEventListener("click", zoomIn);
  zoomOutBtn.addEventListener("click", zoomOut);
  swapBtn.addEventListener("click", swap);
  closeBtn.addEventListener("click", close);
  overlay.addEventListener("click", (ev) => { if (ev.target === overlay) close(); });

  // Wheel to zoom
  overlay.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    if (ev.deltaY < 0) zoomIn(); else zoomOut();
  }, { passive: false });
  // Pan with middle/right mouse
  overlay.addEventListener("mousedown", (ev) => {
    if (ev.button !== 1 && ev.button !== 2) return;
    isPanning = true;
    panStart = { x: ev.clientX - panX, y: ev.clientY - panY };
  });
  window.addEventListener("mousemove", (ev) => {
    if (!isPanning) return;
    panX = ev.clientX - panStart.x;
    panY = ev.clientY - panStart.y;
    applyTransform();
  });
  window.addEventListener("mouseup", () => { isPanning = false; });
  // Keyboard: Esc to close, arrows to adjust slider, +/- to zoom
  function onKey(ev) {
    if (ev.key === "Escape") { close(); return; }
    if (ev.key === "ArrowLeft") { setPos(position - (ev.shiftKey ? 10 : 2)); ev.preventDefault(); return; }
    if (ev.key === "ArrowRight") { setPos(position + (ev.shiftKey ? 10 : 2)); ev.preventDefault(); return; }
    if (ev.key === "+" || ev.key === "=") { zoomIn(); ev.preventDefault(); return; }
    if (ev.key === "-" || ev.key === "_") { zoomOut(); ev.preventDefault(); return; }
    if (ev.key === "0") { fit(); ev.preventDefault(); return; }
    if (ev.key === "1") { actual(); ev.preventDefault(); return; }
  }
  window.addEventListener("keydown", onKey);
}

export const _internal = { el };
