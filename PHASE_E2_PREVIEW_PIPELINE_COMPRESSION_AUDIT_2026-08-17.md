# Phase E2 Preview Pipeline Compression Audit

Date: 2026-08-17
Phase: E2 read-only architecture audit
Scope: Preview compression seam, output transport, History V2 association, and terminal ordering

## Executive Verdict

The lowest-latency Preview seam is the existing remote direct-output sink:

```text
clamped IMAGE tensor
-> ComfyModalProductionOutput.encode
-> encode_image_tensor_batch
-> WebP bytes in the production registry
-> descriptor persistence
-> History Preview asset
```

This avoids a PNG write/read/re-encode round trip. The existing runtime already
skips post-hoc conversion when the selected strategy is
`direct_output_sink` (`comfymodal_runtime/modal_app.py:14474-14537`).

The seam is not yet a complete Phase E Preview pipeline. Preview intent is not
propagated as an immutable attempt mode, ordinary output attachments are
hardcoded to `original`, and direct-sink codec timing is not recorded as
format-specific conversion timing. These are correctness and observability
gaps, not reasons to move compression to local materialization.

No deployment, live Modal generation, GPU-credit expenditure, or source-code
change was performed for this audit. Compression latency is UNKNOWN until a
deterministic benchmark and the later minimal live gate provide evidence.

## Contract To Preserve

From the authoritative post-Phase-D handoff:

- Preview default: OFF.
- Preview codec: WebP.
- Preview quality: 70.
- Preview should compress immediately after workflow output.
- Preview-only work should avoid permanently retaining a full transient Original.
- Preferred compression time: `<100 ms`; practical upper target: about `135 ms`.
- Generate Original is a full rerun from the exact immutable request.
- Preview and Original are separate Attempts under the same Generation.
- Required output/asset association must complete before a successful terminal.

The quality target must not silently change the existing Original/default output
behavior, which currently uses `original` and quality 75.

## Current Pipeline Map

### 1. Remote direct-output sink: recommended Preview seam

`comfyapp.py:602-755` implements `encode_image_tensor_batch`. It converts the
already clamped `[B,H,W,C]` uint8 tensor directly to PNG, WebP lossless, WebP
lossy, or JPEG bytes.

`comfyapp.py:817-931` runs the authorized
`ComfyModalProductionOutput` node. It obtains output settings, calls the tensor
encoder, and stores encoded bytes in the in-memory production registry without
writing a file or placing raw bytes into execution history.

`comfyapp.py:16985-17006` registers the active production request, including
`output_format`, `quality`, and `webp_lossless_compression`.

`comfymodal_runtime/modal_app.py:13333-13383` reconstructs the production
request from the frozen `ExecutionPlan` and exposes the same settings to the
remote sink.

This is the preferred E2 location because it has one tensor-to-codec pass and
does not require a PNG intermediate.

### 2. Remote post-hoc conversion: fallback only

`comfymodal_runtime/modal_app.py:14474-14537` invokes
`convert_output_items` only when the selected strategy is not
`direct_output_sink` and a non-original format was requested.

`comfymodal_runtime/result_delivery.py:323-421` converts already-collected
`OutputItem` bytes and records batch conversion totals. This is useful for
non-production/history/filesystem fallback paths, but it is slower and can
become a PNG read/re-encode path.

`comfyapp.py:17363-17739` contains another legacy filesystem collection and
parallel conversion path. It reads files first and converts afterward. It must
not become the modern Preview primary path.

### 3. Persistence and descriptor path

`comfymodal_runtime/modal_app.py:15121-15212` writes selected bytes to
content-addressed `output_assets/<sha>.<ext>` files and starts an asynchronous
volume commit. Descriptor construction follows the write and the deferred
commit is finalized later (`modal_app.py:15214-15249`).

`comfymodal_runtime/output_delivery.py:243-292` builds metadata-only
descriptors. `attempt_to_descriptor_result` defaults to no inline base64
(`output_delivery.py:295-407`).

`comfymodal_runtime/result_delivery.py:467-788` materializes legacy inline
base64 payloads locally, but descriptor-mode entries do not decode or rewrite
bytes. Local materialization is therefore not the right compression seam.

### 4. Modern Single and Experiment lifecycle

Modern Single execution materializes before its normal history callback in
`comfymodal_runtime/playground_service.py:760-795,891-918`.

