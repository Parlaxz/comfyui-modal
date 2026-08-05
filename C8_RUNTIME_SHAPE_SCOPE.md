# C8 runtime-shape experiment scope

## Attribution

The runtime-shape work starts after `e28192f8195bf3d79ca859449c504329ba9aec22`.
That prerequisite commit activates the production P1-P5 wrappers and changes
batch-profile defaults; it is not itself a C8 runtime-shape change. C8 result
reports must retain that prerequisite in their baseline description.

This branch does not include the later C5 BF16 final commit. The selected C8
winner must be retested after C5 BF16 is integrated before it is treated as a
production conclusion.

## Runtime policies

- `TBASE` is the default pass-through control. It does not set Torch thread
  counts, native-library thread variables, or allocator settings.
- `T1`, `T2`, and `T3` are explicit thread-policy candidates and must be
  selected with `COMFYMODAL_V2_THREAD_POLICY`.
- `O0` is the existing CLIP -> UNET -> VAE construction order.
- `O1` through `O3` change model construction order only. They do not measure
  final tensor-page touch order before capture.
- `COMFYMODAL_V2_RUNTIME_SHAPE_LABEL` is optional human metadata. The
  `runtime_shape_fingerprint` is always computed from the requested shape.

## Matrix order

1. `TBASE/O0/current CPU/current memory`
2. `T1/O0/current CPU/current memory`
3. `T2/O0/current CPU/current memory`
4. `T3/O0/current CPU/current memory`
5. Select the thread winner, then test `O1` through `O3`.
6. Test CPU and memory requests separately.

The benchmark rejects more than one changed axis unless
`COMFYMODAL_V2_ALLOW_MULTI_AXIS=1` is explicitly supplied. Set
`COMFYMODAL_V2_BASELINE_CPU_REQUEST` and
`COMFYMODAL_V2_BASELINE_MEMORY_REQUEST` when testing resource axes against a
known current-production allocation.
