# Modal Studio Backend Hardening Design

## Goal

Refactor Modal Studio backend/frontend architecture so Workflow Snapshots and Backend Presets become the canonical Studio model, legacy comparison profiles remain compatibility/import sources only, Playground and Experiment consume Backend Presets only, and persistence/normalization/status handling move to safer, reviewable modules.

## Scope

In scope:

- Extract Studio snapshot/preset model, storage, and route code out of `__init__.py`.
- Add one reusable atomic JSON store with locking and explicit failure handling.
- Add server-side snapshot/preset normalizers and status derivation.
- Keep legacy comparison profile discovery/import support without using it as Studio runtime truth.
- Change new Studio selectors to consume Backend Presets only.
- Split `web/studio-backend.js` into focused frontend modules.
- Replace class-toggled feature chips with semantic chip buttons.
- Add behavior-oriented tests for normalization, route behavior, archived filtering, and preset-only selection flows.

Out of scope:

- New image-edit, SAM, mask-brush, or graph-binding editor features.
- Big-bang global rename of every historical “backend” reference.
- Silent auto-migration of all legacy profiles into snapshots/presets.
- Removal of old legacy screens.

## Domain Model

### Legacy comparison profile

- Import/discovery source only.
- Not the main Studio runtime object.
- Old legacy UI may continue using it directly.
- New Studio may inspect it, import it, or convert it into snapshot/preset records only through explicit user action.

### Workflow Snapshot

- Saved workflow/graph source of truth.
- Owns graph payload, API prompt payload, node-binding state, output mapping state, metadata, and archival state.
- Can be duplicated, archived, and edited.
- Status is derived server-side.
- Not necessarily runnable by itself.

### Backend Preset

- The only runtime-selectable object in new Studio.
- Playground backend selector consumes presets only.
- Experiment compare backend list consumes presets only.
- References a snapshot or an import/legacy source record.
- Status and disabled reason are derived server-side.

### Studio Backend

- Compatibility/UI label only.
- Not a separate persisted source of truth.
- Existing `.studio_backends.json` becomes compatibility/import support, not the future runtime model.

## Server Architecture

Add focused modules:

- `studio_models.py`
  - schema constants
  - feature requirement mirror/helpers
  - payload normalizers
  - snapshot/preset status derivation
  - stable error classification helpers
- `studio_store.py`
  - reusable `StudioJsonStore`
  - atomic write helper
  - file lock ownership
  - typed read/update entrypoints for list-shaped stores
- `studio_routes.py`
  - route registration function(s)
  - snapshot routes
  - preset routes
  - compatibility/import routes if needed by new Studio

`__init__.py` should keep route registration wiring only.

## Persistence Design

Create one reusable `StudioJsonStore` used by snapshots and presets.

Required behavior:

- one store instance per JSON file
- in-process `threading.Lock`
- read method returns parsed list data or raises a handled store error
- update method loads, mutates, writes atomically, and returns updated result
- atomic writes go to `*.tmp`, flush, `fsync`, then `os.replace`
- malformed JSON is treated as a handled store failure, not as “empty list”
- no silent exception swallowing

Files:

- `.studio_snapshots.json`
- `.studio_presets.json`
- `.studio_backends.json` remains compatibility/import data only

## Feature Requirement Mirror

Status derivation must use feature requirements from the Studio feature registry or a server-side mirror of the same minimum rules.

For this pass, use conservative rules:

- `txt2img` requires prompt binding, output mapping, and API prompt to be runnable.
- `object_remove` and `object_replace` may be saved, but should remain non-runnable unless required image/mask bindings are explicitly known.
- If required bindings/output mapping are not known, do not mark the snapshot or preset runnable.

The server mirror may start as a small constant structure in `studio_models.py`, but it should be shaped so it can later align more directly with the frontend feature registry.

## Snapshot Normalization

Snapshot create/update handlers must normalize server-side.

Normalize:

- `name`
- `description`
- `compatibleFeatures`
- `graphJson`
- `apiPromptJson`
- `nodeBindings`
- `outputNodeId`
- `modelSummary`
- `source`
- archival flags/metadata timestamps

Rules:

- trim labels/descriptions and enforce bounded lengths
- validate compatible feature IDs strictly; invalid IDs return a stable validation error
- reject malformed payload shapes instead of storing them verbatim
- constrain large payload fields conservatively
- never trust client-provided `status` or `disabledReason`

## Preset Normalization

Preset create/update handlers must normalize server-side.

Normalize:

- `label`
- `description`
- `snapshotId`
- `compatibleFeatures`
- `defaults`
- `sourceType`
- `sourceId`
- archival flags/metadata timestamps

Rules:

- validate `snapshotId` existence for snapshot-backed presets
- if a referenced snapshot is missing, preset status is `invalid`
- import/legacy-backed presets should report `metadata_only` or `import_only` unless they are actually executable through the new preset path
- never trust client-provided `status` or `disabledReason`

## Status Derivation

