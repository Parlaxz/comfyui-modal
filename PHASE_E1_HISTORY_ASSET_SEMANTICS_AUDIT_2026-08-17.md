# Phase E1 History Asset Semantics Audit

Date: 2026-08-17
Status: Read-only audit complete; production changes intentionally not made.

## Scope and Evidence

This audit covers the current History V2 asset model, SQLite persistence,
production writer, producer/Modal asset adoption, managed-asset URL serving,
Original failure projection, featured output selection, retry behavior, and
frontend cover/image projections.

The requested authoritative post-Phase-D handoff
`COMFY_AI_HUB_STUDIO_POST_PHASE_D_ZERO_CONTEXT_HANDOFF_2026-08-17.md` was not
present in the workspace. The audit therefore uses the current source, nearby
Phase-D reports, preserved artifacts, and read-only database evidence. No
deployment, live generation, production source edit, or commit was performed.

Primary source files:

- `history_v2_models.py`
- `history_v2_store.py`
- `history_v2_repository.py`
- `history_v2_routes.py`
- `history_v2_writer.py`
- `comfymodal_runtime/playground_service.py`
- `__init__.py`
- `web/history-v2-repository.js`
- `web/studio-history-v2.js`
- `web/studio-history-v2-detail.js`
- `web/studio-history-v2-experiment.js`

Preserved read-only evidence:

- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\.studio_history_v2\history_v2.db`
- `.experiment_leases.db`
- `d7r2-original-0.png`
- `d7r2-original-1.png`
- `PHASE_D_FOLLOWUP_2_REPORT_2026-08-16.md`
- `PHASE_D_FOLLOWUP_RECONCILIATION_2026-08-15.md`
- `PHASE_D_INTERFACE_FREEZE.md`

## Executive Summary

1. The persisted model correctly distinguishes `original`, `preview`, and
   `thumbnail`, and it also supports `input`, `mask`, and `secondary`. An
   `Asset` belongs to a Generation and may be associated with a Run Attempt by
   `run_id`; a Generation has one optional `featured_asset_id`. There is no
   first-class logical-output identity separate from the attempt association.

2. Local output files follow the intended managed-asset path: the writer copies
   an Original into the History asset root and attempts to make a local WebP
   Thumbnail. Producer references are different: a local producer path is
   adopted by reference, and a `modal://` producer path is stored verbatim as a
   remote reference. Producer adoption intentionally does not copy, re-encode,
   or thumbnail the source.

3. Remote serving is structurally implemented. The History asset endpoint
   recognizes `modal://`, resolves the workspace, calls
   `modal_client.read_output_asset`, validates the payload type, retries missing
   remote files, and returns the bytes. The API projection is nevertheless
   wrong: `original_failed` checks `Path(original.managed_path).is_file()`, so a
   valid remote Original is reported as failed because `modal://...` is not a
   local filesystem path.

4. Failed Original attempts are retained in `run_attempts`, but the output
   projection only examines asset rows. A successful Preview followed by a
   failed Original therefore does not set `original_failed` when no Original
   asset row exists. The frontend can show `No original` instead of
   `Original generation failed - preview retained`.

5. Output identity is not stable across retries. Cell retries reuse the same
   Generation and append a new Attempt and new assets, while `_build_outputs`
   groups by `run_id`. This can expose retries as separate output groups. The
   same lack of logical-output identity also makes featured-index mapping and
   multi-file output behavior ambiguous.

6. `output_count` is currently the count of visible asset rows, not the count of
   logical output groups. A normal local output with one Original and one
   Thumbnail can report `output_count: 2` while `_build_outputs()` returns one
   output group.

7. The preserved D7R2 database confirms the remote-only shape in actual data:
   both named Generations have a completed Original Attempt and one remote
   Original asset, but no Preview or Thumbnail asset. The current pure route
   projection reports an Original URL and `has_image: true`, but empty
   `thumb_url`/`preview_url` and `original_failed: true`. The History feed card
   and experiment cell therefore have no image source, while Generation detail
   can fall back to the Original URL.

## Current Domain Model

### Asset Types

`history_v2_models.py:38-45` defines:

- `thumbnail`
- `preview`
- `original`
- `input`
- `mask`
- `secondary`

`RunMode` has `preview`, `original`, and `secondary`
(`history_v2_models.py:47-50`). `input` and `mask` are asset types but not run
modes.

The SQLite `assets` table stores `asset_id`, `generation_id`, optional `run_id`,
`type`, `managed_path`, `filename`, dimensions, format, SHA-256, metadata, and
creation time (`history_v2_store.py:115-131`). The schema has no SQL `CHECK`
constraint on `type`; application code validates types through `AssetType` in
`attach_asset`, while direct/migrated database rows could contain arbitrary
values.

`Asset` has no `preferred` flag and no logical-output key
(`history_v2_models.py:305-318`). Preference is represented at Generation level
by `featured_asset_id` (`history_v2_models.py:227-244`).

### Generation, Attempt, and Asset Relationships

- One Generation can have many Run Attempts.
- One Generation can have many Assets.
- An Asset may point to an Attempt through `run_id`, but that association is
  provenance, not a logical output identity.
- A Generation has at most one `featured_asset_id`.
- Assets are retained; attaching a new result does not delete a previous
  Original or Thumbnail.
- `run_attempts` retains `mode`, `status`, `error`, timing, and timestamps
  (`history_v2_store.py:97-113`).

Generation status is derived from attempts. Any queued/running attempt makes
the Generation running; otherwise any completed attempt makes it completed,
even when another attempt failed (`history_v2_models.py:131-151`). This is
appropriate for Preview success plus Original failure, provided the API also
projects the failed Original attempt explicitly.

Cell status instead follows the latest attempt, so a newer retry can supersede
the visible state of an older terminal attempt
(`history_v2_models.py:154-179`). The repository creates retry attempts against
the existing cell Generation (`history_v2_repository.py:774-824` and
`history_v2_repository.py:2047-2082`).

## Current Asset Truth Table

| Case | Persisted asset | Served by History endpoint | Thumbnail behavior | Current failure projection | Assessment |
|---|---|---|---|---|---|
| Local output candidate | `original` copied below `.studio_assets/<generation>` by `attach_asset(copy=True)` | Local bytes are read from the managed path | `_attach_output_assets` attempts a WebP Thumbnail through PIL | `false` while copied Original exists; `true` if the stored local file later disappears | Correct for the normal local path, subject to local liveness |
| Producer asset with existing local path | `original` adopted as a resolved local path by `adopt_asset` | Local bytes are read from the referenced path | Producer adoption does not call `_make_thumbnail_asset` | `false` while the path exists; `true` when absent | Servable, but no derivative Thumbnail is created |
| Producer asset with `modal://` path | `original` with the verbatim remote reference in `managed_path` | `modal://` is parsed and fetched remotely by `read_output_asset` | No Thumbnail is created by producer adoption | Incorrectly `true`, because `Path("modal://...").is_file()` is false | Critical semantic bug |
| Original attempt failed with no Original asset | No Original row; failed Attempt retains `status` and `error` | No Original URL exists | Existing Preview/Thumbnail rows remain if present | Usually `false` on a Preview output group, or no output row at all | Failure is not projected from the Attempt |
| Earlier Original succeeded, later Original failed | Earlier Original remains; later failed Attempt has no asset | Earlier Original remains servable | Existing derivatives remain | Current path check can be false-positive for remote; no attempt-aware failure rule | Must preserve usable Original and report retry outcome separately |
| `input`, `mask`, or `secondary` | Valid asset row if attached through the repository | Asset route can serve a valid local or remote managed path | No automatic output Thumbnail contract | Not included in `original_failed` semantics | Persisted but intentionally excluded from visible output projections |

The relevant implementation is split across:

- Local copy and Thumbnail creation: `history_v2_writer.py:848-931` and
  `history_v2_writer.py:1016-1053`.
- Producer reference classification: `history_v2_writer.py:441-452`.
- Producer adoption: `history_v2_writer.py:933-1014`.
- Reference persistence: `history_v2_repository.py:971-1079`.
- Remote serving: `history_v2_routes.py:1267-1329`.

## Original Failure Semantics

### Current Implementation