The modern Workflow V2 path uses a capture-only callback, strict JSON checks,
output preflight, a nonterminal `running` History write, output association,
then terminal `completed` in `studio_workflow_run.py:603-689,809-939,1240-1282`.

Modern Experiment cells follow the same result-before-terminal rule:
`experiment_modern_scheduler.py:1477-1496` calls result persistence before
recording `completed`; `history_v2_repository.py:1932-2035` verifies the
current attempt and required asset association.

This ordering is Phase-D correctness evidence and must remain unchanged.

## Findings

### E2-1: Preview is not semantically persisted through production paths

The data model already supports Preview:

- `history_v2_models.py:38-50` defines `AssetType.PREVIEW` and `RunMode.PREVIEW`.
- `history_v2_repository.py:524-567` accepts an explicit attempt mode.
- `history_v2_repository.py:885-969` accepts an explicit asset type.

The production paths do not carry those values:

- `history_v2_writer.py:572-575` and `627-630` create single-run attempts as
  `mode="original"`.
- `history_v2_writer.py:1147-1151` creates Experiment cell attempts as
  `mode="original"`.
- `history_v2_repository.py:1512-1540` defaults modern matrix attempts to
  `RunMode.ORIGINAL` unless a cell spec supplies `mode`.
- `history_v2_writer.py:887-896` attaches ordinary output files as
  `asset_type="original"`.
- `history_v2_writer.py:993-1004` and `history_v2_repository.py:1006-1010`
  adopt producer assets as `original`.
- `history_v2_writer.py:1233-1245` classifies only thumbnail filename suffixes;
  other cell outputs become originals.
- `comfymodal_runtime/playground_service.py:575-576` registers descriptors
  with `variant="original"`.

Conclusion: changing the codec to WebP alone would create a WebP Original, not
a History Preview. E2 needs an explicit immutable `attempt_mode`/asset-type
projection from accepted request to result persistence.

### E2-2: Direct-sink compression timing is incomplete and mislabeled

The direct sink does not emit conversion metadata in its registry entries:
`comfyapp.py:905-918` records filename, bytes, MIME, extension, dimensions,
index, node, and format, but not conversion duration, quality, or input/output
size.

Consequences:

- `output_delivery.py:521-527` defaults direct-sink conversion timing to zero.
- `Attempt.total_conversion_time_ms` is therefore zero for the direct sink.
- `modal_app.py:14475` skips `output_conversion_start/end` for direct-sink
  output.
- `comfyapp.py:739-747` stores the whole encoder loop under
  `_LAST_PNG_ENCODE_INFO` with `png_compress_ms`, even for WebP/JPEG.
- `modal_app.py:14540-14548` emits that PNG-named field at the next-node or
  persist boundary, not as a precise codec-only measurement.

E2 should expose additive fields such as `codec`, `quality`,
`output_codec_ms`, `encoded_bytes`, and `conversion_fallback`. Existing
output and terminal fields should remain compatible.

### E2-3: Preview quality 70 is not wired; current defaults are 75/original

`output_converter.py:20-48` defines formats and defaults as:

```text
output_format=original
quality=75
webp_lossless_compression=balanced
```

The duplicated inline converter in `comfyapp.py:289-304` has the same defaults.
The direct sink therefore remains Original/PNG unless an explicit output format
is passed, and a future Preview caller must override quality to 70 without
changing Original behavior.

### E2-4: Canonical nested conversion options lose quality and method

`ExecutionOptions.from_legacy` accepts `output_conversion_options` at
`comfymodal_runtime/contracts.py:470-477`, but
`ExecutionOptions.to_legacy_dict` maps only `conversion["format"]` to the
legacy `output_format` key (`contracts.py:606-608`). Nested `quality` and
`webp_lossless_compression` are not promoted.

`comfymodal_runtime/modal_app.py:13373-13376` and `14488-14491` then fall
back to quality 75 and balanced compression. A Preview request represented in
the canonical nested field can consequently execute with the wrong quality.

### E2-5: Conversion vocabulary and validation differ across seams

`output_converter.py:20` accepts `webp_lossless` and `webp_lossy`, not plain
`webp`. An unsupported format is changed to `original` with an error marker at
`output_converter.py:139-147`.

`ExecutionOptions.from_legacy` maps a top-level `output_format` into
`output_conversion_options["format"]` at `contracts.py:470-473`, but does not
normalize the vocabulary. Whether a live caller sends plain `webp` is UNKNOWN.