Status derivation order must be explicit and shared:

1. `archived`
2. `invalid`
3. `needs_bindings`
4. `needs_api_prompt`
5. `metadata_only` / `import_only`
6. `runnable`

### Snapshot status rules

- `archived` if archived flag is set
- `invalid` if required structure is malformed or feature linkage is invalid
- `needs_bindings` if required bindings/output mapping are missing for the snapshot’s compatible feature set
- `needs_api_prompt` if graph exists but API prompt is missing and bindings do not already block execution earlier
- `metadata_only` or `import_only` if the record is intentionally non-executable source metadata
- `runnable` only when all known requirements for the compatible feature set are satisfied

Do not treat “graph + API prompt exist” as automatically runnable when binding/output requirements remain unresolved.

### Preset status rules

- derive from referenced source plus preset defaults
- if referenced snapshot is not runnable, preset is not runnable
- if referenced snapshot is missing, preset is `invalid`
- if preset is legacy/import-backed and not executable in the new preset path, surface `import_only` or equivalent disabled state
- disabled reason is derived server-side from the first blocking condition

## Route Behavior

Snapshot and preset routes should support:

- list
- detail where needed
- create
- update
- archive
- duplicate

Behavior requirements:

- archived items hidden by default in list responses
- opt-in archived inclusion via request flag
- stable user-facing error messages only
- detailed exceptions logged server-side
- no raw exception strings returned to the browser

Example stable messages:

- `Failed to save snapshot`
- `Snapshot not found`
- `Invalid compatible feature`
- `Preset references a missing snapshot`

## Legacy Compatibility Behavior

- `.studio_backends.json` may be read by compatibility/import flows only.
- Playground and Experiment must not consume `.studio_backends.json` after this refactor.
- No automatic bulk conversion of legacy profiles.
- Any import/create from legacy data must be explicit user action.
- Existing legacy screens must remain available and functional.

## Frontend Architecture

Split `web/studio-backend.js` into:

- `web/studio-backend.js`
  - page composition only
  - public exports only
- `web/studio-backend-api.js`
  - fetch helpers for snapshots/presets/compat data
- `web/studio-backend-capture.js`
  - current Comfy graph capture adapter only
- `web/studio-backend-snapshots.js`
  - snapshot list/detail/editor rendering and events
- `web/studio-backend-presets.js`
  - preset list/detail/editor rendering and events
- `web/studio-ui.js`
  - shared DOM helpers, badges, info hints, semantic chip buttons

After this pass, `web/studio-backend.js` should not continue to own backend business logic.

## Frontend Behavior Changes

### Capture adapter

Replace direct UI-mutating graph capture with a clean adapter:

- `captureCurrentComfyGraph()` returns structured success/error data only
- caller decides how to render errors, forms, and follow-up actions

### Playground

- backend selector fetches Backend Presets only
- empty state points to Backend page for preset creation/import flow
- no dependency on `.studio_backends.json` runtime records

### Experiment

- Compare Backends list fetches Backend Presets only
- experiment selection state stores preset IDs only
- legacy/import-only presets may appear disabled or filtered based on server response, but they are not replaced with legacy profile records directly

### Semantic chips

Use `button type="button"` with `aria-pressed="true|false"` for chip toggles.

Requirements:

- JS state is the source of truth
- CSS classes reflect state, not define it
- preserve current Nexus-style chip look

## Migration and Risk Control

Use a staged semantic refactor in this order:

1. extract Studio model/store/routes from `__init__.py`
2. add atomic store and shared error handling
3. add snapshot/preset normalizers and server-side status derivation
4. keep legacy discovery/import support without runtime ownership
5. switch Playground selector to presets only
6. switch Experiment compare list to presets only
7. split frontend backend page modules
8. replace non-semantic chip toggles

This is a hardening/cleanup pass only. Do not add new generation or image-edit features during this work.

## Testing Strategy

Prefer behavior tests over source-string checks.

Required coverage:

- snapshot create/update/list/archive/duplicate route behavior
- preset create/update/list/archive/duplicate route behavior
- archived filtering defaults and include-archived override
- invalid compatible feature rejection
- missing snapshot preset rejection/invalid handling
- status derivation for conservative runnable vs non-runnable states
- Playground selector consuming presets only
- Experiment compare list consuming presets only
- legacy UI access still reachable

Structural/source checks may remain as lightweight guardrails, but they should not be the primary confidence mechanism for this refactor.

## Success Criteria

- `__init__.py` no longer contains the large inlined Studio snapshot/preset storage and route implementation block.
- Snapshot/preset persistence uses one reusable atomic store with no silent load/save failure path.
- Snapshot and preset status/disabled reason are derived server-side.
- `.studio_backends.json` is no longer used by Playground or Experiment selectors.
- Playground and Experiment both consume Backend Presets only.
- `web/studio-backend.js` is reduced to composition/export glue.
- feature chip toggles are semantic buttons with `aria-pressed`.
- legacy screens remain available.
