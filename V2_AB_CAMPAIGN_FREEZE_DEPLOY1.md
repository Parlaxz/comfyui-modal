# V2 A/B Campaign Freeze Record - Deployment 1
generated_at_utc: 
git_head: e5483d5a7a5414fc9baae84d16e02c13bf270520
git_branch: TESTING2
git_status_lines: 65
git_diff_stat:
 V2_CONDITIONING_CACHE_CRITICAL_PATH_DESIGN.md  |  651 +++++++++++++
 __init__.py                                    |  106 ++-
 canonical_execution.py                         |  391 +++++++-
 comfyapp.py                                    |  284 +++++-
 comfymodal_runtime/clip_conditioning_cache.py  | 1200 ++++++++++++++++++++----
 comfymodal_runtime/contracts.py                |  179 ++++
 comfymodal_runtime/modal_app.py                |  564 ++++++++++-
 comfymodal_runtime/modal_transport.py          |  129 ++-
 comfymodal_runtime/model_preload.py            | 1075 ++++++++++++++++++++-
 comfymodal_runtime/output_delivery.py          |   46 +-
 comfymodal_runtime/runtime_bootstrap.py        |  198 ++++
 comfymodal_runtime/runtime_executor.py         |  388 ++++++++
 comfymodal_runtime/v2_waterfall.py             |  714 +++++++++++++-
 debug.log                                      |   12 +
 modal_client.py                                |   16 +
 run_v2_single.bat                              |    4 +-
 tests/test_clip_vae_request_activation.py      |    4 +-
 tests/test_exact_cache_async_persistence.py    |  438 +++++++++
 tests/test_v2_cpu_snapshot_lifecycle.py        |    2 +-
 tests/test_v2_local_submission_timing.py       |   18 +
 tests/test_v2_snapshot_activation_invariant.py |    4 +-
 tests/test_v2_waterfall.py                     |  108 ++-
 tools/analyze_production_candidate.py          |   11 +-
 tools/analyze_resource_gpu_experiments.py      |    2 +-
 tools/benchmark_v2_direct.py                   |  690 +++++++++++++-
 25 files changed, 6882 insertions(+), 352 deletions(-)

pre_freeze_harness_edits:
  - tools/benchmark_v2_direct.py: _EXPERIMENT_ORIGIN_OVERRIDES + _experiment_origin_overrides() wired into _run_one request_origin_info (per-request arm application)
  - run_v2_single.bat: default branch forwards %* CLI args
experiment_defaults: all B arms OFF (no COMFYMODAL_V2_UNET_PINNED_STAGING / VAE_EARLY_START_MS / PNG_COMPRESS_LEVEL / CACHE_ASYNC_LRU / RESTORE_TOTAL_VRAM_FROZEN set)

