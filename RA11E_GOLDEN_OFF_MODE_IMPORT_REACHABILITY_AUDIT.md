# RA11E — Golden OFF-Mode Import Reachability Audit

**Date:** 2026-08-30  
**Scope:** read-only static audit of the canonical
`ModalRuntimeEntrypointV2.run_golden_serial_stream` path. No Modal, deploy,
GPU execution, source implementation, or package installation was performed.
Existing concurrent worktree changes were left untouched; the experimental
RA9C QD module was not analyzed.

## Executive conclusion

`COMFYMODAL_SAMPLING_DEEP_PROFILE=off` is an effective **deep-profiler
behavior gate**, but it is not an import or legacy-runtime gate.

OFF avoids the deep profiler's ComfyUI sampler/model resolution, profile object,
patches, model hooks, CUDA event collection, profile events, and profile
finalization. It does **not** avoid the broad legacy diagnostic/runtime closure:
the canonical Golden sampler unconditionally imports `runtime_executor`, calls
the sampler-wrapper installer, and then imports `sampling_deep_profile` even
when its resolved level is `off`. Building the runtime executor's wrapper also
imports `model_preload`.

The direct Golden runner then invokes the sampler node directly. The source
explicitly notes that the installed production wrapper can therefore be
successfully present without observing that invocation
(`golden_serial.py:5499-5505`). This makes the wrapper installation redundant
for the direct Golden execution path unless a separate behavior dependency is
proven.

There is no evidence in this path of a runtime `pip install` or equivalent
package installer. “Installs” below means Python-side wrapper/hook installation.

## Evidence basis and limits

Primary evidence is current source, with exact source reads after graph discovery.
The codebase graph was ready at generation `2026-08-20`; candidate runtime files
had metadata changes, so source was treated as authoritative. Static analysis
does not prove the success of a ComfyUI wrapper API call, the prior contents of
`sys.modules`, or remote process resource totals.

No local import benchmark was run. Importing the composition root and Golden
module would load Torch and the broad application/runtime surface; executing the
request would require ComfyUI models, CUDA, files, and Modal lifecycle state.
Running that measurement would not be a sufficiently isolated safe import
measurement under this audit's constraints. Consequently, this report makes no
local claims about import wall time, RSS, module totals, threads, or FDs, and no
local import wall is substituted for Modal E2E latency.

RV2B remains useful as remote configuration evidence: its deployment records
stage diagnostics `1` and deep profile `off`, and its five runs emitted ordinary
Golden stage events without a deep-profile event
(`RV2B_REMOTE_GOLDEN_BASELINE_TRUTH_REPORT.md:38-45,81-87`). RV2B did not
measure the OFF+stage-diagnostics-off import closure.

## Entry-point reachability

`run_golden_serial_stream` lazily imports `golden_serial` and calls
`golden_serial_execute` exactly once after request validation, volume checks,
GPU readiness, and DynamicVRAM activation
(`comfymodal_runtime/modal_app.py:21110-21309`). It deliberately bypasses the
normal `ExecutionPlan`, `PromptExecutor`, and `run_plan_stream` path.

That narrow execution body is reached from a broad composition root. At module
import, `modal_app.py` imports `runtime_executor`, `model_preload`, snapshot
models, probes, output delivery, and other runtime surfaces
(`modal_app.py:32-138`). The package initializer also eagerly imports
`contracts` and `trace` (`comfymodal_runtime/__init__.py:3-40`). Thus a fresh
process importing the canonical Modal application has already crossed much of
the old runtime boundary before the Golden request's own sampling branch.

## OFF sampling branch

The relevant control flow is:

1. `golden_sampling` optionally creates the lightweight Golden sampling
   diagnostics object only when `COMFYMODAL_GOLDEN_SAMPLING_DIAGNOSTICS` is on
   (`golden_serial.py:5453-5463`). This is separate from the deep-profile flag.
2. It unconditionally imports `runtime_executor` and calls
   `ensure_sampling_timing_wrapper(session.patcher)`
   (`golden_serial.py:5472-5481`).
3. Importing `runtime_executor` constructs its singleton wrapper at module load
   (`runtime_executor.py:5153-5155`). Wrapper construction imports
   `_ACTIVE_LANE_TRACE` and `_ACTIVE_REQUEST_TRACE` from `model_preload`
   (`runtime_executor.py:4352-4387`).
