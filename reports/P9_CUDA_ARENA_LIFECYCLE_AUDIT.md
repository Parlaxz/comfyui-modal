# P9 — CUDA Arena Lifecycle / C0 Host-Registration Audit

**AUDIT ONLY.** No production behaviour, geometry, timing boundary, or CUDA call
was changed on this branch. Nothing was deployed, promoted, tagged, or merged.

## 0. Evidence labels used throughout

Every claim below carries one of these. They are not interchangeable and are
never mixed inside a single conclusion.

| Label | Meaning |
|---|---|
| `[DOC]` | Verbatim from NVIDIA CUDA or PyTorch documentation, quoted |
| `[CODE]` | Verified in the source at `AUDIT_BASE_SHA` (file:line cited) |
| `[MEAS]` | Measured in this repository's own true-cold H100! cohorts |
| `[INFER]` | An inference. The basis is stated. Not documentation, not proof |

Two prior reports in this repository carry the load-bearing measurements:

- `REGISTRATION_INVESTIGATION_REPORT_TESTING8.md` — 320 MiB / 5-slot C0
  candidate. Matched same-host one-shot A/B of mapping provenance and of CUDA
  context state. This is the strongest registration evidence in the repo.
- `reports/PRODUCTION_009_EASY_OPTIMIZATION_PASS.md` — 512 MiB and 1 GiB
  counted cohorts. This is the only 1 GiB registration evidence that exists.

---

## 1. Audit base SHA

```
AUDIT_BASE_SHA  = 211d204b06f1246bbd2b5b591473d7d08b629030
AUDIT_HEAD      = (see §19)
AUDIT_BRANCH    = audit/cuda-arena-lifecycle
AUDIT_WORKTREE  = .slim/worktrees/cuda-arena-lifecycle-audit
```

`211d204b` is `docs(golden-source): report the pathological source stall
mechanism`, the tip of `audit/vae-residency`, and it is the last commit shared
by **every** active lane. It was selected, not guessed:

```
git log --oneline --decorate -14 211d204b
  211d204b (audit/vae-residency)          docs(golden-source): report the pathological source stall mechanism
  975aec14                               fix(golden-config): let the source copy probe reach the container
  cfee2acf                               fix(golden-source): import the copy probe without a relative import
  28506a03                               chore(golden-diagnostic): add the isolated source-stall diagnostic profile
  dce3c4ac                               feat(golden-source): classify pathological mapped-copy stalls
  95e90b26                               docs: production-009 easy-optimization pass report and 3 profiler traces
  04dc0906                               fix(golden-unet): bound the layout pre-resolve join
  fbd81c46                               fix(golden-c0): make the source-thread arena gate track its owning module
  2465d990                               perf(golden-unet): resolve the dynamic UNET layout during CLIP load
  5b12fb47                               feat(golden-telemetry): decisive per-block source latency and placement evidence
  a6bd7d88                               perf(golden-c0): deepen the source arena to 16 x 64 MiB
  ccc2c531 (origin/main)                 docs: production-009 profiler derived reports (3 traced runs)
```

**Why this SHA satisfies the selection criteria**

| Required in the baseline | Present at `211d204b` | Evidence |
|---|---|---|
| Accepted 16-slot source architecture | yes | `a6bd7d88` is an ancestor; `golden_source_threads.py:76-78` gives `ARENA_BYTES = 16*64*1024*1024`, `SLOT_COUNT = 16`, `SLOT_BYTES = 64 MiB` |
| Phase-1 source diagnostics | yes | `dce3c4ac`, `28506a03`, `cfee2acf`, `975aec14`, and the Phase-1 report `211d204b` itself |
| NOT partial/unverified Phase-2/3 lane | excluded | The Triton Phase-2 lane is `ac56539b` → `d4613e19`, both **descendants** of `211d204b`, checked out detached in `.slim/worktrees/p8fix` |
| NOT the source-copy-isolation experiment | excluded | `cc2f541c` `feat(experiment): isolate source versus pinned-arena copy stalls` is a **descendant** of `211d204b` (`exp/source-copy-isolation`) |
| NOT the VAE audit lane's own work | excluded | `audit/vae-residency` was verified clean at `211d204b` before branching and is not modified |

`cc2f541c`'s own message independently confirms the parentage: *"fast_unit is
609 passed with only the two pre-existing test_rx9p_h_identity_chain failures
that 211d204b already documented."*

The dirty root checkout (`TESTING8` @ `61f99648`, with uncommitted studio edits
and untracked Phase-1 profiles) was not read from, modified, or used as a base.
`.slim/` is gitignored (`.gitignore:117`), so the new worktree cannot collide
with the active lanes' trees.

## 2. Branch and worktree

```
branch   audit/cuda-arena-lifecycle
worktree .slim/worktrees/cuda-arena-lifecycle-audit   (added from 211d204b, clean)
```

Isolation of other lanes at the time of branching:

| Lane | Location | State | Touched? |
|---|---|---|---|
| Root `TESTING8` / Phase-2/3 | root checkout + `.slim/worktrees/p8fix` @ `d4613e19` (detached) | dirty / active | **no** |
| Source-copy-isolation | `.slim/worktrees/source-copy-isolation` @ `cc2f541c` | active | **no** |
| VAE audit | `.slim/worktrees/vae-residency-audit` @ `211d204b` | clean | **no** (read-only base) |

---

## 3. Current arena lifecycle diagram

Counted profile: `config/v2/profiles/golden_p1_parallel_c0_source_h100.toml`
(`COMFYMODAL_GOLDEN_C0_SOURCE_THREADS=1`, `..._SOURCE_WORKER_KIND="thread"`,
`..._MMAP_LIFECYCLE="whole"`, `..._C0_HOST_REGISTER="1"`,
`COMFYMODAL_V2_MINIMAL_RESTORE="1"`, H100!, CPU 12, 24576 MB).

```
Modal container start
└─ startup()                                   modal_app.py:11291   [ snap=True ]
   ├─ ComfyUI forced to CPU mode               modal_app.py:12743   "snap=True forced ComfyUI
   │                                                                   into CPU mode so the snapshot
   │                                                                   carries no CUDA driver handles"
   ├─ NO CUDA call, NO arena, NO registration   verified: no ensure_arena_runtime /
   │                                           initialize_cuda / SharedArenaRing reference in
   │                                           modal_app.py:11291-12458
   └─ ── memory snapshot captured ──           modal_app.py:24535   enter(snap=...)(cls.startup)
                 ║
                 ║  Modal restores the process image; kernel/external objects are NOT in it
                 ▼
restore()                                       modal_app.py:12805   [ snap=False ]  modal_app.py:24537
├─ _golden_minimal_reset_container_state()     modal_app.py:12821
├─ _golden_minimal_restore_logical_gpu_state()  modal_app.py:12825   flags only, "Deliberately performs NO
│                                                                                 CUDA probe, synchronize, or memory query"
├─ _golden_minimal_assert_models_generation()   modal_app.py:12845   (runs AFTER the arena arm)
│
└─ IF COMFYMODAL_GOLDEN_C0_SOURCE_THREADS      modal_app.py:12836
   └─ GoldenModelTransport.initialize_cuda()    golden_model_transport.py:886
      ├─ prepare_cpu()
      ├─ ensure_arena_runtime()                 golden_model_transport.py:909 → golden_io_process_v2.py:11115
      │  ├─ [module singleton _C0_RUNTIME short-circuit]      golden_io_process_v2.py:11118
      │  ├─ SharedArenaRing(...) constructor    golden_io_process_v2.py:4209
      │  │  ├─ strict size == slot_count*slot_bytes           :4218
      │  │  ├─ source-thread geometry gate vs golden_source_threads  :4239-4244
      │  │  ├─ REQUIRE c0_host_register_enabled()              :4245-4246  -> "source_threads_requires_cuda_host_register"
      │  │  ├─ REQUIRE mmap_lifecycle in {fresh, whole}        :4249-4250
      │  │  └─ snapshot launch-time selectors                  :4333-4336
      │  └─ .ensure()                            golden_io_process_v2.py:4487
      │     ├─ marks[c0_ensure_enter]                            :4493
      │     ├─ _require_torch(); cudart = torch.cuda.cudart()   :4499-4501  marks[torch_required]
      │     ├─ [OPTIONAL] _preinit_primary_context()           :4503-4511  flag default OFF
      │     ├─ register = getattr(cudart,"cudaHostRegister")    :4513-4515
      │     ├─ SharedMemory(create=True, size=1 GiB)            :4518       3.50-6.93 ms [MEAS]
      │     │     -> /dev/shm/psm_* named POSIX segment
      │     ├─ torch.frombuffer(shm.buf, uint8)                 :4525       marks[torch_frombuffer_*]
      │     ├─ _shm_address(shm)  -> arena base address         :4528
      │     ├─ 16 slot views (tensor slices)                    :4530-4534  marks[slot_views_*]
      │     │
      │     │   DEFAULT registration_order == "overlap"         golden_io_process_v2.py:118-122
      │     ├─ SourceThreadProcess(arena_name, ...)             :4554       golden_source_threads.py:804
      │     │  ├─ creates CONTROL_BYTES shared block + FileLock  golden_source_threads.py:815-822
      │     │  └─ spawn()   Popen([python, __file__, --source-child, ...])  golden_source_threads.py:865-871
      │     │       env CUDA_VISIBLE_DEVICES=""      <-- CUDA-sterile
      │     │       marks[source_thread_spawn_begin/end]         :4553 :4567
      │     │        │
      │     │        │  CHILD PROCESS (concurrent)  ─────────────────────────────┐
      │     │        │  _child_main()               golden_source_threads.py:1978 │
      │     │        │   _init_native()  libc mmap/munmap/memmove only            │
      │     │        │   _PosixAttachment(arena_name, ARENA_BYTES)   <-- NAME attach, exec'd, no inheritance
      │     │        │   _PosixAttachment(control_name, CONTROL_BYTES)
      │     │        │   4 reader threads start, hit the startup barrier
      │     │        │   NO plan installed yet (plan_once is per-request)
      │     │        │   emit READY (geometry asserted equal to parent's)         │
      │     │        │                    684-933 ms @320 MiB [MEAS]              │
      │     │        └────────────────────────────────────────────────────────────┘
      │     │
      │     ├─ _register_arena()                 :4573-4582 (overlap arm)
      │     │  └─ rc = cudaHostRegister(arena_base, 1 GiB, flags=0)   :4453
      │     │     t0 = perf_counter()      :4450   <-- boundary OPEN
      │     │     ... call ...                   includes LAZY PRIMARY-CUDA-CONTEXT CREATION
      │     │     register_ms = perf_counter()-t0  :4459  <-- boundary CLOSE
      │     │     marks[cuda_host_register_begin/end]  :4449 :4458
      │     │     registered = True                  :4484
      │     │     552.5-956.7 ms, median 713 @1 GiB   [MEAS]
      │     │
      │     ├─ await_ready()  JOIN               :4584   marks[source_thread_ready]
      │     ├─ child_torch_imported / child_cuda_initialized must both be False   :4837-4842
      │     ├─ epoch += 1; created = True          :4617-4618
      │     └─ return self                         :4620
      │
      ├─ GoldenTransferResources.create_shared()  golden_model_transport.py:913 → golden_qd_transport.py:253
      │     one dedicated H2D stream + 16 reusable event PAIRS; NO pinned host allocation
      ├─ GpuDestinationPool(target)              golden_model_transport.py:921
      ├─ c0.new_stage_pool()  StagingPool over the 16 registered slot tensors  golden_model_transport.py:934
      │     └─ buffers=self._slot_tensors        golden_io_process_v2.py:5231
      └─ GoldenQDTransport(..., persistent_dispatcher=True).start()  golden_model_transport.py:938
      marks["source_transport_created_once"]     golden_model_transport.py:944
                 ║
                 ▼  restore complete, request begins
first model PLAN (CLIP, then UNET, then VAE reuse)
├─ SourcePlanBridge.publish_all()               golden_source_threads.py:1360
│  ├─ manager.plan_once(...)  installs ranges in the CONTROL block
│  └─ per READY_BLOCK doorbell:
│     ├─ manager.claim_ready(record)            golden_source_threads.py:1184
│     ├─ transport.adopt_external_slot(slot_index, generation, range, producer)  :1402
│     ├─ lease._external_release_callback = manager.release_slot(rec, completion_ns=now)  :1408
│     └─ transport.publish(lease, ready_record, externally_filled=True)  :1419
│        └─ Dispatcher._run()                   golden_qd_transport.py:2667
│           └─ CudaTransferBackend.submit_h2d_ticket -> _submit   golden_qd_transport.py:4305 / :4318
│              with torch.cuda.stream(h2d_stream):
│                  ticket.start_event.record(stream)                     :4336
│                  dest[off:end].copy_(arena_slot_view, non_blocking=True) :4337
│                  ticket.end_event.record(stream)                       :4341
│              ^ SOURCE IS THE REGISTERED POSIX-SHM SLOT VIEW
│           └─ Dispatcher._poll() polls ticket.end_event.query()  golden_qd_transport.py:2270 / :4353
│              └─ _return_completed -> lease._external_release_callback
│                 -> manager.release_slot()    golden_source_threads.py:1204   "only after H2D completion was proven"
UNET reuses the SAME arena, SAME registration, SAME stream/events (created once, restore-owned)
request teardown
└─ close()                                     golden_io_process_v2.py:5503
   ├─ stop source process; require the stop to be proven   :5517-5541
   ├─ _unregister()   cudaHostUnregister(arena_base)       :5542 → :5893
   └─ _release_mapping()  buf.release(); shm.close(); shm.unlink()   :5544 → :5909
```

