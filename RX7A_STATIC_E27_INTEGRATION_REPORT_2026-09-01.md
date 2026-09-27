# RX7A Static E27 Integration Report — 2026-09-01

## Result

- `STATIC_E27_ACCEPTED=YES`
- `MECHANISM_PROVEN=NO`
- `RX8_STARTED=NO`
- No Modal deploy or remote run was performed.

## Integration

- Canonical branch: `TESTING2`
- Canonical starting tip: `7aa2a7c` (`docs: record RX6B integration into TESTING2`)
- Source RX7 commits integrated: `1dd4a47`, `156e721`, `7185be0`
- Clean integration lane was based on source-equivalent `17bf190`; RX6B/RX6C source edits were preserved.
- Resulting canonical integration commit: `083629f` (`feat: integrate accepted RX7 static E27 scheduling`)
- Conflicts: none.
- Unrelated pre-existing working-tree changes were not reset, stashed, cleaned, or included.

## Verification

The focused RX7/QD/Golden and RX6B/RX6C waterfall suites passed:

```text
pytest -q \
  tests/test_golden_qd_transport.py \
  tests/test_p1_golden_serial.py \
  tests/test_ra9c_golden_qd_integration.py \
  tests/test_v2ctl_config.py \
  tests/test_v2_waterfall.py \
  tests/test_v2_waterfall_contract.py \
  tests/test_v2_waterfall_scheduling_contract.py \
  tests/test_waterfall_reconciliation.py
321 passed
```

The optional broader `tests/test_waterfall_restoration_wiring.py` run retained two unrelated Studio direct-path assertion failures. No code in that area was changed for RX7A.

## RX7 Evidence

- CLIP median: `1862.709 ms -> 1623.743 ms` (`-12.8%`).
- UNET median: `2098.561 ms -> 1960.827 ms` (`-6.6%`).
- Broad-request median remains externally variable.
- Source-QD occupancy and source-wall telemetry were unavailable; the accepted result is therefore static/configuration evidence, not mechanism proof.
- RX6B/RX6C waterfall behavior remains covered: populated Golden waterfalls remain visible, empty partial waterfalls are suppressed, and raw telemetry console dumps are suppressed.
