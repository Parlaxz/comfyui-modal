# P9 source full-read warm-mmap experiment (arms A and A4)

## 1. Starting SHA

```
b9ad22d40272363e35776ea12f0f870ef79c68c9
```

`docs(experiment): flag the committed destination change as an open item`, on
`exp/source-copy-isolation`, clean tree, branch `exp/source-copy-isolation`.

## 2. Final experiment SHA

```
HEAD = b9ad22d40272363e35776ea12f0f870ef79c68c9   (start)
510d270                                         feat(experiment): add synchronous full-read mmap isolation arm
<report commit>                                 docs(experiment): report warmed-mmap source results
```

Committed in this lane only: the A4 harness, its tests, and this report. No
production source replacement, no merge, no tag movement.

## 3. Worktree / branch

```
WORKTREE=.slim/worktrees/source-copy-isolation
BRANCH=exp/source-copy-isolation
```

Root checkout, `p8fix`, `main`, production tags and the production app were not
touched.

## 4. Established prior evidence (not re-litigated)

The 2x2 experiment established **`SOURCE_SIDE`**: the pathological 64 MiB
`libc.memmove` needs the whole-file `MAP_PRIVATE` mapping of the Volume-backed
checkpoint and is completely absent when the source is resident anonymous RAM.
The pinned shared arena was exonerated.

| arm | source | destination | verdict |
|:--|:--|:--|:--|
| A | Volume mmap | pinned arena | PATHOLOGICAL |
| B | Volume mmap | anonymous | PATHOLOGICAL |
| C | anonymous RAM | pinned arena | HEALTHY |
| D | anonymous RAM | anonymous | HEALTHY |

The A2/A3 follow-up then established that the two obvious prefetch mechanisms
are **accepted and inert** on this Modal Volume / gVisor Sentry path:

| mechanism | call wall | implied for 12,309,866,400 B | a real read takes |
|:--|--:|--:|--:|
| `posix_fadvise(WILLNEED)` | 0.040 ms | 308 GB/s | ~1.2 s |
| `mmap(MAP_POPULATE)` | 0.774 ms | 16 GB/s | ~1.2 s |

So A2/A3 tested whether the platform honours the request, not whether having the
bytes removes the stall. No further advisory prefetch variants were run.

## 5. Arm A definition (control)

Unchanged production shape, no treatment at all:

```
open source fd
  -> whole-file MAP_PRIVATE mmap
  -> existing production reader loop (4 readers, 64 MiB blocks, 4 ms pacer,
     16 x 64 MiB pinned shared arena, cudaHostRegister)
  -> libc.memmove from the mapping into the arena slot
  -> existing per-copy SourceCopyProbe around the memmove and nothing else
```

No warmup. No fadvise, no madvise, no `MAP_POPULATE`, no positioned read. The
process-local population gate *is* still raised around the experiment's own
`build_plan` call — both arms get identical gating — and arm A's hook records
`warm_read_called=false`, which is what makes "the control never warmed"
provable rather than assumed.

## 6. Arm A4 definition

Identical to A except for one diagnostic step, in this exact order inside the
production `build_plan`:

```
open source fd
  -> whole-file MAP_PRIVATE mmap                                  (unchanged)
  -> SYNCHRONOUS positioned read of EVERY byte of the source file
     through the same descriptor, into a bounded reusable 64 MiB scratch buffer
  -> discard the scratch
  -> the EXACT SAME timed mmap -> arena copy loop as arm A
```

The timed copy path is untouched: same `_run_reader_loop`, same `execute_block`,
same `libc.memmove(pinned_arena_slot, map_address + source_offset, length)`.

Deliberately **not** done, because each would stop it being a diagnostic:

* no pipelining, no QD, no second warm-reader thread, no overlap between the warm
  read and the timed copies or with H2D — the claim under test is "every byte was
  synchronously consumed before copy timing began";
* no whole-file anonymous copy — 12.31 GB will not fit beside the 1 GiB pinned
  arena in a 24 GiB container, and holding it would replace the mmap read with an
  ordinary RAM read, which is a different experiment;
* no `mmap` and no slicing of the source mapping for the warm read, so the warm
  path and the timed path are provably different code.

## 7. Exact warm-read implementation

`comfymodal_runtime/source_population_policy.py::full_file_read`, called from
`golden_source_threads.build_plan` immediately **after** the mapping is created
and **before** `build_plan` returns.

