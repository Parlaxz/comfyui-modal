# Transport Lane Ownership Proof

Status: resolved
Type: research
Blocked by: none

## Question

What facts prove a request-local UNET transport lane is safe to run under CLIP forward: dedicated H2D stream identity, pinned arena/slot lease, event-pair lifecycle, worker join/drain, `_require_transport_quiescence`-style proof, and `GoldenTransferResources` / `_QDReaderState` / `read_file_qd_gpu` boundaries, including which transport arms qualify and which are rejected?

## Answer

Qualifying path is resource-backed `dispatcher`/`static_e27` with request-local `GoldenTransferResources`: dedicated H2D stream ordering, exclusive pinned arena leases, slot event-pair record/harvest, full worker join, H2D event drain, exact record reconciliation, and `_require_transport_quiescence` before any view adoption. Rejected for this proof: `legacy`, `decoupled`/preplanned, and CPU-prefetch paths. Smallest seam is a joinable transport operation reusing `GoldenTransferResources` + `_QDReaderState` with `join()` as the sole quiescence boundary; no owner/views before join+drain. Full evidence: `../research/02-transport-lane-ownership.md`.

## Comments

Resolution recorded from completed research lane; no source, branch, scheduling, or dirty state modified.