Generation feed outputs use this rule:

```text
original_failed = original_asset_exists AND NOT Path(original.managed_path).is_file()
```

This is implemented at `history_v2_routes.py:243-263`. Experiment cell detail
duplicates the same rule at `history_v2_routes.py:781-844`.

The rule has two independent defects:

1. It treats a remote reference as a local path. A valid `modal://` Original is
   therefore marked failed even though the asset endpoint can fetch it.
2. It does not inspect failed Original Attempts. If a Preview asset exists but
   the Original Attempt failed before producing an asset, `original` is `None`
   and `original_failed` is `false`.

The route also emits attempt errors separately in Generation detail
(`history_v2_routes.py:771-777`), but the frontend's Original slot and failure
badge consume `original_failed` (`web/studio-history-v2-detail.js:308-357`).

### Required Canonical Behavior

The API contract should distinguish asset availability from attempt outcome:

| State | `original_url` | `original_failed` |
|---|---|---|
| No Original attempt yet | empty | `false` or an explicit pending state |
| Original queued/running | empty | `false`; status remains in-flight |
| Original completed and local asset exists | URL | `false` |
| Original completed and remote reference is valid by contract | URL | `false` |
| Original failed, Preview retained, no usable Original remains | empty | `true` |
| Earlier usable Original retained, later Original retry failed | earlier URL | `false` for asset availability; retry failure remains visible in attempts/errors |
| Remote fetch later returns 404/502 | URL remains the persisted reference; fetch error is request-time availability, not proof that the attempt originally failed | Do not silently conflate this with the terminal Attempt status |

The precise liveness policy for remote fetch failures should be owned jointly by
History V2 backend and the producer asset contract. It should not be inferred by
calling `Path.is_file()` on a URI.

## URL and Remote Asset Contract

### Write Path

The production writer resolves `primary_asset_id` through the producer
LeaseRegistry (`history_v2_writer.py:393-438`). `_producer_reference` keeps a
`modal://` path verbatim and treats a non-remote path as a local source path
(`history_v2_writer.py:441-452`). `adopt_asset` stores a remote reference in
`managed_path` without reading or fabricating bytes
(`history_v2_repository.py:987-1004`).

The adopted remote Original carries producer identity and metadata such as
`producer_asset_id`, `variant`, `mime_type`, `path`, `byte_size`, and
`content_hash` (`history_v2_writer.py:982-1004`). Cross-generation reuse of a
content-addressed producer ID mints a History-local ID and retains the producer
ID in metadata (`history_v2_repository.py:998-1004`).

### Read Path

All projected History URLs use the stable local endpoint prefix
`/comfymodal/history-v2/assets/{asset_id}` (`history_v2_routes.py:170-171`). The
endpoint:

1. loads the History Asset row;
2. parses `modal://workspace|gpu|backend_path`;
3. resolves the workspace;
4. calls `read_output_asset` with the stored SHA-256, GPU, and workspace;
5. retries `FileNotFoundError` up to three attempts; and
6. returns bytes using the persisted format or path suffix.

This endpoint behavior is compatible with remote Originals. The projection
layer is the incompatible part because it uses local filesystem liveness for
the remote URI.

## Read-Only D7R2 Database Evidence

The database was queried with a read-only SQLite connection for
`experiment_id = exp_v2_01b2ae94b76e`.

### Generation and Attempt Rows

| Generation | Status | Featured asset | Attempt | Mode/status |
|---|---|---|---|---|
| `gen_934b870c790f9222` | `completed` | `ast_ee2c51d6c012` | `run_4ebccb6556f4224d` | `original` / `completed` |
| `gen_ffd5d12d41275be0` | `completed` | `8b7972ca37d7f81ba4f0e32cdccd7879f3eac5a6eba50d48c272715ff823f203` | `run_e94d8cf18fd182d1` | `original` / `completed` |

### Asset Rows

Both Generations have exactly one visible asset, of type `original`, and no
`preview` or `thumbnail` row:

- `ast_ee2c51d6c012` stores
  `modal://ws_f1a4990a74fd||output_assets/5be181cae909abe184fc5c5ec010daf85c2bff11b779cd0260359ad3f75f96b0.png`.
