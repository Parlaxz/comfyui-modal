# ComfyModal Generated-Output Durability Policy

**Status:** Current canonical policy · **Scope:** generated request output only

This policy is deliberately separate from source publication. The S4/source-
publication and custom-node Volume rules remain mandatory and are never made
optional by this policy.

## Configuration

`COMFYMODAL_OUTPUT_DURABILITY=off|strict` accepts exactly:

```text
off | strict
```

- Missing or `off` means **off** (`missing/off -> off`).
- An invalid explicit value is a **configuration error**. The system must fail
  with: `configuration error: COMFYMODAL_OUTPUT_DURABILITY must be off or strict`.
- Output durability is **off by default**. An explicit `strict` selection is
  required for generated-output persistence proof.

## Required result boundaries

| Mode | Required sequence | Result target |
| --- | --- | --- |
| `off` (default) | encode → observe SHA/bytes → `FIRST_RESULT_READY` → return | result-ready |
| `strict` (opt-in) | write/fsync → `Volume.commit` → reopen/hash proof → `TRUE_FIRST_DURABLE_RESULT` → return | true-durable |

The default target is **result-ready**; the strict target is **true-durable**.

In `off` mode, `FIRST_RESULT_READY` means that the encoded output bytes and
their observed SHA/byte count are available. It must not be labeled
`TRUE_FIRST_DURABLE_RESULT`. In `strict` mode, no durable/result event may be
stamped before the write, fsync, commit, reopen, and required hash proof have
completed. A strict failure is a failure; it must not silently downgrade to
`off`.

The output path has **no persistent output work**, persistent output worker,
background durability work, deduplication shortcut, or mode-dependent shortcut
around the required sequence. The caller owns the selected endpoint and
receives only after that endpoint is reached.

## Source publication is a separate invariant

Never make S4 publication durability optional. Shared custom-node publication,
its authoritative full-content identity, and its required Volume/receipt
readback remain mandatory regardless of generated-output mode. A generated
output's `off` mode is not permission to weaken source publication.

## Measurement rationale

The motivation for making generated-output durability opt-in is that the
observed `Volume.commit` cost is material: an earlier measurement reported
approximately **764 ms minimum, 1,028 ms median, and 1,826 ms maximum**.
Reopen/read/hash verification was only a few milliseconds in that observation.
These are historical/sample measurements, not universal provider, region,
Volume, workload, or time guarantees; every experiment must measure its own
boundary. Compare result-ready and true-durable timings only when the endpoint
is named explicitly.
