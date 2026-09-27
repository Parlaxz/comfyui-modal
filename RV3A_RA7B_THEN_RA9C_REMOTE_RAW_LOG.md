# RV3A Raw Evidence Index

This index preserves the complete command/provider captures by path. JSON
attempt, event, manifest, and summary artifacts referenced by each run manifest
are authoritative for classification and timing.

## RA7B

All RA7B raw captures are under:

`RA7B_REMOTE_STEP1_EVIDENCE_20260831T000000Z/`

Notable retained captures:

- `16_orchestrator_deploy.log`
- `17_orchestrator_source_probe.log`
- `18_orchestrator_postdeploy_status_doctor.log`
- `19_orchestrator_ra7b_smoke.log`
- `20_orchestrator_deploy_after_validator_fix.log`
- `21_orchestrator_source_probe_after_validator_fix.log`
- `22_orchestrator_postdeploy_status_doctor_after_validator_fix.log`
- `23_orchestrator_ra7b_smoke_after_validator_fix.log`
- `23_remote_snapshot_platform_dnf_20260831T113747.log`
- `24_orchestrator_ra7b_cohort_01.log` through
  `28_orchestrator_ra7b_cohort_05.log`
- `29_ra7b_acceptance_summary.txt`

The six accepted run manifests are the `run_*_d9057c47.json` records for
`11:42:11`, `11:47:06`, `11:58:11`, `11:58:59`, `12:01:06`, and `12:06:47`.

## RA9C

All RA9C captures are under:

`RA9C_REMOTE_EVIDENCE_20260831T000000Z/`

Retained sequence:

- `01_doctor.log`
- `02_deploy_legacy.log`, `03_source_probe_legacy.log`,
  `04_source_probe_legacy_explicit_app.log`
- `05_source_probe_legacy_receipt_bound_timeout.log`,
  `06_source_probe_legacy_receipt_bound_retry.log`
- `07_postdeploy_status_doctor_legacy.log`
- `08_redeploy_legacy_with_qd_selector.log`
- `10_source_probe_legacy_final.log`
- `11_deploy_dispatcher.log`, `12_source_probe_dispatcher.log`
- `15_redeploy_legacy_selector_baked.log` through
  `24_smoke_dispatcher_current_bundle.log`

The invalid dispatcher smoke artifact is:

`artifacts/phase_p1_serial_golden_v1/cohort_2026-08-31_18-22-24_1601fe/attempt_0.json`

Its event stream and summary are in the same directory. It records
`qd_transport_arm=dispatcher`, `source_qd_target=4`, source worker cleanup
failure, stale lease-generation secondary errors, and no terminal result.

No RA9C timing statistic is reported as an accepted comparison until a valid
legacy/dispatcher cohort exists.