4. `ensure_sampling_timing_wrapper` adds the keyed
   `WrappersMP.SAMPLER_SAMPLE` wrapper when absent
   (`runtime_executor.py:5157-5189`).
5. `golden_sampling` unconditionally imports
   `sampling_deep_profile` and resolves its level
   (`golden_serial.py:5514-5520`). For OFF, it does not import `model_preload`
   or `trace` from this branch and does not begin a profile.
6. `begin_sampling_profile` normalizes the level and returns `None` immediately
   for `off` (`sampling_deep_profile.py:2705-2727`). Its module contract states
   that OFF performs no ComfyUI sampler imports, patches, events, or
   synchronizations (`sampling_deep_profile.py:47-53`).

The wrapper's body would import additional `model_preload` helpers and arm the
one-shot sampler-stall watchdog at a real sampler boundary
(`runtime_executor.py:4617-4657`). However, the direct Golden runner bypasses
the ComfyUI wrapper invocation, so static source proves wrapper installation,
not that this watchdog executes in the canonical direct Golden invocation.

## Configuration matrix

“Deep profile state” means an active `SamplingDeepProfile`, profiler-owned
patches/hooks, profile trace events, or profile CUDA event realization. “Golden
background resources” means ordinary request resources such as QD workers,
pinned staging, source FDs, and completion events; these are not evidence that
the deep profiler ran.

| Configuration | `runtime_executor` imported | `sampling_deep_profile` imported | `model_preload` imported | `trace` imported | sampler wrapper install | deep-profile state/hooks | Golden background resources |
|---|---|---|---|---|---|---|---|
| **A — deep off, stage diagnostics off** | YES, via `modal_app` and sampling branch | YES, then resolves `off` | YES, via composition root and wrapper construction | YES, via package/runtime trace path | YES/attempted; direct Golden sampler may not invoke it | NO | YES: QD GPU buffer, pinned slots, completion events, source FDs, joined daemon workers |
| **B — deep off, stage diagnostics on** | YES | YES, then resolves `off` | YES | YES | YES/attempted | NO | YES, plus diagnostic timing/snapshot resources |
| **C — `steps`** | YES | YES | YES | YES | YES/attempted | YES unless lifecycle ownership rejects it; step-level profile setup/events | YES; same QD resources |
| **D — `blocks`** | YES | YES | YES | YES | YES/attempted | YES unless lifecycle ownership rejects it; block hooks and optional CUDA events | YES; same QD resources |

For C and D, the enabled branch imports `model_preload` to obtain the active
request trace and may import `trace` to create a fallback trace
(`golden_serial.py:5520-5528`). It then begins the requested profile
(`golden_serial.py:5534-5590`). Blocks mode owns the additional block-level hook
and optional CUDA-event behavior described by `sampling_deep_profile.py:19-45`.

## Stage diagnostics comparison

Stage diagnostics are independently selected by
`COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS`; only `1/true/yes/on` enables them
(`golden_serial.py:946-954`). They affect work inside model-load and transport
stages, not the named-module import predicates above:

- CLIP and VAE stages take page-fault, allocator, and timing snapshots only
  when enabled (`golden_serial.py:4365-4370,4631-4635,5846-5866`).
- QD transport always allocates the GPU buffer, pinned slots, correctness
  completion events, opens source FDs, starts workers, joins them, and waits
  completion events (`golden_serial.py:2300-2349,2357-2388`).
- Stage diagnostics add measurement-only CUDA timing events and telemetry
  structures (`golden_serial.py:2265-2299,2325-2346`).

Therefore stage diagnostics **changes runtime measurement/resource work**, but
does not change the import closure of `runtime_executor`,
`sampling_deep_profile`, `model_preload`, or `trace` in the canonical path.

## OFF answers

### Is each target imported anyway?

- **`runtime_executor`: YES.** It is imported at `modal_app` composition-root
  import and again by `golden_sampling` before the OFF decision.
- **`sampling_deep_profile`: YES.** The module is imported to resolve the level,
  even though its `begin_sampling_profile` OFF branch is cheap and inert.
- **`model_preload`: YES.** It is imported by `modal_app`; independently,
  constructing the runtime executor's wrapper imports it.
- **`trace`: YES.** It is eagerly imported by `comfymodal_runtime.__init__`
  and is part of the runtime trace surface. This is not proof that deep-profile
  trace state was created.

### Is the sampling wrapper installed anyway?