* Primitive selection, `_positioned_read_capability()`: `os.preadv`, then
  `os.pread`, and **no** seek-based fallback. Same precedence as the production
  fillers `golden_io_process_v2._pread` and `clip_qd_reader._syscall_mode`, pinned
  by a behavioural test against `clip_qd_reader`. One deliberate divergence:
  `clip_qd_reader` may fall back to `lseek`+`read` because each of its workers
  owns a private descriptor; A4 must not, because a silent fallback would mean
  the experiment measured a different primitive than the one it names.
* Geometry: one `bytearray(64 * 1024 * 1024)` scratch, allocated once and reused
  for every block. `warm_scratch_reused=true`, `warm_scratch_bytes=67108864`,
  `warm_uses_mmap=false`. A `bytearray` is plain anonymous memory — no mapping is
  involved at all.
* Walk: sequential, contiguous, from offset 0 in 64 MiB steps to the final short
  block, until `total_bytes_read == file_size`. Offsets in the syscall log are
  strictly increasing, which is what proves nothing was overlapped.
* Per-syscall record: attempt, source offset, requested bytes, returned bytes,
  wall ms/ns, thread CPU ms, state (`ok`/`eintr`/`error`), error string.
* Per-block record: ordinal, source offset, requested/returned bytes, wall ms,
  thread CPU ms, attempts, short-read retries, EINTR retries, error.
* Fail-closed: a hard `OSError` raises `positioned_read_failed`; a zero read
  (EOF) raises `positioned_read_short:...:eof_before_expected_size`; an
  `InterruptedError` is counted and retried without advancing the offset; a final
  byte count short of the declared size raises `full_file_read_incomplete`.
* The A4 contract in `population_contract` requires three independent facts to
  agree before the arm counts as run: `warm_bytes_read == warm_bytes_requested`,
  `warm_bytes_requested == mapped_bytes`, and `warm_complete` with
  `warm_uses_mmap is False`.

The policy module imports only `__future__`, `ctypes`, `os`, `time` and
`typing`, so the CUDA-sterile source owner can load it as a standalone script. A
test parses the imports with `ast` rather than scanning lines, so prose cannot
decide whether an import exists.

### Process gating

`COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_POPULATION` is raised by
`source_copy_isolation._PopulationGate` **only** around the experiment's own
`build_plan` call and popped immediately. The warm read therefore applies only to
the experiment's mapping. The real Golden source owner is a separate process
spawned later in the same container, never sees the gate, and stays an untreated
control — verified on all 20 requests, whose 10 control-side payloads all report
`warm_read_called` absent/false while the real Golden CLIP/UNET loads completed
with the exact expected output SHA.

## 8. Deployment identities

Destination `Testing 1 / ws_e677ab553606` (`config/v2/modal_target.toml`) — see
§25.

| arm | profile | app | deploy fingerprint | image | source/config identity |
|:--|:--|:--|:--|:--|:--|
| A | `golden_p1_parallel_p9_srccopy_a4-control_h100` | `batch-p9srccopy-a4-control-h100` | `41276f960291633f3ae7a14d5de75691a856743eea435c81f005922024729062` | `im-2tE3XZA55mQz1…` | `132b61bb9f8a…` |
| A4 | `golden_p1_parallel_p9_srccopy_a4-fullread_h100` | `batch-p9srccopy-a4-fullread-h100` | `cb3883ab867c5531c721a5b210c84f2d426e45eea507c77361b5b30adef1b494` | `im-s9fuRAvMVsWLs…` | `132b61bb9f8a…` |

Experiment module SHA-256, identical locally and in both containers:

```
comfymodal_runtime/source_population_policy.py  a909928fb0e1b59ed26c182f3bc32ac8f8edb57c90568723e319b6bed620286a
comfymodal_runtime/source_copy_isolation.py     708ae9deb04fc58b6fa77ee7c9cfe1b0736f4b8315bf95357470219ab4ac86f4
comfymodal_runtime/golden_source_threads.py      8bc28a27a9be685f0c63cbef35e99f74bf25b3a3944cf79186d720cef7caa870
```

`v2ctl source-probe` returned `RESULT=PASS source_identity=MATCH` for both apps,
including the new module:

```
comfymodal_runtime/source_population_policy.py: MATCH remote_sha=a909928fb0e1b59e expected_sha=a909928fb0e1b59e
```

Two images, one per app, is correct: the arm is a deploy-baked value and each arm
owns its own app identity. Both arms share **one source/config identity**, which
is what makes the comparison contemporaneous. `v2ctl doctor` reported no problems
and no runtime overrides for either.

