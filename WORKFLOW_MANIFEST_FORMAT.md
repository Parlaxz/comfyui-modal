# Studio Workflow Manifest Format

Reference documentation for `studio_workflow_manifest.py` (repo root) and the
portable manifest shape it builds, validates, canonicalizes, and hashes.

This document describes the format as implemented. The module is pure: it
performs no I/O, no network access, no filesystem access, and imports only the
Python standard library.

---

## 1. Purpose

A Studio Workflow manifest is a portable, JSON-shaped document that captures
everything needed to reproduce one workflow run, without carrying the heavy
artifacts themselves.

The domain model is:

- **Workflow** — logical identity (`wf_...`), tags, favorite, default preset.
- **Workflow Version** — an immutable snapshot of one exact graph
  (`wv_...`, `version_number` starting at 1, computed `graph_hash`).
- **Mapping** — exactly ONE per Version (store-enforced). Maps semantic roles
  (`positive_prompt`, `seed`, `steps`, ...) to graph node inputs/outputs plus
  graph-derived metadata (min/max/step, enum options, control kind).
- **Presets** — saved values for one mapped Version (`wpres_...`).

Large external dependencies are **referenced, not embedded**: model files,
custom-node repos, and assets appear as small reference records (filename,
sha256, repo URL, revision) with no bytes included in the manifest.

The manifest is designed to be:

- **Deterministic** — the same logical manifest always serializes and hashes
  identically, regardless of dict insertion order.
- **Verifiable** — the embedded graph's sha256 is recomputed on import; every
  reference is cross-checked against the Version identity.
- **Portable** — a plain dict/JSON document with no dependency on Python class
  internals.

---

## 2. Schema

A manifest is a dict with fixed root sections. `ROOT_SECTIONS` (in order):

| Root section | Required | Type | Notes |
|---|---|---|---|
| `manifest_version` | yes | int | Currently `1`; must be in `SUPPORTED_MANIFEST_VERSIONS`. |
| `workflow` | yes | dict | Identity + embedded graph + graph hash. |
| `version` | yes | dict | Immutable Version snapshot fields. |
| `mapping` | yes | dict | The exactly-one Mapping for this Version. |
| `presets` | no | list of dicts | Normalized to `[]` on parse if missing. |
| `models` | no | list of dicts | Normalized to `[]` on parse if missing. |
| `custom_nodes` | no | list of dicts | Normalized to `[]` on parse if missing. |
| `assets` | no | list of dicts | Normalized to `[]` on parse if missing. |
| `metadata` | no | dict | Free-form, unvalidated. Normalized to `{}` on parse if missing. |

Rules:

- **Required roots** are `manifest_version`, `workflow`, `version`, `mapping`.
  A manifest missing any of them fails validation.
- **Unknown ROOT sections are rejected.** Adding a new root section requires a
  `manifest_version` bump (see Versioning).
- **Unknown keys INSIDE sections are preserved as data.** The validator only
  type-checks the documented fields; anything else round-trips untouched.
- **No default-filling inside presets.** A preset missing `values`,
  `description`, `is_default`, etc. is valid and round-trips with the same key
  set. The module never repairs or invents fields.
- Empty-string ids/names are rejected; `bool` is never accepted where an int
  or number is expected, and vice versa.

### Annotated full example