**YES/attempted.** The installer is unconditional and adds the keyed wrapper if
the patcher and ComfyUI wrapper API are available
(`runtime_executor.py:5157-5189`). Static analysis cannot certify a successful
remote API mutation for every patcher, so “YES” means the canonical code path
performs the installation and its success is recorded, not that every failure
case must return true.

### Is there an expensive transitive closure anyway?

**YES.** The broad `modal_app` root imports normal executor, preload, snapshot,
probe, output, tracing, and diagnostic surfaces before the Golden method. The
runtime executor also imports guarded optimization diagnostics and prompt
signature cache modules at top level (`runtime_executor.py:40-86`), while
`model_preload` imports conditioning/cache, snapshot, trace, lane coordination,
UNET probe, `unet_backing` unless lean-snapshot is enabled, and
`variance_diagnostics` (`model_preload.py:34-132`). Guarded feature flags stop
some behavior; they do not make the Python imports disappear.

This is an import-closure finding, not a measured claim about RSS or Modal
latency. The size of the native Torch/CUDA and custom-node closure remains
unattributed by this audit.

### Does OFF avoid installing the old broad diagnostic runtime?

**NO.** It avoids the deep profiler's active instrumentation, but it does not
avoid importing the old broad runtime surfaces or installing the always-on
sampler timing wrapper. The wrapper is likely redundant for the direct Golden
runner because the source says that runner calls the node method directly.

## Conservative avoidable-import count

For the required completion field, `OFF_MODE_AVOIDABLE_IMPORTS` counts named
Python module boundaries that are reachable on OFF and are clearly removable
from a **dedicated direct-Golden OFF path**, while excluding required
`contracts`/`trace` lifecycle surfaces and ordinary stdlib/third-party
dependencies. It is not a count of every transitive module in the process.

The conservative count is **5**:

1. `comfymodal_runtime.runtime_executor` — only needed by the currently
   unconditional legacy sampler-wrapper bridge, not by the direct Golden node
   call after that dependency is proven absent.
2. `comfymodal_runtime.model_preload` — reached by the broad shared root and
   runtime-wrapper construction; its normal preload machinery is not Golden's
   direct model-loading path.
3. `comfymodal_runtime.sampling_deep_profile` — imported even after the OFF
   level could be resolved without entering the profiler module.
4. `comfymodal_runtime.unet_backing` — imported by `model_preload` unless the
   separate lean-snapshot gate is enabled, despite its diagnostic helpers being
   independently gated.
5. `comfymodal_runtime.variance_diagnostics` — imported by `model_preload`
   even when variance diagnostics are disabled.

This count deliberately does not count `optimization_diagnostics` and
`prompt_signature_cache` separately: they are advisory, guarded imports inside
the legacy executor and the audit does not claim their individual import cost
or removal independently. It also does not count `trace`, which is part of the
current canonical lifecycle trace surface even though a future dedicated
bootstrap could potentially narrow it.

## Smallest future cleanup (not implemented)

The smallest behavior-preserving candidate is to stop the direct Golden path
from calling `ensure_sampling_timing_wrapper` after proving that
`GoldenSerialRunner` never depends on the wrapper's events, watchdog, or model
identity checks. Keep the wrapper for normal V2 execution. This removes the
direct Golden-triggered `runtime_executor` → `model_preload` bridge but does not
by itself remove the `modal_app` composition-root imports.

The next, larger cleanup is a dedicated Golden bootstrap/composition boundary
that preserves restore identity, GPU reattachment, node registration, output
durability, and trace contracts while keeping normal V2 executor/preload code
out of the Golden process. That should follow a fresh-process A/B measurement;
it is not implemented here.

## Final fields

```text
RA11E_COMPLETE=YES
OFF_IMPORTS_RUNTIME_EXECUTOR=YES
OFF_IMPORTS_SAMPLING_DEEP_PROFILE=YES
OFF_IMPORTS_MODEL_PRELOAD=YES
OFF_IMPORTS_TRACE=YES
OFF_INSTALLS_SAMPLING_WRAPPER=YES
STAGE_DIAGNOSTICS_CHANGES_IMPORT_CLOSURE=NO
OFF_MODE_AVOIDABLE_IMPORTS=5
RUNTIME_SOURCE_MODIFIED=NO
MODAL_CONTACTED=NO
REPORT=RA11E_GOLDEN_OFF_MODE_IMPORT_REACHABILITY_AUDIT.md
```