Geometry unchanged from every prior phase: `H100!`, `CPU=12` requested, memory
24576 MB, `ModalRuntimeEntrypointV2`, `run_golden_parallel_stream`, whole mmap
lifecycle, thread source owner, 64 MiB blocks, 16 x 64 MiB pinned arena,
`conditioning_cache=forced_miss`, `fresh_required=true`, expected output SHA
`3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577`,
`min_containers=0`, single-use containers.

## 9. Cohort validity

20 requests, strictly serial, never concurrent, one `golden run` per request,
10 per arm.

| check | result |
|:--|:--|
| attempts | 20 |
| valid | **20/20** |
| DNF | 0 |
| true-cold | **20/20** |
| `restore_count` / `request_count` | 1 / 1 on all 20 |
| exact output SHA | **20/20** (`3a6a0306…`, 3083864 bytes) |
| output durability mode | `off` on all 20 |
| fallback / fatal failure | `None` / `False` on all 20 |
| request-time `SNAPSHOT_CAPTURE` | none; capture guard `ELIGIBLE` on all 20 |
| arm contract `satisfied` | **20/20** |
| arm identity match (`declared == observed`) | 20/20 (A/A on 10 controls, A4/A4 on 10 treatments) |
| full read proven | **10/10** treatment containers |
| controls unwarmed | **10/10** |
| teardown `cuda_host_unregistered` | `true`, `rc=0` on all 20 |
| single-use containers / `min_containers` | `true` / `0` |
| source/config identities in the cohort | one (`132b61bb9f8a…`) |

**Nothing was discarded.** All 20 attempts are usable.

Cohort size: the control produced 3 pathological containers out of 10, not zero,
so the escalation rule did not trigger and the cohort was not extended. The rule
also forbids extending selectively on the basis of which arm looks better, and
neither arm was given extra runs.

## 10. Warm-read total cost

| metric | value |
|:--|--:|
| containers | 10 |
| blocks per container | **184** = 183 full 64 MiB blocks + a final short block of **28,944,288 B** at offset 12,280,922,112 (183 x 67,108,864 = 12,348,030,976 exceeds the file by 38,164,576 B) |
| total blocks | 1840 |
| bytes read per container | **12,309,866,400** — exact, all 10 (sum of `returned_bytes` verified per container) |
| bytes requested per container | 12,309,866,400 — exact, all 10 |
| `warm_complete` | true, 10/10 |
| read syscalls per container | 184 — **zero** short-read retries, **zero** EINTR |
| warm total, all containers | 63,808.1 ms |
| warm total per container | min 4851.6 / **p50 6274.2** / p90 7022.7 / p99 8544.1 / max 8713.2 ms |
| thread CPU for the whole warm read | ~60 ms per container against ~6274 ms wall — the read blocks, it does not burn CPU |

The short final block is also the fastest block in the walk (8.41 ms, ordinal
183) and ordinal 0 the slowest of the first eight (50.83 ms), which is the
opposite of a tail-at-the-end pattern.

`FULL_READ_PROVEN=yes`.

## 11. Warm-read block distribution

1840 blocks of 64 MiB, pooled:

| min | p50 | p90 | p95 | p99 | max | mean | SD | CV |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 5.35 | **33.43** | 37.73 | 39.62 | 57.54 | **971.77** | 34.57 | 25.01 | 0.7234 |

| threshold | blocks | fraction |
|:--|--:|--:|
| >100 ms | 8 | 0.43% |
| >250 ms | 3 | 0.16% |
| >500 ms | 1 | 0.05% |
| >1000 ms | 0 | 0% |

Per container (64 MiB blocks):

| request | blocks | warm ms | GB/s | p50 | p90 | p99 | max | blocks >250 ms |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| `673fa85f7212` | 184 | 6834.9 | 1.801 | 36.59 | 39.37 | 45.59 | 58.05 | 0 |
| `4f8b42490386` | 184 | 6320.5 | 1.948 | 33.79 | 36.86 | 42.20 | 54.17 | 0 |
| `c93af51aa8e2` | 184 | 6274.2 | 1.962 | 34.12 | 35.47 | 37.46 | 60.77 | 0 |
| `c55ed913ebec` | 184 | 6071.7 | 2.027 | 32.39 | 34.15 | 40.62 | 65.50 | 0 |
| `f12157c94514` | 184 | 4851.6 | 2.537 | 25.87 | 27.39 | 32.04 | 47.40 | 0 |
| `43654a84869b` | 184 | 5984.9 | 2.057 | 31.95 | 34.72 | 39.87 | 51.48 | 0 |
| `50b7422d5347` | 184 | 6662.8 | 1.848 | 35.14 | 40.67 | 52.10 | 61.03 | 0 |
| `8af154c39711` | 184 | 6097.2 | 2.019 | 32.95 | 35.76 | 37.74 | 53.80 | 0 |
| `e6eb965847e7` | 184 | 5997.1 | 2.053 | 31.88 | 36.13 | 58.58 | 73.13 | 0 |
| `a3f51d2427d5` | 184 | 8713.2 | 1.413 | 35.10 | 49.13 | **322.46** | **971.77** | **3** |