- `8b7972ca37d7f81ba4f0e32cdccd7879f3eac5a6eba50d48c272715ff823f203` stores
  `modal://ws_f1a4990a74fd||output_assets/8b7972ca37d7f81ba4f0e32cdccd7879f3eac5a6eba50d48c272715ff823f203.png`.

The stored SHA-256 values match the producer-side content identity. This
confirms that the current adoption path retained remote references rather than
copying the Original bytes into the local History asset root.

### Current Projection Consequences

For each of these rows, the current pure route projection produces:

- `has_image: true`;
- `original_available: true`;
- an `original_url` pointing to the History asset endpoint;
- empty `thumb_url` and `preview_url`; and
- `original_failed: true` because the URI is not a local file.

Consequently:

- the generation feed card uses an empty Thumbnail URL;
- the experiment cell has no image because it only considers Preview or
  Thumbnail;
- Generation detail can display the Original in its featured image because it
  falls back to `previewUrl || originalUrl`; and
- Generation detail still shows the false Original-failed badge.

## Output Projection and Cover Behavior

### Generation Feed and Detail

`_build_outputs` groups assets by `run_id`, orders groups by earliest asset
timestamp, and selects a group's primary asset in this order:

```text
original -> preview -> thumbnail -> first asset
```

(`history_v2_routes.py:222-263`). It emits `thumb_url`, `preview_url`,
`original_url`, and `original_failed` per group.

The feed Generation item counts visible asset rows rather than output groups:

```text
output_count = len([asset for asset in assets if asset.type in _OUTPUT_TYPES])
```

(`history_v2_routes.py:301-366`). This is inconsistent with the `outputs` list.
For a local output with one Original and one Thumbnail, `output_count` is 2
while `outputs` normally has one group.

Featured selection also has an identity hazard. `featured_asset_id` is matched
against each group's primary `asset_id` to derive `featured_output_index`
(`history_v2_routes.py:331-366`). If a featured asset is a Thumbnail or a
non-primary asset in a group, no match is found and the index silently remains
0. The direct featured endpoint allows an asset ID from the Generation and the
output-index endpoint resolves through `_build_outputs`
(`history_v2_routes.py:1202-1231`).

### Frontend Generation Card

The feed card renders only `record.featuredOutput.thumbUrl`
(`web/studio-history-v2.js:398-431`). It does not fall back to Preview or
Original. A remote-only Original therefore yields a blank card even when the
backend says `has_image: true`.

### Generation Detail

The detail output strip uses `thumbUrl || previewUrl` for each output
(`web/studio-history-v2-detail.js:265-305`). The large featured image uses
`previewUrl || originalUrl` (`web/studio-history-v2-detail.js:335-360`), so a
remote-only Original can appear there. The Preview/Original slots correctly
show a placeholder, an image, or the `original_failed` badge based on the
projected fields, but the false remote failure currently drives the wrong badge.

### Experiment Feed and Detail

Experiment cell detail selects one Thumbnail, one Preview, and one Original
from each Generation and returns separate URLs
(`history_v2_routes.py:781-844`). The experiment cover is built from the first
four cells and uses `_cell_thumb_url`, which only searches for a Thumbnail
(`history_v2_routes.py:370-379` and `history_v2_routes.py:1159-1165`).

The browser cell tile considers a cell image present only when it has a Preview
or Thumbnail and uses that URL for the tile
(`web/studio-history-v2-experiment.js:416-481`). Remote-only Original cells
therefore remain visually empty in the experiment grid even though their
Original endpoint may be valid.

## Retry and Multiple Original Analysis

The repository supports Preview followed by Original, failed Original followed
by retry, and retained assets. Existing tests explicitly cover these sequences
(`tests/test_history_v2_repository.py:56-146`).

For modern experiment cells, the writer creates a stable Generation for the
cell and creates a new Attempt for each cell attempt. Result attachment then
adds assets to that same Generation (`history_v2_writer.py:1055-1258`).
First-terminal-wins protects an individual Attempt status, but it does not
choose or delete assets when a later attempt attaches another result
(`history_v2_writer.py:755-816`).

