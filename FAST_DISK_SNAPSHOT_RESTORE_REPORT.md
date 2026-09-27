# FAST-DISK SNAPSHOT RESTORE REPORT

Authoritative source: `comfymodal-data/benchmarks/runs/restore_only_2026-08-11_20-27-45/`
(`backfilled_summary.json`, `backfilled_run_0.json` … `backfilled_run_5.json`).
Mode: `snapshot_restore_only_backfill` — six selected reused-snapshot restore-only probes
(UNET-absent, clip_vae eviction retain). All figures below were independently re-derived
from the artifacts.

---

# Executive conclusion

The six selected restored-snapshot probes are valid: every probe restored from the same
snapshot identity
`5650749f8b24244f9c20976b55000470835daf23b6a34f108c29248325e60d60` on GCP/us-east4,
RTX PRO 6000, 12 CPU / 32768 MiB, with distinct restored instance IDs and
`restore_count = request_count = 1`. Post-restore state is exactly the designed
UNET-absent footprint: `unet_present=0`, no retained/reconstructed UNET payload,
container present but inactive, CLIP and VAE retained, and no graph/UNET-load/VAE-decode/
Volume-read work performed by any probe.

Against the FULL-snapshot reference, the FAST-DISK UNET-absent design did **not**
materially improve the Modal pre-Python restore segment (every distribution point is
worse), but it did improve Python restore at median and max, and it reduced the restored
RSS to ~12.826 GiB (about 8.2–10.2 GiB below the 21–23 GiB FULL reference). Because the
comparison is cross-experiment and the FULL reference's provider/region mix is
unavailable, **no causal attribution is claimed** for the timing deltas; only the
post-restore invariants and footprint are directly attributable to the snapshot design.

A protocol deviation is disclosed: the original harness issued 30 cold candidates
(because the default log source hid the platform banner); after the INFO/system-log
retrieval fix, attempts 0–5 were backfilled and selected with exact task-ID-correlated
banners. The report therefore describes the first six probes, not an operationally clean
six-valid hard stop.

# Snapshot validity

Each selected probe's post-restore invariants (identical for all six runs, taken directly
from each `backfilled_run_<n>.json` `result.invariant` / top-level flags):

| Run | unet_present | retained_unet_payload | reconstructed_unet_present | retained runtime UNET state | retained eviction model | container present | container active | clip | vae | retain role | graph_executed | unet_loaded | vae_decoded | volume_read |
|----:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | clip_vae | false | false | false | false |
| 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | clip_vae | false | false | false | false |
| 2 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | clip_vae | false | false | false | false |
| 3 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | clip_vae | false | false | false | false |
| 4 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | clip_vae | false | false | false | false |
| 5 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | clip_vae | false | false | false | false |

All six probes satisfy every validity rule: UNET absent with no retained or reconstructed
payload, `cpu_snapshot_models_present=1` and `cpu_snapshot_models_active=0`,
`container_retained=1`, `clip_present=1`, `vae_present=1`, snapshot identity nonempty,
placement (cloud/region/gpu) present, `restore_count=request_count=1`, a nonempty fresh
`restored_instance_id`, the container-observed Python-resume/restore-start/restore-end/
total timestamps, method-entry timestamp, RSS, locally captured dispatch timestamp, and a
directly observed Modal pre-Python `Restoring Function from memory snapshot.` system
banner within `dispatch <= banner <= python-resume`.

**Intended lifecycle.** Startup builds the full CLIP/UNET/VAE CPU snapshot normally
(`load_cpu_snapshot_models` with UNET BF16/diffusion-model validation); the strict
`clip_vae` eviction retain role then evicts the UNET and reloads fresh CLIP/VAE into the
retained `CpuSnapshotModels` container before capture
(`COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1`, `COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae`).
Honest limitation: the local deploy output did **not** preserve the snapshot-construction
log lines that prove the original UNET weakref-dead check ran pre-capture. The
post-restore invariants directly prove the captured state (no UNET object, no retained or
reconstructed payload, container retained with CLIP/VAE); the pre-capture eviction
mechanism itself is code/config evidence rather than directly observed log evidence.

**Protocol deviation disclosure (neutral).** The original harness issued 30 cold
candidates because the default log source never surfaced the Modal system/INFO platform
banner, so every candidate was marked invalid and the bounded attempt cap was consumed.
After fixing INFO/system log retrieval, attempts 0–5 were backfilled and selected using
exact task-ID-correlated direct banners (`pair_status=paired_task_scoped`,
`correlation=<container_task_id>`, one exact system banner each, distinct timestamps, in
bounds). Attempts 6–29 are instrumentation overrun: they were issued only because the
log-source bug marked candidates invalid; they are excluded and were never substituted for
the first six. No additional restore probes were launched after diagnosis. This report
does **not** claim the six-valid hard stop worked operationally — the distribution is
bounded to the first six probes, but 24 excess requests occurred.