Nine of ten containers are extremely tight (max 47–73 ms). One is not.

## 12. Warm-read throughput

Note on geometry, because it changes every throughput figure below: the timed copy
loop performs **256 copies totalling 17,141,700,608 bytes**, not 12.31 GB. The
checkpoint has 184 distinct 64 MiB blocks and 4 readers x 64 iterations = 256
copies, so ~72 offsets are visited a second time — 1.39 passes over the file.
That is the inherited A/B/C/D geometry, unchanged by this experiment. Throughput
is therefore computed from bytes actually copied, not from file size.

| metric | value |
|:--|--:|
| warm read pooled effective (12.31 GB / 63.81 s) | **1.929 GB/s** |
| warm read per-container p50 | 1.990 GB/s |
| warm read per-container min / max | 1.413 / 2.537 GB/s |
| warm read per-container mean / CV | 1.966 GB/s / 0.1415 |
| A control timed copy, median per-container (17.14 GB) | **6.81 GB/s** |
| A4 post-warm timed copy, median per-container (17.14 GB) | **14.89 GB/s** |

The warmed mapping moves data **7.7x faster** than the positioned read that
warmed it. See §21 — that ratio is the whole reason the positioned-read
replacement is not justified.

## 13. Control mmap distribution (arm A, 10 containers, 2560 copies)

Pooled: p50 41.71, p90 54.92, p95 61.72, **p99 428.40**, **max 2100.67**,
mean 44.91, SD 92.72, CV 2.0646.

| threshold | copies | fraction |
|:--|--:|--:|
| >100 ms | 64 | 2.500% |
| >250 ms | 45 | 1.758% |
| >500 ms | 18 | 0.703% |
| >1000 ms | 6 | 0.234% |

Per container:

| request | p50 | p90 | p99 | max | cpu p50 | >100 | >250 | >500 | >1s | pathological |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--|
| `c180102c0de6` | 43.39 | 49.78 | 59.57 | 67.20 | 40 | 0 | 0 | 0 | 0 | . |
| `3971906ef69d` | 39.37 | 44.07 | 49.78 | 59.16 | 40 | 0 | 0 | 0 | 0 | . |
| `9aa3cf8f25bf` | 40.26 | 46.72 | 56.30 | 61.94 | 40 | 0 | 0 | 0 | 0 | . |
| `bf87290b69ef` | 44.29 | 50.82 | 58.11 | 60.39 | 40 | 0 | 0 | 0 | 0 | . |
| `7858f4b866d4` | 44.71 | 52.68 | 67.29 | 72.93 | 40 | 0 | 0 | 0 | 0 | . |
| `03b74815572a` | 50.17 | 59.75 | 70.29 | 75.05 | 50 | 0 | 0 | 0 | 0 | . |
| `65b569884ba7` | 45.26 | 50.60 | 59.89 | 75.84 | 40 | 0 | 0 | 0 | 0 | . |
| `0d2aed4eaff5` | 45.86 | 70.21 | 532.31 | 1127.78 | 40 | 12 | 10 | 3 | 2 | **YES** |
| `bcd5ca474f06` | 30.36 | 142.31 | 926.12 | 1386.23 | 30 | 27 | 16 | 7 | 1 | **YES** |
| `9ae3fd19c0f7` | 28.88 | 63.94 | 997.05 | **2100.67** | 30 | 25 | 19 | 8 | 3 | **YES** |

Seven of ten containers are completely clean (max 59–76 ms). Three are not, and
they are not marginal: 64 of the 2560 slow copies exceed 250 ms and six exceed
one second.

## 14. Post-warm mmap distribution (arm A4, 10 containers, 2560 copies)

Pooled: **p50 10.11**, p90 12.82, p95 13.64, **p99 36.43**, **max 200.29**,
mean 10.98, SD 10.92, CV 0.9945.

| threshold | copies | fraction |
|:--|--:|--:|
| >100 ms | 14 | 0.547% |
| >250 ms | **0** | 0% |
| >500 ms | **0** | 0% |
| >1000 ms | **0** | 0% |

