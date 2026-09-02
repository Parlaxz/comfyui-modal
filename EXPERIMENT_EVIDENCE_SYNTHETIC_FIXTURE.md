# Experiment evidence: `SYNTHETIC_FIXTURE`

This Git-visible sample is produced from offline fixture cohorts. It covers
clean exact, mismatch warning, failed, incomplete, mixed attention backend,
adjacent/concurrent creation, large event-stream omission, missing receipt, and
normal multi-arm cohorts. No Modal deployment or paid request is involved.

- **EXPERIMENT_EVIDENCE_STATUS:** `OK`
- **EXPERIMENT_VERDICT:** `INCONCLUSIVE`
- **Raw bundle:** `artifacts/SYNTHETIC_FIXTURE_evidence_2026-09-01/`

## Frozen identity

```json
{
  "attention_backend": "pytorch",
  "profile": "golden_p1",
  "profile_config_fingerprint": "fixture-profile-sha256",
  "run_fingerprint": "fixture-run-sha256",
  "v2ctl_invocation_id": "fixture-invocation",
  "request_id": "fixture-request"
}
```

Identity chain: `v2ctl invocation ID -> request ID -> exact cohort directory -> manifest.json -> attempt artifact(s) -> summary.json`.

## Compact cohort index

| cohort | arm | attention backend | classification | failure / missing declaration |
|---|---|---|---|---|
| clean-exact | control | pytorch | EXACT | none |
| mismatch-warning | control | pytorch | MISMATCH | expected/observed SHA warning retained |
| failed | control | pytorch | MISMATCH | attempt failure retained |
| incomplete-directory | control | pytorch | INCOMPLETE | MISSING: `summary.json` |
| mixed-attention | candidate | mixed | MISMATCH | pytorch + sage attempts rejected |
| adjacent-concurrent-a | control | pytorch | EXACT | separate exact cohort path |
| adjacent-concurrent-b | control | pytorch | EXACT | separate exact cohort path |
| large-events | control | pytorch | EXACT | `attempt_0_events.json` omitted from text only; raw bytes/SHA256 retained |
| missing-receipt | control | pytorch | MISMATCH | MISSING: deployment receipt |
| normal-multi-arm-a | arm-a | pytorch | EXACT | complete |
| normal-multi-arm-b | arm-b | pytorch | EXACT | complete |

## Evidence contract

Every embedded object carries its source path and every source file is listed
with byte size and SHA256. Text is embedded verbatim after only secret
redaction/encoding normalization. The large event stream is the sole allowed
text omission and remains auditable through its exact source path, cohort, byte
size, SHA256, and omission reason.