The tensor encoder also passes quality directly to Pillow at
`comfyapp.py:681-688`, while `output_converter.convert_image_bytes` clamps it
to 0-100 at `output_converter.py:145-147`. The two seams can therefore behave
differently for invalid quality values. `_collect_production_request_params`
uses `int(req.get("quality", 75))` at `comfyapp.py:809-814`; a `quality: null`
request would raise before the sink try block. Whether that input is produced
is UNKNOWN.

### E2-6: Existing output and completion ordering is sound and must not regress

The modern Experiment path has the required order:

```text
running current Attempt
-> execute
-> materialize/resolve output
-> record_result / attach assets
-> verify required association
-> completed terminal
```

The repository rejects stale or terminal attempts before result persistence
(`history_v2_repository.py:1948-1960`) and checks visible asset association
before returning success (`history_v2_repository.py:2027-2035`).

The scheduler records `failed` before result persistence only for an execution
that explicitly failed (`experiment_modern_scheduler.py:1477-1487`). That is
the correct failure branch; it must not be changed into a Preview success.

### E2-7: History projection understands Preview but not newest Original

`history_v2_routes.py:222-263` exposes separate thumbnail, preview, and
original URLs and prefers `original > preview > thumbnail` for the primary
output. `history_v2_routes.py:781-829` also looks for these asset types in
generation detail.

This is compatible with Preview-only generations and later Original upgrades.
However, the current grouping uses ascending asset order and selects the first
matching Original (`history_v2_routes.py:244-249`). The handoff requirement
that the newest successful Original become preferred needs a later focused
projection change. It is not a reason to alter the E2 compression seam.

The existing `original_failed` derivation checks local
`Path(original.managed_path).is_file()` (`history_v2_routes.py:256-259`). That
is misleading for a valid remote `modal://` managed path and remains a separate
Phase E cleanup item.

## Recommended E2 Design

### A. Freeze output intent before execution

Carry an immutable output intent in the accepted request/plan and snapshot,
separate from workflow graph content:

```json
{
  "output_mode": "preview",
  "output_format": "webp_lossy",
  "quality": 70,
  "preview_enabled": true
}
```

The exact field names may follow the existing contract, but the persisted
request must distinguish Preview from Original. Preview default OFF must resolve
to the current Original behavior. Generate Original must create a new Attempt
with only output behavior changed.

For Experiment cells, freeze the mode in each cell plan/spec. Do not infer it
from mutable UI state at execution time. The existing `create_modern_matrix`
mode field can carry this once the planner/route supplies it.

### B. Use the direct sink for Preview

When Preview is enabled and production output is active:

1. Keep the normal workflow and output node.
2. Let the authorized direct sink encode directly from the clamped tensor.
3. Pass WebP lossy and quality 70 by default.
4. Persist and transport only the requested encoded bytes.
5. Do not run `convert_output_items` after a successful direct-sink attempt.

This avoids the PNG intermediate and preserves strict output-node validation.
The non-direct strategy conversion path remains a fallback, with explicit
conversion timing and error/fallback metadata.

### C. Thread Preview type through History

At minimum, thread these values through the result-to-history seam:

- attempt mode: `preview` or `original`;
- asset type: `preview` or `original`;
- codec, quality, and conversion timing metadata;
- producer variant/type for descriptor-only remote assets.

Use the same Generation for Preview and Generate Original, append a new Attempt,
and retain every prior Attempt and asset. The existing
`record_result -> completed` ordering must remain the success gate.

The writer/repository must not infer Preview from the `.webp` extension. WebP
can be either a Preview or an explicitly requested Original.

### D. Keep local materialization descriptor-only where possible

For remote descriptor results, local materialization should not decode and
re-encode the image. It should resolve the asset reference and preserve the
codec metadata. The managed History asset, not the configured export folder,
remains authoritative.

### E. Keep Original behavior unchanged when Preview is OFF

The Preview feature must not change:

- workflow graph;
- Version/Preset identity;
- seed or controls;
- model selection;
- required output node binding;
- output-before-terminal ordering;
- existing Original asset semantics.

## Focused Deterministic Gate

No paid/live run should occur until these local/fake tests pass.

### Compression behavior

1. Test `encode_image_tensor_batch` for Original, WebP lossless, WebP lossy,
   and JPEG output MIME/extension and decodability.