```json
{
  "manifest_version": 1,

  "workflow": {
    "workflow_id": "wf_0123456789abcdef",
    "version_id": "wv_fedcba9876543210",
    "display": { "name": "Test Workflow", "description": "A fixture workflow" },
    "source": { "author": "fixture", "url": "https://example.com/workflows/test" },
    "graph_hash": "<sha256 hex of graph below, 64 lowercase chars>",
    "graph": {
      "nodes": [
        { "id": 1, "type": "CLIPTextEncode", "inputs": { "text": "a serene mountain lake" } },
        { "id": 2, "type": "CheckpointLoaderSimple", "inputs": {} },
        { "id": 3, "type": "KSampler", "inputs": { "seed": 42, "steps": 20 } }
      ],
      "links": [ { "source": 1, "target": 3, "slot": "conditioning" } ],
      "extra": { "group_nodes": [], "version": 0.4 }
    }
  },

  "version": {
    "workflow_version_id": "wv_fedcba9876543210",
    "workflow_id": "wf_0123456789abcdef",
    "version_number": 1,
    "immutable": true,
    "graph_hash": "<sha256 hex, same value as workflow.graph_hash>",
    "created_at": "2026-08-14T00:00:00+00:00"
  },

  "mapping": {
    "mapping_id": "wm_1122334455667788",
    "workflow_version_id": "wv_fedcba9876543210",
    "output_node_id": "3",
    "entries": {
      "positive_prompt": {
        "semantic_role": "positive_prompt",
        "node_id": "1",
        "input_name": "text",
        "output_name": "",
        "kind": "node_input",
        "data_type": "STRING",
        "enum_options": [],
        "minimum": null,
        "maximum": null,
        "step": null,
        "required": true,
        "multiline": true,
        "control_kind": "multiline",
        "display_name": "Positive Prompt"
      },
      "seed": {
        "semantic_role": "seed",
        "node_id": "3",
        "input_name": "seed",
        "output_name": "",
        "kind": "widget",
        "data_type": "INT",
        "enum_options": [],
        "minimum": 0,
        "maximum": 4294967295,
        "step": 1,
        "required": false,
        "multiline": false,
        "control_kind": "integer",
        "display_name": "Seed"
      }
    }
  },

  "presets": [
    {
      "preset_id": "wpres_0011223344556677",
      "workflow_version_id": "wv_fedcba9876543210",
      "workflow_id": "wf_0123456789abcdef",
      "name": "Default Quality",
      "description": "Quality preset",
      "values": { "positive_prompt": "a cat", "seed": 7, "steps": 25 },
      "model_choices": { "model": "sdxl_base.safetensors" },
      "lora_values": { "lora1": 0.7 },
      "exposed_controls": ["positive_prompt", "seed", "steps"],
      "recommended_values": { "steps": 25 },
      "favorite": true,
      "tags": ["quality", "default"],
      "dropped_controls": ["negative_prompt"],
      "is_default": true,
      "created_at": "2026-08-14T00:00:00+00:00",
      "updated_at": "2026-08-14T00:00:00+00:00"
    }
  ],

  "models": [
    {
      "filename": "sdxl_base.safetensors",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "folder": "checkpoints",
      "model_type": "checkpoint",
      "display_name": "SDXL Base",
      "provider": "huggingface",
      "revision": "main",
      "size": 6876255102,
      "source_urls": [
        "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"
      ],
      "role": "checkpoint",
      "compatibility": "sdxl"
    }
  ],

  "custom_nodes": [
    {
      "name": "comfyui-something",
      "display_name": "Something Nodes",
      "repo_url": "https://github.com/example/comfyui-something",
      "revision": "3fa4c9d1e2",
      "classes": ["FooNode", "BarNode"]
    }
  ],

  "assets": [
    {
      "filename": "preview.png",
      "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "size": 1024,
      "mime_type": "image/png",
      "role": "thumbnail"
    }
  ],

  "metadata": {
    "exported_at": "2026-08-14T12:00:00+00:00",
    "exporter": "studio-manifest-tool",
    "note": "free-form metadata is not validated"
  }
}
```

Field highlights by section:

- **workflow** — `workflow_id`, `version_id`, `graph` (must be a dict — the
  executable graph JSON object), `graph_hash` (required 64-hex sha256, must
  equal the recomputed canonical hash of `graph`). `display` and `source` are
  optional dicts.
