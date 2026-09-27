# V2 Batch C4 — Snapshot Hygiene OFF/ON Causal A/B (Prep Report)

Status: **PREPARED — NOT EXECUTED.** No deploy, no Modal runs, no commit.

## 1. Objective

Batch B observed one construction of the allocator-hygiene path:

| | RSS |
|---|---|
| before | 27,007,828 KB |
| after | 24,734,984 KB |
| delta | −2,272,844 KB (~ −2.17 GiB) |

That single observation proved hygiene can return RSS to the kernel, but it
did **not** prove a startup/restore performance win, because there was no
hygiene-OFF control.

Batch C4 prepares the causal A/B that can later answer: *does hygiene actually
improve Modal startup, pre-Python snapshot restoration, and Python/application
restore — and by how much?*

This batch only builds the offline harness/parser + tests. It changes no
production runtime behavior and runs nothing remotely.

## 2. The causal protocol (encoded by the harness)

Arms differ **only** in the feature flag:

- **A** — `COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE=0` (hygiene OFF; runtime
  default per `modal_app.py` `_runtime_env` passthrough)
- **B** — `COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE=1` (hygiene ON)

Both arms require a **freshly constructed snapshot for the corresponding
condition**. Hygiene acts at capture time (capture-boundary gate in
`modal_app.py` R2a; event stashed at `_restore_timing["snapshot_capture_hygiene"]`).
Per-request flag flips on an existing snapshot are invalid — the harness
rejects/Flags this via the `snapshot_per_arm_fresh` and
`snapshot_consistent_within_arm` protocol checks.

Held identical across arms (operator responsibility, checked where observable):
deployment lineage (image), GPU, CPU/memory request, TBASE/O0, model snapshot
configuration, workflow, Batch-C acceptance expectations, cold/single-use
behavior.

## 3. Run-count policy

No default cohort. The operator workflow is:

1. one cold validation for A;
2. one valid measurement if correct;
3. one cold validation for B;
4. one valid measurement if correct.

If the A/B difference is clear → **STOP**. Expand toward a maximum of **5 valid
runs/arm** only when consistency or variance requires it.

The harness/report supports 1–5 samples per arm and never pretends n=1 has a
p90 or a meaningful median.

The number of runs collected is an operator choice (1–5 per arm, biased
toward fewer; validation alone may be sufficient) and is independent of the
classification labels in §5, which describe the strength of inference the
collected data can support — a small cohort never inflates its own
classification, and a larger cohort is never required just to keep a label.

## 4. Metrics

**Primary (causal, scheduling-excluded):**

| metric | source |
|---|---|
| command without scheduling → response | `command_response_ms − scheduling_ms` (only when both present; else unavailable) |
| pre-Python snapshot restore | waterfall stage `pre_python_snapshot_restore` (fallback key `pre_python_snapshot_restore_ms`) |
| Python/application restore | waterfall stage `application_restore` (fallback `restore_total_ms`) |
| Modal startup | `submission_to_remote_python_resume_ms` (else stages sum) — **scheduling-inclusive, reported but excluded from the causal verdict** |

**Capture-time (hygiene event, arm A typically absent → unavailable, never 0):**
before/after/Δ RSS (kB), RssAnon/RssFile when available, cgroup
`memory.current` before/after/Δ, hygiene wall cost, `gc_collected`,
`malloc_trim` result/availability. Convention: `delta_rss_kb = before − after`
(positive = returned to kernel).

**Secondary:** H2D, sampling, process CPU, provider/region.

## 5. Classification

Per primary metric (modal startup excluded from the verdict):

- **CONFIRMED** — ≥ 3 valid runs per arm (default) **and** fully separated
  value ranges on a scheduling-free primary metric.
- **SUPPORTED INFERENCE** — ≥ 2 per arm, delta beyond the noise floor
  (default 1 ms), ranges overlap.
- **INSUFFICIENT DATA** — n < 2 on either side, metric missing on a side, or
  no measurable difference within the floor.

Overall verdict = strongest primary-metric classification (mixed directions
reported explicitly). **An RSS drop alone never upgrades the verdict** — the
report surfaces `rss_drop_without_startup_win` as an explicit "no claim" note.

Scheduling contamination is measured and reported
(`scheduling_contamination` check: median scheduling delta vs. primary deltas)
but never subtracted into the primary comparison — scheduling is excluded by
construction, not by correction.

## 6. Deliverables

| file | purpose |
|---|---|
| `tools/benchmark_v2_snapshot_hygiene_ab.py` | offline A/B analyzer + report renderer (stdlib only, 1320 lines) |
| `tests/test_benchmark_v2_snapshot_hygiene_ab.py` | pytest suite, 10 tests (365 lines) |

Verified: `python -m pytest tests/test_benchmark_v2_snapshot_hygiene_ab.py -q`
→ **10 passed**.

### Later operator usage

```bat
python -m benchmark_v2_snapshot_hygiene_ab ^
  --arm-a <A-run-dir-or-json> --arm-b <B-run-dir-or-json> ^
  --out hygiene_ab_report.md --json hygiene_ab_analysis.json
```

Each `--arm-*` path is a directory of `run_*.json` artifacts (or a single JSON
file). Arm A is extracted with expected flag `"0"`, arm B with `"1"`; a present
but mismatched flag invalidates the run; an absent flag is retained but flagged
UNVERIFIED. Run artifacts come from the existing V2 harness
(`comfymodal-data/benchmarks/runs/v2_<ts>/run_*.json`), which already persists
`effective_env` (flag included), `command_response_ms`, `scheduling_ms`,
`final_reconciled_waterfall`, `snapshot_identity`, and
`_restore_timing.snapshot_capture_hygiene`.

### Test coverage

n=1 each side (insufficient, no fake p90) · multiple samples (medians +
CONFIRMED) · large scheduling difference with equal non-scheduling startup ·
hygiene RSS drop with no startup win (no claim) · hygiene startup win · missing
RSS fields · invalid structural runs excluded · experiment-record shape ·
n=1 extremes without p90 · flag-absent unverified-but-valid.

## 7. Constraints honored

- No production runtime behavior modified (new tool + tests + this report only).
- No deploy, no Modal runs, no commit (CURRENT main only).
- Batch-C concurrent writers: additive, isolated files only.
