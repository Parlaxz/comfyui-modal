# Studio History Grid and Carousel Design

## Goal

Turn Studio History into an image-first browsing surface and turn the Playground strip into a true image carousel, while keeping the current Studio shell and existing run-history backend contract.

## Scope

In scope:

- Replace the row-based History rendering in `web/studio-history.js` with an image-card grid.
- Replace the text-only Playground filmstrip in `web/studio-playground.js` with an image carousel.
- Reuse the existing `/comfymodal/run-history?limit=50` fetch path for both surfaces.
- Keep status, feature, preset, and timestamp visible in both views.
- Add a large preview/lightbox from History cards.
- Keep non-image runs visible in History through fallback cards.

Out of scope:

- Changing the Studio shell navigation in `web/studio-shell.js`.
- Adding new backend endpoints unless a tiny URL-normalization adapter is required in frontend code.
- Reworking experiment execution, run storage, or run-history persistence.
- Syncing History selection back into Playground.
- Building a full asset-management view.

## Current Context

- `web/studio-history.js` currently renders grouped and ungrouped runs as compact text rows inside cards.
- `web/studio-playground.js` currently renders the strip as a vertical list of clickable text items that only navigate to the History page.
- `web/studio-playground.js` already knows how to derive a displayable output URL from `primary_asset_id` and `output_paths` during run completion polling.
- `web/studio-styles.js` owns the Studio-specific visual system and should remain the styling owner for both redesigns.

## Architecture

### Shared run-to-image normalization

Introduce a small shared normalization layer in the Studio frontend so History and Playground do not each guess differently about image availability.

The normalization helper should produce, for each run:

- stable run id
- status
- feature id
- preset label/id
- timestamp
- duration if present
- prompt/description snippet
- preview image URL if one can be derived
- `hasImage` boolean

Preferred image resolution order:

1. `extra.primary_asset_id`
2. `run.asset_id`
3. first available output path from `run.outputs` or similar output arrays

The helper should tolerate partial or missing metadata and return a valid card model even when no image exists.

### History page ownership

`web/studio-history.js` remains the owner of the History page. It should keep fetching run history directly, but render image-first grouped sections instead of row lists.

Experiment grouping remains useful and should stay, but each group becomes a gallery section:

- group header with experiment/studio label and summary counts
- responsive image grid beneath
- fallback single grid for ungrouped runs

### Playground carousel ownership

`web/studio-playground.js` remains the owner of the canvas and carousel. The carousel should be fed from the same normalized run data, filtered down to image-producing runs only.

Carousel selection stays local to Playground state. Clicking a carousel item updates the main canvas preview rather than forcing a page change.

## UI Design

### History grid

The History page should shift from text rows to visual cards.

Each card should contain:

- image thumbnail when available
- fallback empty tile when no image is available
- status badge
- feature badge such as `txt2img`
- preset label when available
- timestamp

Card behavior:

- entire card is clickable
- click opens a large preview overlay/lightbox
- preview prioritizes the image, with metadata shown alongside or below it

Grouping behavior:

- keep grouped experiment sections when `experiment_id` is present
- keep current success/failure summary information in each section header
- ungrouped runs render in the same card style without a group wrapper

### History preview overlay

The preview overlay should be intentionally lightweight:

- large centered image preview
- metadata block with status, feature, preset, timestamp, prompt snippet, and duration when present
- close button and click-away/escape dismissal

The overlay is for inspection, not editing. No new secondary workflow is required in this pass.

### Playground carousel

The strip under the main canvas should become a horizontal carousel of image thumbnails.

Each carousel tile should show:

- thumbnail
- active-state highlight
- status indicator
- short preset/feature label

Interaction:

- click thumbnail to load that image into the main canvas
- left/right arrow controls
- horizontal scrolling via wheel/trackpad
- optional drag-scroll only if it stays simple and does not fight native scrolling

Behavior:

- newest image-first ordering
- only runs with usable image URLs are included
- latest completed image auto-selects when appropriate
- failed runs with no image are excluded from the carousel but remain visible in History

## Data Flow

### History

1. History page requests `/comfymodal/run-history?limit=50`.
2. Response is normalized into run card models.
3. Runs are grouped by `experiment_id` when present.
4. Group sections render responsive image cards.
5. Clicking a card opens the preview overlay using the normalized model.

### Playground carousel

1. Playground requests `/comfymodal/run-history?limit=50` for recent runs.
2. Response is normalized through the same helper used by History.
3. Runs are filtered to `hasImage === true`.
4. Carousel renders thumbnails in newest-first order.
5. Clicking a tile updates the active Playground preview image.

## Error Handling and Empty States

- If history fetch fails, keep the existing retryable error pattern.
- If there are no runs at all, History should show a truthful empty state.
- If runs exist but none have images, History still renders fallback cards while the carousel shows its own empty state.
- If an image URL cannot be derived for a specific run, render a stable non-broken placeholder tile rather than a broken image element.
- Missing feature/preset metadata should fall back to concise generic labels instead of leaving empty UI gaps.

## Responsive Behavior

- History grid should collapse gracefully from multi-column desktop layout to fewer columns on narrower modal widths.
- Thumbnail aspect ratios should stay consistent enough to avoid jumpy card heights.
- Carousel tiles should preserve a readable thumbnail size without forcing the canvas off-screen.
- Overlay preview should fit within the existing Studio modal bounds and avoid nested scroll traps.

## Testing

Manual verification should cover:

1. History loads and renders image cards instead of text rows.
2. Grouped experiment headers still show accurate counts and statuses.
3. Image-producing runs show thumbnails in both History and the Playground carousel.
4. Non-image runs still appear in History with fallback cards.
5. Clicking a History card opens and closes the preview overlay correctly.
6. Clicking a carousel thumbnail updates the main canvas image.
7. Carousel arrow navigation and horizontal scrolling work with multiple images.
8. Empty and error states remain clear and truthful.

## Risks and Constraints

- `web/studio-playground.js` and `web/studio-history.js` currently duplicate some run interpretation logic; this change should reduce duplication rather than add more.
- Run-history payload shape may vary between stored runs, so normalization must be defensive.
- Broken or missing asset URLs are likely in historical data; placeholder rendering is required to avoid a degraded UI.
- `web/studio-styles.js` is already large, so new selectors should stay scoped and additive.

## Implementation Notes

- Prefer a small shared helper module or tightly scoped shared functions over copy-pasting URL derivation logic.
- Keep the existing History fetch limit unless there is a demonstrated UX reason to change it.
- Preserve the current dark Studio visual language from `web/studio-styles.js` rather than introducing a different component style.
- Do not change backend contracts unless frontend-only normalization proves insufficient.