- **version** — `workflow_version_id`, `workflow_id` (must equal
  `workflow.workflow_id`), `version_number` (int >= 1, not bool), optional
  `immutable` (bool), optional `graph_hash` (64-hex if present — provenance of
  the domain's stored fingerprint, NOT recomputed), optional `created_at` (str).
- **mapping** — `mapping_id`, `workflow_version_id` (must equal
  `version.workflow_version_id`), `entries` (dict keyed by semantic role; roles
  are extension-friendly and NOT enum-restricted — `guidance`, `prompt`, etc.
  are legal), optional `output_node_id` (str). Light type checks on known entry
  fields only; unknown entry keys are preserved.
- **presets** — `preset_id` (required, unique across the list),
  `workflow_version_id` (must equal `version.workflow_version_id`), `name`
  (required non-empty str). Optional light checks: `is_default`/`favorite` bool,
  `exposed_controls`/`dropped_controls`/`tags` lists of str,
  `values`/`model_choices`/`lora_values`/`recommended_values` dicts,
  `description`/`created_at`/`updated_at` str. At most one preset may have
  `is_default == true`.
- **models / custom_nodes / assets** — see Dependency references below.

---

## 3. Versioning

- `manifest_version` must be an **int** (a `bool` is rejected as such), and must
  be in `SUPPORTED_MANIFEST_VERSIONS`. Currently only `1` is supported; a
  version `2`, `0`, the string `"1"`, or `true` all fail validation with
  `unsupported manifest version: <v> (supported: 1)`.
- **New root sections require a version bump.** The validator rejects unknown
  root sections (`unknown root section: <name>`). This is deliberate: a new
  root section is a schema change, and schema evolution is signalled by
  bumping `manifest_version` (and extending `SUPPORTED_MANIFEST_VERSIONS`).
- **Unknown future fields policy:** root-level strict, section-level lenient.
  Unknown keys inside `workflow`, `version`, `mapping`, presets, models,
  custom-node records, and assets are treated as data: preserved untouched,
  never validated, never stripped.

---

## 4. Canonical hash semantics

Canonicalization and hashing follow the project convention established in
`production_workflow.py`:

- `canonicalize(manifest)` returns a **new** dict with keys recursively sorted
  (dicts rebuilt in sorted-key order) while **lists keep their element order**;
  scalars are untouched.
- `canonical_json(manifest)` is:

  ```python
  json.dumps(canonicalize(manifest), sort_keys=True, separators=(",", ":"),
             ensure_ascii=False, allow_nan=False)
  ```

  Compact separators, no ASCII escaping, and `allow_nan=False` so non-finite
  floats raise `ValueError` instead of producing divergent output.

- `graph_hash(graph)` = sha256 hex digest of the graph dict serialized with the
  exact same canonical kwargs — matching the `production_workflow.py`
  convention. It **fails closed**: a graph containing NaN/Infinity raises
  `ValueError`.
- `manifest_hash(manifest, include_metadata=True)` = sha256 hex digest over
  `canonical_bytes(manifest)`. With `include_metadata=False`, the `metadata`
  root is replaced with `{}` before canonicalization — the documented mechanism
  by which **timestamps are excluded from identity**.
- **No timestamps are ever added by the module.** `build_manifest` assembles
  exactly the sections it is given and adds no fields.
- **No memory addresses or object identities** influence the hash. Only the
  canonical serialized bytes matter, so the same logical manifest hashes
  identically regardless of insertion order, in any process, on any machine.

Determinism guarantees (covered by the test suite):

- Same logical manifest, different dict insertion orders → identical
  `canonical_json` strings and identical `manifest_hash`.
- Any value change → hash change.
- Metadata change → hash change by default; `include_metadata=False` ignores it.

---

## 5. Workflow Version immutability

- `workflow.version_id` **must equal** `version.workflow_version_id`
  (else `workflow.version_id does not match version.workflow_version_id`).
- `version.workflow_id` **must equal** `workflow.workflow_id`.
- `mapping.workflow_version_id` **must equal** `version.workflow_version_id`
  (the exactly-one-Mapping-per-Version association).
- Each preset's `workflow_version_id` **must equal**
  `version.workflow_version_id` (a preset is version-specific).
- `version.graph_hash` is optional and, when present, is **format-checked only**
  (64 lowercase hex). It is the provenance of the domain's stored Version
  fingerprint and is **not recomputed** by the manifest.
- `workflow.graph_hash` **is recomputed** from the embedded `graph` and must
  match, so a manifest whose graph bytes diverge from its declared hash fails
  validation on import.
- Immutability itself is a **domain guarantee**: WorkflowVersions are frozen
  records with no update/delete path in the store, and the store enforces
  exactly one Mapping per Version. The manifest documents and cross-checks
  that identity; it does not re-implement the store.

---

## 6. Dependency references

Dependencies are reference records only — filenames, hashes, URLs, and
revisions, never bytes.

### models — list of dicts

- `filename` — required non-empty str.
- `sha256` — optional; when present must be 64 lowercase hex chars
  (else `invalid model hash: <filename>`).
- `size` — optional int >= 0 (bool rejected).
- `folder`, `model_type`, `display_name`, `provider`, `revision`,
  `compatibility`, `role` — optional strs if present.
- `source_urls` — optional list of strs.
- **Identity** = `(filename, sha256-or-None)`. Duplicate identities are
  rejected (`duplicate model dependency: <filename> (<hash or 'no hash'>)`).
  The same filename with **different** sha256 values is legal — two distinct
  model identities, mirroring the model-library rule that same filename +
  different hash => distinct records.

### custom_nodes — list of dicts

- `repo_url` — required non-empty str with no leading/trailing whitespace.
- `revision` — required non-empty str (the expected commit/revision).
- `classes` — optional list of non-empty strs.
- `name`, `display_name` — optional strs.
- Duplicate `(repo_url, revision)` pairs are rejected
  (`duplicate custom-node dependency: <url>@<revision>`). URL strings are
  **data only** — never fetched, never executed.

### assets — list of dicts

- `filename` — required non-empty str.
- `sha256` — optional 64-hex; `size` — optional int >= 0.
- `mime_type`, `role` — optional strs.
- Unknown keys preserved.

---

## 7. Import validation

`parse_manifest(source)` accepts a **dict, str, or bytes**:

- `str`/`bytes` are parsed with `json.loads` using a `parse_constant` callback
  that raises on `NaN`/`Infinity`/`-Infinity`; decode failure is reported as a
  leading `invalid JSON: ...` issue.
- Missing optional roots are normalized: `presets`/`models`/`custom_nodes`/
  `assets` become `[]`, `metadata` becomes `{}`.
- Validation runs, then the manifest is canonicalized and returned.

**All issues are collected** — validation never fails fast. Every problem found
across all sections is accumulated into `ManifestValidationError.issues`
(list of str), and the exception is raised once at the end. An empty issue list
means no exception.

**Validity vs readiness are separate concerns:**

- `validate_manifest(manifest)` is the structural gate. It **never checks disk
  and never scans the Model Library**; missing/uninstalled dependencies are
  perfectly valid. It also never mutates its input.
- `check_readiness(manifest)` is a **pure structural pre-check** returning
  `{"ready": bool, "missing": [str]}`. It flags model refs lacking a valid
  sha256 (`models: <filename> (missing hash)`) and custom nodes lacking
  `repo_url` or `revision` (`custom_nodes: <name-or-url> (missing repo/revision)`).
  Actual local resolution of those references is a later, wiring-time concern
  owned by the route layer.

---

## 8. What is deliberately not embedded

- **Model bytes** — only `filename`/`sha256`/`size`/`source_urls` references.
- **Custom-node code or installs** — only `repo_url`/`revision`/`classes`.
- **Package archives** — only `filename`/`sha256`/`size`/`mime_type`/`role`.
- **Timestamps** — allowed only inside the free-form `metadata` root, which is
  deliberately excluded from identity hashing via `include_metadata=False`.
  The module itself never creates timestamps.
- **Domain internals** — the parser does not depend on Python class internals.
  It consumes and produces plain dicts; `studio_domain` entities are
  serialized/deserialized by the route layer, not by this module.

---

## 9. Security model

- **Pure module.** Imports are stdlib-only (`copy`, `hashlib`, `json`, `math`,
  `re`, `typing`). There is no `os`, `sys`, `pathlib`, `subprocess`,
  `importlib`, `urllib`, `socket`, `eval`, `exec`, or `open` anywhere in the
  module.
- **Zero I/O, zero network, zero execution.** No file reads/writes, no HTTP,
  no git operations, no downloads, no subprocesses, no installation logic.
- **URLs and repo strings are data.** They are validated for shape (non-empty,
  no leading/trailing whitespace) and never dereferenced.
- **Malformed/pathological input is rejected via type/shape validation**:
  root and section types, non-empty strings, `bool` vs int/number discipline,
  finite-float checks on mapping bounds, 64-hex sha256 checks, duplicate
  identity detection.
- **Fail-closed NaN handling.** `json.dumps(... allow_nan=False)` and the
  `parse_constant` rejector mean non-finite floats either raise or become
  validation issues — they can never silently alter a hash.
- No arbitrary imports, no command execution, no memory-address leakage into
  the serialized form.

---

## 10. Future route integration

Exact wiring points for the (not yet wired) route layer:

- `studio_workflow_routes.py` — import `studio_workflow_manifest` (the module
  is import-safe: no side effects at import time).
  - **Build:** assemble manifests from domain records
    (`WorkflowVersion.to_dict()`, `Mapping.to_dict()`, preset records,
    `model_library.py` records, `custom_node_registry.py` records) via
    `build_manifest(workflow=..., version=..., mapping=..., presets=...,
    models=..., custom_nodes=..., assets=..., metadata=...)`.
  - **Import/validate:** `parse_manifest(raw)` for incoming manifests (dict,
    JSON str, or bytes) — it normalizes, validates, and canonicalizes in one
    call.
  - **Identity:** `manifest_hash(manifest)` for exact-version identity;
    `manifest_hash(manifest, include_metadata=False)` whenever timestamps must
    not participate in identity.
  - **Readiness:** `check_readiness(manifest)` as a pure structural pre-check
    before any dependency resolution.
  - **Hashing:** `graph_hash(graph)` to compute/verify the graph fingerprint.

Explicit notes:

- **Routes are NOT wired yet.** The core module was delivered in isolation
  (Batch C3 isolated-core pattern); nothing imports it in production code
  today.
- **The module must remain pure.** All I/O, library scanning, network access,
  and installation logic belong to the route layer. `validate_manifest` and
  `check_readiness` must never gain disk or network access — they are the
  structural guarantees that keep the manifest portable and hash-stable.
