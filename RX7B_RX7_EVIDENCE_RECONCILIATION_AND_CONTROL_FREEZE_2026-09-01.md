# RX7B RX7 Evidence Reconciliation and Control Freeze

Date: 2026-09-01  
Canonical repository: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`  
Canonical branch: `TESTING2`

## 1. Scope, method, and evidence custody

This is a repository-and-history reconciliation of the RX7 E27 dispatcher
control versus static E27 comparison. It does not rerun Modal, reconstruct
missing JSON, or infer fields from a summary. The evidence custody boundary is
the canonical `TESTING2` checkout, its Git history, the surviving reports, the
current implementation, and the profile/registry sources cited below.

The requested raw artifacts are absent from the canonical checkout and Git
history:

- `.v2ctl/confirmations/confirm_20260901-170959_b561647c.json`
- `.v2ctl/confirmations/confirm_20260901-171335_a6d4f18b.json`
- all twelve RX7 cohort directories listed by the aggregate report under
  `artifacts/phase_p1_serial_golden_v1/`
- RX7 deployment receipts/manifests under `.v2ctl/deployments/`

The artifact and deployment directories themselves contain older unrelated
material, but not the requested RX7 objects. Only the aggregate RX7 A/B report
survives as RX7 measurement evidence. This prevents independent per-run proof
and reproduction. No missing field is fabricated here.

## 2. Evidence inventory

### Present evidence

| Evidence | Status and use |
|---|---|
| `RX7_E27_CONTIGUOUS_QD4_SOURCE_SCHEDULING_AB_REPORT_2026-09-01.md:8-19` | Present aggregate verdict and its explicit limitation: accepted comparison arm, not direct source-bandwidth/QD-occupancy proof. |
| `RX7_E27_CONTIGUOUS_QD4_SOURCE_SCHEDULING_AB_REPORT_2026-09-01.md:21-38` | Present frozen identity, profile, provider/backend label, workflow/output/publisher identities, and deployment fingerprints. |
| `RX7_E27_CONTIGUOUS_QD4_SOURCE_SCHEDULING_AB_REPORT_2026-09-01.md:42-45` | Present aggregate validity claim for twelve runs; not a surviving per-run artifact. |
| `RX7_E27_CONTIGUOUS_QD4_SOURCE_SCHEDULING_AB_REPORT_2026-09-01.md:48-68` | Present reported total walls, summary statistics, and selected stage medians. |
| `RX7_E27_CONTIGUOUS_QD4_SOURCE_SCHEDULING_AB_REPORT_2026-09-01.md:70-86` | Present report narrative for static partition/read/reconciliation claims and its missing source-QD fields. |
| `RX7_E27_CONTIGUOUS_QD4_SOURCE_SCHEDULING_AB_REPORT_2026-09-01.md:88-114` | Present artifact names and cohort names as references, not as surviving files. |
| `comfymodal_runtime/golden_qd_transport.py:80-95,261-304,1642-1737,2088-2141` | Present static-region planning, producer lease safety, contiguous block-clamped record splitting with unique IDs, exact coverage/H2D reconciliation, poison handling, and quiescence checks. |
| `comfymodal_runtime/golden_serial.py:3038-3261,3288-3300,3518-3568` | Present static arm validation, fixed QD4/32 MiB constraints, direct positioned per-producer reads, static work planning, record/H2D reconciliation, quiescence, ownership, and fail-closed evidence fields. |
| `RX7A_STATIC_E27_INTEGRATION_REPORT_2026-09-01.md:3-8,10-18,22-45` | Present accepted integration result, focused verification, and explicit mechanism-unproven status. |
| `RX7A_RX6B_AND_STATIC_E27_CANONICAL_INTEGRATION_REPORT_2026-09-01.md:30-35,46-68,70-84` | Present canonical wiring/contract and the statement that no RX8 behavior was introduced. |
| `E36_FULL_CRITICAL_PATH_REPORT.md:182-210` | Present valid QD4 source evidence and a variance-based historical interpretation; not an RX7 per-run artifact. |
| `OC2_CLIP_LOAD_TIMING_COMPLETENESS_2026-08-25.md:145-151` | Present correction that approximately 1385.929 ms was retained-model CLIPTextEncode/conditioning, not cold CLIP weight load. |
| `COMFYUI_MODAL_V2_AUG9_RESOURCE_GPU_OPTIMIZATION_REPORT.md:140-160` | Present historical restore/resource comparison; its approximately 1.381 s figure is restore median, not equivalent cold CLIP/UNET load. |
| `C8_BENCHMARK_REPORT.md:25-40` | Present documented clean production baseline of CPU 16 and memory 49152 MiB. |
| `config/v2/flag_registry.toml:196-214,672-679,882-900` | Present registry defaults: stage diagnostics 0, cast-once 0, legacy transport, and static E27 registered as opt-in. |

### Absent evidence

| Requested object | Status |
|---|---|
| `.v2ctl/confirmations/confirm_20260901-170959_b561647c.json` | ABSENT from canonical checkout and Git history. |
| `.v2ctl/confirmations/confirm_20260901-171335_a6d4f18b.json` | ABSENT from canonical checkout and Git history. |
| `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-06-15_5af272` | ABSENT. |
| `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-06-47_5b0588` | ABSENT. |
| `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-08-03_9d7245` | ABSENT. |
| `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-08-42_13d865` | ABSENT. |
| `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-09-07_3d012c` | ABSENT. |
| `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-09-35_5d96be` | ABSENT. |
| `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-10-34_0b5ea0` | ABSENT. |
| `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-10-58_c94483` | ABSENT. |
| `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-11-19_d98b45` | ABSENT. |
| `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-11-54_d1ac6e` | ABSENT. |
| `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-12-20_c9fc2a` | ABSENT. |
| `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-01_17-12-42_280411` | ABSENT. |
| RX7 deployment receipt/manifest objects under `.v2ctl/deployments/` | No RX7-specific receipt or manifest survives there. Existing files are from other deployments. |

### What the aggregate report says, and what it does not say

The report identifies profile `golden_p1`, GPU `rtx-pro-6000`, explicit
backend/provider label `pytorch`, workflow SHA
`14f815f1916e075ae79de7325681f6b0ec2216b8ad86c45e9bfa18f6388f5ea9`, expected
output SHA
`8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`, publisher
generation
`2853bea2379ad48b85b54f9d10ae01677bded3191b0a85bd53cbd246eb47ebe2`, and
deployments:

- control `rx7-e27-control`, fingerprint
  `165997db2bd87600615524c122865b3bab06202dc0fc0dd0cb9ef5937c9cf2ae`
- static `rx7-e27-static`, fingerprint
  `6f1a32acd2d42150c117ace4e2203867fad5023fedf76bc64579b15b1fcaa2c3`

Those identities are report claims, not independently recoverable deployment
receipts. The report claims all twelve runs were valid/exact, zero DNF, zero
fallback, and serial; those claims cannot be independently checked per run
without the absent artifacts. It does not state CPU, RAM, region, CLI
overrides, per-run cast-once, complete stage walls, complete
`FIRST_RESULT_READY`, per-run output SHA, per-run durability, or per-run
fallback/poison/seriality evidence. Source-QD occupancy and source-wall are
explicitly null.

The surviving report supplies one `Workflow SHA`, but does not distinguish an
outer workflow hash from the actual Golden workflow/prompt SHA. The value is
therefore retained as a report-level workflow identity only; no separate
outer-workflow or prompt hash is promoted to per-run proof. Likewise, the
profile name is reported as `golden_p1`, but no surviving artifact contains the
fully resolved profile values for any individual run.

## 3. Twelve-row run reconciliation

The following total walls are copied from the aggregate report and are labeled
**aggregate-report-only**. They are not independently verified. Rows 1–6 are
the control values and rows 7–12 are the static values from
`RX7_E27_CONTIGUOUS_QD4_SOURCE_SCHEDULING_AB_REPORT_2026-09-01.md:46-51`.

### Known report identity and timing fields

| Run | Arm / report row | Deployment / fingerprint | Profile; GPU; backend/provider | Workflow SHA; expected output SHA; publisher generation | Reported total wall (ms) |
|---:|---|---|---|---|---:|
| 1 | Dispatcher control / 1 | `rx7-e27-control` / `165997db2bd87600615524c122865b3bab06202dc0fc0dd0cb9ef5937c9cf2ae` | `golden_p1`; `rtx-pro-6000`; `pytorch` | `14f815f1916e075ae79de7325681f6b0ec2216b8ad86c45e9bfa18f6388f5ea9`; `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`; `2853bea2379ad48b85b54f9d10ae01677bded3191b0a85bd53cbd246eb47ebe2` | **29311.277** |
| 2 | Dispatcher control / 2 | same as run 1 | same as run 1 | same as run 1 | **74754.025** |
| 3 | Dispatcher control / 3 | same as run 1 | same as run 1 | same as run 1 | **36579.626** |
| 4 | Dispatcher control / 4 | same as run 1 | same as run 1 | same as run 1 | **23822.577** |
| 5 | Dispatcher control / 5 | same as run 1 | same as run 1 | same as run 1 | **25659.068** |
| 6 | Dispatcher control / 6 | same as run 1 | same as run 1 | same as run 1 | **24006.175** |
| 7 | Static E27 / 7 | `rx7-e27-static` / `6f1a32acd2d42150c117ace4e2203867fad5023fedf76bc64579b15b1fcaa2c3` | `golden_p1`; `rtx-pro-6000`; `pytorch` | same report identities as run 1 | **20204.488** |
| 8 | Static E27 / 8 | same as run 7 | same as run 7 | same as run 1 | **19806.117** |
| 9 | Static E27 / 9 | same as run 7 | same as run 7 | same as run 1 | **32825.490** |
| 10 | Static E27 / 10 | same as run 7 | same as run 7 | same as run 1 | **23551.067** |
| 11 | Static E27 / 11 | same as run 7 | same as run 7 | same as run 1 | **20204.805** |
| 12 | Static E27 / 12 | same as run 7 | same as run 7 | same as run 1 | **52563.720** |

Aggregate-only summary from the same report: control mean/median/min/max/range/
sample SD/CV = `35688.791 / 27485.173 / 23822.577 / 74754.025 /
50931.448 / 19725.337 / 0.553`; static = `28192.615 / 21877.936 /
19806.117 / 52563.720 / 32757.603 / 12922.127 / 0.458` ms or unitless CV.
The report's selected stage medians, also arm-level aggregate values rather
than per-run evidence, are:

| Stage | Control median (ms) | Static E27 median (ms) |
|---|---:|---:|
| `golden_clip_load` | 1862.709 | 1623.743 |
| `golden_clip_forward` | 1676.857 | 1910.512 |
| `golden_unet_load` | 2098.561 | 1960.827 |
| `golden_vae_load` | 184.243 | 107.137 |
| `golden_sampling` | 5964.291 | 5895.927 |
| `golden_output` | 177.820 | 162.689 |

### Required per-run dimensions not recoverable from surviving evidence

`UNKNOWN / not independently verifiable` is intentional in every cell below.
The report's aggregate statement is retained separately and is not promoted to
per-run proof.

| Run | QD arm | Fully resolved profile values |
|---:|---|---|
| 1 | `dispatcher` (report arm label only) | UNKNOWN / not independently verifiable |
| 2 | `dispatcher` (report arm label only) | UNKNOWN / not independently verifiable |
| 3 | `dispatcher` (report arm label only) | UNKNOWN / not independently verifiable |
| 4 | `dispatcher` (report arm label only) | UNKNOWN / not independently verifiable |
| 5 | `dispatcher` (report arm label only) | UNKNOWN / not independently verifiable |
| 6 | `dispatcher` (report arm label only) | UNKNOWN / not independently verifiable |
| 7 | `static_e27` (report arm label only) | UNKNOWN / not independently verifiable |
| 8 | `static_e27` (report arm label only) | UNKNOWN / not independently verifiable |
| 9 | `static_e27` (report arm label only) | UNKNOWN / not independently verifiable |
| 10 | `static_e27` (report arm label only) | UNKNOWN / not independently verifiable |
| 11 | `static_e27` (report arm label only) | UNKNOWN / not independently verifiable |
| 12 | `static_e27` (report arm label only) | UNKNOWN / not independently verifiable |

| Run | CPU | RAM | Region | Outer workflow hash | Actual prompt SHA if distinct | CLI overrides | Cast-once | Diagnostics | Durability | Complete CLIP load | Complete UNET load | Complete Golden wall / `FIRST_RESULT_READY` | Observed output SHA | Per-run fallback / poison / DNF / seriality |
|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable |
| 2 | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable |
| 3 | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable |
| 4 | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable |
| 5 | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable |
| 6 | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable |
| 7 | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable |
| 8 | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable |
| 9 | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable |
| 10 | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable |
| 11 | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable |
| 12 | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable | UNKNOWN / not independently verifiable |

The aggregate report says all twelve were valid, true-cold, single-request,
exact-output, zero-DNF, zero-fallback, and zero-seriality-violation at
`RX7_E27_CONTIGUOUS_QD4_SOURCE_SCHEDULING_AB_REPORT_2026-09-01.md:42-45`.
That remains a report-level claim only.

## 4. Direct answers

1. **What was the intended arm distinction?** Intended distinction was
   scheduling-only: dispatcher control versus static contiguous source
   scheduling. It was not strictly only a scheduling distinction at the
   implementation/observability level: static has explicit plan validation,
   producer wiring, positioned reads, reconciliation, ownership, quiescence,
   and diagnostics behavior. The implementation keeps model adoption and
   Golden stage boundaries shared, but the surviving evidence cannot establish
   that every observed run differed only in scheduling.

2. **What resources did RX7 actually use?** UNKNOWN. The contaminated profile
   that was present before this freeze (`gpu=rtx-pro-6000`, `cpu=8`,
   `memory_mb=8192`, `min_containers=0`, `scaledown_window=4`) is not proof of
   actual RX7 resources. The clean inherited production baseline documented by
   `C8_BENCHMARK_REPORT.md:25-40` is GPU RTX-PRO-6000, CPU 16, RAM 49152 MB,
   but that baseline must not be claimed as RX7's actual allocation.

3. **Can the intended clean serial control be proven?** No. The intended
   control semantics are clear from the profile and Golden Serial design, but
   the requested confirmations, twelve cohort directories, and RX7 deployment
   receipts/manifests are absent. The aggregate claim is insufficient for
   independent proof.

4. **Why was control slow?** Only observed variance, non-equivalent historical
   comparisons, and unknown RX7 configuration/environment can be attributed.
   `E36_FULL_CRITICAL_PATH_REPORT.md:189-210` supports variance in lifecycle,
   source, H2D-host, and pre-sampler portions. It is not valid to call this
   “Modal variance” as a proven singular cause. `OC2_CLIP_LOAD_TIMING_COMPLETENESS_2026-08-25.md:151`
   corrects the approximately 1385.929 ms value as retained-model
   CLIPTextEncode/conditioning rather than cold CLIP weight load, while
   `COMFYUI_MODAL_V2_AUG9_RESOURCE_GPU_OPTIMIZATION_REPORT.md:140-156`
   reports approximately 1.381 s restore median, not equivalent cold CLIP or
   UNET load. No single cause can be proved from the missing RX7 artifacts.

5. **Can the raw six control plus six static runs be reproduced?** No. The
   raw confirmations, all twelve listed cohort directories, and RX7-specific
   deployment receipts/manifests do not survive in canonical `TESTING2` or Git
   history.

6. **How should the result be classified?** RX7 A/B is **inconclusive** for an
   independently proven comparison. The static winner is **unproven**. The
   aggregate report may be retained as a historical report-only observation,
   not as a reproducible acceptance result.

7. **Should the integrated static E27 implementation remain?** Yes. The
   integrated implementation is valid and safe to keep as opt-in, with
   deterministic QD4/32 MiB static regions, exactly producers 0–3, direct
   positioned reads, unique split identities, reconciliation/quiescence/
   ownership checks, and fail-closed behavior. This is consistent with
   `RX7A_STATIC_E27_INTEGRATION_REPORT_2026-09-01.md:3-8,39-45` and
   `RX7A_RX6B_AND_STATIC_E27_CANONICAL_INTEGRATION_REPORT_2026-09-01.md:46-68`.
   It is not default and is not mechanism-proven.

8. **What is the exact clean `golden_p1` profile?** Inherited production
   resources: GPU `rtx-pro-6000`, CPU 16, RAM 49152 MB; `min_containers` and
   `scaledown_window` inherited; transport `legacy`; stage diagnostics 0;
   cast-once 0; deep profile `off`; dynamic VRAM 1; workflow hash check 1;
   runtime overrides forbidden; no CLI overrides. The profile now expresses
   the two clean zero values explicitly so resolution is unambiguous, while
   leaving registry and runtime source unchanged.

## 5. Contamination, restoration, and no-rerun decision

`git blame` on the pre-freeze profile showed the `[resources]` block at lines
15–20 and diagnostics/cast-once values at lines 56–57 as introduced by
`afe4d30`. `afe4d30^:config/v2/profiles/golden_p1.toml` had no resources block,
used legacy transport, and had no diagnostics/cast-once keys. The registry
defaults in `config/v2/flag_registry.toml:196-214,672-679` are diagnostics 0,
cast-once 0, and legacy transport.

The minimal clean-control restoration made in this lane is limited to
`config/v2/profiles/golden_p1.toml`:

- removed the contaminated explicit `[resources]` block, restoring inherited
  production resource resolution;
- retained `COMFYMODAL_GOLDEN_QD_TRANSPORT = "legacy"`;
- changed only the two contaminated explicit diagnostics/cast-once values to
  their clean registry defaults, `"0"` and `"0"`;
- preserved all unrelated profile fields, static E27 registration, and runtime
  source.

This change establishes the next control configuration; it does not
retroactively prove RX7's resources or execution. No Modal deployment or rerun
was performed during this evidence freeze. A remote rerun is required before
the RX7 comparison can be reclassified as independently valid, because the
actual per-run resources, resolved profile, execution boundaries, and terminal
evidence cannot be recovered from the surviving repository artifacts.

## 6. Conclusion and terminal values

The surviving RX7 report is useful as a bounded aggregate observation, but it
cannot support independent per-run validation or reproduction. RX7 A/B is
therefore inconclusive, and the static E27 winner is unproven. The static
implementation itself is suitable to retain as an opt-in, fail-closed path.
The canonical control profile has been restored to inherited production
resources, legacy transport, explicit diagnostics/cast-once zero, deep profile
off, dynamic VRAM enabled, and workflow hash checking enabled.

RX7_AB_VALID=INCONCLUSIVE
RX7_STATIC_IMPLEMENTATION_VALID=YES
STATIC_E27_CANONICAL_WINNER=UNPROVEN
RX7_ACTUAL_CPU=UNKNOWN (not present in surviving RX7 artifacts)
RX7_ACTUAL_RAM_MB=UNKNOWN (not present in surviving RX7 artifacts)
NEXT_QD_CONTROL=golden_p1: inherited production resources (RTX-PRO-6000, CPU 16, RAM 49152 MB), COMFYMODAL_GOLDEN_QD_TRANSPORT=legacy, COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=0, COMFYMODAL_V2_CLIP_FP32_CAST_ONCE=0, COMFYMODAL_SAMPLING_DEEP_PROFILE=off, COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=1, COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK=1, runtime overrides forbidden
REMOTE_RERUN_REQUIRED=YES
