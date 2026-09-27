# Source to H2D Decoupling Architecture

STATUS=IMPLEMENTED_AND_LOCALLY_VALIDATED

## Implemented

- `comfymodal_runtime/preplanned_extent_transport.py` plans source reads into predetermined destination offsets inside reusable pinned extents.
- Source QD, source read size, H2D extent size, H2D in-flight depth, and source capacity are independent inputs.
- An extent becomes READY only after every planned source read completes; the dispatcher submits one H2D copy per extent on one dedicated stream.
- Physical read telemetry retains requested and returned bytes per syscall.
- H2D submit/completion telemetry is kept separate from source syscall telemetry.
- Buffer size, extent identity, source/destination bases, exact coverage, and source-to-destination correspondence are validated.
- Worker and dispatcher cleanup is bounded and failures are recorded rather than silently falling back.
- The legacy and static-E27 arms remain compatibility paths.

## Golden integration

`golden_serial.py` routes both the real CLIP and UNET loader reads through the opt-in `decoupled` arm. The five dimensions are carried through the canonical Modal environment bridge and recorded with provenance. The candidate does not alter the default Golden arm.

## Evidence

- Focused transport/source integration: 72 passed.
- Python compilation and diff checks passed.
- CUDA execution was not available locally; no local result substitutes for remote CUDA evidence.
- Pure-source collection was stopped after 123 eligible observations at the user's direction. All interrupted attempts remain retained and reconciled in the campaign ledger.

## Not established

The decoupled integrated matrix and full Golden A/B were not run. Existing static-E27 Experiment-05/06 artifacts remain historical comparison evidence and are not relabeled as decoupled results.
