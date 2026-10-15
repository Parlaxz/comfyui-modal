// Studio portal target — the one obvious place to resolve it.
//
// Reka/shadcn portalled UI (Dialog, Popover, Select, Dropdown) must render
// into `[data-studio-portals]`, the Studio-contained target owned by the
// ComfyUI host (see web/studio-vue-host.js) — never into document.body,
// where Studio styling, z-index, focus, and containment break down.
//
// If the target is missing, the host contract is broken: fail visibly with
// a descriptive error rather than silently teleporting to document.body.

export function getStudioPortalTarget(): HTMLElement {
  if (typeof document === "undefined") {
    throw new Error(
      "[studio] portal target unavailable: no document (the Vue Studio only runs in the ComfyUI browser host)",
    );
  }
  const target = document.querySelector<HTMLElement>("[data-studio-portals]");
  if (!target) {
    throw new Error(
      "[studio] missing [data-studio-portals]: the ComfyUI host must create the Studio-contained portal target before mounting the Vue app",
    );
  }
  return target;
}
