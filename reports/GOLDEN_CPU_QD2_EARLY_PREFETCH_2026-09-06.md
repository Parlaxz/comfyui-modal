# Golden CPU-QD2 Early Prefetch — 2026-09-06

## Scope and verdict

The diagnostic arm and both requested five-run cohorts were structurally accepted with the exact PNG SHA-256:

`8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`

The CPU-QD2 path started before GPU readiness, continued while H2D was legal, and accumulated the complete 8,044,936,192-byte CLIP backing without a second source owner. Every QD2 run reported `source_completed_before_h2d=false`.

Important limitation: the deployed profile requested `memory_mb=8192`, while the requested host allocation was described as 16 GB. The measured process high-water RSS was ~11.62 GB. cgroup memory limits were unavailable in the runtime evidence, so 16-GB safety is established by measured headroom only, not by an authoritative cgroup-limit proof.

## Cohorts

| Arm | Deep profiling | n | E2E median / P90 | E2E mean | E2E min–max | SD / CV | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| Current Golden control | on | 5 | 12,941.6 / 13,497.7 ms | 12,985.6 ms | 12,418.8–13,748.7 ms | 501.7 / 3.86% | accepted |
| Early CPU-QD2 | on | 5 | 12,766.6 / 13,002.3 ms | 12,712.0 ms | 12,352.6–13,159.4 ms | 305.9 / 2.41% | accepted |
| Early CPU-QD2 | off | 5 | 12,383.5 / 12,745.4 ms | 12,370.9 ms | 11,882.0–12,933.8 ms | 386.1 / 3.12% | accepted |

Deep-profiled QD2 versus control improved median E2E by 175.0 ms (1.35%) and P90 by 495.4 ms (3.67%). The no-deep-profiling QD2 cohort is not an apples-to-apples control comparison because no no-deep control cohort was collected.

## QD2 evidence

| Metric | Deep QD2 median | Deep QD2 P90 | No-deep QD2 median | No-deep QD2 P90 |
|---|---:|---:|---:|---:|
| Source start → source complete | 1,684.6 ms | 1,755.6 ms | 1,944.5 ms | 2,317.5 ms |
| GPU legal → CLIP GPU-ready | 1,999.3 ms | 2,061.2 ms | 2,223.6 ms | 2,649.6 ms |
| CLIP exposed wait | 1,417.2 ms | 1,580.0 ms | 1,616.3 ms | 2,043.9 ms |
| H2D stream span | 1,369.4 ms | 1,462.2 ms | 1,624.0 ms | 1,950.5 ms |
| Restore wall | 762.2 ms | 841.3 ms | 715.9 ms | 887.2 ms |
| Peak process RSS | 11.622 GB | 11.622 GB | 11.615 GB | 11.615 GB |

Deep QD2 medians: 939,524,096 bytes at normal CLIP demand, 905,969,664 bytes at DynamicVRAM acceptance, and 1,442,840,576 bytes when H2D began. The source was incomplete at H2D start; the remaining source read overlapped H2D. Median H2D-start → source-complete span was approximately 1.361 s.

The full backing reached 8,044,936,192 bytes in every QD2 run, with one source lifecycle and `read_calls=240`. The raw backing was released after H2D completion. The QD2 source was explicitly marked application-file-read provenance; physical syscall/E27 proof was not claimed.

Memory evidence showed `duplicate_full_size_cpu_copy=false`, no temporary full-size allocation reported, pinned transport allocation of 268,435,456 bytes, and page-fault counters unchanged at the recorded boundaries. cgroup/current memory was unavailable; psutil host available/free memory was approximately 1.088 TB and is not treated as a container-limit proof.

## Audit locations

- Worktree: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`
- HEAD at validation: `be86e9393ac498bdbf5663deaf1b3c81a7958d6f` (worktree dirty; no commit created)
- Implementation: `comfymodal_runtime/golden_serial.py`, `comfymodal_runtime/modal_app.py`
- Control-plane: `config/v2/flag_registry.toml`, `tools/v2_control/golden_payload.py`, `tools/benchmark_v2_direct.py`, `tools/v2_control/cli.py`, `tools/v2_control/backend.py`, `tools/v2_control/experiment_evidence.py`, `tools/v2_control/fingerprints.py`, `tools/v2_control/provenance.py`, `tools/v2_control/validation.py`
- Tests: `tests/test_cpu_qd2_prefetch.py`, `tests/test_golden_cpu_qd2_control.py`
- Synthetic fixtures: `tests/test_cpu_qd2_prefetch.py` creates a synthetic safetensors payload; no production model fixture was modified.
- Diagnostic evidence: `EXPERIMENT_EVIDENCE_golden_p1_18f9bef82563436e_2026-09-06.md`
- Deep QD2 cohort evidence: `EXPERIMENT_EVIDENCE_golden_p1_c107ccd6416e2dca_2026-09-06.md`
- Deep control cohort evidence: `EXPERIMENT_EVIDENCE_golden_p1_6c52b8529f84b52e_2026-09-06.md`
- No-deep QD2 cohort evidence: `EXPERIMENT_EVIDENCE_golden_p1_9d03c137be279e44_2026-09-06.md`
- Derived metrics: this report
- Raw cohort artifacts: `artifacts/phase_p1_serial_golden_v1/`
- Invocation-bound confirmation manifests: `.v2ctl/confirmations/confirm_20260906-214447_dac94fe2.json`, `.v2ctl/confirmations/confirm_20260906-213443_dd613bd2.json`, `.v2ctl/confirmations/confirm_20260906-220029_8dfbf427.json`

The evidence tables retain all five attempts per cohort, including slow/outlier attempts. The cohort index contains a `MISMATCH` classification label on several accepted rows despite exact observed SHA and empty failure lists; that raw inconsistency is retained rather than silently normalized.
