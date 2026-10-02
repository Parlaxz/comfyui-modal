# Next Experiment

Proceed only with a new, uniquely named cohort. Do not reuse a corpus or treat a smoke result as confirmation.

### causal_model
- Classification: **POSSIBLE**
- The raw record supports associations between requested configuration and measured walls, not unobserved causality.
- Valid: 215; failures: 0
- Unsupported/opaque: FUSE internals, kernel cache residency, remote image/runtime implementation, opaque external-loader geometry

### hot_best_candidates
- Classification: **SUPPORTED**
- Best thread, best process, and the one-worker reference are selected only after an all-valid meaningful smoke curve.
- Valid: 16; failures: 0
- Unsupported/opaque: best-candidate selection is smoke-derived unless confirmation exists

### hot_threads_scaling
- Classification: **POSSIBLE**
- Thread scaling is reported only from enclosing coordinated read walls.
- Valid: 8; failures: 0
- Unsupported/opaque: kernel page cache state, FUSE internal scheduling

### hot_process_scaling
- Classification: **POSSIBLE**
- Process scaling retains startup and full-process timing when returned by the remote reader.
- Valid: 8; failures: 0
- Unsupported/opaque: process creation outside the timed read, kernel page cache state

### sequential_advice
- Classification: **POSSIBLE**
- Advice is compared only as fresh before/after observations.
- Valid: 35; failures: 0
- Unsupported/opaque: advice effect is not a causal kernel proof

### fastsafetensors_cpu_source_only
- Classification: **DISFAVORED**
- fastsafetensors is capability/source-only evidence; geometry opacity is explicit.
- Valid: 3; failures: 0
- Unsupported/opaque: API may not expose block geometry, no H2D is permitted

### instanttensor_capability
- Classification: **POSSIBLE**
- InstantTensor is probed for capability and CPU rejection only.
- Valid: 5; failures: 0
- Unsupported/opaque: import/backend/CPU rejection capability only, no H2D is permitted


The next experiment should target the highest-supported unresolved mechanism and preserve the same enclosing-wall, source-proof, and no-H2D gates.