Per container:

| request | p50 | p90 | p99 | max | cpu p50 | >100 | >250 | >500 | >1s | pathological |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--|
| `673fa85f7212` | 10.25 | 12.32 | 29.10 | 29.35 | 10 | 0 | 0 | 0 | 0 | . |
| `4f8b42490386` | 9.95 | 12.83 | 28.76 | 34.73 | 10 | 0 | 0 | 0 | 0 | . |
| `c93af51aa8e2` | 10.23 | 12.64 | 29.08 | 34.62 | 10 | 0 | 0 | 0 | 0 | . |
| `c55ed913ebec` | 11.00 | 12.63 | 32.46 | 35.37 | 10 | 0 | 0 | 0 | 0 | . |
| `f12157c94514` | 7.04 | 7.84 | 21.10 | 21.34 | 10 | 0 | 0 | 0 | 0 | . |
| `43654a84869b` | 11.75 | 13.13 | 31.73 | 35.07 | 10 | 0 | 0 | 0 | 0 | . |
| `50b7422d5347` | 10.72 | 13.33 | 30.22 | 39.14 | 10 | 0 | 0 | 0 | 0 | . |
| `8af154c39711` | 9.59 | 12.46 | 29.87 | 34.10 | 10 | 0 | 0 | 0 | 0 | . |
| `e6eb965847e7` | 8.02 | 9.36 | 24.81 | 26.91 | 10 | 0 | 0 | 0 | 0 | . |
| `a3f51d2427d5` | 11.03 | 32.95 | 161.44 | **200.29** | 10 | 14 | 0 | 0 | 0 | **YES** |

Headline movement, same deployment, same code, same containers' configuration:

| metric | A (control) | A4 (post-warm) | change |
|:--|--:|--:|--|
| copy p50 | 41.71 ms | 10.11 ms | **4.13x faster** |
| copy p90 | 54.92 ms | 12.82 ms | 4.28x faster |
| copy p99 | 428.40 ms | 36.43 ms | **11.8x better** |
| worst single copy | 2100.67 ms | 200.29 ms | **10.5x better** |
| copies >250 ms | 45 | **0** | eliminated |
| copies >1 s | 6 | **0** | eliminated |
| timed-copy throughput (17.14 GB, median container) | 6.81 GB/s | 14.89 GB/s | 2.19x |
| pathological containers | 3/10 | 1/10 | −2 (see §20) |

## 15. Per-container pathology

A container is pathological when **any single copy exceeds 100 ms**. That rule is
the pre-existing per-container rule from the A2/A3 phase, applied unchanged.

| arm | pathological / total |
|:--|--:|
| A (control) | **3 / 10** |
| A4 post-warm mmap copies | **1 / 10** |
| A4 warm positioned reads (>250 ms, threshold fixed before any A4 container ran) | **1 / 10** |

The remaining A4 sick container, `golden-p1-0-a3f51d2427d5`, is qualitatively
different from the control's three:

* its worst copy is **200.29 ms**, against 1386 / 2101 / 1128 ms for the control's
  three sick containers — an order of magnitude milder;
* it has **zero** copies over 250 ms, where the control's sick containers had 16,
  19 and 10;
* it is the **same container** that had the pathological warm read (8 blocks over
  100 ms, worst 971.77 ms). That host was slow at both primitives.

So A4 did not produce a clean arm; it produced an arm whose worst case is
200 ms instead of 2101 ms, and whose one sick container is confounded with a
sick warm read on the same host.

## 16. Pooled statistics, and why pooled alone would mislead

Pooled, A4 passes the pre-registered rule (0.547% over 100 ms against a 1% floor,
p99 36.43 ms against a 100 ms floor) and A fails it (2.500%, p99 428.40 ms). That
would read as `BACKING_AVAILABILITY_CONFIRMED`.

It is not reported that way, for the reason the A2/A3 phase already paid for: a
pooled distribution cannot see one sick container inside an otherwise healthy
arm. A4's pooled verdict and its per-container verdict disagree, and
`classify_fullread` refuses to credit a treatment that left a pathological
container. Both readings are printed:

```json
"fullread_decision": {
  "classification": "MIXED",
  "reasons": [
    "positioned_read_is_materially_slower_than_the_warmed_mmap_copy_so_replacing_it_would_regress_the_source_pass",
    "both_access_paths_show_a_tail_but_the_positioned_reads_are_fewer"
  ],
  "contemporaneous": true,
  "full_read_proven": true,
  "postwarm_mmap_clean": false,
  "positioned_read_replacement_justified": "no",
  "pathological_containers": {"A": 3, "A4": 1, "A4_warm_reads": 1}
}
```

