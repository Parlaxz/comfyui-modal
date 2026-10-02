# U1 QD4 Transport Finalization

## Result

The local QD dispatcher path is finalized for the later remote campaign. The
dispatcher adapter now uses `GoldenQDTransport` with an acquired pinned staging
lease and a positioned `readinto(target, offset)` source contract. Source bytes
are read directly into the lease storage, then submitted by the dispatcher to
one CUDA destination. The normal dispatcher path does not create a
model-block-sized Python `bytes` or `bytearray` payload.

The legacy path was not redesigned. Its scheduling remains the existing
per-worker positioned-read, pinned-slot, event-gated algorithm. It now exposes
bounded diagnostics for positioned source-read wall/count/bytes and per-read
percentiles/max, pinned-slot wait, allocation/pinning, H2D submit, H2D event
wait, final drain, and post-transport residual classification.

## Cleanup and ownership

- Natural producer completion joins workers, drains the dispatcher without the
  cleanup deadline, reconciles records/bytes, and then succeeds.
- Abort/cancel uses one absolute bounded deadline shared by producer joins and
  dispatcher cleanup.
- Late events returned after handoff detachment remain explicitly owned,
  terminally polled, and classified. Failed terminal events are removed;
  unresolved pending/uncertain events remain visible and block quiescence.
- Unresolved late-event ownership retains the CUDA owner/transport. Failed
  reader closes remain tracked and fail snapshot quiescence until retry-close
  succeeds.
- Poisoned pools, active workers, open readers, live leases, queued/handoff
  state, and outstanding events reject snapshot quiescence.
- Abort stale-receipt suppression is limited to the expected stale/detached
  lease states; unrelated `LeaseError` values remain errors.

## Truthful telemetry

Dispatcher records actual positioned source-read wall and per-read
p50/p90/p99/max, source bytes/read count, lease wait, ready-queue backpressure,
pinned allocation, H2D submit wall, event polling, submit-to-completion
latency, final drain, producer QD occupancy, free/ready depth, fallback, and
exact byte reconciliation. CPU-to-pinned copy and legacy pinned-slot wait are
reported as `NOT RUN` for the dispatcher; event polling is not mislabeled as a
host wait. Broad producer lifetime is not called source I/O.

## Local verification

Passed:

```text
pytest tests/test_golden_qd_transport.py tests/test_ra9c_golden_qd_integration.py
       tests/test_e30_clip_qd_io.py tests/test_c9_qd_probe.py
       tests/test_golden_core_invariant_shield.py
       tests/test_ra9h_golden_clip_residency.py
       tests/test_ra9g_clip_fp32_ownership_transfer.py -q
187 passed, 2 skipped

pytest tests/test_p1_golden_serial.py::test_vae_load_performs_single_header_and_payload_read
       tests/test_p2_golden_core_contract.py tests/test_p2_golden_observability.py -q
66 passed, 1 skipped

python -m py_compile <changed QD/Golden/test modules>
python -m compileall -q comfymodal_runtime tests
git diff --check
```

No Modal deployment, remote request, or other remote contact was performed.
The CUDA allocator/event behavior and physical performance result remain to be
established by the approved later remote A/B campaign.

```text
U1_COMPLETE=YES
DIRECT_SOURCE_TO_PINNED=YES
MODEL_BLOCK_PAGEABLE_INTERMEDIATE=NO
NORMAL_SUCCESS_USES_CLEANUP_DEADLINE=NO
LATE_H2D_EVENT_ACCOUNTED=YES
POISONED_SNAPSHOT_QUIESCENCE_REJECTED=YES
LEGACY_SCHEDULING_CHANGED=NO
LEGACY_TAIL_COMPONENT_TELEMETRY_READY=YES
DISPATCHER_PERF_TELEMETRY_TRUTHFUL=YES
MODAL_CONTACTED=NO
READY_FOR_REMOTE_QD_TEST=YES
```
