# Modal Workspace Swap + Manifest Sync Design

Date: 2026-06-11

## Goal

Let one local ComfyUI install switch between multiple **Modal workspaces** from the comfyui-modal sidebar, while keeping model downloads, custom-node sync, and redeploy behavior aligned with the selected workspace.

The workflow should stay simple:

- choose a saved Modal workspace from a dropdown
- click **Swap Workspace**
- repair any missing manifest links if needed
- install manifest-backed models missing from that Modal workspace
- sync custom nodes
- redeploy

The feature also adds manifest maintenance and sharing:

- every new model download is written to a persistent manifest
- a **Manifest Repair** button fixes incomplete manifest entries
- an **Export Workflow Manifest** button exports the model links used by a workflow
- an **Import Workflow Manifest** button merges a shared workflow manifest into the local manifest

## Success Criteria

- the sidebar can save and switch between multiple Modal workspace profiles from one local install
- workspace switching does **not** depend on changing the ComfyUI root path
- every Modal-bound action resolves against the selected workspace
- every newly installed model is recorded in a master manifest with folder/type and source URL
- swapping to a workspace installs manifest-backed models that are missing remotely
- swapping pauses for manifest repair when a required model is missing a source URL
- custom nodes are synced after model reconciliation
- redeploy starts after a successful swap sync sequence
- workflow manifest export contains the models used by the workflow and excludes tokens
- workflow manifest import merges safely and surfaces conflicts instead of silently overwriting
- manifest repair can be run directly from the sidebar even outside a workspace swap

## Non-Goals

This design does **not** include:

- creating a second local ComfyUI installation
- moving or duplicating the local ComfyUI root
- reusing the user's global `~/.modal.toml` as the primary source of truth
- exporting or importing workspace tokens
- automatically inferring every missing model URL from the internet
- adding checksum-based model verification in v1
- changing the current placeholder model mechanism
- git commits unless explicitly requested by the user

## User-Approved Decisions

- “workspace” means a **Modal workspace/token context**, not a local filesystem workspace
- the local ComfyUI install stays the same; only the Modal workspace changes
- the main UX lives in the existing comfyui-modal sidebar
- the sidebar gets a workspace dropdown plus action buttons
- swap behavior should:
  - check the manifest and local custom nodes
  - install manifest-backed models missing from the selected Modal workspace
  - redeploy
- any new model installed from now on must be written to the manifest
- if a workspace swap hits manifest entries with missing links, the UI must open a repair window before continuing
- manifest entries must remember model type/folder such as LoRA, CLIP, VAE, etc.
- there must be an **Export Workflow Manifest** button so a friend can import the links into their own manifest
- there must be an **Import Workflow Manifest** button to merge a shared workflow manifest into the local master manifest
- there must also be a standalone **Manifest Repair** button

## Current Context

Current relevant behavior in this repo:

- Modal token handling is currently single-workspace oriented in `__init__.py`
  - `_MODAL_TOML_PATH` is written by `_write_modal_toml(...)`
  - `_is_modal_token_set()` checks one token location
- Hugging Face and Civitai tokens are stored locally in the custom node via:
  - `_HF_TOKEN_PATH`
  - `_CIVITAI_TOKEN_PATH`
  - `_read_hf_token()`, `_write_hf_token()`, `_read_civitai_token()`, `_write_civitai_token()`
- model downloads currently go through:
  - `/comfymodal/model/install`
  - `/comfymodal/models/batch-install`
  - `download_model_stream(...)`
  - `batch_download_models(...)`
- placeholder support already exists through:
  - `local_placeholders.py`
  - `/comfymodal/models/inject`
  - `/comfymodal/models/inject-all`
- model listing currently comes from `/comfymodal/models`, backed by `list_models()`
- custom-node sync already exists through `/comfymodal/sync/custom-nodes`
- background deploy already exists via `_run_deploy_background(...)` and deploy status routes
- the current client layer in `modal_client.py` builds Modal handles at module import time and caches them globally

The missing pieces are:

- a multi-workspace registry in the plugin
- a workspace-aware Modal execution layer
- a persistent source-link manifest for models
- a repair flow for incomplete manifest entries
- workflow-specific manifest export/import

## External Modal Constraints

Official Modal behavior relevant to this design:

- a Modal token identifies the workspace context; switching tokens switches workspaces
- apps, secrets, volumes, and function lookups are workspace-scoped
- the Python SDK caches client state early, so changing workspace tokens mid-process is error-prone if code relies on a single globally initialized client
- `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` can override config file resolution
- mutating the user's global Modal profile state is possible but is not a good primary design for this plugin

This strongly favors a plugin-managed workspace registry plus explicit workspace-scoped execution instead of rewriting the user's global active Modal profile.

## Approaches Considered

### 1. Plugin-managed workspace profiles + workspace-aware execution **(recommended)**

The plugin stores multiple Modal workspace profiles locally and routes every Modal-bound action through the selected workspace context.

Pros:

- matches the requested sidebar UX
- avoids relying on the user's global `~/.modal.toml`
- makes workspace switching explicit and local to the plugin
- can support model sync, deploy, and manifest flows consistently

Cons:

- requires refactoring current Modal-bound calls to stop assuming one global client context

### 2. Plugin-managed `.modal.toml` with multiple profiles

The plugin owns its own config file and switches profiles using `MODAL_CONFIG_PATH` and `MODAL_PROFILE`.

Pros:

- aligns with Modal profile semantics

Cons:

- still easy to get stale in-process client handles if the current code keeps global Modal objects alive
- less direct than using explicit token-bound execution state inside the plugin

### 3. Rewrite the user's global active Modal profile

The sidebar edits the user's active profile in the global config and then continues normally.

Pros:

- smallest short-term change

Cons:

- leaks plugin behavior into other shells and tools
- can be overridden by environment variables outside the plugin
- creates surprising side effects for the user

## Recommended Design

Use a **plugin-managed workspace registry** combined with a **workspace-aware Modal execution layer** and a **persistent master model manifest**.

This design has five units:

1. workspace registry
2. workspace execution context
3. master model manifest
4. manifest repair flow
5. workflow manifest export/import

## Architecture

### 1. Workspace Registry

Add a local plugin-managed registry of saved Modal workspaces.

Each workspace profile stores:

- `id`
- `label`
- `token_id`
- `token_secret`
- `last_used_at`
- `last_deploy_status`
- `notes` (optional)

One workspace id is stored as the current active selection.

Requirements:

- labels are used in the dropdown
- token secrets are masked in the UI after save
- tokens never appear in workflow manifest export/import files
- registry storage is local to the plugin and independent of the user's global Modal config

### 2. Workspace Execution Context

Every Modal-bound action must resolve against the selected workspace rather than one startup-time global client.

That includes:

- deploy
- custom-node sync
- model list
- single model install
- batch model install
- prompt execution
- health/object-info/runtime actions that refer to deployed Modal resources

Design requirement:

- centralize workspace selection in one execution path instead of sprinkling token overrides across unrelated route handlers

Key rule:

- switching the selected workspace in the UI does **not** silently mutate the user's global Modal profile state

### 3. Master Model Manifest

Add one local manifest file that stores all known source-backed model entries.

Identity key:

- `(folder, filename)`

Each manifest entry stores:

- `folder`
- `filename`
- `url`
- `source_kind` — `huggingface`, `civitai`, `direct`, or `unknown`
- `requires_hf_token` — bool
- `requires_civitai_token` — bool
- `sha256` — optional, reserved for future use
- `notes` — optional
- `added_at`
- `updated_at`

The master manifest becomes the source of truth for:

- workspace swap installs
- manifest repair
- workflow export/import
- future source-link reuse

### 4. Manifest Repair Flow

Add a repair flow that scans the master manifest for incomplete or inconsistent entries.

Repair should detect:

- missing `url`
- missing `source_kind`
- invalid or unsupported folder/type
- duplicate entries for the same `(folder, filename)`

The repair flow is used in two ways:

- proactively, from the sidebar **Manifest Repair** button
- as a blocking prerequisite during workspace swap or workflow export when required entries are incomplete

### 5. Workflow Manifest Export / Import

Add export/import support for sharing model source links used by a workflow.

Export must:

- include only models used by the workflow
- exclude workspace tokens and local secrets
- use the same manifest entry schema subset for easy merge

Import must:

- merge into the master manifest
- never overwrite conflicting URLs silently
- surface conflicts for explicit user choice

## Sidebar UX

Add a new **Workspace** section in the existing comfyui-modal sidebar.

Controls:

- **Workspace dropdown** — lists saved Modal workspace profiles by label
- **Swap Workspace** button
- **Manifest Repair** button
- **Export Workflow Manifest** button
- **Import Workflow Manifest** button

Interaction rules:

- selecting a dropdown item alone does not immediately switch workspaces
- the user must explicitly click **Swap Workspace**
- if a swap or deploy is already running, swap/repair/import/export actions are disabled
- no hover-only controls
- no icon-only controls for primary actions

### Swap Workspace Flow

When the user clicks **Swap Workspace**:

1. validate the selected workspace credentials
2. query that workspace's remote model inventory
3. compare:
   - master manifest
   - selected workspace remote models
   - local custom nodes for sync/deploy follow-up
4. if required manifest entries are unresolved, open Manifest Repair before continuing
5. after repair/skip resolution:
   - install manifest-backed models that are missing remotely
   - sync custom nodes
   - redeploy
6. present final results showing:
   - selected workspace name
   - installed model count
   - skipped model count
   - failed model count
   - custom-node sync result
   - deploy result

### Progress Presentation

Swap progress should be displayed in one sidebar progress region with phase labels:

- repairing manifest
- downloading models
- syncing custom nodes
- deploying

### Manifest Repair Modal

The repair modal shows unresolved entries in a table.

Columns:

- model type/folder
- filename
- source status
- editable URL input
- source badge
- per-row action state

Actions:

- **Save**
- **Skip**
- **Save All Valid**
- **Skip All**
- **Cancel**

The repair modal can also be opened manually from the standalone **Manifest Repair** button.

## Manifest Write Rules

From the moment this feature ships, new model installs must update the master manifest.

Applies to:

- `/comfymodal/model/install`
- `/comfymodal/models/batch-install`

Each successful install should write or update the manifest entry with:

- folder/type
- filename
- source URL
- source kind
- token requirement flags when known
- timestamps

If the install request lacks enough source metadata to produce a valid manifest entry, the request should either:

- persist the best-known partial record and surface it in Manifest Repair, or
- reject the install if the design chooses to require a valid URL at install time

For v1, partial records are acceptable as long as they are clearly surfaced by Manifest Repair.

## Workflow Export Format

Workflow manifest export contains:

- `manifest_version`
- `exported_at`
- `workflow_name` or workflow hash
- `models: []`

Each exported model entry contains:

- `folder`
- `filename`
- `url`
- `source_kind`
- `requires_hf_token`
- `requires_civitai_token`
- optional `notes`

Tokens, token secrets, and workspace ids are never included.

## Import Merge Rules

Use `(folder, filename)` as the merge identity.

On import:

- if no local entry exists, add the imported entry
- if a local entry exists with no URL and the imported entry has one, fill the missing URL
- if both entries match, keep the local record and optionally refresh timestamps
- if both exist but URLs differ, open conflict review

Conflict choices:

- keep local
- use imported
- skip

Never overwrite conflicting entries silently.

## Error Handling

### Invalid workspace token

- stop before model sync
- show a workspace authentication error
- do not change the active workspace selection used for live operations until the swap succeeds

### Missing manifest URLs

- pause swap
- open Manifest Repair
- require save or explicit skip for unresolved required entries

### Model download failures

- continue independent downloads when possible
- report installed / skipped / failed separately
- if any manifest-backed model required by the current swap remains unresolved, skipped, or failed to download, stop the swap before custom-node sync and deploy

For v1, a workspace swap is only considered successful when all manifest-backed missing models for that swap were installed successfully.

### Custom-node sync failure

- keep completed model results intact
- do not redeploy
- report sync as the failing phase

### Deploy failure

- keep the selected workspace as active if workspace authentication and swap setup already succeeded
- expose normal deploy status/log through the existing deploy-status flow
- do not roll back manifest state

### Import conflicts

- require explicit user resolution
- do not overwrite silently

## Edge Cases

- block a second workspace swap while a swap or deploy is already running
- if prompt execution is active, warn and require confirmation before switching workspaces
- if workflow export finds models missing from the master manifest, route through Manifest Repair first
- allow the same filename in different folders
- require duplicate consolidation when the same `(folder, filename)` appears multiple times in the manifest
- keep export/import free of tokens and local secrets

## API / Route Changes

The design requires backend support for these route families:

- `/comfymodal/workspaces/*`
  - workspace registry CRUD
  - active selection
  - workspace swap orchestration
- `/comfymodal/manifest/*`
  - manifest read
  - repair scan
  - repair update
- `/comfymodal/workflow-manifest/*`
  - workflow export
  - workflow import

The existing routes for model install, model list, deploy, prompt execution, and custom-node sync should be upgraded so they execute against the selected plugin-managed workspace context.

## Testing Strategy

This feature should be implemented test-first.

Required automated coverage:

- workspace registry persistence and active selection
- workspace-aware execution context selection
- manifest append/update on new model installs
- repair detection for missing URL, missing source kind, duplicate key, and invalid folder
- workspace swap comparison logic:
  - already present remotely
  - missing remotely
  - missing URL blocks swap
- workflow manifest export for models used by a workflow
- workflow manifest import merge and conflict handling
- route/API responses for swap, repair, export, and import
- token leakage prevention in exported files and inappropriate API payloads

Recommended manual verification:

1. save two Modal workspaces in the sidebar
2. switch from workspace A to workspace B
3. confirm missing manifest-backed models install into workspace B
4. confirm custom nodes sync
5. confirm redeploy starts and status/logs are visible
6. run Manifest Repair manually and fix missing links
7. export a workflow manifest
8. import that manifest into another setup
9. confirm conflicts are surfaced instead of silently overwritten

## Open Questions Resolved by Design

- local ComfyUI root remains fixed; only Modal workspace changes
- manifest entries are keyed by `(folder, filename)`
- missing links block swap until repaired or explicitly skipped
- every new installed model must be added to the manifest
- Manifest Repair exists both as a standalone tool and as a swap/export prerequisite

## Implementation Direction

The implementation should minimize global Modal state assumptions.

The main refactor target is the current single-workspace execution model in `modal_client.py` and the route handlers in `__init__.py` that assume one Modal client context for the lifetime of the process.

The preferred end state is:

- a workspace-aware execution abstraction
- plugin-owned workspace and manifest persistence
- sidebar actions that orchestrate repair, model reconciliation, custom-node sync, and deploy in one controlled flow