2. Verify Preview default resolves to WebP quality 70 while Original remains
   unchanged.
3. Verify quality clamping and a `quality: null` request are handled without
   a sink exception.
4. Verify accepted format vocabulary, including explicit rejection of
   unsupported plain `webp` unless it is intentionally normalized.
5. Verify RGBA-to-JPEG white compositing.
6. Verify the direct sink does not trigger a second conversion.

### Contract propagation

1. Round-trip `ExecutionOptions.output_conversion_options` with format,
   quality, and lossless method; assert all three reach the remote request.
2. Assert the frozen plan/snapshot retains Preview output intent.
3. Assert Preview creates a `preview` Attempt and `preview` asset.
4. Assert Preview followed by Generate Original keeps one Generation, appends
   an Original Attempt, and retains the Preview asset.
5. Assert failed Original leaves the Preview usable and preserves the failed
   Attempt.
6. Assert repeated terminal/result callbacks do not duplicate assets.

### Ordering and History

1. Assert result asset association occurs before `completed`.
2. Assert a required-output Preview cannot complete without a visible Preview
   or valid producer asset association.
3. Assert remote `modal://` assets are not marked `original_failed` merely
   because they are not local files.
4. Assert Preview-only feed/detail responses expose Preview URLs without
   requiring an Original.
5. Add a later projection test for newest-successful-Original preference.

### Diagnostics

1. Record format-specific `output_codec_ms`, quality, encoded byte count, and
   fallback status for direct-sink output.
2. Keep existing output write and volume commit timing separate from codec
   timing.
3. Replace or supplement the PNG-specific timing label with a format-neutral
   output encode record.
4. Assert `Attempt.total_conversion_time_ms` is nonzero when the sink performs
   a measured conversion and remains zero only for a true Original/no-op path.

## Minimal Change Boundary

Likely E2-owned surfaces:

- `comfyapp.py`: direct sink output intent, validation, and format-specific
  encoder diagnostics;
- `comfymodal_runtime/contracts.py`: lossless round-trip of conversion fields;
- `comfymodal_runtime/modal_app.py`: result metadata and no-double-conversion
  diagnostics;
- `comfymodal_runtime/output_delivery.py`: descriptor metadata if needed;
- `history_v2_repository.py` and `history_v2_writer.py`: explicit mode/type
  threading and Preview asset association;
- `experiment_modern_plan.py` / `experiment_modern_routes.py`: frozen Preview
  intent for Experiment cells;
- focused tests under `tests/`.

Do not modify restore, model loading, GPU teardown, transport cancellation, or
performance-track code for E2. Do not change the workflow graph to implement
Preview. Do not create a second Experiment execution architecture.

## Evidence Classification

### Proven by source inspection

- Direct tensor-to-codec encoding exists and is the lowest-latency available
  seam.
- Direct-sink output skips post-hoc conversion.
- Modern result persistence precedes successful terminal completion.
- Data models support Preview modes/types.
- Current production writer and producer adoption hardcode Original.
- Direct-sink conversion timing is not currently exposed as codec timing.
- Current defaults are Original/quality 75, not Preview/WebP/quality 70.

### Inferred risk

- A nested canonical quality/method can silently fall back to 75/balanced.
- `quality: null` can fail in the direct sink before its encoding try block.
- PNG-named timing can overstate or misattribute WebP/JPEG timing.

### Unknown until targeted evidence

- Actual Preview compression latency for representative 1088x1920 outputs.
- Whether any current frontend caller sends plain `webp`.
- Whether any current caller sends `quality: null`.
- Whether a live descriptor path already registers a producer asset variant
  that can safely be classified as Preview without new plumbing.

## Decision

Proceed with E2 around the remote direct-output sink, not post-hoc local or
filesystem conversion. First make output intent and Preview asset semantics
explicit, then add format-specific timing and deterministic coverage. Preserve
the existing result-before-terminal invariant and keep Preview OFF as the
default until the local gate is green.

## E2A Implementation Follow-Up

Date: 2026-08-17
Scope: canonical runtime output intent, direct-sink codec behavior, and codec diagnostics

### Executive Result

**VERIFIED CURRENT BEHAVIOR**

The direct-output sink remains the Preview compression seam. The sink now
normalizes its request before Pillow, encodes the already clamped tensor once,
stores additive codec metadata with each registry entry, and the modern runtime
continues to skip post-hoc conversion for `direct_output_sink`.