## 17. Ordinal / source-offset analysis

**Warm reads, ordinals 0–7 vs the tail:** head p50 45.72 ms / max 50.83 ms; tail
p50 33.42 ms / max 971.77 ms. Per-ordinal p50: ordinal 0 = 45.7 ms, ordinals
1–7 = 32.3–34.3 ms. There is a small first-block effect — the very first 64 MiB
costs about 12 ms more than steady state — and it is **not** pathological. The
single worst warm block (971.77 ms) is at a mid-file offset, not the beginning.

**Mapped copies, ordinals 0–7 vs the tail:** control A head p50 48.31 / max 60.15
against tail p50 41.67 / max 2100.67; A4 head p50 29.38 / max 34.83 against tail
p50 10.10 / max 200.29. The pathology is **not** concentrated at the start in
either arm, which is consistent with a first-touch story being wrong and a
per-page/per-host availability story being right. (A4's head is higher than its
tail because the first eight copies are the four readers contending on a cold
start, not because of the mapping.)

**Offset identity.** This is the most useful new finding:

| set | distinct slow offsets | appear in >1 container |
|:--|--:|--:|
| A control, copies >100 ms | 53 | **11** |
| A4, copies >100 ms | 14 | 0 |
| A4, warm blocks >100 ms | 8 | 0 |

The control's 11 recurring offsets each appear in exactly **2 of the 3** sick
control containers (none in all three); the other 42 appear once. So certain
source offsets are intrinsically slower to fault in through the mapping, in more
than one independent container. Nothing similar appears in A4 or in the warm
reads.

**Do the same offsets go slow in both primitives?** Only 3 offsets are slow in
both the warm read and a mapped copy, each exactly once, out of 8 warm-slow and
14 copy-slow offsets — consistent with chance at this cohort size. Within the one
sick A4 container the overlap is **zero**: it had 8 slow warm blocks and 14 slow
copies at entirely disjoint offsets. That container was slow everywhere, not slow
at particular places.

Correlation from a 10-container cohort should not be over-read. The control's
cross-container offset recurrence is the part worth carrying forward, because
"same offset, different container" cannot be produced by per-host noise.

## 18. Total cost accounting

The timing boundaries are kept separate, and the warm read is never folded into
"setup":

| boundary | A (control) median | A4 median |
|:--|--:|--:|
| `fd_open_ms` | ~0.2 | ~0.3 |
| `mmap_create_ms` | ~0.4 | ~0.5 |
| **`warm_read_ms`** | — (A4 only) | **6274.2** |
| `warm_complete_to_first_copy_ms` | — | ~226 |
| `mmap_copy_loop_ms` | **2545.1** | **1155.1** |
| `total_generation_experiment_ms` (setup+copy) | **3089.8** | 7915.6 |
| **`warm_read + copy_loop`** | — | **7422.1** |

Per container, A4 `warm+copy` ranges 5982–11005 ms; the control's copy loop alone
ranges 2245–5413 ms.

**A4 is not an optimisation.** It spends ~6274 ms to save ~1390 ms of copy time.
Its source-side total is **2.4x the control's whole generation**, and it pays for
the source data twice: once through the positioned read and once through the
mapping. A faster copy loop was not supposed to be read as a faster arm, and the
accounting above exists so it cannot be.

## 19. Golden request correctness

All 20 requests, each checked individually — exit code alone was not accepted:

| requirement | result |
|:--|:--|
| `valid=true` | 20/20 |
| `true_cold=true` | 20/20 |
| `restore_count == 1` | 20/20 |
| `request_count == 1` | 20/20 |
| no fallback | 20/20 (`fallback_reason=None`) |
| no fatal failure | 20/20 (`fatal_failure=False`) |
| exact output SHA `3a6a0306…` | 20/20, 3083864 bytes |
| output durability mode `off` | 20/20 |
| complete experiment payload | 20/20 (`variants_complete == variants_expected`) |
| arm identity match | 20/20 |
| treatment contract satisfied | 20/20 |
| pinned arena teardown successful | 20/20 (`cuda_host_unregistered=true`, `rc=0`) |
| real Golden source owner untreated | 10/10 control-side payloads unwarmed; all 20 Golden loads completed |

## 20. Classification

```
CLASSIFICATION=MIXED
POSITIONED_READ_REPLACEMENT_JUSTIFIED=no
```

Against the four cases:

* **CASE 1 (`BACKING_AVAILABILITY_CONFIRMED`) — not claimed.** It requires A4's
  post-warm copies to be clean across *all* usable treatment containers. They are
  not: 1 of 10 still has 14 copies over 100 ms.
* **CASE 2 (`MMAP_PATH_CONFIRMED`) — rejected.** This requires the mapped reads to
  remain pathological after a proven full read. They do not remain in the same
  regime: the second-scale tail is entirely gone (6 copies over 1 s → 0; 45 over
  250 ms → 0), p99 fell 11.8x, and the worst copy fell 10.5x. Declaring the mmap
  path itself pathological would contradict the measurement.
* **CASE 3 (`BROADER_SOURCE_BACKEND_PATHOLOGY`) — rejected.** The warm reads do
  carry a tail, but the mapped copies no longer do. Both primitives are not
  equally affected.
* **CASE 4 (`INCONCLUSIVE_CURRENT_COHORT`) — not used either.** The control
  reproduced the pathology 3 times in 10 containers, so the comparison was
  informative.
* **MIXED** is the honest label: the warm read reproducibly and substantially
  improves the mapped-copy distribution, and does not eliminate the tail. One
  container in ten is still sick, and that container was also sick at the
  positioned read.

The per-container counts are suggestive, not significant: **3/10 versus 1/10,
Fisher exact two-sided p = 0.58.** A4 clearly improved the *distribution*
(p50 4.13x, second-scale tail eliminated, 2 fewer sick containers) but the
per-container *rate* difference is well within noise at n=10.

What is established, and what is not:

* **Established:** with the backing file demonstrably consumed in full
  beforehand, the identical mmap copy path moves its 17.14 GB at 14.89 GB/s
  instead of 6.81 GB/s and never once exceeds 200 ms. Backing availability is
  therefore *strongly implicated* in the stall.
* **Not established:** that backing availability is the *whole* cause. One
  container in ten still shows the regime, and it was slow at both primitives.

## 21. Positioned-read replacement evidence

```
POSITIONED_READ_REPLACEMENT_JUSTIFIED=no
```

Not because the positioned reads are unhealthy — they are mostly excellent — but
because they are **far slower than the thing they would replace**:

| path | bytes moved | throughput |
|:--|--:|--:|
| A4 warm positioned read (`os.preadv`, 64 MiB blocks) | 12.31 GB | **1.93 GB/s** |
| A4 post-warm mmap copy (`mmap` + `libc.memmove`) | 17.14 GB | **14.89 GB/s** |

`classify_fullread` computes the ratio from the payloads rather than asserting a
verdict, and applies a pre-set rule: a full-file positioned read costs one pass
and the mapping it would replace also costs one pass, so if the positioned read
is below half the warmed copy's throughput the swap is a regression.

```
"throughput_gbps": {"warm_positioned_read": 1.9292,
                    "postwarm_mmap_copy": 14.8889,
                    "control_mmap_copy": 6.8118}
"warm_read_vs_postwarm_mmap_ratio": 0.1296
"positioned_read_replacement_justified": "no"
```

At a ratio of **0.13**, the positioned read is **7.7x slower** than the warmed
mapping. Replacing `mmap -> memmove` with `preadv -> arena` would make the source
pass substantially worse. The warm read's median block is a healthy 33.43 ms
(1.88 GB/s) with a tight CV of 0.14 across containers, but a ~6.3-second
full-file pass is still far worse than a ~1.2-second warmed copy pass.

## 22. Next experiment

**Not implemented here, by instruction.** The open question A4 creates is:

> How do we get the backing data resident without performing two complete source
> passes?

A4 pays 12.31 GB of reads to make the copy of 12.31 GB cheap, and the cheap copy
still costs 1.16 s. The obvious next discriminator, in order:

1. **Warm only what is about to be copied, and overlap nothing.** The copy loop is
   strictly ordered and single-pass; the question is whether warming the *next*
   window just ahead of the reader (one 64 MiB block of lookahead) removes the
   tail without a full extra pass. This is the smallest change that could turn the
   mechanism finding into a wall-clock win.
2. **Warm with the destination already resident.** The control's `gen->setup` is
   ~430–630 ms, dominated by the experiment's own 1 GiB `cudaHostRegister`. Not
   the target here, but it means any warm-up budget has to be measured against
   total generation wall, not copy wall.
3. **Test the 11 recurring control offsets directly.** They are pathological in 2
   of 3 sick control containers and nowhere in A4, which is the strongest
   per-offset signal in this lane. Reading those specific 64 MiB ranges with and
   without a mapping would tell us whether the property is the offset or the
   access path.

