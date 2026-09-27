# Batch A — Host Telemetry Final-State Shipping Audit

Audit of `comfymodal_runtime/host_hardware_telemetry.py` +
`tests/test_host_hardware_telemetry.py` against the approved final state in
`V2_HOST_HARDWARE_AND_PRESSURE_TELEMETRY.md` (§18–§21), including the
post-validation zero-sync classification edge fix that had not yet ridden a
successful deployment.

**Result: the working tree already contains the full approved final state,
including the zero-sync fix. No code change was made. No deploy was run.**

---

## 1. Verification summary

| Requirement | State in working tree | Evidence |
|---|---|---|
| Always-on Tier A, zero subprocesses | PRESENT | `collect_host_fingerprint` runs no subprocess on the healthy path: `lscpu` is Tier B, deferred unless `COMFYMODAL_V2_HOST_DIAGNOSTICS=1` (`host_hardware_telemetry.py:312-318`); `capture_resource_snapshot` is in-process only (`:463-526`). Enforced by `test_tier_a_healthy_path_zero_subprocesses` (subprocess.run patched to raise) |
| CPU grouping fingerprint | PRESENT | `cpuinfo_fingerprint_hash` (`:599-617`): sha256 over vendor/family/model/stepping/microcode + sorted flags; explicitly excludes cpu MHz and model name — stable per CPU class, usable as a grouping key |
| Cheap process CPU snapshots | PRESENT | `capture_resource_snapshot` uses `getrusage` + `/proc/self/stat` with delta accounting (`:463-526`, `:1590-1674`) |
| H2D decomposition | PRESENT | `classify_h2d` + `h2d_cuda_elapsed_ms` / `h2d_enqueue_host_ms` / `h2d_sync_wait_host_ms` family (`:363-387`) |
| Capability caching | PRESENT | `_CAP_CACHE` probes psi/cgroup once, first caller wins (`:75-82`, `:264-277`); verified by `test_capability_cache_skips_repeat_probes` and `test_fingerprint_opened_path_reduction` |
| Slow trigger default 4000 ms | PRESENT | `_slow_h2d_threshold()` default `"4000.0"` via `COMFYMODAL_V2_SLOW_H2D_THRESHOLD_MS` (`:247-251`); `should_trigger_slow_probe` uses `>=` (`:390-401`); verified by `test_should_trigger_slow_probe_thresholds` (2500 no / 4000 yes / 4100 yes / 9200 yes) + env override + diag flag tests |
| Tier B on slow H2D only | PRESENT | `emit_slow_h2d_forensics` runs nvidia-smi FULL→CORE→MINIMAL + PCIe probe + `lscpu -J` only on trigger (`:404-460`); healthy run = 0 GPU/lscpu subprocess calls (`slow_trigger_probe_ms = 0` per §20) |
| H2D classifications | PRESENT | `TRAILING_SYNC_STALL` / `COPY_INTERVAL_SLOW` / `HOST_OVERHEAD_AROUND_COPY` / `UNKNOWN/MIXED` (`:363-387`), wired to `h2d_classification` on `unet_fast_disk_complete` and the measurement clone |
| **Zero-sync edge fix** | **PRESENT** | see §2 |
| CPU physical identity wording safe | PRESENT | see §3 |

## 2. Zero-sync classification edge fix — PRESENT

The post-validation label-only fix is in the working tree:

`classify_h2d` (`host_hardware_telemetry.py:371-377`) validates the sync field
with an explicit range check, not a truthiness check:

```python
s = record.get("h2d_sync_wait_host_ms")
if (not isinstance(c, (int, float)) or isinstance(c, bool) or c <= 0
        or not isinstance(e, (int, float)) or isinstance(e, bool) or e <= 0
        or not isinstance(s, (int, float)) or isinstance(s, bool) or s < 0):
    return "UNKNOWN/MIXED"
```

- `s == 0.0` → passes validation (`0 < 0` is False) → treated as a **valid
  measured zero**, flows into the normal classification rules. No
  `if s:` / `or s` style truthiness check anywhere in the function.