**RECOMMENDED PHASE-E CONTRACT**

The canonical runtime codec vocabulary is:

| Input value | Canonical format | Codec | Extension/MIME |
| --- | --- | --- | --- |
| `original`, `png` | `original` | PNG | `.png` / `image/png` |
| `webp`, `webp_lossy` | `webp_lossy` | WebP lossy | `.webp` / `image/webp` |
| `webp_lossless` | `webp_lossless` | WebP lossless | `.webp` / `image/webp` |
| `jpeg`, `jpg` | `jpeg` | JPEG | `.jpg` / `image/jpeg` |

Unsupported codec values are rejected at the typed contract boundary and are
returned as an explicit conversion error/fallback by the standalone byte
converter. They are not silently changed into Original output.

### Files and Functions Changed

**VERIFIED CURRENT BEHAVIOR**

- `comfymodal_runtime/contracts.py`: added `normalize_output_format`,
  `normalize_quality`, `normalize_webp_lossless_compression`, and
  `normalize_output_conversion_options`; `ExecutionOptions.__post_init__`,
  `from_legacy`, and `to_legacy_dict` now preserve and project format, quality,
  and `webp_lossless_compression`.
- `comfyapp.py`: `_collect_production_request_params` now handles null,
  coercible, and out-of-range quality values safely; `encode_image_tensor_batch`
  uses the canonical vocabulary and measures actual PIL codec work; both
  production sink nodes attach per-output codec metadata; `_convert_image_bytes`
  delegates to the canonical converter.
- `output_converter.py`: `convert_image_bytes` uses the same normalization,
  supports the aliases above, preserves existing Original/quality-75 defaults,
  applies Preview WebP alias quality 70, and returns additive codec timing and
  fallback metadata.
- `comfymodal_runtime/output_delivery.py`: `ConversionMeta` and
  `AssetDescriptor` carry codec, quality, `output_codec_ms`, encoded byte count,
  and fallback status; direct-sink items now contribute codec time to
  `Attempt.total_conversion_time_ms` and descriptor results.
- `comfymodal_runtime/result_delivery.py`: post-hoc conversion preserves the
  canonical returned format and new metadata while retaining legacy result
  compatibility.
- `comfymodal_runtime/modal_app.py`: output trace enrichment now includes
  format-neutral codec metadata; output diagnostics separate codec time from
  asset write/volume commit time; `_should_run_posthoc_output_conversion`
  makes the direct-sink no-double-conversion gate explicit.

### Output Options Schema

**VERIFIED CURRENT BEHAVIOR**

The accepted nested shape is now lossless across the local plan and legacy
runtime projection:

```json
{
  "output_conversion_options": {
    "format": "webp_lossy",
    "quality": 70,
    "webp_lossless_compression": "balanced"
  }
}
```

`ExecutionOptions.to_legacy_dict()` additionally projects these values to
`output_format`, `quality`, and `webp_lossless_compression` for the existing
remote request shape. A user-facing `format: "webp"` is canonicalized to
`webp_lossy` and, when quality is absent or null at that boundary, resolves to
70. Explicit canonical `webp_lossy` without a supplied quality retains the
existing generic default of 75; the Preview caller must use the user-facing
Preview alias or provide 70 explicitly. Original remains `original` with the
existing quality-75 default and its graph/output-node behavior is unchanged.

Quality accepts integers and coercible numeric strings, clamps to 0-100, and
uses a deterministic default for null/malformed values. `quality: null` no
longer reaches `int(None)` in the sink setup path.

### Direct-Sink Diagnostics

**VERIFIED CURRENT BEHAVIOR**

Each direct-sink registry entry may now expose:

- `codec` (`png`, `webp`, or `jpeg`);
- canonical `format`;
- effective `quality` where applicable;
- `output_codec_ms`, measured around the actual PIL `save` call;
- `encoded_bytes`;
- `source_bytes`;
- `webp_lossless_compression` where applicable;
- `conversion_fallback`;
- compatibility `conversion_time_ms` equal to codec time for the sink item.

The existing `compress_level` and `png_compress_ms` fields remain available for
trace compatibility. They are supplemented, not relabeled: `output_codec_ms`
is the truthful format-neutral field. `output_asset_write_ms`,
`output_volume_commit_ms`, and commit overlap remain separate persistence
measurements. Descriptor result entries and `output_diagnostics` expose the
codec fields without adding a second image encode.