# Probe table

Per-run intervals, in **seconds** (3 decimals), from `backfilled_summary.json` runs
(`dispatch_to_banner_ms`, `pre_python_restore_ms`, `python_restore_total_ms`,
computed restore-end→method, `dispatch_to_method_entry_ms`). Restore→method is
restore END → method entry, not resume→entry. Restored RSS is the probe-observed
`status_vmrss_mib` (~12.826 GiB).

| Run | Cloud | Region | Restored RSS | Dispatch→restore | Modal pre-Python restore | Python restore | Restore→method | Dispatch→method |
|----:|:-----:|:------:|------------:|-----------------:|-------------------------:|---------------:|---------------:|----------------:|
| 0 | GCP | us-east4 | 13133.76 MiB | 91.106 | 6.495 | 0.611 | 0.031 | 98.242 |
| 1 | GCP | us-east4 | 13133.76 MiB | 56.415 | 9.754 | 2.674 | 0.165 | 69.008 |
| 2 | GCP | us-east4 | 13133.76 MiB | 111.173 | 6.485 | 0.721 | 0.015 | 118.395 |
| 3 | GCP | us-east4 | 13133.76 MiB | 81.641 | 6.328 | 0.466 | 0.123 | 88.558 |
| 4 | GCP | us-east4 | 13133.75 MiB | 5.197 | 5.448 | 0.607 | 0.073 | 11.325 |
| 5 | GCP | us-east4 | 13133.76 MiB | 3.637 | 6.480 | 0.626 | 0.101 | 10.844 |

All six runs: RTX PRO 6000, 12 CPU, 32768 MiB, snapshot identity
`5650749f8b24244f…e60d60`, `restore_count=request_count=1`.

## Per-probe identity / timestamp evidence

Epoch values sourced from artifacts; timestamps in epoch **ms** (ns values converted by
`ns / 1e6`). Instance/task IDs truncated for display; full 32-char instance IDs and full
task IDs are recorded in each `backfilled_run_<n>.json`.

| Run | restored instance ID (short) | container task ID (short) | snapshot ID (short) | dispatch ms | banner ms | first Python/resume ms | restore end ms | method entry ms | GPU / CPU / MiB |
|----:|:---|:---|:---|----------:|----------:|----------:|----------:|----------:|:---|
| 0 | ec9f3b5364fd | ta-01KZS85Q6… | 5650749f8b24 | 1786480066308 | 1786480157413.946 | 1786480163908.991 | 1786480164536.418 | 1786480164550.497 | rtx-pro-6000 / 12 / 32768 |
| 1 | 364d2e766006 | ta-01KZS8B49… | 5650749f8b24 | 1786480212549 | 1786480268963.550 | 1786480278717.422 | 1786480281545.693 | 1786480281556.712 | rtx-pro-6000 / 12 / 32768 |
| 2 | 426ebf5376af | ta-01KZS8GAV… | 5650749f8b24 | 1786480328974 | 1786480440147.110 | 1786480446632.513 | 1786480447356.803 | 1786480447369.218 | rtx-pro-6000 / 12 / 32768 |
| 3 | e6f899ceeb86 | ta-01KZS8MGS… | 5650749f8b24 | 1786480495346 | 1786480576987.452 | 1786480583315.242 | 1786480583893.797 | 1786480583903.768 | rtx-pro-6000 / 12 / 32768 |
| 4 | 43f56f678c84 | ta-01KZS8PBD… | 5650749f8b24 | 1786480631652 | 1786480636849.076 | 1786480642296.898 | 1786480642965.410 | 1786480642976.954 | rtx-pro-6000 / 12 / 32768 |
| 5 | 91ad06f53588 | ta-01KZS8R2K… | 5650749f8b24 | 1786480690171 | 1786480693808.345 | 1786480700288.330 | 1786480701003.416 | 1786480701015.255 | rtx-pro-6000 / 12 / 32768 |

Notes: first Python = restore start (`remote_python_resume_wall_unix_ns` ==
`restore_method_start_wall_unix_ns`). All six banners were paired
task-ID-correlated (`paired_task_scoped`, `anchor_found=false`; the stdout anchor line
was not retained historically). RSS `status_vmrss_mib` = 13133.76 for runs 0–3,5 and
13133.75 for run 4; cgroup current 13592.96 MiB is secondary; smaps rollup unavailable
(`source=unavailable`).

# Distribution

Single-cohort selected set (all GCP/us-east4), min / median / max in seconds:

| Interval | min | median | max |
|:--|--:|--:|--:|
| Modal pre-Python restore (banner→Python resume) | 5.448 | 6.480 | 9.754 |
| Python restore (container-reported total) | 0.466 | 0.611 | 2.674 |
| Restore end→method entry | 0.015 | 0.087 | 0.165 |
| Dispatch→method entry | 10.844 | 69.008 | 118.395 |

Because all six selected probes are one cohort (GCP/us-east4, RTX PRO 6000, 12 CPU,
32768 MiB), the cohort statistics are identical to the overall statistics; there is **no
multi-region selected cohort** in this set, so no cross-cohort comparison is possible
from this experiment alone.

# Comparison to FULL snapshot

FULL-snapshot reference (provided by USER): Modal pre-Python 1.9 / 4.7 / 7.4 s; Python
restore 0.48 / 1.33 / 3.81 s (min / median / max); restored RSS 21–23 GiB.

| Metric | FULL reference min / med / max | FAST-DISK UNET-absent min / med / max | Delta (min / med / max) |
|:--|--:|--:|--:|
| Modal pre-Python restore | 1.9 / 4.7 / 7.4 s | 5.448 / 6.480 / 9.754 s | +3.548 / +1.780 / +2.354 s |
| Python restore | 0.48 / 1.33 / 3.81 s | 0.466 / 0.611 / 2.674 s | −0.014 / −0.719 / −1.136 s |
| Restored RSS | 21–23 GiB | ~12.826 GiB | ≈ −8.2 to −10.2 GiB |

- **Pre-Python did NOT materially improve**: every distribution point is worse than the
  FULL reference. This comparison is cross-experiment, and the FULL reference's
  provider/region mix is unavailable, so **no causal attribution** is made.
- **Python restore improved at median (~54% lower**: 0.611 vs 1.33) and at max (~30%
  lower: 2.674 vs 3.81); min is effectively unchanged / slightly lower (0.466 vs 0.48).
- **RSS shows a material footprint reduction** (~8.2–10.2 GiB lower, 21–23 GiB → 12.826
  GiB), consistent with the UNET-absent clip_vae-evicted snapshot design.
- Dispatch is scheduling-dominated and highly variable; provider/region effects cannot be
  estimated within the selected six because all runs are the same cohort. This report does
  not claim any provider/region effect larger than the composition; the provider/region
  component is **unknown/uncontrolled**.

# Interpretation

Direct answers to the five experiment questions:

1. **Did the FAST-DISK UNET-absent snapshot materially improve the Modal pre-Python restore?**
   No. Every distribution point is worse than the FULL reference (min 5.448 vs 1.9,
   median 6.480 vs 4.7, max 9.754 vs 7.4 s). Because the FULL comparison is
   cross-experiment with an unavailable provider/region mix, this is not attributable to
   the snapshot design — it is simply "no observed improvement."

2. **Did it improve the Python restore time?**
   Yes at median and max: 0.611 vs 1.33 s (≈54% lower) and 2.674 vs 3.81 s (≈30% lower).
   The minimum is effectively unchanged (0.466 vs 0.48 s). This is the strongest
   positive timing signal, but remains a cross-experiment comparison.

3. **Does restored RSS correlate with either restore interval?**
   ~12.826 GiB (VmRSS 13133.75–13133.76 MiB; cgroup current 13592.96 MiB as secondary;
   smaps unavailable). That is ~8.2–10.2 GiB below the 21–23 GiB FULL reference — a
   material, directly attributable footprint reduction consistent with the UNET-absent
   snapshot. Within these six probes RSS is effectively constant, so it cannot explain
   either timing's variance. Across the two experiments, lower RSS coincides with faster
   median Python restore but slower Modal pre-Python restore; that aggregate contrast is
   not enough to establish correlation.

4. **Are provider/region effects visible?**
   Unknown/uncontrolled. All six selected runs are a single GCP/us-east4 cohort, so no
   provider/region effect can be estimated within this selection, and the report makes no
   claim beyond composition. Dispatch→method is scheduling-dominated and highly variable
   (10.8–118.4 s), which dominates the total and should not be read as a restore metric.

5. **Is the result causal?**
   No. The pre-Python/Python timing deltas are cross-experiment; the FULL reference's
   provider/region mix is unavailable; and the UNET-absent arm's first-six distribution is
   confounded by scheduling variance. Only the post-restore invariants (UNET absent, no
   retained/reconstructed payload, CLIP/VAE present, no graph work) and the footprint are
   directly attributable to the snapshot design.

# Recommended next action

- Run a bounded **six-probe FULL-snapshot restore-only control** using the fixed
  system-log harness (task-ID-correlated INFO banner pairing), the same unpinned
  placement policy and the same resource shape (RTX PRO 6000, 12 CPU, 32768 MiB), then
  compare only the overlapping provider/region cohorts against this FAST-DISK UNET-absent
  set. Recommendation only — do not run here.
