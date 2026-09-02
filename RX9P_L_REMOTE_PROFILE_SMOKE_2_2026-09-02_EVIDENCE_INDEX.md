# RX9P-L Remote Profile Smoke #2 Evidence Index

These are Git-visible pointers to the ignored runtime evidence directory
`artifacts/rx9p_l_remote_profile_smoke_2_2026-09-02/`.

## Identity

```text
PRE_RECONCILIATION_HEAD=3bb02cafc077bab4c8878ad4558fdb42d09f42e9
RECONCILED_TESTING2_HEAD=cc8907d1cb2dfffe5bf324b5d090c78ce1b4b5c5
APP=rx9p-l-remote-profile-smoke-2
PROFILE=golden_p1
CLASS=ModalRuntimeEntrypointV2
METHOD=run_golden_serial_stream
```

## Persisted artifacts

| Artifact | Bytes | SHA256 |
|---|---:|---|
| `committed_git_sha.txt` | 45 | `868bd0fd737908a96ed068fc592d2f01f5f5c977b90dcb0de958f930cbf7418a` |
| `predeploy_git_status.txt` | 54 | `05c37be8747fac62bd030fe85e71af98ba13ab1e18362397fbd3405770769173` |
| `preflight_lock_status.txt` | 21 | `b7719fbc7486c2e39a43ca9d84338019985370851708a7cbc97eb908bab55808f` |
| `preflight_config.json` | 40111 | `b72b6d1f6a748d0d662136a457f8328dfffbdc335b589837b6ac332c772c0b70` |
| `preflight_deploy_dry_run.txt` | 8717 | `d5ebfdeb7dd917ef85ec3b543fb872c0017664a03a5ef2bc42c5d4a111809433` |
| `deploy_timeout_record.txt` | 580 | `370e990b005f0e214cfc3d104671794ad5f5bd629f4a9ede6088786b5f06c4a2` |
| `postdeploy_status.json` | 1745 | `30d5568bf5f7b70238628a64b971833a3dfc807d1742c8f382c0cdcb7c50cd56` |

`deploy.log`, a deployment receipt, and a deployment manifest were not
produced. `postdeploy_status.json` records no matching deployment and
`ready=false`.

## Budget accounting

```text
REMOTE_DEPLOYS=1
REMOTE_GOLDEN_REQUEST_COUNT=0
DEPLOYED_SOURCE_MATCH=NO
REMOTE_PROFILE_SMOKE_2=FAIL
```

No remote Golden evidence bundle exists for this lane. Historical `.v2ctl`
cohorts and reports were not substituted for the current invocation.