### Focused Tests and Results

**VERIFIED CURRENT BEHAVIOR**

New `tests/test_e2_preview_codec.py` passed: 19 tests. It covers option
round-trip, Preview WebP quality 70, Original defaults, aliases, unsupported
codec handling, quality coercion/clamping, WebP lossless, JPEG, PNG, decodable
bytes, RGBA-to-JPEG white compositing, direct-sink metadata, descriptor timing,
and no-double-conversion gating.

Additional focused local results:

- `tests/test_runtime_output_delivery.py` and
  `tests/test_runtime_result_delivery.py`: 101 passed;
- `tests/test_runtime_contracts.py` and
  `tests/test_milestone1_v2_runtime.py`: 54 passed after updating stale
  pre-canonical `webp` assertions;
- `tests/test_v2_ab_experiments.py`: 10 passed.

No Modal execution, deployment, GPU test, or latency benchmark was run. The
`<100 ms` and approximately `135 ms` targets remain **UNKNOWN / NEEDS
IMPLEMENTATION PROOF** until the later benchmark/live gate.

### Protected-Runtime Classification

**VERIFIED CURRENT BEHAVIOR: B — narrow protected-runtime change was required.**

The only protected-runtime file changed was
`comfymodal_runtime/modal_app.py`, and only its output collection/diagnostic
path was touched. No snapshot/restore, model loading, PromptExecutor cache,
cancellation, GPU teardown, or deployment-performance path was modified for
E2A. The remaining changes are in the contract, sink, converter, and output
descriptor layers.

### Remaining E2B Work

**UNKNOWN / NEEDS IMPLEMENTATION PROOF**

E2A deliberately does not thread Preview mode or asset type into History V2.
The next lane must still freeze `preview` versus `original` at request
acceptance, carry it through Single and Experiment persistence, classify
managed assets without inferring type from extension, and preserve the
Phase-D `result/asset association -> completed` ordering. It must also decide
how Preview-only managed assets and later Original attempts coexist. No
History routes, repository, writer, planner, frontend settings, Generate
Original replay, or fake-browser surfaces were changed here.

## E2 Implementation Follow-Up B — Preview Semantic Threading

Date: 2026-08-17
Scope: explicit Preview/Original output intent from accepted modern execution
request through Single/Experiment plans and producer/result metadata.

### Executive Result

**IMPLEMENTED WITH A THUMBNAIL TRANSPORT BLOCKER**

Preview mode is now explicit and immutable. It is never inferred from WebP,
quality, filename, extension, or codec. Preview ON resolves to lossy WebP at
the frozen requested Preview quality, defaulting to 70; Preview OFF resolves to
Original and leaves the existing Original codec/default behavior intact.

### Files and Functions Changed

- `comfymodal_runtime/contracts.py`: added `output_mode` to
  `ExecutionOptions`, strict `preview`/`original` normalization,
  `normalize_output_intent_options`, and the shared logical-output-key builder.
  Legacy and canonical plan serialization preserve the mode and conversion
  options.
- `studio_workflow_run.py`: modern Single plan construction normalizes the
  accepted modal options once, carries `output_mode` and `variant` in request
  metadata, and gives non-production plans the same frozen output contract.
  The legacy/shadow workflow path also carries the explicit mode.
- `experiment_modern_plan.py`: definition-level `modal_options` are normalized
  before expansion; every `CellPlan` freezes the same `output_mode`, and its
  serialized execution plan carries the mode and Preview conversion settings.
- `experiment_modern_scheduler.py`: result projection copies the immutable
  cell-plan mode/variant and fills missing descriptor logical keys before
  result persistence. Existing result-before-terminal ordering is unchanged.
- `comfymodal_runtime/playground_service.py`: producer adoption uses the
  descriptor/result variant instead of hardcoding `original`.
- `comfymodal_runtime/output_delivery.py`: descriptor/result metadata now
  carries `output_mode`, `variant`, and `logical_output_key` while retaining
  E2A codec diagnostics.
- `comfymodal_runtime/result_delivery.py`: materialized and primary-output
  metadata preserves the semantic fields.
- `comfymodal_runtime/modal_app.py`: direct-sink registration receives the
  frozen output mode, and descriptor results use the plan mode/variant.
- `tests/test_e2_preview_mode.py`: new deterministic E2B coverage.