The current data model has no `logical_output_id`, output ordinal, or explicit
"current Original" relation. `run_id` records which Attempt produced an Asset,
but `_build_outputs` treats each run as a separate output group. Therefore:

- a failed Original followed by a successful retry can expose Preview and
  retry assets as separate groups rather than one logical output;
- two successful Original Attempts can produce multiple groups without a
  canonical winner;
- multiple Originals attached to one Attempt are reduced to the first Original
  selected by the group ordering; and
- featured-index behavior depends on which asset happens to be the group
  primary.

This is not visible in the two D7R2 Generations because each has one Attempt and
one Original, but it is a material Phase E risk for Original replay.

## Acceptance Matrix

| Contract | Current status | Evidence |
|---|---|---|
| Asset types distinguish Original, Preview, Thumbnail | Pass | `history_v2_models.py:38-45` |
| Local Original is persisted in managed History storage | Pass for path candidates | `history_v2_writer.py:848-897` |
| Local Original can produce a local Thumbnail | Pass when PIL and local bytes are available | `history_v2_writer.py:901-909`, `1016-1053` |
| Producer `modal://` reference is persisted without copying bytes | Pass | `history_v2_writer.py:933-1014`, `history_v2_repository.py:987-1004` |
| History asset endpoint can serve remote references | Structurally pass | `history_v2_routes.py:1267-1329` |
| Valid remote Original is not reported as failed | Fail | `history_v2_routes.py:257-259`, `836-838` |
| Failed Original Attempt is reflected in output projection | Fail/incomplete | `_build_outputs` uses assets only, `history_v2_routes.py:222-263` |
| `output_count` equals logical output count | Fail | `history_v2_routes.py:301-366` |
| Featured asset maps deterministically to an output | Conditional/high risk | `history_v2_routes.py:331-366` |
| Retry assets retain provenance | Pass | `assets.run_id`, repository and writer retry flows |
| Retry assets collapse to a stable logical output | Fail/not modeled | no logical output identity; grouping by `run_id` |
| Feed cards show a remote-only Original | Fail/incomplete | `web/studio-history-v2.js:398-431` |
| Generation detail can show a remote-only Original | Partial pass | `web/studio-history-v2-detail.js:335-360` |
| Experiment cells/covers show a remote-only Original | Fail/incomplete | thumbnail-only cell/cover selection |

## Relevant Existing Tests and Gaps

### Existing Coverage

- `tests/test_history_v2_repository.py:56-146` covers Preview/Original attempt
  order, failed Original after Preview, retry success, retained assets, and
  featured asset changes.
- `tests/test_history_v2_api.py:229-356` covers local feed/detail URL
  projection; `:412-461` covers featured changes; `:521-719` covers managed
  asset serving and producer descriptor adoption.
- `tests/test_history_v2_production_writer.py:632-931` covers producer
  adoption, deduplication, local path behavior, featured association, and the
  intentional no-Thumbnail producer-adoption behavior.
- `tests/test_modal_asset_integration.py` covers producer asset registration and
  metadata/variant relationships.
- `tests/browser/studio-history-v2.spec.mjs` and the fake browser fixtures cover
  feed/detail behavior, including missing Original UI states.
- `tests/test_studio_history_v2_js.py` provides structural JavaScript coverage.

### Missing Regression Coverage

The following tests should be added before treating the E1 contract as closed:

1. A History route test with a valid `modal://` Original must assert a remote
   asset URL, successful remote response, and `original_failed: false`.
2. A Preview-success/Original-failure record with no Original asset must assert
   `original_failed: true` and preserve the Preview URL.
3. A successful Original followed by a failed retry must retain the usable
   Original and keep the retry error visible without marking the retained asset
   failed.
4. A local Original plus Thumbnail must assert one logical output and a single
   `output_count`, not two asset rows.
5. Two Original Attempts in one cell Generation must assert the intended
   logical-output grouping and winner selection.
6. Setting a non-primary asset as featured must either resolve to its logical
   output or be rejected; it must not silently map to output index 0.
7. Feed cards, experiment cells, and experiment covers must have an explicit
   expected behavior for remote-only Original assets with no Thumbnail.

