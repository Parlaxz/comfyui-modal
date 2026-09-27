# R0 Future-Agent Golden Operations Contract

> **SUPERSESSION NOTICE (2026-08-30):** This R0 contract is historical
> guidance for its isolated experiment. Use `.opencode/skills/comfymodal-golden-ops/SKILL.md`
> and `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md` for current operations:
> generated-output durability is off by default and strict is opt-in. S4
> source publication durability remains mandatory.

## Scope

This contract applies to the isolated R0 experiment app only:

- app: `batch-r0-golden-ops`
- class: `ModalRuntimeEntrypointV2`
- method: `run_golden_serial_stream`
- profile: `golden_p1`
- GPU: `rtx-pro-6000`
- expected output SHA-256: `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da`

The protected production app `stable-modal-comfy-v2-golden-p1` must never be
used by ordinary Golden operations. Civitai is outside R0 deployment, runtime,
app-identity, inference, and validation scope.

## Public commands

Run from the repository root. These are the supported commands; do not invoke
the BAT files directly.

```powershell
python tools/v2ctl.py golden status --app batch-r0-golden-ops
python tools/v2ctl.py doctor --profile golden_p1 --app batch-r0-golden-ops
python tools/v2ctl.py golden deploy --app batch-r0-golden-ops
python tools/v2ctl.py --profile golden_p1 --app batch-r0-golden-ops source-probe
python tools/v2ctl.py golden run --app batch-r0-golden-ops
python tools/v2ctl.py gate --profile golden_p1 --app batch-r0-golden-ops
python tools/v2ctl.py --profile golden_p1 --app batch-r0-golden-ops confirm --from <gate-manifest> --runs 5
```

`golden run` is one request. Never replace the one-request sequence with
`deploy-run`, generic `run`, or a multi-request backend invocation.
`source-probe` and `confirm` are top-level commands, so their global options
must precede the subcommand.

## Acceptance rules

1. Deploy must finish before any request and must not perform inference.
2. Status must show matching current/stored deployment fingerprints, matching
   target, verified source and runtime health, no runtime overrides, and
   `ready=True` before final acceptance.
3. A usable attempt is structurally valid, not merely process exit code zero:
   exactly one terminal result, expected output SHA, `true_durable=true`,
   reopen verification, valid snapshot proof, commit-before-reopen ordering,
   strict seriality, completed teardown, and Golden dynamic-VRAM evidence.
4. Every accepted attempt must identify the experimental app/class/method,
   deployment identity, workflow hash, restore/request identity, provider and
   region, and artifact paths.
5. A request-time snapshot capture is `SNAPSHOT_CAPTURE`, is never counted, and
   arms exactly one directly-following invalid request. That guard is then
   consumed; later eligible requests do not require redeployment. Deployment or
   startup snapshot creation is not request-time capture.
6. After a deploy-relevant source/config change, stop and redeploy. Reports,
   logs, artifacts, and passive diagnostics do not require redeployment.

## Current proven deployment

- deployment manifest:
  `.v2ctl/deployments/deploy_20260828-215821_0924070a.json`
- deployment fingerprint:
  `0924070a685e2de4ffe6e7d2b95c1aceffd29e0907cbfb9a04c5dad4468d5cc5`
- deployment combined hash:
  `d25161544d2d2d7461d32a1b2f99ea381c6cf7a108d3c9b2481037192fbeac96`
- source probe: `RESULT=PASS source_identity=MATCH`
- final status: `runtime_health_status=verified`, `source_identity_status=verified`,
  `ready=True`
- final confirmation:
  `.v2ctl/confirmations/confirm_20260829-030820_5d3926df.json`

Retain every run manifest, cohort manifest, summary, attempt, event file, and
raw command log. Do not select evidence by newest mtime or delete invalid
attempts.
