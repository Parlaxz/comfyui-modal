# Workspace Editing and Legacy Settings Launcher Design

## Goal

Keep the current Modal GPU sidebar launcher, add a direct "Open Legacy Settings" entry point there, and restore editable existing workspace management inside the legacy settings Workspace section.

## Scope

In scope:

- Keep the current `Modal GPU` launcher card in `web/modal-testing.js`.
- Add an `Open Legacy Settings` button near the existing `Open Studio` button.
- Reuse the existing legacy settings surface rather than creating a new settings implementation.
- Add edit support for existing workspaces in the legacy Workspace section in `web/modal-settings.js`.
- Allow editing an existing workspace's display label, token id, and token secret.
- Reuse the existing workspace upsert backend route by updating an existing `workspace_id`.

Out of scope:

- Replacing the sidebar launcher with the full legacy settings panel.
- Redesigning the Studio Settings page.
- Introducing a separate workspace detail page.
- Changing workspace swap semantics.
- Encrypting or changing token storage format.

## Architecture

### Sidebar launcher

`web/modal-testing.js` remains the owner of the `Modal GPU` sidebar tab and keeps the current compact launcher card. The launcher should gain one additional action:

- `Open Studio`
- `Open Legacy Settings`

The new button should invoke the already-existing settings entry path instead of creating a second settings shell. The preferred path is the existing global opener used by fallback settings launch flows, such as `window.open_comfymodal_settings()`, so the launcher continues to delegate lifecycle ownership to the existing legacy settings code.

### Legacy settings surface

`web/modal-settings.js` remains the single owner of the legacy settings UI and workspace management logic. The Workspace section already owns:

- workspace listing
- add workspace modal
- active workspace selection
- swap workspace flow
- manifest import/export helpers

This change extends that existing section with an edit flow for an already-saved workspace instead of creating a parallel management UI in Studio or the sidebar.

### Backend workspace update flow

`modal_workspaces.py` already supports create-or-update behavior through `upsert_workspace()` when a `workspace_id` is provided. The frontend should treat workspace editing as an update operation against the existing `POST /comfymodal/workspaces` route in `__init__.py`, using the selected workspace's `workspace_id` plus the edited label and token fields.

No new backend route is required. However, the backend update path should preserve the existing token id and token secret when the edit form submits those fields as empty strings, so label-only edits do not force credential re-entry.

## UI Design

### Sidebar launcher behavior

The launcher card in `web/modal-testing.js` should continue to show the current title, subtitle, `Open Studio` button, and status text. Add one more button directly below or beside `Open Studio`:

- `Open Legacy Settings`

Behavior:

- `Open Studio` continues to open the Studio modal unchanged.
- `Open Legacy Settings` opens the existing legacy settings surface directly.
- No additional launcher modes, drawers, or inline settings embeds are introduced.

### Workspace section behavior

The Workspace section in `web/modal-settings.js` should gain an explicit edit action for the currently selected workspace.

Required behavior:

- User selects an existing workspace from the current dropdown.
- User clicks `Edit Workspace`.
- A modal opens with the existing workspace label prefilled.
- User can update:
  - workspace label
  - token id
  - token secret
- Token fields may start empty with clear "leave blank to keep current" guidance because list responses mask saved credentials.
- Saving updates the existing workspace rather than creating a new one.
- After save, the workspace list reloads and preserves or restores the updated workspace as selected.

The edit modal should reuse the existing add-workspace modal patterns and visual style where possible to keep implementation small and consistent.

### Empty and disabled states

- If there are no workspaces, `Edit Workspace` should be hidden or disabled.
- If the selected value is missing or stale after a reload, the section should fall back to the active workspace or first available workspace the same way the existing workspace loader behaves.
- If the update request fails, the UI should show the existing error pattern already used by the settings panel.

## Data Flow

### Open Legacy Settings

1. User opens the `Modal GPU` sidebar tab.
2. User clicks `Open Legacy Settings`.
3. `web/modal-testing.js` calls the existing legacy settings opener.
4. The legacy settings UI mounts using its current lifecycle.

### Edit workspace

1. `loadWorkspaces()` fetches workspace summaries from `GET /comfymodal/workspaces`.
2. The currently selected workspace summary becomes the source for the edit modal defaults.
3. On save, the frontend posts to `POST /comfymodal/workspaces` with:
   - `workspace_id`
   - `label`
   - `token_id`
   - `token_secret`
4. Backend `upsert_workspace()` updates the matching workspace entry, preserves the existing id, and keeps the existing saved tokens when blank token fields are submitted.
5. Frontend reloads workspace summaries and reselects the updated workspace.

## Error Handling

- If `window.open_comfymodal_settings` is unavailable, the launcher should surface a visible error rather than silently failing.
- If workspace update validation fails server-side, surface the returned error text in the same way the add flow does now.
- If workspace reload fails after a successful edit, keep the modal closed but show an error and leave the user on the settings page so they can retry refresh actions.
- Editing the active workspace should not automatically trigger a workspace swap; credential edits only update saved configuration.
- Edit requests should explicitly avoid changing active workspace state.

## Testing

Manual verification should cover:

1. `Modal GPU` sidebar still renders and `Open Studio` still works.
2. `Open Legacy Settings` opens the existing legacy settings UI directly.
3. Existing workspace can be renamed and the new label appears in the workspace dropdown after save.
4. Existing workspace token id and token secret can be updated without creating a duplicate workspace.
5. Editing the active workspace does not change active selection or trigger a swap.
6. Add-workspace flow still works unchanged after introducing edit mode.
7. Error handling surfaces validation failures and unavailable launcher-opener failures clearly.

## Risks and Constraints

- `web/modal-settings.js` is large and owns polling/timers, so the change should be narrowly scoped to avoid destabilizing unrelated settings behavior.
- If both Studio and legacy settings can be opened simultaneously, shared globals may create duplicated polling or stale UI state. This change should reuse existing openers and avoid copying settings logic.
- Workspace summaries intentionally mask token values in list responses. The edit flow should therefore prefill only the label and rely on backend preservation when token fields are left blank.
- Opening multiple legacy settings surfaces at once may duplicate timers or polling, so the launcher change should reuse the existing opener rather than copy the settings panel into a second surface.

## Implementation Notes

- Prefer reusing existing helper functions in `web/modal-settings.js` over inventing new modal infrastructure.
- The edit request should send `set_active: false` or omit active-selection changes entirely so editing does not accidentally flip the active workspace.
- Keep the change additive and local to the existing launcher and legacy workspace section.
