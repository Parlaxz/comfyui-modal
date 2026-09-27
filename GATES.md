# Gates: persistent M2 Golden transport recovery

OWNS: comfymodal_runtime/golden_model_transport.py, comfymodal_runtime/m2_source_core.py, config/v2/profiles/golden_p1_parallel_m2clip_h100.toml, tests/test_golden_model_transport.py, tests/test_production_m2_loader.py, tests/test_golden_parallel_foundation.py, GATES.md

Scope: Restore the proven M2 source schedule inside one persistent non-C0 transport shared by CLIP, UNET, and VAE while retaining the proven parallel/Gantt orchestration and exact output contract.

- [ ] G1: Focused tests prove QD4/64 MiB/256 MiB staging, sticky self-service scheduling with a 4 ms global gate, non-recursive M2 routing, reusable destination capacity, and the historical parallel/Gantt windows.
  CHECK: python tools/test_perf.py --fast -- tests/test_golden_model_transport.py tests/test_production_m2_loader.py tests/test_golden_parallel_foundation.py -m fast_unit
  EXPECT: passed

- [ ] G2: The full FAST_UNIT verification path passes within its diagnostic budget.
  CHECK: python tools/test_perf.py --fast -- tests -m fast_unit
  EXPECT: passed

- [ ] G3: The exact candidate is deployed through v2ctl to the config-owned experimental app and source-probe/status/doctor prove matching source identity and ready runtime health.

- [ ] G4: One eligible zero-retry Golden parallel request proves exact expected PNG SHA, exact source and H2D coverage, persistent-reader/runtime reuse, `c0_arena_created=false`, both overlap windows, and complete Gantt evidence.

- [ ] G5: Five eligible sequential requests from one frozen deployment preserve the proven M2 source rate and achieve median full CLIP load below 1.5 seconds; all attempts and invalid snapshot-adjacent requests remain recorded.
