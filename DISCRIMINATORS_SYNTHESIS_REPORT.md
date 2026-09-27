# Three Discriminators — Final Synthesis

**Campaign:** CLIP × cold-Volume contention, `TESTING2 @ eebea83` (sampler-parity commit only; all experiment machinery reverted, baseline 22 passed).
**Prior established facts (not re-litigated):** 2 GiB cold reads under CLIP forward tax forward +0.3–1.7 s (full-file +1.3–4.0 s); CPU requests 4→8→16 do not attenuate (medians +351/+370/+532 ms); N0/M1/M2/F1 ladder arms all null; V1 hot reread ≈ +150 ms vs V2 cold ≈ +234–530 ms.
**First-Golden-parallel-run rule:** the first run of every app was excluded from every pair, summary, and interpretation in all three experiments (snapshot building). Excluded IDs are listed per experiment below; all were ELIGIBLE artifacts, preserved, never counted.

## Compact table (all rows ≥5 valid samples)

| Experiment | Control (n) | Treatment (n) | Δ (median) | Result | Strengthened | Weakened |
|---|---|---|---|---|---|---|
| Pinned H2D | H2D-only, 19.05 ms (5 runs) | H2D+cold, 19.09 ms (5 runs) | **+0.11 ms** (5 pairs; range −0.08…+0.50; GB/s ratio 0.994) | no effect | — | PCIe/H2D/interconnect-bandwidth contention |
| Eager CLIP (synthetic) | eager ~13.5 ms (6) | eager+cold (6) | **+1.50 ms** (range +0.94…+3.23) | small tax reproduces | host-launch sensitivity (on equivalent kernel work only) | — |
| CUDA-Graph CLIP (synthetic) | replay ~13.4 ms (6) | replay+cold (6) | **−0.01 ms** (range −0.65…+2.89) | tax vanishes | eager host/runtime submission path (attenuation ≈1.0 of the synthetic tax) | GPU-computation slowing (on equivalent work) |
| Thread reader | CLIP ctl (10) | threaded 2 GiB (5) | **+400.8 ms** (5/5 same sign; +258…+962) | reproduces full tax | — | — |
| Process reader | CLIP ctl (same 10) | spawn-process 2 GiB (5) | **+66.6 ms** (mixed sign; −177…+125; exit 0, startup 7–14 ms pre-window) | ~334 ms attenuation | process-local mechanism | below-thread contention (VolumeFS/kernel/network/backend as sole explanation) |

Excluded first runs: Exp1 `a2033d6c3e18`, `989677a3a5e1` · Exp3 `8d8bf3c6cddd`, `a61c4548ad6f`, `f8724e5cc936` · Exp2 probe `f128bc591ddc` + 4 condition smokes `1ec6fdf5a68b/2eaa8c800b76/e9f22f69d6c6/b1fe1e4b6a01`. Zero invalid runs in Exp1/Exp3; zero replacements needed. Pairing: temporal adjacency (A1B1/B2A2…; Exp3 rotating C-T-C-MP with preceding-control pairing). No region/provider use anywhere (locations recorded only; mixed us-east1/4/5, central1, west1/4, europe-west4).

## Exp2 limitation (stated plainly)

Real-CLIP capture was **not achieved**: resolution to `session.clip_compute_scope` works, but the steady-state probe input raises `RuntimeError` in eager warmup (`failing_op=null`), so neither full nor fallback capture executed. GRAPH-as-specified is unmeasured on CLIP. The synthetic fallback (pure-torch bf16 transformer-like stack, SDPA, fixed shapes) ran at ~14 ms not the designed ~1.2 s (iron delivers ~140+ effective TFLOPS vs the assumed 1.6) — it proves host-launch sensitivity of equivalent-GPU-kernel work at millisecond windows, NOT of CLIP's 1.5 s forward (no tokenization, Qwen weights, SageAttention, or runner). Attenuation ≈1.0 must be read with that scope plus the small-denominator uncertainty (eager spread +0.94…+3.23, graph −0.65…+2.89).

## Answers

1. **Does cold Volume slow actual CUDA H2D?** No — +0.11 ms on 19 ms (0.6%), GB/s ratio 0.994, n=5 pairs. Generic interconnect-bandwidth contention is strongly weakened.
2. **Does removing host launch dependence attenuate the CLIP tax?** On equivalent kernel work, fully (≈1.0 attenuation, n=6/mode). On CLIP itself, untested — capture blocked. Eager-launch sensitivity is supported; CLIP-graph attenuation is not yet demonstrated.
3. **Does process isolation attenuate the tax?** Yes — median +401 ms → +67 ms (~334 ms, ~83% attenuation), n=5/mode, exit-0 spawn children, startup isolated pre-window. Without calling it GIL: the interference is process-local.
4. **What remains plausible?** In-process eager host/runtime submission latency or serialization during cold reads (launch-path stalls, runtime locking/allocator interaction, page-fault/copy activity inside the process); synchronization or runtime behavior in real CLIP outside any captured region; VolumeFS per-byte servicing costs as *felt inside* the process (page-cache insertion, FUSE roundtrip handling) rather than as backend slowness.
5. **Best-supported explanation (not "confirmed"):** cold Volume servicing interferes with the in-process eager host/runtime CUDA submission path — Exp3's process attenuation + Exp2-synthetic's graph attenuation + Exp1's interconnect exoneration + the flat CPU-scaling curve converge on it from four sides. No single experiment confirms it alone.
6. **Actionable production optimization today?** No validated one. Two concrete, untested follow-ups: (a) process-isolated (spawn) UNET prefetch during forward — Exp3 predicts ~80% of the CLIP tax disappears, which could flip the previously-negative net; needs its own A/B with the sampler-parity baseline; (b) real-CLIP CUDA-graph capture (fix warmup input, re-probe) — synthetic evidence justifies the attempt, not the conclusion. Do not ship either without measurement.

## Audit handoff

- Worktree: `ComfyUI/custom_nodes/comfyui-modal`, branch `TESTING2`, HEAD `eebea83` (sampler commit only). Zero experimental commits (all lanes uncommitted; reverted and verified: 4 files restored, 5+2 modules + 2 test files deleted, Serial/profile empty, baseline 22 passed).
- Reports: `CAMPAIGN_REPORT_CLIP_FORWARD_CONTENTION.md` (ladder campaign) + this file. Raw evidence: ~150 `EXPERIMENT_EVIDENCE_*.md` at root.
- Exp1: deploys `6393b5f4`/`35fc0e28` (gen `46c47c48`), 12 manifests `.v2ctl/runs/run_20260911-07*.json`, cohorts `artifacts/phase_p1_parallel_golden_v1/cohort_2026-09-11_12-*.`
- Exp3: deploys `bc7706a7`/`4051c4d3`/`70e1b7a8` (gen `46c47c48`), 23 manifests `run_20260911-07/08*.json`, cohorts `..._12-*/13-*.`
- Exp2: probe deploy `f5884023`, probe run `run_20260911-091651_9af87f1c.json` (req `f128bc591ddc`, cohort `..._14-15-05_2ca7da`); 28 trial manifests + cohorts `..._14-*/`; machine ledgers + tabulators in `C:\Users\parla\AppData\Local\Temp\opencode\` (`x2b_ledger.json`, `x2b_ledger_g.json`, `summarize_attempt.py`, `build_ledger.py`) — NOTE: outside the repo; copy into durable storage if audit requires it.
- Deployment receipts: `.v2ctl/deployments/` per fingerprint above. Excluded-first-run IDs: listed in the table section; every reported delta recomputable from the listed manifests/cohorts without trusting this summary.