## 4. Per-step lifecycle record

`CUDA ctx` = does the step require a current CUDA context in the parent.

| # | Step | File:line / function | Process | Thread | CUDA ctx | Snapshot-safe | Model-specific | Request-specific | Measured cost |
|---|---|---|---|---|---|---|---|---|---|
| 1 | container + `startup()` | `modal_app.py:11291`, `:24535` | parent | main | no | **this IS the snapshot** | no | no | out of scope |
| 2 | ComfyUI forced CPU-only | `modal_app.py:12740-12757` | parent | main | no (explicitly none) | yes | no | no | — |
| 3 | restore reset | `modal_app.py:12821` | parent | main | no | n/a (restore only) | no | no | `mutable_state_reset_ms` |
| 4 | logical GPU state flip | `modal_app.py:12825` | parent | main | no (explicitly none) | n/a | no | no | `logical_gpu_repair_ms` |
| 5 | `initialize_cuda()` | `golden_model_transport.py:886` | parent | restore thread | enters at 8 | **no** | no | no | wrapper of 6-12 |
| 6 | arena constructor gates | `golden_io_process_v2.py:4218-4250` | parent | restore thread | no | no | no | no | µs |
| 7 | torch + cudart resolution | `:4499-4501` | parent | restore thread | no | no | no | no | inside `pre_register_ms` |
| 8 | **[OPT] context preinit** | `:4503-4511`, `:306` | parent | restore thread | **creates it** | no | no | no | flag OFF; 288.4 ms when ON `[MEAS]` |
| 9 | POSIX SHM create | `:4518` | parent | restore thread | no | **no (kernel object)** | no | no | **3.50-6.93 ms** `[MEAS]` |
| 10 | `torch.frombuffer` | `:4525` | parent | restore thread | no | no | no | no | inside `pre_register_ms` |
| 11 | arena base address | `:4528` | parent | restore thread | no | no | no | no | µs |
| 12 | 16 slot views | `:4530-4534` | parent | restore thread | no | no | no | no | inside `pre_register_ms` |
| 13 | CONTROL shm + FileLock | `golden_source_threads.py:815-822` | parent | restore thread | no | no | no | no | µs |
| 14 | **`spawn()` source owner** | `golden_source_threads.py:865-871` | child created | restore thread | no (`CUDA_VISIBLE_DEVICES=""`) | no (a live process cannot be snapshotted) | no | no | `spawn_return_ns` |
| 15 | child interpreter + imports | `golden_source_threads.py:1978-1988` | **child** | child main | no | no | no | no | part of boot |
| 16 | child `/dev/shm` attach | `:1986-1987`, `_PosixAttachment:1552` | **child** | child main | no | no | no | no | part of boot |
| 17 | 4 reader threads + barrier | `:1847 _run_reader_loop`, `:2201` | **child** | 4 readers | no | no | no | no | part of boot |
| 18 | child emits READY | `:2003-2005`, `:893` | child | child main | no | no | no | no | **684-933 ms total boot @320 MiB** `[MEAS]` |
| 19 | **`_register_arena()`** | `golden_io_process_v2.py:4435`, call at `:4453` | parent | restore thread | **yes (creates it lazily)** | **no** | no | no | **552.5-956.7 ms, median 713** `[MEAS]` |
| 20 | `await_ready()` join | `:4584` | parent | restore thread | yes (now current) | no | no | no | `post_register_ms` (1 GiB value unknown) |
| 21 | sterility assertions | `:4837-4842` | parent | restore thread | yes | no | no | no | fail-closed |
| 22 | H2D stream + 16 event pairs | `golden_qd_transport.py:253-294` | parent | restore thread | yes | no | no | no | not separately reported |
| 23 | `GpuDestinationPool` | `golden_model_transport.py:921` | parent | restore thread | yes | no | no | no | not separately reported |
| 24 | `StagingPool` over slot views | `golden_io_process_v2.py:5231` | parent | restore thread | no new | no | no | no | µs |
| 25 | `GoldenQDTransport.start()` | `golden_model_transport.py:938-943` | parent | restore thread | yes | no | no | no | dispatcher thread spawn |
| 26 | first model PLAN | `golden_source_threads.py:927 plan_once`, `:1360 publish_all` | parent+child | request | yes | n/a | **yes** | **yes** | `plan_install_ms` |
| 27 | source memcpy into slot | `golden_source_threads.py:1690-1737` | **child** | 1 of 4 readers | no | n/a | yes | yes | 20-60 ms normal; 1-4.3 s sick `[MEAS]` |
| 28 | READY doorbell | `golden_source_threads.py:1780` | child | reader | no | n/a | yes | yes | µs |
| 29 | `adopt_external_slot` | `golden_qd_transport.py:1132` | parent | request | yes | n/a | yes | yes | µs |
| 30 | **H2D `copy_(non_blocking=True)`** | `golden_qd_transport.py:4337` | parent | dispatcher `_run` | yes | n/a | yes | yes | `h2d_*` telemetry |
| 31 | event poll → completion proof | `golden_qd_transport.py:2270`, `:4353` | parent | dispatcher `_poll` | yes | n/a | yes | yes | µs |
| 32 | `release_slot` | `golden_source_threads.py:1204` | parent | dispatcher | yes | n/a | yes | yes | µs |
| 33 | UNET / VAE reuse | steps 26-32 | parent+child | request | yes | n/a | yes (own ranges) | yes | **no second registration, no second stream, no second events** |
| 34 | `_unregister()` | `golden_io_process_v2.py:5893-5907` | parent | teardown | yes | n/a | no | container | `unregister_ms` |
| 35 | `_release_mapping()` | `golden_io_process_v2.py:5909-5936` | parent | teardown | no | n/a | no | container | µs |

**Ordering invariants that are code-enforced, not hoped for**

- `spawn_begin < source_thread_register_begin < await_ready` — asserted by
  `tests/test_cuda_arena_lifecycle_audit.py::test_registration_precedes_any_source_write_to_the_arena`.
- `ensure()` installs no plan and publishes no block, so a reader cannot write a
  slot before the registration call returns — also asserted by that test.
- `registration is a hard precondition`: `SharedArenaRing.__init__` raises
  `source_threads_requires_cuda_host_register` when
  `COMFYMODAL_GOLDEN_C0_HOST_REGISTER=0` (`:4245-4246`), and `ensure()` raises
  `source_threads_requires_registered_arena` if the selector is off at
  establish time (`:4550-4551`). Both are asserted by tests.

---

## 5. Exact `cudaHostRegister` caller chain

There is exactly **one** registration call site on the live C0 path, and it is
not spelled as a CUDA symbol — it is resolved by `getattr` and injected as a
parameter. That indirection is why the audit needed an AST check rather than a
grep; a grep for `cudaHostRegister(` reports zero hits in the arena path.

```
COMFYMODAL_GOLDEN_C0_SOURCE_THREADS == 1
  modal_app.py:24537            restore()                       [snap=False]
  modal_app.py:12836            if _source_threads_enabled:
  modal_app.py:12840              get_golden_model_transport().initialize_cuda()
  golden_model_transport.py:888    self.prepare_cpu()
  golden_model_transport.py:909      c0.ensure_arena_runtime()
  golden_io_process_v2.py:11118      if _C0_RUNTIME is not None and _C0_RUNTIME.created: return
  golden_io_process_v2.py:11148      runtime.ensure()
  golden_io_process_v2.py:4487        SharedArenaRing.ensure()
  golden_io_process_v2.py:4513          register = getattr(cudart, "cudaHostRegister", None)
  golden_io_process_v2.py:4576          self._register_arena(torch=..., register=register, cudart=..., marks=marks)
  golden_io_process_v2.py:4453            rc = int(register(self._arena_address, self.size_bytes,
                                                             _CUDA_HOST_REGISTER_DEFAULT))   # _CUDA_HOST_REGISTER_DEFAULT == 0
                                       -> libcuda cudaHostRegister  (torch.cuda.cudart() == the CUDA *runtime* API)
```

`ensure()` contains **three** `_register_arena(...)` call sites but at most one
executes in any container `[CODE]`:

| # | Guard | Reached when |
|---|---|---|
| 1 | `_do_register and registration_order == "register_first"` (`:4542`) | non-default order, before spawn |
| 2 | `registration_order != "register_first"` (`:4573`) | **the shipped default**, after `spawn()`, inside the `source_thread_mode` branch |
| 3 | `_do_register and registration_order != "register_first"` (`:4764`) | non-source-thread legacy child path |

Sites 1 and 2 are mutually exclusive on `registration_order`; the
`source_thread_mode` branch `return self`s at `:4620`, before site 3 is
reachable. Pinned by
`tests/test_cuda_arena_lifecycle_audit.py::test_arena_ensure_has_three_but_executes_at_most_one_registration`.

**Every other `cudaHostRegister`/`cuMemHostRegister*` in the tree, and whether it is live**

| Location | API | On the counted Golden C0 path? |
|---|---|---|
| `golden_io_process_v2.py:4453` (`_register_arena`) | runtime `cudaHostRegister` | **yes — the one** |
| `golden_io_process_v2.py:5903` (`_unregister`) | runtime `cudaHostUnregister` | yes — teardown |
| `golden_io_process_v2.py:~623` (`run_primitive_probe`) | runtime `cudaHostRegister` | no — standalone diagnostic, allocates its own buffers, never touches `self._arena_address` (asserted) |
| `golden_model_transport.py:962` | `cuMemHostRegister_v2` | no — the non-C0 `mp.RawArray` staging branch, skipped when `self._c0_enabled` |
| `source_race_gpu.py:195, :275` | `cuMemHostRegister_v2` | no — M2/race harness |
| `unet_salvage_probe.py:1175+`, `registration_probe.py:85, :110` | both | no — probes |
| `model_preload.py:16119 _pin_cpu_storages_for_transfer` | runtime `cudaHostRegister` | no — behind `_pinned_transfer_enabled()`; its single caller at `:17476` is the UNET legacy preload, not the C0 dispatcher |

**H2D call chain, source of truth for what registration buys**

```
golden_qd_transport.py:2667  TransportDispatcher._run()            (dispatcher thread)
golden_qd_transport.py:4305  CudaTransferBackend.submit_h2d_ticket(slot_index, submission_id)
golden_qd_transport.py:4318  CudaTransferBackend._submit(source, destination_offset, ticket=ticket)
  :4331   with torch.cuda.stream(self.stream):
  :4336       ticket.start_event.record(stream)
  :4337       self.destination[off:end].copy_(source, non_blocking=True)
  :4341       ticket.end_event.record(stream)
golden_qd_transport.py:2270  TransportDispatcher._poll()
golden_qd_transport.py:4353  CudaTransferBackend.poll_event(event) -> event.query()
golden_qd_transport.py:1419  StagingPool._return_completed -> lease._external_release_callback
golden_source_threads.py:1204  SourceThreadProcess.release_slot(record, completion_ns=...)
```

`source` is the arena slot tensor: `StagingPool._buffer_for_dispatch`
(`golden_qd_transport.py:1344`) returns `slot.buffer`, and those buffers are the
slices of `torch.frombuffer(shm.buf, uint8)` created at
`golden_io_process_v2.py:4525, :4530-4534`. `GoldenTransferResources.create_shared`
(`golden_qd_transport.py:253-294`) explicitly allocates **no** pinned host
staging — its own docstring says so, and a test asserts `create_shared` and
`new_stage_pool` contain no `pin_memory`, no `cudaHostAlloc`, no `torch.empty`.
So the ONLY pinned host memory in this architecture is the `cudaHostRegister`ed
POSIX arena.

## 6. Why registration is required

### 6.1 What API performs the H2D

`self.destination[off:end].copy_(source, non_blocking=True)`
(`golden_qd_transport.py:4337`), i.e. `torch.Tensor.copy_` CPU→CUDA on a
dedicated `torch.cuda.Stream`, which PyTorch lowers to `cudaMemcpyAsync` on that
stream. `[DOC]` PyTorch, `Tensor.copy_`:

> "**non_blocking** (bool, optional) – if `True` and this copy is between CPU and
> GPU, the copy may occur asynchronously with respect to the host. For other
> cases, this argument has no effect. Default: `False`"

Note the word **may**. That single word is the whole problem, and the CUDA
reference is explicit about it.

### 6.2 Does that API require pinned memory?

Not as an error condition — it never rejects a pageable source. Its
*semantics* differ, and the CUDA reference states exactly how. Verbatim from
the CUDA Runtime API, "API Synchronization behavior"
(`docs.nvidia.com/cuda/cuda-runtime-api/api-sync-behavior.html`):

> In the reference documentation, each memcpy function is categorized as
> synchronous or asynchronous, corresponding to the definitions below.
>
> **Synchronous**
>
> 1. For transfers from pageable host memory to device memory, a stream sync is
>    performed before the copy is initiated. The function will return once the
>    pageable buffer has been copied to the staging memory for DMA transfer to
>    device memory, but the DMA to final destination may not have completed.
> 2. For transfers from pinned host memory to device memory, the function is
>    synchronous with respect to the host.
> 3. For transfers from device to either pageable or pinned host memory, the
>    function returns only once the copy has completed.
> 4. For transfers from device memory to device memory, no host-side
>    synchronization is performed.
> 5. For transfers from any host memory to any host memory, the function is
>    fully synchronous with respect to the host.
>
> **Asynchronous**
>
> 1. For transfers between device memory and pageable host memory, the function
>    might be synchronous with respect to host.
> 2. For transfers from any host memory to any host memory, the function is
>    fully synchronous with respect to the host.
> 3. **If pageable memory must first be staged to pinned memory, the driver may
>    synchronize with the stream and stage the copy into pinned memory.**
> 4. For all other transfers, the function should be fully asynchronous.

Item 3 of the *Asynchronous* list is the decisive sentence: from a **pageable**
source, the driver *may synchronize with the stream* and *stage the copy into
pinned memory* — i.e. it may (a) block the calling thread and (b) add a full
extra host-to-host copy of the block through a small driver staging buffer.

### 6.3 What the current implementation requires of the H2D, and which parts depend on registration

| # | Required property | Where it is relied on | Depends on registration? |
|---|---|---|---|
| P1 | `copy_(non_blocking=True)` must return to the dispatcher thread promptly, so the next block can be claimed while the DMA runs | `_run` loop at `golden_qd_transport.py:2667-2816` submits serially on one dispatcher thread; `_run` is the only producer of submissions | **YES.** `[DOC]` Async-1: "might be synchronous with respect to host"; Async-3: driver "may synchronize with the stream and stage the copy into pinned memory" |
| P2 | QD4 pipelining: up to 4 slots in flight, so a source copy and an H2D overlap | `TransportConfig(queue_depth=4, ...)` at `golden_model_transport.py:924`; capacity semaphore at `golden_source_threads.py:1993` | **YES.** A synchronous submit collapses the pipeline to depth 1 |
| P3 | `ticket.end_event.record(stream)` must be a valid "H2D finished" marker | `golden_qd_transport.py:4341`; polled at `:4353` via `event.query()` | **PARTIALLY.** The event is always valid, but if the host thread was blocked inside `copy_`, the event is recorded *after* the copy is already complete, so the event no longer expresses DMA completion — it becomes a no-op timestamp |
| P4 | slot release only after proven H2D completion | `golden_source_threads.py:1204 release_slot` docstring: "Return a physical slot only after H2D completion was proven"; wired at `:1408` | **NO.** The proof mechanism survives; it would just fire later and serialize |
| P5 | one stable host pointer per slot for the container's life | `_arena_address` set once (`:4528`), registered once (`:4453`), unregistered once (`:5903`) | **YES**, in the sense that pinning is what makes the pointer DMA-safe; the pointer's *stability* does not need pinning |
| P6 | cross-process visibility of the same storage | child attaches by NAME via `_PosixAttachment` (`golden_source_threads.py:1552, :1986`) | **NO.** POSIX SHM provides this with or without registration |
| P7 | source child stays CUDA-sterile | `CUDA_VISIBLE_DEVICES=""` (`:870`), fail-closed at `golden_io_process_v2.py:4837-4842` | **NO** |
| P8 | the full-file `memmove` destination is host RAM the DMA engine can read | `execute_block` → `libc.memmove` into the slot (`golden_source_threads.py:1736`) | **NO.** The child only needs a writable mapping |

### 6.4 Correctness invariant that breaks without registration

**P1/P2: the dispatcher's queue depth collapses, and the source owner
deadlocks or starves.**

The source owner blocks readers on a capacity semaphore
(`golden_source_threads.py:1993 wake()`, `:1229 notify_capacity()`). Capacity is
returned **only** when a slot is released, and a slot is released **only** from
the dispatcher's proven-completion path. If `copy_(non_blocking=True)` from a
pageable source may block the dispatcher thread until the transfer completes,
then:

```
dispatcher thread blocked inside copy_ for slot k  ->  no submit for slot k+1
slot k released only after completion             ->  capacity token returned late
readers that already filled slots k+1..k+3 wait  ->  effective reader concurrency
                                                    drops toward 1
```

That is a **throughput collapse, not a data error** — the bytes are still
correct, and `release_slot`'s generation/`IN_FLIGHT` guards still hold. It
reproduces exactly the pathology the 16-slot change was made to remove, in a
worse form, and the existing `all_slots_occupied` / `slot_wait` telemetry would
light up. Note also that P3 degrades: the completion event stops being evidence
of *asynchronous* DMA and becomes evidence only that the (already synchronous)
copy returned.

A second, sharper correctness point specific to this codebase: the dispatcher's
source tensor is a **1-D CPU `uint8` torch tensor** and `_submit` rejects
anything else (`golden_qd_transport.py:4323-4324`). There is no fallback path
that could quietly substitute a pinned staging buffer. If registration were
simply deleted, the driver would silently insert its own internal staging buffer
— an allocation and a copy the dispatcher neither owns nor accounts for.

### 6.5 Performance invariant that breaks without registration

Two, in order of size:

1. **An extra full-block host→host copy.** `[DOC]` Async-3: the driver "may
   ... stage the copy into pinned memory". A 64 MiB block copied twice
   (file page cache → arena, then arena → driver staging) at ~1.1-1.6 GB/s
   effective (`wall 155-367 ms` against `20-40 ms` CPU for a single 64 MiB
   memmove, per `reports/P9_SOURCE_STALL_ROOT_CAUSE.md`) is a doubling of the
   source path's dominant cost.
2. **Loss of source/H2D overlap.** The whole point of the separate source owner
   is that reads and DMA proceed concurrently. A host-synchronous submit makes
   the DMA a serial tail on every block.

### 6.6 What registration buys, stated as one sentence

`cudaHostRegister` is not needed to *address* the arena, to *share* it, or to
*write* it. It is needed so that `cudaMemcpyAsync` on the dedicated H2D stream
is **fully asynchronous with respect to the host** for a 64 MiB block, which is
the only property that keeps the dispatcher's QD4 pipeline and the source
owner's four-reader concurrency alive.

This is exactly the constraint the repository recorded earlier:

> `M2_VS_E37_MINIMAL_OVERHEAD_AUDIT.md:321`
> `| 65.2 | cuMemHostRegister + alloc | **REQUIRED BY PROCESS+CUDA** / amortize once per container |`

and

> `golden_io_process_v2.py:1763-1765` (`c0_host_register_enabled` docstring)
> "the parent H2Ds directly from the registered shared mapping with **no
> shared->pinned copy**."

## 7. Historical working paths that did not appear to register

`REGISTRATION_INVESTIGATION_REPORT_TESTING8.md` §B already tabulated these.
That table is the primary evidence and is reproduced here with the conclusion
this audit draws, which is stronger than the report's own.

| Implementation | Mapping | Bytes | Host allocation | Explicit registration | Async H2D | CUDA stream ownership | Measured H2D / register | Why it worked without the current registration shape |
|---|---|---:|---|---|---|---|---|---|
| **TESTING8** (the C0 ancestor) | `multiprocessing.shared_memory.SharedMemory` on `/dev/shm` | 320 MiB | POSIX SHM, pageable until registered | **yes** — torch `cudaHostRegister`, flags 0 | yes, after registration | one dedicated stream, events per slot | register 414.7–642.8 ms | Not an exception: this one registers. It is the current design. |
| **production-005** `a186d4c` | POSIX `SharedMemory` | 512 MiB (8×64) | POSIX SHM | **yes** | yes | same | register 402.9–583.1 ms | Same. |
| **standalone M2** `ef34e23` | `mp.RawArray`, anonymous inherited shared mapping | QD4×2×64 = 512 MiB | anonymous `MAP_SHARED`, fork-inherited | **yes** — raw `cuMemHostRegister_v2`, flags 0 | yes | raw driver context created explicitly; stream created explicitly | register 24.9–45.9 ms replayed on today's H100 | It *did* register. The difference is the **mapping primitive** (anonymous vs `/dev/shm`) and an **explicitly created raw driver context** — not the absence of registration. |
| **optimized M2** `3f38b26` | anonymous `mmap(-1, ...)`, shared inherited | 256 MiB | anonymous | **yes** | yes | raw driver context, context init overlapped reader fork/prep | report separates `ctx_init_ms`, `register_ms`, alloc | Same. Context init was overlapped with reader prep — the same trick C0 later adopted for `spawn()`. |
| **E37** (per `M2_VS_E37_MINIMAL_OVERHEAD_AUDIT.md:18, :207`) | n/a | n/a | **torch `pin_memory` caching host allocator** | **no explicit call** — the allocator registers/allocates internally | yes | n/a | `cuMemHostRegister` line delta 65 ms → 0 | It did not need an explicit call because the *allocator* performed the registration. `torch.empty(..., pin_memory=True)` is a registration mechanism with a different API surface, not a way to avoid registration. |
| **`inprocess-pinned-source-threads`** `f525efba` | in-process, no second process | n/a | torch pinned | no explicit call | yes | parent-owned | raw evidence for the pinned-destination A/B/C/D campaign | Same as E37, plus it dropped the second process entirely. |
| **`exp/inprocess-pinned-source-threads` / C0 DMA ring** (`golden_io_process_v2.py` `C0DmaRing`, default OFF) | parent-only 2 × 64 MiB `torch.empty(..., pin_memory=True)` | 128 MiB | torch pinned | no explicit call | yes | parent-owned | `pinned_alloc_ms` recorded | Same. Note this arm **also** still uses the registered SHM arena as its *source*; it adds pinned staging, it does not replace registration. |

### The answer to "why did those work without explicit registration?"

Three distinct reasons, and **none of them is "pageable memory is fine for
async H2D"**:

1. **An allocator did the registration for them.** `pin_memory=True` routes to
   PyTorch's caching host allocator, which is documented to use
   `cudaHostRegister`/`cudaHostAlloc` internally (PyTorch's CUDA notes expose
   the `pinned_use_cuda_host_register` switch for exactly this choice). No
   explicit call in application code, same pinned pages.
2. **They were not cross-process.** Every no-explicit-call path (E37,
   `inprocess-pinned-source-threads`, `C0DmaRing`) is either in-process or
   parent-only. None of them had to hand the buffer to a `CUDA_VISIBLE_DEVICES=""`
   child that attaches by name. The one path that *was* cross-process — M2 —
   registered explicitly, via the raw driver API.
3. **The cheap ones were cheap because of the mapping primitive, not the
   absence of registration.** `[MEAS]`, 320 MiB, matched host and API:
   POSIX `/dev/shm` 191.4 ms vs anonymous `MAP_SHARED` 66.0/67.2 ms vs anonymous
   `MAP_PRIVATE` 91.9 ms vs historical `RawArray` + raw driver context
   24.9/45.9 ms — a ~2.9x provenance effect.