The production replacement — if any — is `preadv -> pinned arena` instead of
`mmap -> memmove`, and on this evidence it would be a regression. Do not build it
from A4.

## 23. Things that remain unproven

* That backing availability is the **sole** cause. One container in ten remained
  pathological after a proven full read.
* That the per-container rate difference (3/10 vs 1/10) is real. Fisher p = 0.58.
* That warming helps *any* real Golden request. A4's warm read is scoped to the
  experiment's own mapping by a process-local gate, and all 20 real Golden loads
  ran untreated.
* That page residency is directly observable. `page_population_observable=false`
  is recorded for A3 and remains unavailable under gVisor mincore; A4's inference
  rests on measured call and copy times, not on a residency probe.
* That the 11 recurring control offsets are a property of the checkpoint file
  rather than of the Volume's backing layout. Three containers is a thin basis.
* Anything about behaviour on a different GPU type, region, or a non-Volume
  filesystem.

## 24. Things that must NOT change

Unchanged and verified unchanged by this experiment: arena design and slot count
(16 x 64 MiB), `cudaHostRegister` behaviour, QD, block size (64 MiB), reader count
(4), the 4 ms pacer, slot-release semantics, the H2D dispatcher, CUDA
streams/events, NUMA policy, CPU affinity, the whole-file mmap lifecycle, the
workflow, the sampler, model files, and Modal GPU/CPU/memory configuration.

Structurally: the timed copy still runs through the production
`_run_reader_loop -> execute_block -> libc.memmove(pinned_arena_slot,
map_address + source_offset, length)` with the existing `SourceCopyProbe` around
the memmove and nothing else. A test asserts `execute_block` still copies from
`plan.map_address + source_offset` with `memmove` and contains no `pread` and no
`full_file_read`. The only added code is one bounded scratch `bytearray` and one
sequential positioned-read loop, both inside `build_plan`, both behind the
process-local gate.

No production source replacement was implemented, and none should be until the
§22 question is answered.

## 25. Testing 1 / `modal_target.toml` warning

`Testing 9 / ws_ee7221847f7d` is over its Modal spend limit
(`Workspace ac-tL3lF9qiTsfwGw0lr4esfg has exceeded its spend limit`; `golden
deploy` exits 1 and writes no manifest). On explicit operator instruction the
experiment destination was moved to `Testing 1 / ws_e677ab553606`.

> **This is a committed edit to `config/v2/modal_target.toml` in this lane's diff,
> not a local override, and it does not belong in production.** The eventual
> integration agent must consciously choose: restore `Testing 9` once its spend
> limit is raised, or keep `Testing 1` deliberately. It must not arrive by
> accident through a merge. This lane did not reset or rewrite any legitimate
> experiment commit to remove it, and did not treat the redirect as a production
> change.

## 26. Local verification

* `python -m pytest tests -m fast_unit -q` → **609 passed, 2 failed, 7 skipped**.
  The two failures are the pre-existing `test_rx9p_h_identity_chain` ones that
  `211d204b` already documented and that reproduce on a pristine tree.
* `python -m pytest tests/test_source_fullread_isolation.py
  tests/test_source_population_isolation.py tests/test_source_copy_isolation.py
  tests/test_c0_source_threads.py tests/test_source_copy_probe.py
  tests/test_v2ctl_source_probe.py tests/test_golden_flag_reaches_container.py
  tests/test_source_child_script_launch.py -q` → **296 passed, 6 skipped**.
* `python tools/source_copy_isolation_report.py --root .
  --profile-prefix golden_p1_parallel_p9_srccopy_a4 --out
  artifacts/source_fullread/summary_fullread.json`

### Two defects the new tests caught before any container ran

* An `InterruptedError` from the positioned read fell through to the
  `got <= 0` EOF check, so an interrupted read aborted the arm with
  `eof_before_expected_size`. EINTR now retries without advancing the offset and
  is counted in `warm_eintr_retries`.
* `population_contract` rejected a control carrying a `fadvise` or
  `MAP_POPULATE` treatment but not one carrying a warm read. All three treatments
  are now listed, so adding a treatment without its control-side check fails the
  contract instead of silently passing.

### One defect the first real cohort caught

`classify_fullread` read `every_warm_read_exact` from the population roll-up dict
rather than from `warm_read_evidence`, so `full_read_proven` was permanently
`False` and every cohort would have been reported inconclusive. The exactness
check now lives in `warm_read_evidence`, which is the function that sees each
container's own byte counts.
