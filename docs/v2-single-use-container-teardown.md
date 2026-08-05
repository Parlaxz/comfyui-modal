# V2 Single-Use Container Teardown

## Symptom

GPU memory dropped immediately after a request, but the Modal container did not
run `@modal.exit` until roughly 24 seconds later. Disabling Modal memory
snapshots did not change that interval.

## Cause

The V2 class was registered with `target_inputs=1` and `max_inputs=1`, but
without `single_use_containers=True`.

Those input limits restrict concurrency; they do not make the container exit
after one request. Modal returned the reusable container to its input loop and
only invoked `@modal.exit` when the platform later scaled the container down.
The application teardown code was not responsible for the delay.

## Evidence

- Snapshot-disabled run `v2-benchmark-0-7c4a0eccd73c`: GPU release ended at
  15:59:23 and `exit_hook_start` occurred at 15:59:47.
- The same run reduced CUDA allocation from 12.67 GB to approximately 68 MB;
  the exit hook itself completed in about 30 ms.
- Single-use run `v2-benchmark-0-d70a20d5a908`: the post-stream release and
  `exit_hook_start` occurred in the same second, with no 24-second idle gap.

## Fix and configuration

`ModalRuntimeSpec.single_use_containers` is controlled by:

```text
COMFYMODAL_V2_SINGLE_USE_CONTAINERS=1
```

The default remains `False` to preserve reusable-container behavior. The
registration forwards the value to `app.cls(single_use_containers=...)`.

Single-use containers trade warm reuse for prompt shutdown. Follow-up method
calls, such as asset reads, may be handled by a fresh container and should be
verified for workflows that depend on reuse.

Memory snapshots are independent of this setting. Use
`COMFYMODAL_V2_ENABLE_MEMORY_SNAPSHOT=0` only when specifically testing the
snapshot-disabled variant.

## Verification

```powershell
$env:COMFYMODAL_V2_SINGLE_USE_CONTAINERS = "1"
$env:COMFYMODAL_V2_TEARDOWN_DIAGNOSTICS = "1"
python -m unittest tests.test_v2_resource_baseline -v
```

The teardown logs should show `exit_hook_start` immediately after the
post-stream release rather than after the reusable-input idle interval.
