# Custom-Node Redeploy Design

Date: 2026-06-06

## Goal

When custom nodes change, automatically rebuild the Modal image in the background so custom-node requirements are installed in the image layer instead of being relied on at cold start.

The user experience should stay simple:

- sync custom nodes
- if the relevant node set changed, start background `modal deploy`
- if it did not change, skip deploy

## Success Criteria

- syncing custom nodes still uploads the current local custom-node set to the Modal volume
- a background deploy starts automatically when the custom-node fingerprint changes
- no background deploy starts when the fingerprint is unchanged
- the fingerprint is updated only after a successful deploy
- deploy status remains visible through the existing deploy-status flow
- the design avoids false retriggers from irrelevant filesystem changes

## Non-Goals

This design does **not** include:

- hashing every file in every custom node
- changing the current custom-node sync transport format
- removing the custom-node volume entirely
- reworking the general deploy UX
- git commits unless explicitly requested by the user

## User-Approved Decisions

- deploy should start in the background, not block the sync request
- the custom-node fingerprint should be intentionally simple
- the fingerprint should be based on:
  - sorted top-level custom-node folder names
  - each node's `requirements.txt` contents, when present

This means the deploy trigger is aimed at dependency-affecting custom-node changes, not every source edit inside a node.

## Current Context

Current relevant behavior:

- local sync route packages `custom_nodes` and uploads it in `__init__.py:1311-1367`
- sync currently calls `sync_custom_nodes(...)` and then `resync_runtime("custom_nodes")`
- background deploy support already exists in `_run_deploy_background()` at `__init__.py:211-276`
- automatic deploy-on-startup currently only compares `COMFYAPP_VERSION` in `_maybe_auto_deploy()` at `__init__.py:278-289`
- the Modal image already bakes local custom nodes and runs build-time `pip install -r requirements.txt` in `comfyapp.py:874-885`

The missing piece is a second freshness signal for custom-node dependency state.

## Approaches Considered

### 1. Always deploy after sync

Every successful sync starts a background deploy.

Pros:

- simplest implementation
- guarantees rebuild after any sync

Cons:

- rebuilds even when nothing relevant changed
- wastes time and Modal build resources

### 2. Fingerprint on folder names only

Use only sorted top-level custom-node folder names.

Pros:

- very simple

Cons:

- misses dependency changes inside an existing node
- `requirements.txt` edits would not trigger rebuild

### 3. Fingerprint on folder names + `requirements.txt` contents **(recommended)**

Use sorted top-level folder names plus each node's `requirements.txt` contents when present.

Pros:

- still simple
- catches new/removed nodes
- catches dependency changes that matter for image-layer installs
- avoids false retriggers from unrelated source edits inside nodes

Cons:

- does not rebuild for non-requirements code edits inside an existing node

## Recommended Design

Treat deploy freshness as the combination of:

- `COMFYAPP_VERSION`
- `custom_nodes_fingerprint`

If either changes, the deployed image is stale.

### Fingerprint Definition

The fingerprint input is:

1. the sorted list of included top-level custom-node directory names
2. for each included top-level directory, the full text of `requirements.txt` if that file exists

Excluded directories should match the existing sync exclusions where relevant, such as hidden/cache/vendor folders that are not treated as first-class custom nodes.

Fingerprint construction should be deterministic:

- sort node directory names
- normalize the manifest shape before hashing
- use UTF-8 text reads for `requirements.txt`
- treat missing `requirements.txt` as an empty value rather than an error

The implementation does not need archive hashing or per-file content hashing.

### Stored Deploy State

Replace the current single-version deploy state with one JSON file that stores both:

- deployed `comfyapp_version`
- deployed `custom_nodes_fingerprint`

Recommended path:

- continue using the existing local node directory next to `.deploy_log`

Recommended shape:

```json
{
  "comfyapp_version": "2.14.2",
  "custom_nodes_fingerprint": "..."
}
```

Using one JSON file keeps the two freshness values in sync and avoids partial updates across multiple files.

Backward compatibility requirement:

- if only the legacy `.deployed_version` file exists, treat its value as the deployed version and assume the custom-node fingerprint is unknown/stale
- once a deploy succeeds under the new system, write the JSON state file

### Sync Flow

For `/comfymodal/sync/custom-nodes`:

1. scan the local `custom_nodes` directory
2. compute the custom-node fingerprint from folder names + `requirements.txt` contents
3. build the existing tar.gz archive
4. upload the archive to the Modal volume with the existing sync function
5. if upload succeeds:
   - compare the new fingerprint against the last successfully deployed fingerprint
   - if changed, start `_run_deploy_background()` in a thread
   - if unchanged, skip deploy
6. return a response that includes both sync status and deploy decision

`resync_runtime("custom_nodes")` should remain optional best-effort behavior for immediate runtime visibility, but it is no longer the mechanism relied on for dependency freshness.

### Deploy Decision Rules

Start background deploy when any of these are true:

- no new JSON deploy-state file exists yet
- `COMFYAPP_VERSION` differs from deployed version
- `custom_nodes_fingerprint` differs from deployed fingerprint

Skip background deploy only when both version and fingerprint already match.

### Deploy Success and Failure Handling

On deploy success:

- write the new JSON deploy-state file with both current values
- clear cached Modal handles using the existing `clear_cache()` path
- expose normal success status through the existing deploy-status route

On deploy failure:

- leave the old deploy-state values untouched
- preserve the failure in `.deploy_log` and deploy status
- report sync success separately from deploy failure or deploy-not-started state

This prevents a failed deploy from being incorrectly treated as current.

## API / UX Changes

The sync route response should include a small deploy summary, for example:

```json
{
  "status": "ok",
  "nodes": ["comfyui-easy-use", "rgthree-comfy"],
  "deploy": {
    "started": true,
    "reason": "custom_nodes_changed"
  }
}
```

Suggested reasons:

- `custom_nodes_changed`
- `version_changed`
- `already_current`
- `deploy_already_running`

This keeps the frontend messaging simple without changing the existing deploy-status endpoint structure.

## Error Handling

- if fingerprint calculation fails, fail the sync request before upload
- if upload fails, do not start deploy
- if upload succeeds but background deploy start fails, return sync success with deploy error detail
- if a deploy is already running, do not start a second concurrent deploy; return a clear status instead

## Testing

Add or update tests for:

- fingerprint changes when a top-level node folder is added or removed
- fingerprint changes when a node's `requirements.txt` changes
- fingerprint stays the same when unrelated files inside a node change but `requirements.txt` does not
- sync starts background deploy when fingerprint changes
- sync skips deploy when fingerprint is unchanged
- deploy success writes combined deploy state
- deploy failure leaves prior deploy state unchanged
- legacy `.deployed_version` state is treated as stale until first successful new-style deploy
- second deploy is not started while one is already running

## Implementation Notes

- keep the fingerprint helper local to the custom-node sync/deploy layer unless reuse emerges naturally
- follow the current lightweight local-state approach in `__init__.py`
- do not introduce runtime dependence on the Modal volume contents for deploy freshness decisions; use local source-of-truth inputs instead

## Rollout Notes

After this design lands, the cold-start path can be simplified in a later change by reducing or removing runtime custom-node requirements installation, because image rebuild becomes the primary dependency-refresh mechanism.

That follow-up is intentionally separate from this design.
