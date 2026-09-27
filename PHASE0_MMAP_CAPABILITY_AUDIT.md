# Phase 0 — mmap capability audit (CPU-only, gVisor)

Runtime: `4.19.0-gvisor` (confirmed by `/proc/sys/kernel/osrelease`). File:
`/root/models/text_encoders/qwen_3_4b.safetensors`, 8044982048 bytes. Block 64 MiB.
Probe: CPU-only Modal function (no `gpu=`), artifact `phase0_probe/capability_probe.json`.

## 1. What the deployed runtime actually does

| mechanism | return | verdict in OUR environment |
|---|---|---|
| `mmap(PROT_READ, MAP_PRIVATE)` | rc 0 | **works** |
| `madvise(MADV_WILLNEED)` | rc 0, errno 0 | **accepted but a functional no-op** (see below) |
| `madvise(MADV_POPULATE_READ)` | rc −1, errno 22 | **NOT SUPPORTED (EINVAL)** |
| `madvise(MADV_POPULATE_WRITE)` | rc −1, errno 22 | **NOT SUPPORTED (EINVAL)** |
| `readahead()` | rc −1, errno 22 | **NOT SUPPORTED (EINVAL)** |
| `mmap(..., MAP_POPULATE)` | rc 0 | **accepted but does not materialize** |
| `mincore()` | rc 0 | **callable but NOT MEANINGFUL** |
| `os.O_DIRECT`, `os.preadv` | — | both available |

### mincore is not meaningful
`mincore_before_touch` reports **16384 of 16384 pages resident** on a mapping that has never
been touched. `mincore_after_touch` and `mincore_populate_window` report the same. mincore
therefore cannot be used to prove or disprove residency anywhere in this work.

### MADV_WILLNEED is a no-op — proven functionally
Because mincore is useless, the only honest test is whether advising *before* a cold first
touch makes that touch faster. Two fresh windows, same container, same file:

| test | first-touch ms |
|---|---:|
| cold (no advice) | 24.7 |
| `MADV_WILLNEED` first | 27.0 |

The advised touch was **not** faster (slightly slower, within noise). Combined with
`readahead` and both `MADV_POPULATE_*` returning EINVAL, the correct reading is that gVisor
**accepts** the WILLNEED hint and does nothing with it. Any earlier M1 result is therefore a
test of *M0 with a no-op call added*, not a test of a real kernel hint.

### MAP_POPULATE does not populate
Mapping a 64 MiB window with `MAP_POPULATE` returned rc 0 in **4.8 ms**. A genuine
materialization of 64 MiB in this environment costs tens to hundreds of ms (below), so
MAP_POPULATE cannot have populated anything. This is consistent with the earlier M2
observation that cost merely *moved* into `map_ms`.

## 2. Where the source cost actually is

| measurement | value |
|---|---:|
| first touch of a 64 MiB mapping (container A, cold) | **1116 ms** (0.057 GB/s) |
| second touch of the same range | **11.7 ms** (5.7 GB/s) |
| first touch, 64 MiB (container B) | **61.0 ms** |
| second touch, same range (container B) | **6.0 ms** |
| `faults_during_memcpy` (minor / major) | **0 / 0** |

Two findings matter:

1. **The entire cost is in the first access.** Second access is 5–95× faster. Nothing about
   the mapping itself is slow; the underlying fetch is.
2. **Cold first-touch cost varies ~18× between containers (61 ms vs 1116 ms)** for the same
   64 MiB block of the same file. This is direct evidence that placement/host state dominates
   source latency, and it is the same variance that produced the region-composition confound
   in the pacing cohorts.
3. gVisor reports **zero page faults**, so fault counters can never be used as evidence here.

## 3. What forces mmap pages to become accessible

In this environment the **only** thing that materializes file-backed mmap pages is an actual
access through the mapping. No advice mechanism can force it:

- `readahead` — unsupported
- `MADV_POPULATE_READ` / `MADV_POPULATE_WRITE` — unsupported
- `MAP_POPULATE` — accepted, does nothing
- `MADV_WILLNEED` — accepted, does nothing (proven functionally)

So a "toucher" is not an alternative to materialization — it **is** the materialization. The
only question a toucher can answer is whether doing that work *earlier* (bounded lookahead)
reduces total wall or tail incidence.

## 4. Answers to the Phase 0 questions

1. **What was M0 copying FROM?** A persistent read-only mapping of the file
   (`mmap(PROT_READ, MAP_PRIVATE)`, taken through libc so the raw address is owned).
2. **What was M0 copying INTO?** A preallocated per-process private `bytearray(read_bytes)`.
3. **Did M0 have any unnecessary intermediate payload buffer?** No — the destination *is* the
   consumer representation; there is exactly one buffer and one copy.
4. **What source-read syscalls occurred in an M0-only run?** None. Only `open`, `fstat`,
   `mmap`, `memcpy`, `munmap`. No `preadv`/`read` ever touches the payload.
5. **Was M1's MADV_WILLNEED implemented, ignored, or unknown?** **Ignored.** Accepted at the
   syscall boundary, proven functionally inert.
6. **What did MAP_POPULATE actually cause?** Nothing material. It returns success and does not
   populate; the 4.8 ms map time proves it.
7. **Is mincore meaningful here?** **No** — it reports full residency unconditionally.
8. **What operations force mmap pages accessible?** Only real accesses through the mapping
   (loads / memcpy / native scan). No advice or flag can do it.

## 5. Consequence for the remaining phases

- **M1 is expected to reproduce M0 exactly**, because its only difference is a proven no-op.
  It is still worth replicating to confirm, but it should be labelled honestly as
  "M0 + inert advice".
- **M2's cost structure is now explained**: with MAP_POPULATE inert, the populate cost the
  earlier work measured in `map_ms` cannot have been population of the payload, so M2's
  observed behaviour needs the replication to be interpreted carefully.
- **A toucher is the only lever available** for moving source work earlier, because it is the
  only mechanism that actually materializes pages. Phase 1 is therefore the right next test.
- **Native touch support is in place**: `source_touch.c` is now compiled into the image as
  `/opt/source_touch.so` (`st_touch_pages`, `st_touch_lines`, `st_reduce_full`), giving
  native, volatile-load materialization with no Python per-page loop and no payload copy.
