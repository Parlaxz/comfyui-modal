# production-006 tag vs live control runtime

**Status:** diagnostic baseline correction. The historical tag is NOT moved and
NOT retagged. This document exists so future agents do not repeat the stale-base
mistake that invalidated the first four M1B runs.

## Summary

The `production-006` **tag** is not a sufficient runtime base for experiments
today. The healthy live control app runs a **newer commit** that contains a
loader-correctness fix the tag lacks.

| identity | commit | contains `ce0a765e`? |
|---|---|---|
| `production-006` tag | `42cf4d048a8dbc66535753a857cc5cd99135f074` | **NO** |
| live control HEAD | `c19e61c11b743069a81a4f3f16f3908f199e792d` | **YES** |

## Exact commit chain: tag -> live

`git log --oneline --reverse 42cf4d0..c19e61c1` — 9 commits:

| commit | subject | files | classification |
|---|---|---|---|
| `852fc551` | persist outer-method lifetime marks into collected telemetry | `golden_parallel.py` +34, `modal_app.py` +16 | telemetry-only |
| `ff8a4448` | emit outer-lifetime marks through the recorder before telemetry persist | `golden_parallel.py` +20/-1 | telemetry-only |
| `528abddb` | include inner stage heartbeats in the recorder mark stream | `golden_parallel.py` +4 | telemetry-only |
| `ec76b64c` | minimal post-request GPU teardown on single-use containers | `config/v2/profiles/golden_p1_parallel_c0_source_h100.toml` +12 | **config/profile** |
| `5ac6f704` | stop duplicating the output image in the terminal result | `modal_app.py` +11 | telemetry / output-shape |
| `821c7760` | measure heartbeat elapsed against the request clock | `golden_parallel.py` +8/-5 | telemetry-only |
| `ce0a765e` | **recover READY ownership from the slot table instead of aborting on a stale doorbell** | `golden_source_threads.py` +11/-5 | **LOADER CORRECTNESS** |
| `6efecb7a` | record container snapshot/region facts at the restore boundary | `golden_serial.py` +51, test | telemetry-only |
| `c19e61c1` | persist container snapshot/region facts on the restore stage | `golden_serial.py` +3, test | telemetry-only |

Exactly **one** loader-correctness commit (`ce0a765e`) and **one** config commit
(`ec76b64c`). Everything else is telemetry.

**No commit in the range touches Sage policy or Sage configuration.** Verified:

```
git diff --name-only 42cf4d0 c19e61c1 | grep -i sage   ->  (no matches)
```

## The loader-correctness difference (`ce0a765e`)

`comfymodal_runtime/golden_source_threads.py`, `SourceThreadProcess._resolve_ready_block`.

Tag behaviour — **fails closed**:

```python
if state == FREE or int(slot_generation) > generation:
    return None
raise SourceProtocolError("stale_ready_generation")
```

Live behaviour — **drops the stale doorbell and re-derives**:

```python
# Either way this announcement cannot be honoured, so it is dropped rather than
# raised: the shared control block is the authority, and wait_ready immediately
# re-derives the real READY token from the slot table. ... claim_ready still
# enforces the exact (slot, generation) token, so recovering from the table
# cannot transfer the wrong bytes.
return None
```

`claim_ready` (line ~1137) intentionally still raises
`SourceProtocolError("stale_ready_generation")`; that is the correctness guard
the recovery design relies on. Do not remove it.

### Observed impact

With the tag as base, every M1B request aborted with
`SourceProtocolError: stale_ready_generation` during `golden_unet_load`, while
the live control passed. The tag path fails closed specifically on **slow
(degraded-throughput) runs**, where a doorbell can legitimately land against a
slot that is `IN_FLIGHT` under an earlier generation — so adding diagnostic work
made the diagnostic app fail and the untouched control pass. This inverted the
apparent A/B result until the base was corrected.

## The config difference (`ec76b64c`)

Adds to `config/v2/profiles/golden_p1_parallel_c0_source_h100.toml`:

```toml
COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN = "1"
```

plus the explanatory comment block. Because the tag predates this commit, a
profile extending that file on the tag resolved
`COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN=0` (the registry default) instead of `1`.
Verified in deploy manifests: control deployments from `02:48` onward resolve
`1`; the tag-based diagnostic deployment resolved `0`.

## Which identity to use for future experiments

Use the **exact current healthy control runtime tree**, i.e. the source tree and
config actually deployed behind the live control app — currently `c19e61c1`.
Concretely:

- Do **not** cut experiment branches from the `production-006` tag.
- Do **not** treat the tag as the experimental runtime base.
- Do **not** move or retag `production-006`; this is diagnostic baseline
  correction only.
- Verify with `git log --oneline 42cf4d0..HEAD` that `ce0a765e` is present
  before trusting any new base.

The M1B diagnostic branch `diag/m1-copy-root-cause` was rebased onto `c19e61c1`
for exactly this reason (commit `116817fe`).

## Consequence for the prior M1 report

The completed M1 loader-forensics report described `production-006` as the
immutable baseline. That description is now known to be incomplete for runtime
purposes: the tag is a valid *historical* anchor but is stale relative to the
live control. M1's conclusions were drawn from control runs executed against the
live tree, so they stand; only any statement that the tag alone reproduces the
control must be amended by this document.
