# RX7A — RX6B + Accepted RX7 Canonical Integration Report

Date: 2026-09-01  
Branch: `TESTING2`

## Result

- `RX6B_INTEGRATED=YES`
- `RX7_INTEGRATED=YES`
- `STATIC_E27_ACCEPTED=YES`
- `MECHANISM_PROVEN=NO`
- `RX8_STARTED=NO`
- No Modal deployment or remote run was performed.

## Integration identity

- Actual canonical TESTING2 HEAD inspected before this lane: `17bf190d8b10cd0bf2ee692840d5c5ff3c30da90`.
- The checkout already contained RX6B behavior in canonical commits:
  - `3f0303292d0a20969d24f3fc37ca336806075adf` — restore Golden waterfall routing.
  - `17bf190d8b10cd0bf2ee692840d5c5ff3c30da90` — suppress the duplicate generic Golden wrapper waterfall.
- RX6B source commits: `37ca169`, `cf2a030`.
- RX6B source report: `9138522`.
- RX6B was therefore integrated semantically already; stale RX6B commits were not replayed or allowed to overwrite newer canonical work.
- RX7 source implementation commits: `1dd4a47`, `156e721`, `7185be0`.
- RX7 source evidence report: `45a4a58`.
- Resulting canonical RX7 implementation commit: `083629f` (`feat: integrate accepted RX7 static E27 scheduling`).
- The existing RX6B integration report commit `7aa2a7c`, RX7 report commit `61eb95c`, and newer concurrent `bundle3` commit `afe4d302` were preserved.
- The current working tree was protected throughout: no reset, clean, stash, force-checkout, or unrelated overwrite was used.

## Conflicts and semantic resolutions

- RX6B had no integration action remaining because its two presentation-routing changes were already present in the inspected canonical HEAD.
- RX7 overlapped newer dirty changes in `golden_serial.py` and `config/v2/flag_registry.toml`. The static-E27 additions were merged into the current implementation rather than cherry-picking stale lane files; unrelated newer changes were preserved.
- RX7 changes are limited to the opt-in transport arm, Golden wiring, registry value, and focused tests/report evidence. Legacy/default transport and central dispatcher/H2D behavior remain unchanged.

## Waterfall contract

The canonical Golden console contract is preserved:

- Populated `V2 GOLDEN WATERFALL - REMOTE` remains visible.
- Empty `V2 COLD WATERFALL - REMOTE/PARTIAL` is suppressed for Golden transport results.
- The raw giant `[v2.golden_telemetry]` console duplication is suppressed.
- The late unnecessary conditioning-cache mode initialization/log remains suppressed.
- Persisted Golden telemetry, returned Golden telemetry, structured waterfall artifacts, host reconciliation, and generic non-Golden waterfalls remain intact.

## Accepted RX7 contract

Static E27 is canonical and fail-closed:

- `static_e27` is opt-in; the default remains `legacy`.
- QD is exactly 4 and each source read is 32 MiB.
- Producers are exactly IDs 0–3, each assigned one deterministic fixed contiguous source region.
- Source offsets move monotonically forward and reads are direct positioned reads into pinned staging.
- There is no fallback path.
- Static-plan identity, exact source/H2D bytes, complete coverage, completed-record identity, short reads, quiescence, and ownership invariants are reconciled.
- Split chunks receive unique record identities; diagnostics-off destination-order observation is reported as unknown rather than fabricated.

## Accepted RX7 measurements and interpretation

- CLIP load median: `1862.709 ms` control → `1623.743 ms` static E27 (`-12.8%`).
- UNET load median: `2098.561 ms` control → `1960.827 ms` static E27 (`-6.6%`).
- The broad request median improved but contains substantial external variance and is not treated as a clean transport metric.
- Source bandwidth improvement was not proven because source-wall/QD-occupancy fields were unavailable.

Therefore the required interpretation is:

`STATIC_E27_ACCEPTED=YES`  
`MECHANISM_PROVEN=NO`

## Verification

Passed against the current canonical tip before this report commit:

- Focused RX6B/RX7/waterfall/QD batch: **467 passed**.
- Additional isolated Golden regressions: **149 passed, 3 skipped**.
- `py_compile` for **14** changed Python files: passed.
- `git diff --check`: passed.

The broader `tests/test_waterfall_restoration_wiring.py` run had 18 passes and 2 known unrelated Studio direct-path assertion failures. The import/setup-heavy `tests/test_cold_start_waterfall_bug.py` and `tests/test_p2_golden_snapshot_adapter.py` exceeded the local timeout without producing a test result; these were not attributed to RX7. No code in those Studio/cold-start areas was changed by this integration.

## Final state

- Final TESTING2 HEAD: the commit containing this report.
- RX8 was not introduced: no dispatcher refill/reaping policy, dispatcher wait, CUDA stream choice, H2D granularity, pinned-ring capacity, read-size, CLIP forward, cast-once, sampler, VAE, resource, or parallelization changes were made for RX7A.
