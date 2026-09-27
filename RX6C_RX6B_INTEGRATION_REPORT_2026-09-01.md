# RX6C — RX6B Waterfall Correction Integration

Date: 2026-09-01  
Status: `RX6B_INTEGRATED=YES`

## Integration identity

- Canonical pre-integration HEAD: `afb9f376ba26edbea44c366c35b8914ee07d0d68`
- Source RX6B implementation commits:
  - `37ca169` — restore Golden waterfall console routing
  - `cf2a030` — suppress generic Golden wrapper waterfall
- Source RX6B report evidence was verified from
  `RX6B_GOLDEN_WATERFALL_ROUTING_CORRECTION_REPORT_2026-09-01.md` at source
  commit `9138522`.
- Resulting canonical RX6B commits:
  - `3f0303292d0a20969d24f3fc37ca336806075adf`
  - `17bf190d8b10cd0bf2ee692840d5c5ff3c30da90`

The source patches were semantically replayed in order. The first ordinary
cherry-pick attempt was blocked by the dirty `modal_app.py`; the patches were
then safely staged and committed without resetting, stashing, cleaning,
force-checking out, or overwriting unrelated work. There were no textual
conflicts or RX6B conflict resolutions. Existing newer dirty and untracked
work remains in the working tree and was not included in these commits.

## Scope and contract

The integration remains presentation/routing only:

- Keeps `V2 GOLDEN WATERFALL - REMOTE`.
- Removes the generic Golden `V2 COLD WATERFALL - REMOTE/PARTIAL` render.
- Removes the giant `[v2.golden_telemetry]` console duplication.
- Removes the late unnecessary conditioning-cache mode initialization/log.
- Preserves persisted Golden telemetry, structured waterfall artifacts, host
  reconciliation data, generic non-Golden cold waterfalls, and RX6
  conditioning-cache peek behavior.

No QD scheduling, dispatcher, CLIP, sampler, VAE, resource, or
parallelization changes were introduced by the RX6B replay.

## Validation

Passed:

- `tests/test_p2_golden_snapshot_adapter.py`: **35 passed**
- RX6B-relevant waterfall suites (`test_v2_waterfall.py`,
  `test_v2_waterfall_contract.py`, `test_waterfall_attach_central.py`,
  `test_p2_golden_observability.py`,
  `test_benchmark_v2_golden_acceptance.py`): **168 passed**
- RX6B-specific restoration routing cases: **3 passed**
- `python -m py_compile` for the changed runtime Python files: passed
- `git diff --check`: passed

The full `tests/test_waterfall_restoration_wiring.py` file still has the two
documented pre-existing unrelated Studio direct-path assertion failures:

- `StudioAdapterPersistenceTests.test_direct_path_copies_waterfall_into_timings`
- `StudioAdapterPersistenceTests.test_direct_path_meta_carries_waterfall`

## Final identity

- Final TESTING2 HEAD: `HEAD` at completion of the report commit (the exact
  resolved hash is returned with this integration result).

The report commit is intentionally separate from the two canonical RX6B
implementation commits above.
