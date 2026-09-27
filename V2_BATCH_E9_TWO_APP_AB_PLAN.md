# V2 Batch E9 Phase-E Two-App Canonical A/B Plan

Planning only. No deploy, no request, and no commit in E9 planning.

`A` and `B` must use separate app names and separate recorded deployment
identities. The request vehicle must fail closed if the served app, deployment,
class, provider, region, GPU, or runtime shape is not the intended one.

APP_A=stable-modal-comfy-v2-restore-only-shadow

APP_B=stable-modal-comfy-v2-restore-only-staged-shadow

A_FLAGS=
```text
APP_NAME=stable-modal-comfy-v2-restore-only-shadow
PROFILE=current canonical production behavior with D15 exactly as currently deployed
STAGED_SAFETENSORS=0
E9 transport controls=absent or current canonical defaults
CPU cast=current canonical value
async H2D=current canonical value
contiguous GPU buckets=current canonical value
UNET prestage=OFF
ALL_OTHER_FLAGS=unchanged from the recorded current canonical A deployment
```

B_FLAGS=
```text
APP_NAME=stable-modal-comfy-v2-restore-only-staged-shadow
PROFILE=byte-for-byte identical to A except for the E9 staged transport bundle
STAGED_SAFETENSORS=1
producers=4
pool=1024 MiB
bucket=256 MiB
CPU cast=ON
async H2D=ON
contiguous GPU buckets=ON only if the E1 safety gate is PASS; otherwise OFF and do not run B
UNET prestage=OFF
D15=exactly the A setting
ALL_OTHER_FLAGS=exactly A
```

The E1 safety decision for contiguous GPU buckets is a precondition, not a
post-hoc interpretation. If E1 does not prove the mode safe, B keeps that
option OFF and the staged profile is not considered the requested B profile
until the safety decision is resolved.

Provider and region are pinned to the same values for A and B and are recorded
in every result. AWS and GCP are never treated as a causal A/B pair. GPU type,
image/dependency identity, ComfyUI/custom-node identity, CPU, memory, workflow,
model files, prompt inputs, seed, nonce, and runtime-shape fingerprint are also
held constant.

VALIDITY_GATES=
```text
1. A and B resolve to their exact expected app names; no legacy/default-app fallback.
2. Each arm is one structural-cold request with the expected fresh/cold identity.
3. A and B have the same provider, region, GPU, image/dependency identity, code identity, runtime shape, workflow, model, inputs, seed, and nonce policy.
4. The canonical output is correct and byte-identical for both arms.
5. Required telemetry is present for both arms:
   CLIP prepare, commit, H2D, bind, forward;
   UNET meta, prepare, commit, H2D, bind;
   peak pinned memory;
   fallback reason, including fallback_reason=none when no fallback occurs;
   MODEL_READINESS_GATE.
6. MODEL_READINESS_GATE is internally consistent with max(CLIP_READY, UNET_READY).
7. No fallback, OOM, incomplete bind, missing readiness boundary, or unexplained telemetry gap occurs.
8. The app/deployment/provider identity is recorded before interpreting timing.
```

PRIMARY_METRIC=
```text
max(CLIP_READY, UNET_READY), measured from the same request boundary.
Compare B against A in milliseconds. Only after this comparison, evaluate
no-scheduling command->response.
```

SUCCESS_THRESHOLD=
```text
Both arms pass every validity gate, and B reduces PRIMARY_METRIC by at least
300 ms versus A. B must not regress no-scheduling command->response by more
than 5% versus A. Output correctness and fallback_reason=none are required.
```

STOP_THRESHOLD=
```text
Stop immediately for any validity-gate failure, wrong served app/deployment,
provider or region mismatch, output mismatch, fallback/OOM, missing required
telemetry, or a B regression greater than 5% in either PRIMARY_METRIC or
no-scheduling command->response. A valid result inside the 300 ms success band
but outside the clear-regression band is indeterminate; expand only when that
ambiguity is material and explicitly justified.
```

Initial execution is exactly one structural-cold A followed by one
structural-cold B. Do not create a cohort or automatically repeat either arm.

MAX_INITIAL_REQUESTS=2