## Cross-Lane Contract Review

The adjacent Phase E lanes have direct dependencies on this contract:

- E2 Preview/Thumbnail pipeline work can add more asset rows and therefore
  expose the `output_count` versus logical-group mismatch. It also needs to
  decide whether remote producer assets receive a derivative Thumbnail or a
  Preview fallback.
- E3 Original replay work can create multiple Original Attempts against one
  Generation. It must not assume `run_id` alone is a logical-output identity or
  that the current `original_failed` projection is correct.
- E4 frontend work consumes `thumb_url`, `preview_url`, `original_url`,
  `original_failed`, and `featured_output_index`. It should not codify current
  false remote failure values or thumbnail-only cover behavior without an
  explicit contract decision.

Recommended ownership:

- History V2 backend owns the canonical output projection, failure semantics,
  logical grouping, and `output_count`.
- Production writer and producer asset contract owners own remote descriptor
  validity, content identity, and derivative availability.
- Frontend owners own fallback rendering and explicit treatment of remote-only
  assets, but should consume stable backend semantics rather than infer them.
- Retry/replay ownership is shared by repository, writer, and E3 because the
  required logical-output identity spans all three.

## Recommended Changes for the Next Lane

No implementation is included in this audit. The smallest coherent follow-up
should:

1. Replace filesystem-only `original_failed` derivation with attempt-aware
   projection plus URI-aware asset availability. A `modal://` reference must
   not be classified as a missing local file.
2. Define one logical output identity per output slot and retain Attempt/Asset
   provenance underneath it. Use that identity for grouping, `output_count`,
   featured selection, and retry replacement.
3. Define a deterministic Original winner: a usable earlier Original must not
   be hidden by a later failed retry; a later successful retry must have an
   explicit replacement rule.
4. Decide whether remote-only assets get producer-side Thumbnail/Preview
   descriptors or whether the History service creates/caches derivatives. The
   current UI cannot reliably render a remote-only Original in feed and
   experiment surfaces without one of those policies or a frontend fallback.
5. Add the seven regression cases above before E1 sign-off.

## Final Finding

The current implementation has a sound storage and remote-serving foundation,
but the public History V2 asset semantics are not yet internally consistent for
remote Originals, failed Original attempts, retries, or derivative-free cover
surfaces. The two preserved D7R2 Generations demonstrate the issue with real
persisted data: valid remote Originals are retained and addressable, while the
projection falsely reports failure and leaves feed/experiment image slots
empty.

## Implementation Follow-Up A - History Original/Preview Projection Truth

Date: 2026-08-17
Status: Implemented and focused-tested; logical-output persistence remains E1B.

### Files Changed

- `history_v2_routes.py`
- `tests/test_phase_e_history_projection.py`
- This audit document (append-only follow-up)

`history_v2_models.py`, the History store/repository/writer, and all runtime,
frontend, settings, playground, experiment-planning, and deployment files were
left unchanged.

### Semantics Implemented

- Added one shared route projection helper for Original asset availability and
  failure state. A persisted `modal://` reference is structurally available
  without a network fetch; ordinary local managed paths still use
  `Path.is_file()`.
- Original assets with attempt provenance are usable only when their producing
  attempt is completed. The persisted asset type remains authoritative for
  existing completed records whose legacy attempt mode does not match the
  asset type.
- Among usable Originals in a projected output group, the newest asset wins by
  `(created_at, asset_id)`. Missing local Originals are not given an
  `original_url` and are reported as failed.
- A failed latest Original Attempt with no retained usable Original sets
  `original_failed: true`; Preview output and its URL remain projected. A
  queued/running latest Original Attempt does not set `original_failed`.
- A retained usable Original wins over a later failed Original retry, keeps its
  `original_url`, and leaves `original_failed: false`. Attempt errors remain
  available through the existing attempt/error projections.
- Generation output/detail and Experiment cell/detail projections now use the
  same helper. No remote fetch is performed while constructing feed/detail
  responses; remote fetch failures remain asset-request-time failures.

### Tests Added and Results

`tests/test_phase_e_history_projection.py` covers:

- usable local Original;
- structurally usable `modal://` Original;
- Preview retained after failed Original with no Original asset;
- retained Original after failed retry;
- newest successful Original winner;
- queued/running Original state;
- missing local Original path;
- shared Experiment cell projection semantics; and
- an explicit skipped E1B logical-output test description.

Focused deterministic validation passed:

- `python -m pytest tests/test_phase_e_history_projection.py -q` -> 9 passed,
  1 skipped;
- `python -m pytest tests/test_history_v2_api.py -q` -> 20 passed;
- `python -m pytest tests/test_history_v2_repository.py -q` -> 22 passed;
- `python -m pytest tests/test_history_v2_modern_experiment.py -q` -> 45 passed.

### E1B Required Logical Output Identity

`E1B_REQUIRED_LOGICAL_OUTPUT_IDENTITY`

The existing persisted data does not contain a stable logical-output or
output-slot identity that survives retries. `Asset.run_id` is attempt
provenance, not a canonical logical-output key. Therefore this follow-up does
not change `output_count` or featured-output mapping: `output_count` remains
the existing visible-asset-row count, and featured selection remains the
existing primary-asset match. The skipped regression explicitly avoids
asserting that an Original plus Thumbnail or retry assets form one logical
output.

E1B must own the missing identity and its persistence/projection contract in:

- `history_v2_models.py`;
- `history_v2_store.py`;
- `history_v2_repository.py`;
- `history_v2_writer.py`; and
- `history_v2_routes.py`, with focused route regression coverage.

E1B must define the stable output-slot relation, retry replacement/winner
rules, `output_count`, and featured asset/index behavior before changing those
fields. E1A intentionally does not use `run_id` as a new canonical identity.

### Cross-Lane Notes

- E2 derivative/thumbnail work may add rows that continue to expose the
  unresolved logical-output count unless it adopts the E1B identity contract.
- E3 Original replay/retry work must preserve attempt history and must not
  infer logical output identity from `run_id` alone.
- E4 frontend consumers can rely on corrected `original_failed` and
  `original_url` semantics, but remote-only feed/experiment image fallback and
  derivative presentation remain outside this backend-only follow-up.
- No deployment, live Modal generation, GPU spend, commit, or push was
  performed.

## E1 Implementation Follow-Up B - Logical Output Identity

Date: 2026-08-17
Status: Implemented and focused-tested; Generate Original remains out of scope.

### Files Changed

- `history_v2_models.py`
- `history_v2_store.py`
- `history_v2_repository.py`
- `history_v2_writer.py`
- `history_v2_routes.py`
- `tests/test_phase_e_logical_outputs.py`
- This audit document (append-only follow-up)

No E2/E3/E4-owned runtime, application, experiment-planning, frontend, or
deployment file was modified.

### Schema and Model

`Asset` now has a nullable first-class `logical_output_key`. The assets table
stores the same nullable field and has a generation/key/created index. Existing
rows remain null and are not rewritten or assigned guessed identities.

`HistoryV2Store.SCHEMA_VERSION` is now `2`. Initialization adds the column with
an idempotent additive `ALTER TABLE` and creates the index with
`IF NOT EXISTS`; fresh databases and pre-existing databases take the same safe
path. Legacy rows remain readable with `logical_output_key = NULL`.

### Canonical Key Contract

The shared field name is `logical_output_key`. The canonical derived format is:

`node:<node_id>:slot:<output_key>:item:<output_index>`

The stable source fields are the current output descriptor fields `node_id`,
`output_key`, and `output_index`. `output_index` is the item index within that
node/output stream. The key does not use Attempt identity, asset type, mode,
codec, filename, content hash, or timestamps. An explicit
`logical_output_key` is preferred; derivation occurs only when the stable node,
slot, and non-negative item index are all present.

### Writer and Adoption

The History writer consumes an explicit key from single-run, cell, local-output,
and producer metadata. It derives the key from the current descriptor fields
when safe. Multiple local output paths require per-item `logical_output_keys`
or `asset_descriptors`/`output_descriptors`; a single shared key is not applied
to an ambiguous multi-file list. Producer adoption consumes an explicit
producer key or derives one from the producer descriptor and persists it on the
adopted Original. Generated Thumbnail assets inherit the Original key.