### Canonical Semantic Contract

The accepted mode vocabulary is exactly:

```text
output_mode = "preview" | "original"
variant = output_mode for required producer output
```

Preview settings are projected into the existing E2A codec contract as:

```json
{
  "output_mode": "preview",
  "output_conversion_options": {
    "format": "webp_lossy",
    "quality": 70
  }
}
```

An explicit `output_mode: "original"` with `output_format: "webp"` remains an
Original WebP. The extension and codec do not select History asset type.

The logical output key matches the E1B model helper exactly:

```text
node:<node_id>:slot:<output_key>:item:<output_index>
```

It is attempt-independent, variant-independent, codec-independent, and does
not contain a run ID, request ID, asset type, format, hash, or filename.

### Single and Experiment Threading

Single accepted `modal_options` are copied into the immutable plan builder.
The resulting `ExecutionPlan.execution_options.output_mode`, nested codec
options, and `request_metadata` are frozen before execution. Later mutation of
the caller's settings object cannot change the accepted plan.

Modern Experiment definitions use the one frozen `modal_options` object from
the accepted definition. It is normalized once before cell expansion, copied
into every cell, serialized in each cell execution plan, and consumed by the
existing scheduler without mutable Settings rereads or browser fanout. No
Experiment concurrency behavior was changed.

### Producer/Result Metadata

Direct-sink descriptor results expose `output_mode`, `variant`, and the stable
logical key alongside the E2A fields `codec`, `quality`, `output_codec_ms`,
encoded byte count, source byte count, and fallback status. Producer lease
registration now uses the descriptor/result variant, so Preview producer assets
are registered as `preview` and Original producer assets remain `original`.
The scheduler also projects the frozen mode when a lower-level result omits
those fields. Required output association still occurs before the scheduler or
modern Single path records successful completion.

### Thumbnail Result and E2C Blocker

No producer Thumbnail derivative is emitted in E2B. The producer has local
encoded bytes, but the current allowed History handoff carries one
`primary_asset_id`; `history_v2_repository.record_result` currently ignores
`asset_descriptors` and the producer lease schema has no descriptor-list or
parent/logical-output transport for a second asset. Emitting an extra WebP
would therefore create no managed History Thumbnail and could not be safely
classified. This is recorded as `E2C_THUMBNAIL_DESCRIPTOR_BLOCKER`.

E2C must add or approve a multi-descriptor producer-to-History association
contract that carries at least asset ID, variant, parent asset ID, logical
output key, dimensions, and independent encode timing. Thumbnail failure must
remain non-fatal to a valid required Preview/Original result.

### Tests and Results

New `tests/test_e2_preview_mode.py`: **6 passed**. It covers Preview ON/OFF
semantics, Preview WebP quality 70, explicit Original WebP, Single plan
freezing, all Experiment cell plans, descriptor variant metadata, logical-key
stability, and exclusion of run/codec/mode identity from the logical key.

Latest post-edit focused verification:

- `tests/test_e2_preview_codec.py` plus `tests/test_e2_preview_mode.py`:
  **25 passed**;
- modern planner/scheduler/binding/plan-identity suites: **97 passed, 21
  subtests passed**;
- Phase-E contract/history/logical-output/replay suites: **47 passed, 4
  skipped, 5 subtests passed**;
- changed E2 Python modules and E2B tests: `py_compile` passed;
- `git diff --check`: clean for the E2-owned tracked files.

The broader `tests/test_runtime_canonical_v2.py` invocation had four existing
cache/profile expectation failures (`cached_unchanged` versus `published`, and
profile publisher call count); these are unrelated to output intent and were
not changed. No Modal execution, deployment, live generation, GPU spend,
benchmark, or commit was performed.

### Protected-Runtime Classification

The only protected-runtime change in E2B is the narrow output/result metadata
path in `comfymodal_runtime/modal_app.py`. No snapshot/restore, model loading,
PromptExecutor cache, cancellation, GPU teardown, or deployment-performance
path was modified.

### Remaining E2C Work

Resolve `E2C_THUMBNAIL_DESCRIPTOR_BLOCKER` with the approved multi-descriptor
producer/History contract, then add deterministic Thumbnail success/failure,
dimensions, same-logical-key, and independent-timing tests. E1B still owns
History persistence/grouping and must consume the explicit mode, variant, and
logical key fields; E3 owns Generate Original replay.