- `s is None` (missing) → `isinstance(None, (int, float))` is False →
  `UNKNOWN/MIXED` (missing is still distinguishable from measured zero).
- Unit test with the exact real-data shape: `test_classify_h2d_zero_sync_wait_is_interval_slow`
  (`tests/test_host_hardware_telemetry.py:1127-1132`):
  `cuda=2821.225, enqueue=2821.286, sync_wait=0.0` → `COPY_INTERVAL_SLOW` (passes).

This is the exact "post-validation, label-only" edge from §21: "A zero-value
`sync_wait` (sub-ms rounding) is treated as a valid measurement, not missing."

## 3. CPU physical identity wording — SAFE

No claim anywhere in the module that family/model identifies a physical CPU
class:

- Module docstring: "physical brand/class and physical topology are NOT
  resolved (model name and stepping are hardcoded `unknown`, siblings/cores/
  physical-id are synthetic). `cpuinfo_fingerprint_hash` is a worker-class
  grouping key, not physical-host identity" (`:16-22`).
- `_cpu_identity_confidence` returns `virtualized_or_inconsistent` whenever
  gVisor-synthetic markers are present (model name `unknown`, or siblings ==
  cpu count with physical id 0) (`:904-940`).
- `cpuinfo_fingerprint_hash` excludes MHz and model name by construction —
  the fingerprint is documented and computed as grouping data only (§16/§22).
- `_build_probe_statuses` labels proc_cpuinfo `AMBIGUOUS` when the model name
  is `unknown` (`:1777-1787`).

## 4. Call-site wiring (read-only check, untouched)

The production call sites from the prior lane remain wired exactly as
approved (not modified by this audit):

- `model_preload.py:4050-4059` — `classify_h2d` on `unet_fast_disk_complete`,
  sets `h2d_classification` only when absent.
- `model_preload.py:4432-4433` — `should_trigger_slow_probe` evaluated after
  the post_h2d snapshot; on trigger `emit_slow_h2d_forensics` runs Tier B.
- `unet_backing.py:851` — `classify_h2d` on the measurement clone.

## 5. Test results

```
python -m pytest tests/test_host_hardware_telemetry.py -q
51 passed in 28.08s
```

Covers (all pass on the Windows dev machine; Linux/gVisor paths via
monkeypatched fixtures): cpuinfo parsing/hash stability, lscpu, PSI absent/
parse + 1-stat gate, cgroup v2/v1/unavailable, nvidia-smi fallback chain +
PCIe probe + TTL cache, no-fake-zeros, bounded overhead, once-per-process
guards, flat metadata, model_preload fault integration, classify_h2d (all
four classes + missing/nonpositive + zero-sync edge), trigger thresholds
(default/env/diag), Tier B forensics (success + all-fail), Tier A
zero-subprocess enforcement, capability cache, opened-path reduction,
lscpu deferred vs diag, torch-only GPU identity.

## 6. Healthy-path overhead expectation

No re-measurement was possible outside the Modal container (audit ran on the
Windows dev machine). The working tree matches the validated production-cheap
design: in-process-only Tier A, fingerprint ~4.3 ms, four snapshots 0.1–4.5 ms,
total **10.15 ms** (validated in §18) vs the ≤20 ms target. No code path in
the module reintroduces a subprocess, ctypes/NVML, or per-phase file read
into the healthy path.

## 7. Completion output

```
report path = V2_BATCH_A_HOST_TELEMETRY_SHIPPING_AUDIT.md
changed files = none (final state already present; no code change made)
commit = none
deploy count = 0
Modal runs = 0

production-cheap Tier A present = YES
zero healthy subprocess design present = YES
zero-sync classification fix present = YES
slow trigger default 4000 ms = YES
CPU physical identity wording safe = YES
tests = tests/test_host_hardware_telemetry.py (51 passed)
ready to ship on next integrated deploy = YES
```