Retry writes with a new Attempt and the same logical key are no longer rejected
merely because the filename matches an earlier Attempt. Same-Attempt replay
remains idempotent through the existing `(run_id, filename)` guard.

### Grouping and Winners

Keyed visible assets group by `logical_output_key`, independently of
`run_id`. Visible legacy assets without a key use a shared non-null `run_id`
only; no-run legacy assets remain isolated by asset id. A legacy metadata row
with the complete stable descriptor fields can be read using the same safe
derived key, but unrelated historical rows are never merged by filename,
hash, timestamp, or asset type. Keyed and unkeyed groups are never implicitly
merged.

Within a logical output, Thumbnail selection is the newest structurally usable
completed-attempt asset, Preview selection is the newest completed Preview
Attempt asset while preserving E1A's retained Preview URL semantics, and
Original selection remains E1A's newest usable successful Original. A later
failed Original retry cannot remove an earlier usable Original. Remote
`modal://` Originals remain structurally available without projection-time
network fetches.

### Output Count and Featured Mapping

`output_count` now counts projected logical output groups rather than raw
Thumbnail/Preview/Original rows. Thus a keyed Thumbnail, Preview, and Original
count as one, while different item indexes or output nodes count separately.
Legacy no-run rows remain separate because their relation cannot be proven;
mixed keyed/unkeyed rows are counted as their independently proven groups.

Featured selection now resolves membership across every asset in a logical
group. A featured Thumbnail, Preview, or older Original therefore maps to its
logical group's `featured_output_index`, even when a newer Original is the
current winner. Output-index selection still stores the selected group's
current primary asset without deleting or rewriting other assets.

### Experiment Behavior

Experiment cell Generations use the same route grouping, winner, count, and
featured helpers as Single Generations. Cell retries keep their Attempt
history and append assets under the same explicit key when the producer
metadata identifies the same workflow output item. No Experiment-specific
logical grouping was introduced.

### Tests and Results

`tests/test_phase_e_logical_outputs.py` adds 17 deterministic tests covering
variant grouping, Preview/Original Attempts, failed and successful retries,
item indexes, output nodes, output count, all requested featured variants,
remote keyed Originals, Experiment reuse, legacy/mixed data, persistence,
writer derivation/adoption, and idempotent migration.

Final focused validation:

- `python -m pytest tests/test_phase_e_history_projection.py tests/test_phase_e_logical_outputs.py -q` -> 26 passed, 1 skipped;
- `python -m pytest tests/test_history_v2_api.py tests/test_history_v2_repository.py tests/test_history_v2_production_writer.py tests/test_history_v2_modern_experiment.py -q` -> 120 passed;
- AST parsing passed for all five changed production modules and the new E1B test file.

The one skipped case is the prior explicit E1B pending test description; its
logical-output assertion is now covered by the new E1B suite.

### Exact E2B Shared Contract

E2B should emit `logical_output_key` on every modern producer/result asset
descriptor whenever the output item is known. The preferred exact value is
`node:<node_id>:slot:<output_key>:item:<output_index>`, using the current
descriptor fields `node_id`, `output_key`, and `output_index`. For a multi-item
result, each item must carry its own index and therefore its own key; E2B must
not reuse one key for an entire batch. For local path lists, E2B should provide
aligned `logical_output_keys` or per-item `asset_descriptors` containing the
same fields. Missing keys remain a supported legacy condition, but E2B should
not substitute filename, content hash, Attempt id, or creation time.

### Remaining Risks

- Older unkeyed assets cannot be retroactively collapsed when their logical
  relation is not persisted or derivable from complete stable descriptor
  metadata.
- Until E2B emits the explicit field on all modern producer descriptors, the
  writer's safe derivation path is the compatibility bridge and ambiguous
  multi-file metadata remains unkeyed.
- Remote-only derivative/cover presentation remains a frontend concern owned by
  E4; this batch only guarantees keyed remote Original grouping and projection.
- Generate Original execution and replay-core preparation were not modified.
- No deployment, live Modal generation, GPU spend, commit, or push was
  performed.