The trap in the original question is real and worth naming: M2's `RawArray`
read like "anonymous memory, no registration" in most summaries, but
`golden_model_transport.py:962` and `source_race_gpu.py:195` show the M2 path
**does** call `cuMemHostRegister_v2`, and
`M2_VS_E37_MINIMAL_OVERHEAD_AUDIT.md:207` says so explicitly
(*"cudaHostRegister is not avoidable by 'allocate pinned in parent before
fork'"*).

## 8. Registration semantics: documented vs Linux vs gVisor vs inference

### 8.1 What NVIDIA documents

`cudaHostRegister` `[DOC]` (CUDA Runtime API, `group__CUDART__MEMORY`):

> "Registers an existing host memory range for use by CUDA."
>
> "Page-locks the memory range specified by `ptr` and `size` and maps it for the
> device(s) as specified by `flags`. This memory range also is added to the same
> tracking mechanism as `cudaHostAlloc()` to automatically accelerate calls to
> functions such as `cudaMemcpy()`."
>
> "On systems where `pageableMemoryAccessUsesHostPageTables` is true,
> `cudaHostRegister` will not page-lock the memory range specified by `ptr` but
> **only populate unpopulated pages**."
>
> "Page-locking excessive amounts of memory may degrade system performance, since
> it reduces the amount of memory available to the system for paging."
>
> Flags: `cudaHostRegisterDefault` — "the memory will be both mapped and
> portable"; `cudaHostRegisterPortable` — "considered as pinned memory by all
> CUDA contexts, not just the one that performed the allocation";
> `cudaHostRegisterMapped` — "Maps the allocation into the CUDA address space";
> `cudaHostRegisterReadOnly` — "treated as pointing to memory that is considered
> read-only by the device".
>
> Alignment: "The pointer `ptr` and size `size` must be aligned to the host page
> size (4 KB)."
>
> `cudaHostUnregister`: "Unmaps the memory range whose base address is specified
> by `ptr`, and makes it pageable again. The base address must be the same one
> specified to `cudaHostRegister()`."

`cudaDevAttrPageableMemoryAccessUsesHostPageTables` `[DOC]`:

> "Device accesses pageable memory via the host's page tables."

`cudaDevAttrHostRegisterSupported` `[DOC]`:

> "Device supports host memory registration via `cudaHostRegister`."

The codebase already queries attribute 99 (`cudaDevAttrHostRegisterSupported`)
and 113 (`cudaDevAttrHostRegisterReadOnlySupported`) in its diagnostic arms. It
does **not** query attribute 92 (`cudaDevAttrPageableMemoryAccessUsesHostPageTables`).
That is a real, cheap gap — see §17.

### 8.2 Linux behaviour `[CODE]/[INFER]`

Not documented by NVIDIA; stated as inference from the API contract plus the
measured RSS transition.

- Registration of an **unpopulated** anonymous or file-backed range must first
  make the pages exist, because a DMA target must be a real page. The
  `pageableMemoryAccessUsesHostPageTables` sentence confirms this explicitly for
  that class of device: it "will not page-lock ... but only populate unpopulated
  pages".
- Registration of an **already populated** range pins/locks existing pages and
  builds the device mapping; it does not need to allocate them.
- Linux pinning is per-page `get_user_pages` + `pin` accounting plus page-table
  and IOMMU mapping work, so the cost is expected to scale with **page count**,
  not with bytes of payload. `AnonHugePages=0` was observed, i.e. 4 KiB pages
  throughout.

### 8.3 gVisor behaviour `[MEAS]`

Everything below is from `REGISTRATION_INVESTIGATION_REPORT_TESTING8.md` §C,
§H, at 320 MiB on H100! under gVisor:

| Observation | Value |
|---|---|
| `Rss` before → after registration | **0 → 327680 kB** |
| `Private_Dirty` before → after | **0 → 327680 kB** |
| `VmLck` (`Locked`) before → after | **0 → 0 kB** |
| mapping flags | `rd wr sh mr mw ms`, `AnonHugePages=0` |
| `numa_maps` | **unavailable** |
| rusage page-fault deltas | **zero** (non-authoritative under gVisor) |
| `cuCtxGetCurrent` before → after | **`0x0` → nonzero** |

Two consequences that matter:

- **`VmLck == 0` after registration.** Under gVisor the classic "locked pages"
  counter is not maintained, so the standard signal for "these pages are pinned"
  is absent. That is a measurement-environment limitation, not evidence that
  nothing was pinned — the DMA engine demonstrably reads the range directly at
  4.78-5.93 GB/s with no staging copy (`PRODUCTION_009` §9), which is only
  possible from real pinned pages.
- **`Rss 0 → full` is direct evidence that registration materialised the range
  in this environment.** Because `Rss` was *zero* before the call, the pages did
  not exist before it; because it became exactly the mapping size after, the
  call created them.

### 8.4 Answers to the eight Step-4 questions

| # | Question | Answer | Label / basis |
|---|---|---|---|
| 1 | Does registration fault/populate every arena page? | **For an unpopulated range, yes — measured.** `Rss 0 → 327680 kB`, `Private_Dirty 0 → 327680 kB`. | `[MEAS]` 320 MiB |
| 2 | Does it merely lock/map existing pages? | **Only when they already exist.** `[DOC]`: on `pageableMemoryAccessUsesHostPageTables` devices it "will not page-lock ... but only populate unpopulated pages" — i.e. population is the floor even there. | `[DOC]` + `[MEAS]` |
| 3 | Can registration itself cause the arena's physical pages to be allocated? | **Yes, and in this code it does.** It is the first touch. | `[MEAS]` |
| 4 | Does whoever touches the pages first influence placement before registration? | **Yes, in principle — and in this code the answer is "nobody does".** Before registration the range is `Rss=0`; the only writer (the source child) is not started until `spawn()`, and receives no plan until after `await_ready()`. | `[MEAS]` + `[CODE]` |
| 5 | Does registration alter NUMA placement? | **Unknown, and unmeasurable here.** `[DOC]` says nothing about NUMA. `numa_maps` is unavailable under gVisor in both this repo's attempts (`golden_io_process_v2.py:232-240`; `PRODUCTION_009` §15 records `numa_maps` unavailable in all ten runs). | `unknown` |
| 6 | Can registration migrate pages? | **No documented guarantee either way.** A range that is already resident is documented to be locked, not relocated. A range that is unpopulated has no prior placement to migrate. | `[INFER]`, from `[DOC]` silence |
| 7 | Does registration of `/dev/shm` behave differently from anonymous memory? | **Yes, measurably.** 320 MiB, matched host/context/API: POSIX SHM 191.4 ms vs anonymous `MAP_SHARED` 66.0/67.2 ms (~2.9x). | `[MEAS]` |
| 8 | Does shared-memory registration have special limitations? | **None documented.** `[DOC]` alignment (4 KB) and unregister-same-base are the only stated constraints. `[MEAS]` the measured pointer had `mod 4096 = 0`. Overlap is not addressed by the documentation; it returns `cudaErrorHostMemoryAlreadyRegistered`, which is the only stated signal for a conflicting range. | `[DOC]` + `[CODE]` |

## 9. Snapshot / restore analysis

### 9.1 Is CUDA initialized before snapshot?

**No, and it is deliberately not.** `[CODE]`

- `modal_app.py:24535`: `startup` is decorated `enter(snap=_resolve_enable_memory_snapshot())` → `snap=True`.
- `modal_app.py:12743-12747` (`_golden_minimal_restore_logical_gpu_state` docstring):
  > "snap=True forced ComfyUI into CPU mode so **the snapshot carries no CUDA
  > driver handles**; model placement and CUDA-only attention paths need GPU
  > state before the first execution. Deliberately performs NO CUDA probe,
  > synchronize, or memory query: the first genuine GPU use pays the driver
  > cost."
- The entire `startup` body (`modal_app.py:11291-12458`) contains **no**
  reference to `ensure_arena_runtime`, `initialize_cuda`, or `SharedArenaRing`
  (verified by grep over that line range).

So the answer to "is CUDA intentionally forbidden during snapshot" is: not by an
explicit guard, but by construction and by the CPU-mode forcing. That is a
stronger guarantee than a guard, because it is the state the snapshot was built
in.

### 9.2 Is registration associated with process, context, driver state, VA, or backing?

| Association | Verdict | Basis |
|---|---|---|
| **process** | YES — registration is per-process state in the parent | `cudaHostUnregister` "must be the same one specified to `cudaHostRegister()`" `[DOC]`; the code calls it from the same object's `_unregister` `[CODE]` |
| **CUDA context** | YES — `[DOC]` `cudaHostRegisterPortable` distinguishes "pinned memory by all CUDA contexts, **not just the one that performed the allocation**", which only makes sense if the default binding is context-local | `[DOC]` |
| **CUDA primary context** | YES — the range is bound to whichever context is current at the call | `[MEAS]` `cuCtxGetCurrent` was `0x0` before and nonzero after; the preinit arm (`golden_io_process_v2.py:306`) exists precisely to make the primary context current first |
| **driver state** | YES — it is driver bookkeeping (`getattr(cudart, ...)` → `libcuda`) | `[CODE]` |
| **virtual address** | YES — the API is `ptr`+`size`; same address is required to unregister | `[DOC]` |
| **physical backing** | YES — page locks and the DMA mapping are on the physical pages | `[DOC]` `[MEAS]` |

### 9.3 After restore, what is preserved?

| Thing | Preserved across Modal's memory snapshot? | Basis |
|---|---|---|
| same virtual address | **Yes, for heap/stack the snapshot restores the process image** — but irrelevant, because the arena does not exist in the snapshot | `[CODE]` (arena is created in restore) |
| same backing pages | **No.** The arena is a `/dev/shm/psm_*` kernel object created by `SharedMemory(create=True)` at `golden_io_process_v2.py:4518`, i.e. **during restore**. A process memory snapshot cannot contain a kernel-owned IPC object. | `[CODE]` + `[INFER]` |
| same process | Yes (the parent container process is the snapshot unit) | `[DOC]`/Modal semantics |
| same CUDA context | **No — deliberately.** The snapshot carries no CUDA driver handles by design. | `[CODE]` quoted above |
| same CUDA driver state | **No**, for the same reason | `[CODE]` |
| the registered range | **No.** There is nothing to preserve: it is created after restore. | `[CODE]` |

### 9.4 Can registration survive snapshot restore in principle?

**No, and not merely "not currently".** `[INFER]` from `[DOC]`:

- A registered range requires a current CUDA context at the call
  (`cudaHostRegisterDefault` binds to the calling context). The snapshot
  deliberately contains no CUDA context, so on restore the binding target does
  not exist.
- It also requires the virtual address and the physical backing to be the ones
  that were registered. A process memory snapshot preserves neither the CUDA
  context nor any kernel IPC object.
- Additionally, Modal's `snap=True` snapshot is a memory image of a
  CPU-only, CUDA-driver-handle-free process. Even if a driver could restore its
  own bookkeeping, the pinned-page and IOMMU state is host kernel state outside
  the image.

### 9.5 If not, what exactly becomes invalid?

Everything downstream of "a current CUDA context in this process at this virtual
address over these physical pages". Concretely, on restore the following would
all be invalid if they had existed in the snapshot: the primary context handle,
the registered-range binding, the DMA/IOMMU mapping, the H2D stream, and the 16
CUDA event pairs (`golden_qd_transport.py:278-288`).

### 9.6 Could the arena backing exist in the snapshot while registration happens after restore?

**No, for the current primitive, and it would not help anyway.**

- It cannot: the backing is a `/dev/shm` POSIX segment, not process memory. A
  memory snapshot does not carry it, so "in the snapshot" is not a reachable
  state for this primitive. `[INFER]`
- Even if the backing could be carried (e.g. an anonymous `MAP_SHARED` region,
  which *is* process memory), it would have to be re-created by a
  fork-without-exec or re-`mmap` after restore, and then it would carry 1 GiB of
  dirty page-table state into the snapshot image for no benefit.

### 9.7 Would snapshotting 1 GiB of arena backing be wasteful even if registration were deferred?

**Yes, and materially so.** `[INFER]`

- The image is written and read on every container start. 1 GiB of
  zero-then-dirtied anonymous pages is at minimum ~1 GiB of extra I/O per
  cold start, on top of the ~713 ms already being spent.
- The 16-slot change showed the arena is the binding constraint for the larger
  UNET model in 3 of 10 runs (`PRODUCTION_009` §9), so the capacity cannot just
  be shrunk to make the snapshot cheap.
- There is no correctness benefit: the pages would have to be re-registered
  after restore regardless.

### 9.8 Hard conclusion

```
REGISTRATION_MUST_BE_POST_RESTORE
```

Not `NEEDS_RUNTIME_PROOF`. The code already runs it post-restore, the snapshot
is deliberately CUDA-free, and the documented context/address/backing binding
makes survival impossible in principle. `ARENA_BACKING_CAN_EXIST_IN_SNAPSHOT
= no` for the POSIX-SHM primitive, on the same reasoning.

This is the one Step-5 question that resolves without a GPU measurement, and it
resolves against moving any part of this work earlier than restore.

---

## 10. First-touch / page-placement audit

### 10.1 Who touches each arena page first, in the current code

```
SharedMemory(create=True, size=1 GiB)        golden_io_process_v2.py:4518
    -> shm_open + ftruncate.  NO physical pages.   [MEAS] 3.50-6.93 ms for 1 GiB
torch.frombuffer(shm.buf, uint8)             :4525   maps, does not touch
_shm_address(shm)                             :4528   ctypes addressof, does not touch
16 slot views                                 :4530   tensor slicing, does not touch
<<< FIRST PHYSICAL TOUCH HAPPENS HERE >>>     golden_io_process_v2.py:4453
cudaHostRegister(arena_base, 1 GiB, 0)
    Rss 0 -> 327680 kB, Private_Dirty 0 -> 327680 kB     [MEAS] 320 MiB
spawn() -> child maps by name                golden_source_threads.py:865, :1986   (maps only)
child reader threads memmove into slots       golden_source_threads.py:1736       (AFTER the plan exists)
```

### 10.2 The eight questions

| # | Question | Answer | Label |
|---|---|---|---|
| 1 | Before registration, are arena pages physically instantiated? | **No.** `Rss=0`, `Private_Dirty=0`, `Locked=0` immediately before the call. | `[MEAS]` |
| 2 | Does creation/truncation allocate physical pages? | **No.** 1 GiB in 3.50-6.93 ms is ~150-290x faster than page population; the cost is `shm_open`+`ftruncate`. | `[MEAS]` + `[INFER]` |
| 3 | Does registration instantiate them? | **Yes.** `Rss 0 → 327680 kB`, `Private_Dirty 0 → 327680 kB`, exactly the mapping size. | `[MEAS]` |
| 4 | Does the source write become the first physical touch? | **No.** The parent registers first, and the child is given no plan until after `await_ready()`. | `[CODE]` |
| 5 | If readers were first touch, which thread/CPU decides placement? | **Not applicable today.** If registration were removed or deferred, it would be whichever of the four reader threads happened to write each slot. `[INFER]` | — |
| 6 | Could four reader threads first-touch different arena chunks onto different NUMA nodes? | **Yes — but only in a hypothetical without registration.** With registration this mechanism is *absent*. | `[INFER]` |
| 7 | Is this observable under gVisor? | **No.** `numa_maps` unavailable; `_proc_mapping_snapshot` labels its own smaps reliability `supporting_only_on_gvisor` (`golden_io_process_v2.py:229`); `PRODUCTION_009` §15 records arena NUMA unavailable in 10/10 runs. `sched_getcpu` also unavailable (`P9_SOURCE_STALL_ROOT_CAUSE.md` §13). | `[MEAS]` |
| 8 | Could a deterministic pre-touch make placement more stable? | **Architecturally plausible, and empirically UNPROVEN-TO-BREAKEVEN.** See §10.3. | — |

### 10.3 Pre-touch: plausible mechanism, already-tested negative result

`cudaHostRegister` is the first touch, so a deterministic pre-touch **would**
move first-touch placement from "whichever CPU the CUDA driver walks on during
registration" to "whichever CPU we choose". That is architecturally coherent
and `COMFYMODAL_GOLDEN_C0_SHM_POPULATE` / `c0_populate_shm_parallel`
(`golden_io_process_v2.py:1706+`, default **OFF**, 8 workers, disjoint
page-aligned slices, one real `libc.memset` each) already implements exactly
that.

**But it has already been run**, and the result is recorded
(`REGISTRATION_INVESTIGATION_REPORT_TESTING8.md` §H):

> "This agrees with the prior populate experiment: **prepopulation can make the
> registration subspan faster but costs more in population plus registration
> end-to-end. No new evidence supports prepopulation as an optimization
> recommendation.**"

There is also a documented reason it could be a no-op on some hardware:
`[DOC]` "On systems where `pageableMemoryAccessUsesHostPageTables` is true,
`cudaHostRegister will not page-lock the memory range specified by `ptr` but
only populate unpopulated pages" — on such a device a pre-populated range has
nothing left to populate, so the treatment degenerates to the population cost
alone.

**Verdict: worth exactly one A/B on a NUMA-observable host, as a placement
control, not as a speed treatment.** It must not be bundled into a registration
experiment, because it has a measured net-negative end-to-end result.

## 11. Relationship to the source-copy sickness

Observed pathology `[MEAS]` (`reports/P9_SOURCE_STALL_ROOT_CAUSE.md`,
`211d204b`): isolated 64 MiB copies occasionally take 1–1.5+ s (worst observed
in the wider cohort 4.3 s) with `wall/cpu` p50 ≈ 1.03-1.10; zero major faults,
zero minor faults, zero `inblock`, zero context switches, on every copy over
100 ms and every copy over 1000 ms. Classified 99.5% `CPU_MEMORY_STALL`.

### 11.1 Candidate mechanisms, one by one

| Candidate | Verdict | Basis |
|---|---|---|
| registration first-touches destination pages | **CONFIRMED as the mechanism, not as the fault.** `Rss 0 → full` at the call. | `[MEAS]` |
| registration pins pages before NUMA placement is settled | **POSSIBLE, untestable here.** `[DOC]` says nothing about NUMA; `numa_maps` unavailable. | `[INFER]` |
| registration forces page allocation | **CONFIRMED.** Same RSS/Private_Dirty transition. | `[MEAS]` |
| registration causes page-table fragmentation | **UNTESTED.** No counter for it exists in this environment. | `unknown` |
| registration changes cache/TLB behaviour | **UNTESTED and unfalsifiable here** — nothing in the telemetry observes it. | `unknown` |
| large pinned region affects reclaim/compaction | `[DOC]` "Page-locking excessive amounts of memory may degrade system performance, since it reduces the amount of memory available to the system for paging." The 16-slot change raised pinned bytes from 512 MiB to 1 GiB. | `[DOC]` + `[INFER]` |
| 1 GiB pinning affects source mmap page availability | **UNMEASURED.** The two compete for the same 24576 MB cgroup; nothing records cgroup pressure during the copies. | `unknown` |
| destination pages are distributed inconsistently | **POSSIBLE, untestable here.** If the driver's registration walk is single-threaded it would place the whole range by one CPU's node; the source pages are first-touched by four readers on arbitrary CPUs. A cross-node `memmove` produces exactly `wall ≈ cpu`, no faults. | `[INFER]` |

### 11.2 What this audit adds that the Phase-1 report could not see

Phase-1 correctly declined to name a mechanism and correctly said NUMA was
unobservable. This audit establishes one **structural** fact that changes which
hypotheses are still live:

> **The four source readers are NOT the first touch of the arena.** The CUDA
> driver's registration walk is. `[MEAS]` `Rss=0` before the call.

Consequences:

1. **One live hypothesis is eliminated.** "The four readers first-touch different
   arena chunks onto different NUMA nodes" — the mechanism the Phase-1 report
   flagged as a possible explanation for uniform reader involvement — **cannot
   be operating on the current 16-slot registered arena.** It would become
   operating the moment registration were removed or deferred, which means a
   "just drop registration" experiment is not a neutral change to this
   pathology: it would *introduce* a placement variable.
2. **A different hypothesis is promoted.** A single-threaded-or-few-threaded
   registration walk can place all 1 GiB by one CPU's node, while the
   Volume-backed source pages are first-touched by four readers. A cross-node
   `memmove` is CPU-bound, fault-free, and thread-CPU-tracking. That is the
   observed signature.
3. **The timing correlation is suggestive but not evidence.** `PRODUCTION_009`
   §9: the extra 512 MiB of registration cost ~240 ms median, and the same
   report records that 2 of 10 counted runs became source-path pathological
   while the other 8 were healthy. Two runs is not a trend, the cohorts differ,
   and the sick runs were not characterised as sick *after* the change.
4. **The `[DOC]` reclaim warning is a real, unpriced cost** of the 16-slot
   change, and it has never been measured. This is the one place where the
   512 MiB→1 GiB decision and the source sickness could share a cause through a
   documented mechanism rather than a guess.

### 11.3 Verdict

```
POSSIBLY_RELATED
```

Not `LIKELY_RELATED` — no measurement in this environment can separate it, and
`numa_maps` is unavailable in every attempt recorded here. Not
`NO_EVIDENCE_OF_RELATION` — there is a confirmed first-touch-by-registration
fact, a `[DOC]` reclaim warning that scales with the pinned region, and an
unmeasured cgroup interaction. Not `UNRESOLVED` — that would discard the
structural finding, which is solid.

The discriminating experiment is *not* a registration experiment. It is the one
`PRODUCTION_009` §17 already nominated — make arena NUMA observable (non-gVisor
host, or read placement from the mapping's own `numa_maps`) and record it
**immediately after registration**, before any reader has written — plus one
new element this audit adds: record cgroup memory pressure across the copies, so
the `[DOC]` reclaim path becomes observable.

## 12. Alternative host-memory constructions

Fixed constraints every option is scored against:
**(C1)** the source owner is a *separately exec'd* process
(`subprocess.Popen([sys.executable, ...])`, `golden_source_threads.py:865`) so
it cannot inherit parent address space; it reaches the arena **by name**
(`_PosixAttachment`, `:1986`).
**(C2)** it runs with `CUDA_VISIBLE_DEVICES=""` and the parent fails the launch
if `torch_imported` or `cuda_initialized` is true (`:4837-4842`).
**(C3)** H2D must be fully asynchronous so the QD4 pipeline survives (§6).
**(C4)** pointer ownership, event authority, and slot-release-on-proven-H2D stay
in the parent (`SourcePlanBridge` docstring, `golden_source_threads.py:1348`).

| | A. POSIX SHM + `cudaHostRegister` (current) | B. `cudaHostAlloc` | C. `cudaHostAlloc` + Mapped | D. `torch.empty(pin_memory=True)` | E. Torch caching host allocator | F. POSIX SHM + **partial** registration | G. anonymous `mmap` + registration |
|---|---|---|---|---|---|---|---|
| **C1** source child reaches the same storage | **yes** (by name) | **NO** — parent address space, exec'd child cannot see it | **NO** | **NO** | **NO** | **yes** (by name) | **NO** — `MAP_SHARED` anonymous is shared only across `fork()`, and `Popen` execs |
| Shared across processes | yes | no | no | no | no | yes | fork-only |
| **C2** source stays CUDA-sterile | **yes** | yes | yes | yes | yes | **yes** | yes |
| **C3** H2D stays async | **yes** | yes | yes | yes | yes | **yes for registered slots only** | yes |
| CUDA events authoritative | yes | yes | yes | yes | yes | **only if the slot is registered** | yes |
| **C4** pointer ownership in parent | **yes** | yes | yes | yes | yes | **yes** | yes (fork-inherited only) |
| Physically committed at allocation | no (`Rss=0`) | yes | yes | yes | yes | no for the unregistered tail | no |
| Pinned at allocation | no — pinned later, once | **yes, at allocation** | **yes** | **yes** | **yes** | partially | no — pinned later |
| Cleanup semantics | `unregister(same base)` then `close/unlink` | `cudaFreeHost` | `cudaFreeHost` | caching allocator returns to the pool | same | N × `unregister` then the rest | `unregister` + `munmap` |
| Snapshot semantics | post-restore (backing is a kernel object) | post-restore | post-restore | post-restore | post-restore | post-restore | backing *could* be snapshotted but would buy nothing (§9.7) |
| Expected alloc cost `[MEAS]` | **3.50-6.93 ms** (SHM) + 553-957 ms (register) | not measured here; the in-tree `C0DmaRing` records `pinned_alloc_ms` and allocates **128 MiB** | not measured | not measured; PyTorch may route through `cudaHostRegister` internally | not measured | SHM + N × per-call register | 24.9-67.2 ms at 320 MiB `[MEAS]` |
| Memory footprint | 1 GiB SHM + 1 GiB pinned | 1 GiB pinned (replaces SHM) | same | same | same | pinned prefix only | 1 GiB pinned |
| Implementation complexity | shipped | would need source restructure | same + device-pointer plumbing | would need source restructure | same | **dispatcher slot-state changes** | **process-topology change** |
| Correctness risk | none (shipped) | breaks C1 | breaks C1 | breaks C1 | breaks C1 | dispatcher must never dispatch an unregistered slot | breaks C1 unless fork-without-exec |
| Verdict | **baseline** | **infeasible** | **infeasible** | **infeasible** | **infeasible** | **feasible, medium risk (§13)** | **infeasible** |

**The binding constraint is C1, and it is not a preference.** Any option that
allocates host memory in the parent's address space is unreachable by a child
that is `exec`'d. Only a *named* kernel object survives `exec`. That single fact
eliminates B, C, D, E, and G for the current source architecture — and it is
why `M2_VS_E37_MINIMAL_OVERHEAD_AUDIT.md:163` records torch `pin_memory` as
failing on "process-shared mmap needs pinning" in the *other* direction, and
`:207` states "cudaHostRegister is not avoidable by 'allocate pinned in parent
before fork'".

Option G is the interesting near-miss: it is the cheapest measured primitive
(24.9-67.2 ms at 320 MiB vs POSIX 191.4 ms, `[MEAS]`) and it is exactly what
historical M2 used. It is excluded only because M2's readers were **forked**,
not exec'd. Restoring that would mean changing the source process topology —
which the task's own constraints forbid, and which would put a forked
post-CUDA child on the table. **Not recommended, recorded for completeness.**

## 13. Partial-registration feasibility

### 13.1 Geometry: arithmetically valid `[DOC]` + `[CODE]`

`[DOC]` "The pointer `ptr` and size `size` must be aligned to the host page size
(4 KB)." A 64 MiB slot stride is 16384 pages, so every slot sub-range is
4 KB-aligned relative to a 4 KB-aligned base. `[MEAS]` the measured pointer had
`mod 4096 = 0`. Ranges are disjoint by construction. Overlap returns
`cudaErrorHostMemoryAlreadyRegistered`, the only stated signal for a
conflicting range, so a disjoint partition is exactly the shape the API
describes.

This is proved mechanically by
`comfymodal_runtime/cuda_arena_lifecycle_audit.py::slot_registration_plan` and
tested (`slot_stride_page_aligned`, `all_prefix_ranges_disjoint`,
`strict_product_holds`, clamping, and fail-closed on a geometry mismatch).
Its own docstring states the limit: *"Acceptance, thread-safety against an
in-flight H2D, and cost are NOT established here."*

### 13.2 Option A — register only N of 16 slots

| Question | Answer |
|---|---|
| Can unused slots stay unregistered until needed? | Geometrically yes. |
| Would the dispatcher know which ranges are registered? | **Not today.** `StagingPool` has no "this slot is unregistered" state. `_buffer_for_dispatch` (`golden_qd_transport.py:1344`) returns `slot.buffer` for any `IN_FLIGHT` retired lease, and `StagingPool` hands free slots to whichever producer leases next — there is no prefix-static allocation to piggyback on. A partially-registered arena would therefore hand the dispatcher an unregistered view with **no error**, and `copy_(non_blocking=True)` would silently take the documented pageable path. |
| Could slot registration state be explicit? | Yes, but it is a new dispatcher invariant, not a flag. |
| Would registration calls serialize with active H2D? | **Undocumented.** CUDA documents nothing about `cudaHostRegister` concurrent with `cudaMemcpyAsync` on another stream. Not "safe", not "unsafe" — simply unspecified. |
| Is unregister/re-register safe? | `[DOC]` yes for the same range, and it "makes it pageable again" — but re-registering then re-pays the whole cost. |

**Cost/benefit.** Registering 4 slots (256 MiB) instead of 16 would remove ~3/4
of the *size-dependent* component (§14.2: ~425-485 ms) — roughly 320-365 ms.
But 4 slots is exactly QD4 with zero slack, and the entire reason the arena is
16 deep is that 8 slots was outrun by a healthy QD4 source: `slot_wait` 654 ms,
`all_slots_occupied` 101, effective reader concurrency 3.51/4
(`PRODUCTION_009` §9). Reintroducing a shallow registered window while keeping
16 logical slots reintroduces precisely that regression, and the recurring cost
(654 ms of slot wait) is larger than the one-time saving. **Bad trade.**

### 13.3 What partial registration would actually require

Not a flag. It requires, at minimum:

1. A per-slot registration bitmap owned by the arena.
2. `StagingPool.acquire` refusing to hand out an unregistered slot, or
   `adopt_external_slot` failing closed on one — a new dispatcher invariant.
3. The **source owner** must also not be told to fill an unregistered slot: the
   slot is claimed in the CONTROL block by the child (`claim_block`,
   `golden_source_threads.py:732`) long before the parent sees it. So the
   registration bitmap has to be visible across the process boundary and
   respected by `claim_block`.
4. A background thread registering the tail after READY, plus its own
   unregister symmetry for N ranges rather than one.

That is a dispatcher change plus a control-protocol change. It is not
low-risk, and the task's own constraints forbid changing the H2D dispatcher.

## 14. Incremental-registration feasibility

| Question | Answer | Label |
|---|---|---|
| Thread safety | The CUDA runtime API is thread-safe as an API. `[DOC]` says nothing about registering a range while another thread is copying from a *different* registered range on a stream. Unspecified. | `unknown` |
| CUDA API guarantees for adjacent ranges | Non-overlapping adjacent ranges are not addressed in the documentation. `[DOC]` only names `cudaErrorHostMemoryAlreadyRegistered` for a conflicting range. | `unknown` |
| Does registration block globally? | `[DOC]` notes page-locking reduces memory available to the system for paging — a system-wide effect — but says nothing about intra-process serialization. `[MEAS]` at 320 MiB, registration consumed 820/870/1000 ms of *process* CPU against 550/560/670 ms thread CPU, i.e. it used **other threads too**. | `[MEAS]` + `unknown` |
| Can registration of adjacent ranges conflict? | Only if they overlap. Disjoint is the documented-safe reading. | `[INFER]` |
| Can it run concurrently with copies from already-registered ranges? | Unspecified. And the dispatcher's correctness depends on the answer, so this is a blocking unknown, not a nice-to-have. | `unknown` |

**Verdict: `NEEDS_RUNTIME_PROOF`.** The static audit cannot close it, and
closing it requires a GPU run that this audit branch is forbidden from
performing. It is also gated behind §13.3's dispatcher and control-protocol
changes, so it is not the cheapest next experiment.

**One structural fact that does lower its cost:** the fixed ~230-290 ms
component (§15.2) is paid **once**, on the first `cudaHostRegister` call, because
it is lazy context creation. Every subsequent incremental call pays only its
byte-proportional share. So an incremental schedule does not multiply the fixed
cost — which is the main argument in its favour and the reason it is not
dismissed.

---

## 15. Overlap opportunities

### 15.1 Current timeline (what the shipped code already does)

```
restore
  legacy_api_reset ......................................... [_t]
  logical_gpu_repair ...................................... [_t]
  ensure_arena_runtime
    c0_ensure_enter
      torch + cudart resolution ............................  marks[torch_required]
      [opt] primary-context preinit  (default OFF) ........  flag
      SharedMemory(create)  3.50-6.93 ms ....................  marks[shm_create_*]
      frombuffer / 16 slot views ...........................  marks[*_views_*]
      |
      |  spawn()  Popen(exec) ................................................──┐
      |    child: interpreter boot, imports, /dev/shm attach,                   │
      |             4 reader threads, startup barrier, emit READY               │
      |                                                        684-933 ms @320  │
      |  _register_arena()  cudaHostRegister(1 GiB, flags 0) ───────────────────┤
      |      ~713 ms median, and it CONTAINS ~230-290 ms of lazy               │
      |      CUDA primary-context creation                                     │
      |  await_ready()  JOIN ................................................──-┘
  models_generation_check
  GoldenTransferResources.create_shared   (stream + 16 event pairs)
  GpuDestinationPool
  GoldenQDTransport.start()
```

**The registration call is ALREADY overlapped with the source-process boot.**
This is not a proposal; it shipped as `533ce94` and the default
`registration_order == "overlap"` (`golden_io_process_v2.py:118-122`,
`:4568-4573`). `[MEAS]` its A/B result: overlap register 503.3/414.7/642.8 ms
with child boot 684-933 ms; register-first 489.2/419.3 ms with child boot
172-223 ms. *"Does concurrent child boot/fork inflate `cudaHostRegister`? NO,
not materially."*

### 15.2 The cost decomposition this audit can actually defend

Two models, both stated with their weakness. Neither is presented as fact.

**Model A — within-320-MiB matched decomposition. Strongest available.**
Same host, same API, same run, isolating one variable at a time `[MEAS]`:

| Component | Value |
|---|---:|
| Lazy CUDA primary-context creation, isolated | **288.4 ms** |
| POSIX-SHM registration + page materialization, with context already current | **172.6 ms** (isolated) / **191.4 ms** (one-shot) |
| Sum | 461-480 ms |
| Observed register wall at 320 MiB | 414.7 / 503.3 / 642.8 ms |

The sum brackets the observation, so the split is credible: **~60% of the
measured register wall at 320 MiB is CUDA context creation, not pinning.**

**Model B — two-point fit across the 512 MiB and 1 GiB counted cohorts. Weak.**
`median(512 MiB) = 470`, `median(1 GiB) = 713` → +243 ms per +512 MiB →
**0.475 ms/MiB marginal**, intercept **≈ 227 ms fixed**.

*Disclosed weakness:* Model B predicts 379 ms at 320 MiB against an observed
median of 503. The cohorts are different deployments on different hosts, so the
intercept is not transferable. Reported, not hidden.

**Blended estimate at 1 GiB `[INFER]`, median 713 ms:**

| Component | Range | Basis |
|---|---:|---|
| Lazy CUDA primary-context creation | **230-290 ms** | Model A's measured 288 ms; Model B's intercept 227 ms |
| POSIX-SHM registration + page materialisation of 1 GiB | **425-485 ms** | residual; consistent with Model B's 0.475 ms/MiB × 1024 = 487 ms |

### 15.3 Is the measurement boundary honest? (Step 11 correction)

**Yes, and this is the one place the existing number needed no correction.**

`[CODE]` `_register_arena` (`golden_io_process_v2.py:4448-4459`):

```python
self.register_start_ns = time.monotonic_ns()      # boundary OPEN  (before the call)
marks["cuda_host_register_begin"] = int(self.register_start_ns)
t0 = time.perf_counter()
try:
    rc = int(register(self._arena_address, self.size_bytes, _CUDA_HOST_REGISTER_DEFAULT))
...
self.register_end_ns = time.monotonic_ns()        # boundary CLOSE (after the call)
marks["cuda_host_register_end"] = int(self.register_end_ns)
self.register_ms = round((time.perf_counter() - t0) * 1000.0, 4)
```

`register_ms` brackets **the call and nothing else**: no surrounding setup, no
post-register pointer/device lookup, no event/stream setup. The deep diag arm
independently records `wall_monotonic_ns = end - start` for the same span, and
the counted profile reports `backing_create_ms` separately
(3.50-6.93 ms). A test asserts the two agree within 2 ms on a recorded block.

**But `register_ms` is not "raw cudaHostRegister".** It is the raw *call*, and
that call performs lazy primary-context creation internally
(`cuCtxGetCurrent == 0x0` before, nonzero after). So:

```
HOST_REGISTER_RAW_MS (1 GiB, median) = 713 ms   <- call-only boundary, correct as labelled
HOST_REGISTER_INCLUDED_EXTRA_WORK   = yes      <- lazy CUDA primary-context creation is inside it
pure registration/page work (INFER)  = 425-485 ms
```

**No new runtime instrumentation was needed to establish any of this.** Every
number above comes from fields the counted profile already emits
(`arena_ensure.register_ms`, `.backing_create_ms`, `.startup_marks`,
`.child_ready_evidence`) plus the three opt-in arms that already exist:

| Flag | Default | What it answers |
|---|---|---|
| `COMFYMODAL_GOLDEN_C0_REGISTRATION_DIAG` | OFF | context handle before/after, `/proc` RSS/Locked, mapping, rusage, alignment |
| `COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT` | OFF | separates context creation from registration at 1 GiB |
| `COMFYMODAL_GOLDEN_C0_REGISTRATION_ORDER` | `overlap` | `register_first` vs `overlap` at 1 GiB |

That is why this branch adds a **pure analysis module and zero runtime hooks**
(§17). The instrumentation exists; the missing thing is a 1 GiB run of it.

### 15.4 Work that has no dependency on registered memory

| Work | Duration | Could overlap registration? |
|---|---|---|
| source-process boot (spawn → READY) | 684-933 ms @320 MiB | **already overlapped** — this is the shipped design |
| `legacy_api_reset` | `mutable_state_reset_ms`, not reported | already before it |
| `logical_gpu_repair` | "Deliberately performs NO CUDA probe" (`modal_app.py:12746`) | already before it |
| `models_generation_check` | one JSON read + `isdir` (`modal_app.py:12770`) | **YES** — pure CPU/filesystem, no arena dependency, currently runs *after* |
| `create_shared` (stream + 16 event pairs) | not separately reported | **YES** — needs a CUDA context, not a registered range; currently runs *after* |
| `GpuDestinationPool` reserve | not separately reported | **YES** — same |
| model path resolution, metadata/layout inspection | per-request, 11.9-28.6 ms | n/a — different phase |
| CLIP skeleton construction | per-request | n/a |
| UNET pre-resolve | 11.9-28.6 ms, completes before CLIP forward in 10/10 | n/a |

### 15.5 Answering the Step-8 questions

1. **Which work has no dependency on registered memory?** The models-generation
   guard, `create_shared`, and `GpuDestinationPool`. All are small; none is the
   ~230-290 ms problem.
2. **Which can safely run concurrently with registration?** The models-generation
   guard definitively. `create_shared` and `GpuDestinationPool` can, but they
   need the CUDA context that registration is itself creating — so they cannot
   start earlier without moving the context creation earlier too.
3. **Does registration consume enough CPU/memory bandwidth that overlap would
   slow the other work?** `[MEAS]` Yes, measurably: at 320 MiB registration
   consumed 820-1000 ms of *process* CPU against 550-670 ms of thread CPU, so
   it used **other threads**, and it is a 1 GiB page-population walk competing
   with whatever else is running. Overlapping CPU work with it is not free.
   This is also why the already-shipped `spawn()` overlap was measured rather
   than assumed — and it came out fine, because a child interpreter boot is
   mostly single-threaded and IO-bound.
4. **Can the source owner attach before registration finishes?** **It already
   does** in the shipped overlap order — `spawn()` precedes
   `_register_arena()`. `[CODE]` `:4554-4567` then `:4573-4582`.
5. **Can source readers begin filling ONLY the already-registered prefix?** Not
   today, for two independent reasons: there is no registered prefix (one call
   covers all 16 slots), and there is no plan to fill — `plan_once` is invoked
   per model load at request time, and readers block on the startup barrier plus
   the capacity semaphore. The barrier is protocol, not CUDA.
6. **Could first registration start immediately after restore while other setup
   occurs?** Yes, and it already does — it is the first thing
   `initialize_cuda()` does. The only genuinely earlier start available is
   hoisting the **CUDA primary-context creation** out of the register call and
   onto a restore thread that runs concurrently with `legacy_api_reset` /
   `logical_gpu_repair`. The helper already exists
   (`_preinit_primary_context`, `:306`) behind a flag that is already plumbed
   through all three required layers.

### 15.6 Maximal-safe-overlap timeline

```
restore
  legacy_api_reset ──────────────┐
  logical_gpu_repair ────────────┤  (no CUDA probe, no arena dependency)
                                 ├── concurrent
  [NEW] CUDA primary-context init on a restore thread
         ~230-290 ms, hidden behind the two stages above IF they are that long
         └─ once complete, the register call below contains NO lazy context work
  ensure_arena_runtime
      SharedMemory(create) 3.50-6.93 ms
      spawn() ─────────────────────────────────────┐
      cudaHostRegister(1 GiB) now pure page work ──┤  (~425-485 ms)
      await_ready() ───────────────────────────────┘
  [NEW] create_shared + GpuDestinationPool  (moved before models_generation_check)
  models_generation_check
```

**Non-overlapping root-wall saving, honestly bounded:**

| Item | Ceiling |
|---|---:|
| Hoisting lazy context creation out of the register call | **0 to ~230-290 ms** — zero if the pre-arena restore stages are shorter than the context creation, which is not measured |
| Moving the models-generation guard / stream / pool creation off the tail | single-digit to low tens of ms (not separately reported) |
| Registration × child boot | **already 0** — do not count it again |
| **Total defensible low-risk ceiling** | **~0-290 ms**, unproven above 0 without the restore-stage breakdown |

`comfymodal_runtime/cuda_arena_lifecycle_audit.py::overlap_timeline` implements
this arithmetic and, importantly, its test
`test_overlap_ceiling_never_credits_time_already_hidden` proves it cannot
double-count: with a 759 ms boot and a 713 ms call the credited saving is
exactly `0.0`, not `713`.

---

## 16. Optional microbenchmark — SKIPPED, with reasons

**Decision: not run.** Three reasons, in order of weight:

1. **It is forbidden here.** Step 12 asks for an "isolated diagnostic app" on
   "same H100 environment". Producing that requires a Modal deploy, and this
   branch's rules explicitly forbid deploying a treatment or touching Modal
   configuration. A microbench run outside this branch would also destroy the
   audit-only property of the worktree.
2. **The scaling question is already answered.** "Does registration cost scale
   with bytes/pages?" — yes, and it is already measured at two sizes on the
   production primitive: 512 MiB median 470 ms, 1 GiB median 713 ms
   `[MEAS]`, with a 320 MiB point at 414.7-642.8 ms. Adding four more sizes
   would refine a slope that is already good enough to rank treatments.
3. **The pre-touch question is already answered, negatively.** "Does pre-touch
   change cost materially?" — the populate experiment ran and its end-to-end
   result was net negative (`REGISTRATION_INVESTIGATION_REPORT_TESTING8.md` §H).

The matched 320 MiB provenance A/B (`POSIX 191.4` / `anon-shared 66-67.2` /
`anon-private 91.9` / `RawArray+raw-ctx 24.9-45.9` ms) is a better instrument
than a fresh size sweep, because it varies the *primitive* rather than the
*size*. Re-running it is specified in §18.

**What a future microbench would still be worth doing**, if someone runs it
outside this branch: the 320 MiB provenance A/B re-run at 1 GiB, with attribute
92 (`cudaDevAttrPageableMemoryAccessUsesHostPageTables`) recorded. The 2.9x
provenance effect was measured at 320 MiB; whether it holds at 1 GiB is
unknown, and it is the single largest untested number in this report.

---

## 17. What this branch added

Two new files, both audit-only. **No production file was modified** — `git diff`
against `211d204b` is empty for every tracked file.

### 17.1 `comfymodal_runtime/cuda_arena_lifecycle_audit.py`

A pure analysis module. It is **imported by nothing in `comfymodal_runtime/`**
(asserted by
`test_audit_analysis_is_imported_by_no_production_module`), so it cannot affect
any runtime path, and it allocates nothing.

| Function | Answers |
|---|---|
| `decompose(ensure)` | splits one container's establishment into measured phases; proves `register_ms` is the call-only boundary; reports `unknown` rather than inferring a missing phase |
| `registration_context_evidence(ensure)` | was a context already current at the call; did registration materialise the pages (`Rss 0 → full`) |
| `slot_registration_plan(ensure, prefix_slots=…)` | disjoint + 4 KB-aligned prefix feasibility; clamps; fails closed on a geometry mismatch; states that acceptance/thread-safety/cost are **not** established |
| `overlap_timeline(ensure)` | current vs maximal-safe-overlap, with a non-double-counting root-wall ceiling |
| `enabled()` | the gate for a future opt-in arm. **Not** declared in `config_authority`/`flag_registry`/`_runtime_env` — a three-layer deploy flag would imply an arm that does not exist, and `975aec14` is a recorded case of exactly that flag silently doing nothing |

It is deliberately **not** wired into the container. Adding a runtime hook would
mean editing `_register_arena`, and §15.3 shows the boundary is already honest
and the fields are already emitted — so a hook would add risk and no
information.

### 17.2 `tests/test_cuda_arena_lifecycle_audit.py`

30 tests, `fast_unit`, **1.31 s** (slowest single test 0.23 s after the AST
parse was hoisted into an `lru_cache`; it was 0.64 s before).

Proves, in order:

| Group | Tests |
|---|---|
| audit analysis | disabled by default; not imported by any production module; phase split; `unknown` instead of invention; `register_ms` is the call-only boundary; overlap ceiling cannot double-count; context evidence `unknown` without the diag arm; detects lazy context creation; detects an already-current context; detects first-touch-by-registration from the RSS transition |
| partial-registration arithmetic | disjoint, 4 KB-aligned, clamps to the real slot count, fails closed on geometry mismatch, `unknown` without geometry, and an explicit test that the module does not claim acceptance/cost |
| shipped-code contracts | no direct CUDA registration symbol is called anywhere in the module; exactly one injected registration call and it is `_register_arena`'s; `cudaHostRegister` resolved only from `ensure` + the standalone `run_primitive_probe` (which provably never touches the arena); `cudaHostUnregister` never from `ensure` |
| registration range + symmetry | one call, args exactly `(self._arena_address, self.size_bytes, _CUDA_HOST_REGISTER_DEFAULT)`; `register_ms`/`registered` owned by `_register_arena` alone; unregister uses the **same** address and is guarded by `if not self.registered` |
| once per container | `ensure()` has exactly three mutually exclusive registration guards and short-circuits on `created`; `_C0_RUNTIME` is a module singleton so CLIP/UNET/VAE share one arena and one registration |
| CUDA sterility + ordering | the source child is `exec`'d with `CUDA_VISIBLE_DEVICES=""`, attaches by name, and contains no `cudaHostRegister`/`cudart`/`torch`; `shm_create < address < spawn < register < await_ready`; `ensure()` installs no plan |
| H2D contract | `_submit` is `non_blocking=True` under `torch.cuda.stream` with both event records; `create_shared` and `new_stage_pool` contain no `pin_memory`, no `cudaHostAlloc`, no `torch.empty` — the registered arena is the only pinned host memory |
| defaults unchanged | host-register default ON, order default `overlap`, diag and preinit default OFF |
| branch hygiene | `_register_arena` still contains exactly two `time.perf_counter()` calls and the `ensure` mark names are unchanged — a tripwire if anyone later edits a timed call site on an audit branch |

### 17.3 Verification

```
# new file only
tests/test_cuda_arena_lifecycle_audit.py .......  30 passed in 1.31s

# whole fast_unit suite, this branch
2 failed, 639 passed, 7 skipped, 9 subtests passed in 30.89s

# the 2 failures
tests/test_rx9p_h_identity_chain.py::test_success_path_exact
tests/test_rx9p_h_identity_chain.py::test_compact_nested_sage_observation_is_mismatch
```

**The 2 failures are pre-existing and unrelated.** They are the exact pair that
`211d204b` documents (*"fast_unit is unchanged at 609 passed with only the two
pre-existing test_rx9p_h_identity_chain failures"*), they are in a file this
branch does not touch, and `609 + 30 = 639`.

The suite wall is 30.89 s here versus the `tools/test_perf.py` default hard
timeout of 15 s. That is a host difference, not a regression: this is Windows
with the tree under OneDrive. The tool was re-run with `--timeout 180` and its
`MEASURED_MAX_TEST_WALL: 3998 ms` resolves to the pre-existing
`test_ten_thousand_tiny_calls_accumulate`; the slowest test in the new file is
0.23 s.

---

## 18. Candidate treatment table

Root-wall gain is *non-overlapping* and against the 1 GiB median of 713 ms.

| # | Treatment | Semantic purpose | Correctness risk | Root-wall gain | Difficulty | Source-process compatible | Snapshot compatible | Evidence |
|---|---|---|---|---|---|---|---|---|
| T0 | **Keep full registration as-is** | none (baseline) | none | 0 | none | yes | yes | 13/13 exact SHA at 1 GiB `[MEAS]` |
| T1 | **Hoist lazy CUDA primary-context creation onto a restore thread** | the ~230-290 ms fixed component is real work the container needs anyway; it just happens to sit inside the register call | **low** — the helper already exists (`_preinit_primary_context`, `:306`), is already flagged, and is already plumbed through all three layers; worst case it is a no-op reorder | **0 to ~230-290 ms** | low (a reorder + the existing flag) | yes — no source change | yes — still post-restore | **strong**: 288.4 ms isolated at 320 MiB, `cuCtxGetCurrent 0x0 → nonzero` `[MEAS]` |
| T2 | **Register a prefix (e.g. 8 of 16 slots), tail in background after READY** | remove unused pinned bytes | **medium-high** — needs a per-slot registration bitmap enforced by `StagingPool.acquire`/`adopt_external_slot` **and** by the child's `claim_block` across the process boundary; an unregistered slot reaching `copy_` degrades silently, with no error | ~210-240 ms (half of 425-485) | **high** — dispatcher + control protocol | yes in principle | yes | **weak**: geometry proven `[DOC]`+`[CODE]`; acceptance, thread-safety and cost **all unmeasured** |
| T3 | **Register incrementally: prefix → source proceeds → register tail** | same bytes, spread across the boot window | **high** — `cudaHostRegister` concurrent with in-flight `cudaMemcpyAsync` is unspecified by CUDA | up to ~425-485 ms *if* it all fits in the boot window, which at 320 MiB it did not | high — T2 plus a registration lock | yes in principle | yes | **none for the concurrency question** — `unknown` |
| T4 | **Pre-touch, then register** | deterministic page placement | low mechanically, but **already measured net negative end-to-end** | **0 or negative** | low | yes | yes | **strong and negative**: `REGISTRATION_INVESTIGATION_REPORT_TESTING8.md` §H |
| T5 | **`cudaHostAlloc` arena** | born pinned | — | — | — | **NO** — unreachable by an exec'd child | yes | **infeasible** (§10, C1) |
| T6 | **`cudaHostAlloc` + Mapped** | born pinned, zero-copy device access | — | — | — | **NO** | yes | **infeasible** (§10, C1) |
| T7 | **`torch.empty(pin_memory=True)`** | born pinned via the caching host allocator | — | — | — | **NO** | yes | **infeasible** (§10, C1); and PyTorch's allocator does the registration anyway |
| T8 | **Alternate shared allocation: anonymous `MAP_SHARED` + fork-without-exec** | cheapest measured primitive (66 ms vs 191 ms at 320 MiB) | **high** — restores M2's forked-reader topology and puts a forked post-CUDA child on the table | **~300 ms** `[INFER]` at 1 GiB | very high — full process-topology change | **NO** — violates CUDA sterility as structured | yes | **strong on cost, disqualifying on architecture** |
| T9 | **Move registration to snapshot time** | pay it once ever | — | — | — | — | **NO** | **impossible**: §9.4, `REGISTRATION_MUST_BE_POST_RESTORE` |
| T10 | **Restore-time vs request-time relocation** | pay it only when a model is actually needed | — | 0 (single-use containers: `min_containers=0`, and the counted profile is `run_count = 1`) | low | yes | yes | **ruled out by the workload shape** — deferring to request time moves 713 ms *into* the measured request wall, and `PRODUCTION_009` §9 already notes the cost currently lands outside every measured stage |

**Not ranked purely by theoretical speed.** T8 has the largest theoretical gain
and is architecturally disqualifying. T4 is trivial and measured negative. T3 has
the largest ceiling and the weakest evidence. T1 is small, already implemented,
and rests on the only measurement in this report that was isolated on a matched
host.

## 19. Primary classification

```
REGISTRATION_REQUIRED_BUT_OVERLAPPABLE
```

Not `REGISTRATION_REQUIRED_AS_IS`, because there is a measured, already-built,
already-plumbed relocation available: the ~230-290 ms of lazy CUDA
primary-context creation that the register call performs implicitly can be
hoisted explicitly onto a restore thread and overlapped with restore work that
has no dependency on it.

Not `REGISTRATION_CAN_BE_REDUCED` or `..._REPLACED_BY_PREPINNED_ALLOCATION`,
because every reduction or replacement path is blocked by one hard structural
constraint — the source owner is `exec`'d and reaches the arena **by name**, so
only a named kernel object is reachable — and the two paths that survive that
constraint (prefix registration, incremental registration) both require
dispatcher and control-protocol changes that are explicitly out of scope, with
their key safety question unanswerable from documentation.

Not `MULTIPLE_LOW_RISK_IMPROVEMENTS_AVAILABLE`, because there is exactly **one**
low-risk improvement. Claiming more would be inflation.

| | |
|---|---|
| **Best low-risk treatment** | **T1** — hoist lazy CUDA primary-context creation onto a restore thread, before `ensure_arena_runtime()`, using the existing `_preinit_primary_context` helper and its existing opt-in flag. Zero geometry, source, dispatcher, or event changes. |
| **Best medium-risk treatment** | **T2** — register a prefix and the tail in the background, with a registration bitmap enforced by both `StagingPool` and the child's `claim_block`. Do not ship without proving the bitmap cannot be bypassed. |
| **Maximum plausible root-wall gain** | **low risk: ~0-230-290 ms** (the honest floor is 0; the ceiling requires the pre-arena restore stages to be at least as long as the context creation, which is not measured). **medium risk: a further ~210-240 ms**, i.e. roughly half of the 425-485 ms size-dependent component — at the price of the dispatcher and control-protocol work in §13.3. |
| **Confidence** | **HIGH** — registration is required and *why* is documented (§6.2); the measurement boundary is honest (§15.3); the call is already overlapped (§15.1); the fixed/size split is measured on a matched host (§15.2 Model A); the snapshot answer is structural (§9); the constraint that kills B/C/D/E/G is a fact about `exec` (§12 C1); pre-touch is already measured negative. **MEDIUM** on the 1 GiB split — inferred across cohorts, with Model B's 320 MiB misprediction disclosed. **MEDIUM-LOW** on the NUMA/first-touch relation — structurally established, unmeasurable here. **LOW** on T2/T3 performance and thread-safety — undocumented and unmeasured. |

## 20. Smallest decisive next experiment

**Not implemented here.** One experiment, three arms, one deployment, one flag
change. Nothing else moves: same QD4, same 64 MiB blocks, same 4 ms pacer,
same `whole` mmap lifecycle, same four readers, same 16 x 64 MiB arena, same
snapshot/restore shape, same output SHA.

```
CONTROL   (COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT=0, default)
TREATMENT (COMFYMODAL_GOLDEN_C0_REGISTRATION_CONTEXT_PREINIT=1)
          _preinit_primary_context() runs on a RESTORE THREAD started
          before ensure_arena_runtime(), concurrently with
          legacy_api_reset + logical_gpu_repair.
          The register call then runs with the context already current.
INSTRUMENT (COMFYMODAL_GOLDEN_C0_REGISTRATION_DIAG=1) on BOTH arms
```

This is the smallest experiment that can be decisive because **it separates the
two components of the number at 1 GiB** — the only decomposition still
inferred. It uses two flags that already exist in all three required layers,
needs no new selector, and changes no geometry, source, dispatcher, event, or
snapshot behaviour.

**Measure, all of which the counted profile already emits:**

| Metric | Field |
|---|---|
| raw register wall | `arena_ensure.register_ms` |
| **context-init wall (the treatment's whole point)** | `arena_ensure.registration_diagnostic.context_preinit_ms` |
| pure registration wall (control: `register_ms`; treatment: `register_ms`) | `arena_ensure.register_ms` — the comparison that decides the treatment |
| context present before the call | `registration_diagnostic.before.identity.context_handle_before_or_after` |
| source child ready wall | `arena_ensure.child_startup_ms`, `child_ready_evidence.source_startup_ns` |
| spawn→register and register→ready legs | `startup_marks.source_thread_spawn_begin`, `cuda_host_register_begin/end`, `source_thread_ready` |
| total establishment wall | `audit.decompose(ensure).establishment_total_ms` |
| CLIP source throughput, slot wait | `source.threads.*`, `slot_wait_ms`, `all_slots_occupied` |
| correctness | exact output SHA, `restore_count=1`, `request_count=1` |

**Add exactly one new read, no new behaviour:** record
`cudaDevAttrPageableMemoryAccessUsesHostPageTables` (attribute 92) alongside the
two attributes the diag arm already queries (99, 113). It is the one documented
switch that decides whether `cudaHostRegister` pins at all or merely populates
pages, it is a single `cudaDeviceGetAttribute` call inside an existing opt-in
arm, and without it the 320 MiB first-touch evidence cannot be generalised to
any hardware.

**Decision rule, fixed in advance:**

| Outcome | Conclusion |
|---|---|
| treatment's `register_ms` falls by ≈ the `context_preinit_ms`, and `establishment_total_ms` falls by the same | T1 confirmed; ship the reorder |
| `context_preinit_ms` is large but `establishment_total_ms` does not move | the context creation is hidden by the child boot already; T1 gains 0 and the classification falls back to `REGISTRATION_REQUIRED_AS_IS` |
| both are small at 1 GiB | Model A's ratio does not hold at 1 GiB; re-derive the decomposition before proposing anything |
| any arm shows slot wait, or a SHA mismatch | stop; the decomposition is not worth a source/H2D regression |

**Deliberately NOT bundled** (each confounds and must be its own arm):
pre-touch (T4, already negative), partial registration (T2), incremental
registration (T3), `register_first` vs `overlap` (already measured, not material),
and the source-path sickness investigation.

---

## 21. Exact things that must NOT change

Restating the constraints as invariants, because several of them are the reason
this report's conclusions hold:

**Arena geometry and payload**
1. 16 slots of exactly 64 MiB, `size_bytes == slot_count * slot_bytes`. The
   strict product check at `golden_io_process_v2.py:4218` stays strict; it is
   what makes `slot_registration_plan`'s arithmetic trustworthy.
2. The 16-slot change's benefit is not re-litigated here: 8 → 16 slots took CLIP
   `slot_wait` from 654 ms to 0. Any "register fewer slots" proposal must beat
   that, not ignore it.

**Source architecture**
3. `READER_COUNT = 4`, `SLOT_BYTES = 64 MiB`, `PACER_GAP_NS = 4 ms`, whole-file
   `MAP_PRIVATE` mmap mapped once per generation (`golden_source_threads.py:76-81`).
4. The source owner stays a separate `exec`'d process attaching the arena **by
   name**, with `CUDA_VISIBLE_DEVICES=""`.
5. The source owner stays **CUDA-sterile**. The parent's fail-closed checks at
   `golden_io_process_v2.py:4837-4842` (`c0_child_not_cuda_sterile`,
   `c0_child_cuda_initialized`) stay.
6. Slot release stays gated on proven H2D completion
   (`golden_source_threads.py:1204`).

**H2D and CUDA ownership**
7. H2D stays `copy_(..., non_blocking=True)` on the dedicated stream
   (`golden_qd_transport.py:4337`). This is the property registration exists to
   protect.
8. `GoldenTransferResources.create_shared` stays free of any pinned host
   allocation. The registered arena is the only pinned host memory in the path.
9. The H2D stream and the 16 event pairs stay restore-owned, created once,
   reused across CLIP/UNET/VAE (`golden_model_transport.py:913, :938`).
10. `register` stays resolved once, in `ensure`, and injected once
    (`:4513-4515`, `:4453`).

**Lifecycle**
11. Registration stays **post-restore**. `REGISTRATION_MUST_BE_POST_RESTORE`
    (§9.8).
12. `registration_order` stays `"overlap"` by default. The register-first A/B is
    already measured and not material; reverting it would only re-serialize the
    source boot.
13. `_register_arena`'s timing boundary stays exactly as it is — two
    `perf_counter()` calls bracketing the call and nothing else. If it is ever
    "improved", the 713 ms stops meaning what §15.3 says it means.

**What this branch is not**
14. No production treatment. No deployment. No promotion, no tag, no merge, no
    cherry-pick into the active Phase-2/3 lane.
15. No change to the source-copy-isolation experiment or the VAE audit lane.
16. `triton`/Phase-2A work (`ac56539b`, `d4613e19`) and the source-copy-isolation
    experiment (`cc2f541c`) are descendants of this base and were not touched.

---

## 22. Terminal summary

```
AUDIT_BASE_SHA=211d204b06f1246bbd2b5b591473d7d08b629030
AUDIT_HEAD=(this branch's tip; `git -C .slim/worktrees/cuda-arena-lifecycle-audit rev-parse HEAD`)
AUDIT_BRANCH=audit/cuda-arena-lifecycle
AUDIT_WORKTREE=.slim/worktrees/cuda-arena-lifecycle-audit

ARENA_BYTES=1073741824
HOST_REGISTER_REQUIRED=yes
HOST_REGISTER_RAW_MS=713
HOST_REGISTER_INCLUDED_EXTRA_WORK=yes

REGISTRATION_CONTEXT_BOUND=yes
REGISTRATION_PROCESS_BOUND=yes
REGISTRATION_SURVIVES_SNAPSHOT=no

ARENA_BACKING_CAN_EXIST_IN_SNAPSHOT=no

SOURCE_PROCESS_REQUIRES_SHARED_STORAGE=yes
SOURCE_PROCESS_CAN_REMAIN_CUDA_STERILE=yes

PREPINNED_ALLOCATION_FEASIBLE=no
PARTIAL_REGISTRATION_FEASIBLE=yes
INCREMENTAL_REGISTRATION_FEASIBLE=unknown
OVERLAP_FEASIBLE=yes

REGISTRATION_SOURCE_STALL_RELATION=POSSIBLY_RELATED

PRIMARY_CLASSIFICATION=REGISTRATION_REQUIRED_BUT_OVERLAPPABLE

BEST_LOW_RISK_TREATMENT=hoist_lazy_cuda_primary_context_creation_onto_a_restore_thread_before_ensure_arena_runtime
PLAUSIBLE_ROOT_WALL_GAIN_MS=0-290
NEXT_EXPERIMENT=CONTROL_PREINIT=0_vs_TREATMENT_PREINIT=1_on_a_restore_thread_plus_REGISTRATION_DIAG_on_both_arms_one_deployment_deciding_on_establishment_total_ms

PRODUCTION_CODE_CHANGED=no
MERGED=no
```

### Reading the values that need a word

- `HOST_REGISTER_RAW_MS=713` is the **median of the call-only boundary** at
  1 GiB, and it is already correctly bounded (§15.3). It is *not* pure pinning:
  `HOST_REGISTER_INCLUDED_EXTRA_WORK=yes` because the call performs lazy CUDA
  primary-context creation internally. Pure registration + page materialisation
  is **~425-485 ms** `[INFER]`, fixed context creation **~230-290 ms** `[MEAS]` at
  320 MiB.
- `PARTIAL_REGISTRATION_FEASIBLE=yes` is **geometry only** — disjoint, 4 KB-
  aligned sub-ranges of one mapping. Acceptance, thread-safety against an
  in-flight H2D, and cost are all unmeasured, and the dispatcher has no
  unregistered-slot state today (§13).
- `INCREMENTAL_REGISTRATION_FEASIBLE=unknown` because CUDA documents nothing
  about registering a range while another thread copies from a different
  registered range, and the dispatcher's correctness depends on the answer.
- `OVERLAP_FEASIBLE=yes` refers to the **residual** relocation — hoisting the
  lazy context creation. The registration call is *already* overlapped with the
  source-process boot (`registration_order="overlap"`, shipped as `533ce94`),
  and its saving is correctly counted as zero, not twice.
- `PLAUSIBLE_ROOT_WALL_GAIN_MS=0-290` is stated as a range, not a point, because
  the floor is genuinely 0 unless the pre-arena restore stages are at least as
  long as the context creation — which has never been measured at 1 GiB.