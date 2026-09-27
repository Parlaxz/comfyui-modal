# Modal Snapshot and Runtime Resync Design

## Goal

Reduce effective cold-start latency for Modal-hosted ComfyUI by making snapshot restore as cheap as possible, while keeping an explicit runtime resync path for newly added models and custom nodes.

## Root cause

- `restore()` currently performs work that should not happen on snapshot restore:
  - reloads the custom-node volume
  - rebuilds custom-node symlinks
  - may reinstall custom-node requirements
  - may restart ComfyUI
- That restore-path work directly consumes the latency savings that Modal memory snapshots are supposed to provide.
- Modal snapshots are not request-selectable by model name. They snapshot one deployed class state, not a per-request runtime variant.
- ComfyUI loads checkpoints on demand per workflow, so model-specific snapshot selection is not a practical fit for this repo.

## Confirmed Modal behavior

- `@modal.enter(snap=True)` runs before the snapshot is taken.
- `@modal.enter(snap=False)` runs after restore from the snapshot.
- Heavy work in `snap=False` reduces or negates snapshot benefit.
- Snapshots are used to accelerate cold boots after scale-to-zero or new worker startup.
- Snapshots are tied to the deployed class/function state, not chosen dynamically per request.
- Parameterized per-model snapshot pools are not a supported path for this use case.

## Approved scope

- Keep `min_containers=0`.
- Keep snapshots model-agnostic.
- Make `restore()` nearly no-op.
- Keep heavy sync/install work in `startup()` and explicit management actions only.
- Add a manual runtime resync control in the UI.
- Add timing and install-skip optimizations to reduce cold boot work.

## Design

### Lifecycle split

`startup()` remains the only heavy lifecycle hook. It will:

- ensure the ComfyUI models path points at the Modal models volume
- sync custom nodes from the custom-node volume into `ComfyUI/custom_nodes`
- install custom-node requirements when needed
- launch ComfyUI
- wait for ComfyUI readiness

`restore()` becomes near no-op. It will not:

- reload any Modal volume
- sync models or custom nodes
- reinstall requirements
- force a ComfyUI restart

At most, `restore()` may do a tiny in-process sanity check if required by reliability testing. The default design is an empty or nearly empty restore path.

### Model-agnostic snapshot strategy

The snapshot should capture a booted ComfyUI runtime, not a checkpoint-specific runtime.

This means snapshot value comes from skipping:

- Python import cost
- ComfyUI bootstrap and node registration
- CUDA/runtime initialization already completed before snapshot

This design intentionally does not try to snapshot arbitrary workflow-selected checkpoints. New workflows may still pay model-load cost when ComfyUI first needs a checkpoint after restore.

### Explicit runtime resync

Add an explicit runtime resync path for stale runtime state caused by newly added models or custom nodes.

Recommended behavior:

1. stop the ComfyUI subprocess
2. reload only the necessary Modal volumes
3. resync models/custom nodes into the in-container ComfyUI filesystem
4. reinstall custom-node requirements only when the resync scope includes custom nodes and the requirements changed
5. restart ComfyUI
6. wait for readiness and return a structured result

This gives the user a repair/reload path without discarding the whole Modal worker.

### Resync scopes

Support scoped runtime resync internally:

- `models`
- `custom_nodes`
- `all`

The UI may expose one button initially, but the backend should accept scope so the flow can stay efficient and extensible.

### UI control

Add a management button in `web/modal-settings.js` for manual runtime reconciliation.

Recommended label:

- `Resync Remote Runtime`

Expected behavior:

- call a backend endpoint that triggers scoped runtime resync
- show pending/success/failure feedback
- update visible status after completion
- keep wording clear that this reloads the remote ComfyUI runtime so new models or custom nodes become visible

### Runtime staleness detection

Add lightweight runtime-state detection so the UI can guide the user when resync is likely needed.

Examples:

- model inventory changed in the models volume after the runtime was started
- custom-node inventory changed after the runtime was started

This detection should be used to:

- surface “runtime may be stale” messaging
- encourage or trigger the manual resync path from explicit management actions

This detection must not be used to pretend Modal can pick different snapshots by model.

### Requirements install caching

Avoid reinstalling custom-node requirements on every cold startup when nothing changed.

For each custom node with `requirements.txt`:

- compute a deterministic hash of the file contents
- persist an installed-hash record in lightweight metadata
- skip `pip install -r requirements.txt` when the stored hash matches
- reinstall only when the hash changes or the metadata is missing

The metadata may live in a simple JSON file under a stable writable location in the container or volume-backed runtime metadata area.

### Timing instrumentation

Add structured timing logs around:

- startup total
- models volume setup
- custom-node sync
- requirements install total and per node
- ComfyUI launch
- ComfyUI readiness wait
- runtime resync total
- prompt queue submission
- prompt completion / history fetch

This logging should make it easy to distinguish:

- snapshot restore cost
- ComfyUI boot cost
- checkpoint/model load cost during generation
- workflow execution cost

### Failure handling

- If runtime resync fails before ComfyUI restarts, return a clear error payload and leave status as degraded/stale.
- If a custom-node requirements install fails, return which node failed and surface stderr/stdout excerpts as today.
- If runtime resync succeeds partially, return created/removed/kept/blocked details and any skipped install reasons.
- If `restore()` sanity checks reveal a dead subprocess, allow a minimal local restart fallback only if reliability testing proves it is necessary. Do not reintroduce full sync/install work there.

## Testing

Add or update tests for:

1. `restore()` does not call custom-node sync, requirements install, or volume reload logic
2. explicit runtime resync stops ComfyUI, reloads required volumes, and restarts ComfyUI
3. scoped resync only performs the requested work
4. unchanged `requirements.txt` skips reinstall
5. changed `requirements.txt` triggers reinstall
6. runtime staleness detection reports changed models/custom nodes without mutating runtime state
7. UI action hits the new backend endpoint and surfaces result states correctly

## Non-goals

- `min_containers=1`
- per-request model-specific snapshot selection
- parameterized snapshot pools per checkpoint
- preloading a default checkpoint into the snapshot
- full worker kill/redeploy as the default recovery path
