# V2 Variance-Cold A/B Report

Generated from the confirmed cold-run artifacts on 2026-08-05.

## Scope

- **A — disabled:** `COMFYMODAL_V2_VARIANCE_DIAGNOSTICS=0`, `COMFYMODAL_V2_UNET_PRETOUCH=0`
- **B — enabled:** `COMFYMODAL_V2_VARIANCE_DIAGNOSTICS=1`, `COMFYMODAL_V2_UNET_PRETOUCH=1`
- Modal app: `stable-modal-comfy-v2-variance-shadow`
- Workspace: `Testing5`
- GPU: `rtx-pro-6000`
- Gap: 25 seconds
- Statistics below use only artifacts with `cold=true` and `cold_valid=true`.
- Missing metrics remain `unavailable` and are excluded; they are never treated as zero.

## Completeness and provenance

| Condition | Artifact source | Records | Valid cold | Excluded failures |
|---|---|---:|---:|---:|
| A / disabled | `../../comfymodal-data/benchmarks/runs/v2_2026-08-05_19-11-53` | 5 | **5** | 0 |
| B / enabled | `../../comfymodal-data/benchmarks/runs/v2_2026-08-05_19-17-25` plus `v2_2026-08-05_19-21-40` | 7 | **5** | 2 |

The two excluded B records failed before a valid remote cold identity was
established with:
`unsupported_unet_shape`.
They are retained in the raw artifact directories and are not relabeled as
cold or included in the timing statistics.

Valid B run IDs:

- `variance-cold-p1-1-e1f37c61`
- `variance-cold-p1-2-a5d35c93`
- `variance-cold-p1-3-901e2425`
- `variance-cold-p1-4-54774948`
- `variance-cold-p1-1-e974ea82`

All ten included records reported the intended app name and distinct
request/container identity. Each passed the request-scoped cold invariant
(`restore_count == 1`, `request_count == 1`, and a non-empty restored instance
identity).

## Overall timing

Values are milliseconds. Delta is `(B - A) / A`.

| Metric | A median | B median | Delta | A p90 | B p90 |
|---|---:|---:|---:|---:|---:|
| Wall time | 21,743.400 | 18,286.300 | **-15.9%** | 133,704.500 | 79,520.700 |
| `t3b_to_t8` bookkeeping | 11,478.174 | 8,024.582 | **-30.1%** | 21,919.282 | 8,727.542 |
| Restore total | 896.558 | 1,373.356 | **+53.2%** | 2,457.030 | 4,291.832 |
| Snapshot restore | 867.710 | 1,262.520 | **+45.5%** | 2,386.980 | 3,434.830 |
| UNET demand → first forward | 143.707 | 121.622 | **-15.4%** | 1,065.117 | 143.449 |
| CPU page traversal | 0.779 | 2.981 | **+282.7%** | 1.147 | 3.465 |
| CPU → GPU transfer | 2.391 | 2.194 | **-8.2%** | 978.409 | 3.731 |
| Variance process CPU | 21,730.000 | 22,440.000 | **+3.3%** | 22,510.000 | 26,430.000 |
| Sampler activation wait | 145.288 | 123.186 | **-15.2%** | 1,066.958 | 145.209 |
| Sampling | 3,695.354 | 3,688.962 | **-0.2%** | 3,715.850 | 3,706.522 |
| Sampler wall | 4,935.013 | 4,887.157 | **-1.0%** | 5,196.029 | 5,035.370 |

With the default slow-run threshold of twice each condition's median wall
time, A had **1/5** slow runs above `43,486.800 ms`; B had **1/5** above
`36,572.600 ms`.

## Pretouch and diagnostic observations

- B pretouch effect: median **1.565 ms**, p90 **1.757 ms**.
- A pretouch effect: unavailable, as expected with the feature disabled.
- CPU page traversal instrumentation is present in B and adds a small measured
  local interval, but the absolute median is only **2.981 ms**.
- Page-fault counts, traversal bytes, and effective GB/s were unavailable in
  these artifacts; no page-fault or bandwidth conclusion is made from them.

## Interpretation

The enabled bundle reduced median wall time by **3,457.100 ms** and reduced
the median `t3b_to_t8` interval by **3,453.592 ms**. It also reduced the
UNET demand-to-first-forward and sampler activation-wait medians by about
15%. Sampling itself was effectively unchanged.

The same bundle increased measured restore time substantially. Therefore the
result is not evidence that every stage improved: the observed end-to-end
benefit is dominated by the bookkeeping/activation-side reduction and partly
offset by slower restore. Because diagnostics and pretouch were enabled
together, this run does **not** isolate which flag caused each change.

### Best-supported next step

Run a second controlled matrix with the same cold protocol and four conditions:

1. both flags disabled;
2. diagnostics only;
3. pretouch only;
4. both flags enabled.

Keep the current cold-identity assertions and collect at least five valid cold
runs per cell. The first priority is explaining the B restore increase before
making the enabled bundle the default.

## Verification performed

- Aggregated with `tools/variance_report.py` over the raw `run_*.json` files.
- Confirmed 5 valid cold A records and 5 valid cold B records.
- Confirmed invalid B startup records were excluded rather than counted as
  cold.
- Variance unit tests and Python compilation passed earlier in this run.
- The combined registration test command still has 7 failures and 1 import
  error because the current `modal_app.py` does not contain the separate
  publisher-marker registration expected by that test; those changes are
  outside this variance report and were not altered here.
