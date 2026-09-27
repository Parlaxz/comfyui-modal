# Golden experiment history — 2026-09-09

## Canonical handoff

- Canonical comfyui-modal commit: `4421610c1a40794a2414d69f2f383880b100ffe5`
- Durable tag: `golden-canonical-2026-09-09`
- Winning DynamicVRAM-before-QD2 commit: `0ea9428636afe06adf3e6a05319898473ebdd64d`
- Accepted sampler health: approximately **4.65 s** (`4647.374 ms` mean)
- Exact output SHA: `790c3052a9b4a5ed01369e81cf79eac389f1d69b25578be3aa033e673570e89d`
- Accepted deployment fingerprint: `0a14fabb22fb63fbcdfd38e1a937fb95443170538a638b329b9f9fec96266232`
- Workflow SHA: `e44389ea2eda82ba5e2328acc08307b6879ed6d4ea4b030727ab044704c0d3b5`
- Stock RES4LYF remains owned by its normal checkout at
  `119679d8d8d26e6db52757e705488abb6399d7d4`; no RES4LYF change is canonical.

## Decisions retained

- DynamicVRAM activation stays before QD2 prefetch. The accepted five-run
  evidence showed activation return before backing allocation and removed the
  post-allocation delay from the pre-Golden critical path.
- Lazy QD2 mmap backing was rejected: backing creation improved by about
  `689 ms`, but CLIP source worsened by about `1171 ms` and resume→FRR worsened
  by `474 ms` (`3.71%`).
- Sampler Lane A proved the approximately `822.6 ms` stock RES4LYF
  `gc.collect()` tail. Lane B was only a small RK improvement. A+B is
  reference-only and was not promoted; old Lane A/B/A+B RES4LYF commits stay
  out of the normal checkout.

## Operating rules and next work

- Preserve exact source, workflow, output, deployment, and raw-run identity;
  raw evidence outranks derived summaries.
- Golden Serial remains serial; do not hide future-stage work behind its stage
  boundaries or move costs outside the measured endpoint.
- Next optimization target: **incremental QD2 source-ready → H2D overlap**.
  This promotion task does not begin that work.
- Separate pending maintenance task: **lightweight experiment guardrails** —
  worktree/bootstrap and canonical paths when worktrees are genuinely needed,
  safe long-running Modal/v2ctl handling, and a small experiment preflight
  checklist.

The `canonical/` subtree contains the accepted report, deployment/source
identity, correctness smoke, five timing manifests, their raw verification
cohorts, and per-run evidence. `historical/` contains the three decision
reports above plus selected unique audit material; duplicate retired cohorts
are intentionally not retained.
