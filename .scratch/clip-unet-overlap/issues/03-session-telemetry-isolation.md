# Session and Telemetry Isolation Contract

Status: open
Type: grilling
Blocked by: 01-unet-seam-cut.md

## Question

What is the parallel schedule-proof contract that replaces seriality without touching Serial semantics: lane identifiers, per-lane intervals, dependency edges, nonzero timestamp-intersection rule, both-ready-before-sampler-prepare, failure/cancel drain, and no-duplicate-ownership — given the singleton `GoldenTelemetryRecorder`, shared `GoldenSession`, and one-node-at-a-time `GoldenSerialRunner`?
