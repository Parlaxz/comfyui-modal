# Causal Model

The campaign distinguishes observed configuration-to-wall associations from causal explanations. The following candidates are classified only from raw evidence.

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

### hot_best_candidates
- Classification: **SUPPORTED**
- Best thread, best process, and the one-worker reference are selected only after an all-valid meaningful smoke curve.
- Valid: 16; failures: 0
- Unsupported/opaque: best-candidate selection is smoke-derived unless confirmation exists

### hot_speedups
- Classification: **POSSIBLE**
- Speedups use median aggregate bytes / coordinated wall relative to the one-worker reference.
- Valid: 16; failures: 0
- Unsupported/opaque: speedup is relative to retained observations, not worker-rate sums

### cache_control_vs_dontneed
- Classification: **POSSIBLE**
- CONTROL and DONTNEED are compared as separate fresh-corpus branches.
- Valid: 4; failures: 0
- Unsupported/opaque: kernel reclaim completion is not directly observed

### cache_o_direct
- Classification: **POSSIBLE**
- O_DIRECT support or bypass is an observed capability/error outcome only.
- Valid: 2; failures: 0
- Unsupported/opaque: filesystem and mount O_DIRECT semantics

### cache_mmap_dontneed
- Classification: **POSSIBLE**
- mmap plus DONTNEED is classified from the returned result or exact error.
- Valid: 2; failures: 0
- Unsupported/opaque: mmap residency and kernel reclaim behavior

### mount_options
- Classification: **POSSIBLE**
- Mount options are quoted from raw FUSE diagnostics when present.
- Valid: 2; failures: 0
- Unsupported/opaque: mount options are remote diagnostic output; host mount policy remains opaque

### fuse_visibility
- Classification: **POSSIBLE**
- FUSE visibility is diagnostic, not a throughput claim.
- Valid: 2; failures: 0
- Unsupported/opaque: FUSE connection-to-mount mapping may be unavailable

### fuse_backpressure
- Classification: **POSSIBLE**
- Backpressure is classified only from raw samples.
- Valid: 2; failures: 0
- Unsupported/opaque: max_background/congestion_threshold/waiting/abort are unavailable unless returned

### fuse_syscall_latency
- Classification: **POSSIBLE**
- Per-worker syscall latencies are preserved without merging FUSE values into authoritative cohorts.
- Valid: 2; failures: 0
- Unsupported/opaque: per-worker syscall boundaries and scheduler attribution

### cold_thread_curve
- Classification: **DISFAVORED**
- Cold thread rates use bytes divided by the enclosing coordinated wall.
- Valid: 10; failures: 0
- Unsupported/opaque: page-cache state between separate containers

### cold_process_curve
- Classification: **POSSIBLE**
- Cold process observations retain startup/full-process timing and coordinated read throughput separately.
- Valid: 25; failures: 0
- Unsupported/opaque: process startup attribution depends on returned timing fields

### sequential_advice
- Classification: **POSSIBLE**
- Advice is compared only as fresh before/after observations.
- Valid: 35; failures: 0
- Unsupported/opaque: advice effect is not a causal kernel proof

### twelve_worker_headroom
- Classification: **POSSIBLE**
- A 12-worker observation is retained only when the bounded gate admits it.
- Valid: 1; failures: 0
- Unsupported/opaque: 12-worker branch is conditional on a material 4-to-8 smoke improvement

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

### causal_model
- Classification: **POSSIBLE**
- The raw record supports associations between requested configuration and measured walls, not unobserved causality.
- Valid: 215; failures: 0
- Unsupported/opaque: FUSE internals, kernel cache residency, remote image/runtime implementation, opaque external-loader geometry


Opaque layers: kernel cache residency, FUSE queue internals, scheduler attribution, remote image implementation details, and external-loader block geometry unless a raw response exposes them.
