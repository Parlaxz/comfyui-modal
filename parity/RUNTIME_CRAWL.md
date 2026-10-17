# Runtime crawl (reconciliation with source audit)

Status: PLANNED — source audit is done (behavior_inventory.json); runtime crawl
requires a live ComfyUI host. Every row stays UNKNOWN until crawled.

Protocol per behavior (record action, precondition, state before/after, UI,
network, persistence):
1. Open legacy Studio via `open_testing_modal` (web/modal-testing.js) on a clean profile.
2. Exercise the behavior with the parity corpus fixture mounted (parity/corpus/*.json).
3. Capture: screenshot/DOM snapshot, `localStorage`/`sessionStorage` diff, network (upload/image, mapping, run, history-v2), request intent payload.
4. Repeat in Vue via `openStudioVue` (web/studio-vue-host.js) on the same fixture.
5. Attach both semantic traces to the manifest row and flip legacy_runtime_verified only on evidence.

Real-app validation layer (Chrome DevTools MCP, never agent-browser, no GPU
unless generation is genuinely required): graph interaction, uploads,
real model inventories, editor/canvas, install/download flows, host integration.
Deterministic harness proves logic; this layer proves the host-dependent remainder.

Reconciled so far: none — all rows legacy_runtime_verified=false (see manifest.json).
Source-only findings are marked as such; runtime-only findings get added here, never silently.
