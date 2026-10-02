# Task 1 — Proven memory layout of primary vs rescue destinations

Audited implementation: `run_odirect_rescue_probe` / `_od_reader_child` (the Exp-4 O_DIRECT rescue
path actually under test). Evidence is runtime addresses recorded from a real rescue event, not names.

## The event

`task1_layout/im-01.json` (gcp:us-west). Four real rescue attempts; two shown here.

| event | block | primary | primary ms | rescue | rescue ms | winner |
|---|---:|---|---:|---|---:|---|
| A | 30 | reader 2 (pid 8) | 1608.6 | reader 4 (pid 10) | 1367.1 | rescue |
| B | 31 | reader 4 (pid 10) | 1887.6 | reader 2 (pid 8) | 448.1 | rescue |

Note event B: reader 4 was the spare, promoted to a normal worker after winning event A, and reader 2
(the original loser of A) later took the spare role. That is the lifetime rule working, and it also
proves the rescue destination is not tied to a fixed "spare slot".

## Address table (real addresses, one run)

| thing | process | backing object | base addr | write addr | length | overlaps canonical SHM slot? |
|---|---|---:|---:|---:|---:|---|
| stuck buffered primary dest (block 30) | reader 2, pid 8 | private `bytearray` on process heap | `0x2b5588000010` | `0x2b5588000010` + block offset within buffer (0) | 134217728 | **No — there is no payload SHM slot** |
| O_DIRECT rescue dest (block 30) | reader 4, pid 10 | anonymous `mmap(-1, ...)` (MAP_PRIVATE) | `0x2b5590001000` | `0x2b5590001000` (block start; 4096-aligned) | 134217728 (rounded to 4096) | **No — there is no payload SHM slot** |
| canonical / publication SHM slot | — | **does not exist for payload bytes** | — | — | — | n/a |
| shadow / side buffer | reader 4, pid 10 | same anonymous mmap as the O_DIRECT dest | `0x2b5590001000` | same | 134221824 allocated | No |
| final winner-copy source/dest | — | **no winner copy of payload bytes occurs** | — | — | — | n/a |

Per-reader addresses (all five readers, same run):

| reader | pid | buffered dest | len | O_DIRECT dest | len | intra-process overlap |
|---:|---:|---:|---:|---:|---:|---|
| 0 | 6 | `0x2b5588000010` | 134217728 | `0x2b5590001000` | 134221824 | False |
| 1 | 7 | `0x2b5588000010` | 134217728 | `0x2b5590001000` | 134221824 | False |
| 2 | 8 | `0x2b5588000010` | 134217728 | `0x2b5590001000` | 134221824 | False |
| 3 | 9 | `0x2b5588000010` | 134217728 | `0x2b5590001000` | 134221824 | False |
| 4 | 10 | `0x2b5588000010` | 134217728 | `0x2b5590001000` | 134221824 | False |

**Read this carefully:** the virtual addresses are identical across readers because every reader is
`fork`ed from the same parent and allocates the same layout. Identical VAs across **different PIDs are
different address spaces backed by different physical pages** — they are not the same memory. Within
each process the two destinations are disjoint (separate mappings ~134 MB apart).

Shared memory actually used by the engine — **all of it**:

| object | addr | bytes |
|---|---:|---:|
| ownership | `0x2b55800d6000` | 60 |
| winner | `0x2b55800d6040` | 240 |
| winner_kind | `0x2b55800d6130` | 60 |
| start_ns | `0x2b55800d6170` | 480 |
| winner_exit_ns | `0x2b55800d6350` | 480 |
| attempts | `0x2b55800d6530` | 240 |
| rescue_sent | `0x2b55800d6620` | 60 |
| lane_flat | `0x2b55800d6670` | 240 |
| lane_off | `0x2b55800d6760` | 20 |
| next_global | `0x2b55800d6668` | 8 |
| last_start | `0x2b55800d6778` | 8 |
| spare_promoted | `0x2b55800d6780` | 4 |
| spare_refilled | `0x2b55800d6788` | 4 |
| **total shared** | | **1904 bytes** |

`payload bytes in shared memory: 0`. The engine shares **1.9 KB of integers**, not file bytes.

## Explicit answers

**1. Is the stuck primary physically writing into the same memory range the rescue writes into?**
**No.** The buffered primary writes into its own process-private `bytearray`; the O_DIRECT rescue
writes into a different process's anonymous private mmap. Different address space, different physical
pages. Recorded `intra_process_overlap` is `False` for all five readers.

**2. Or are they completely separate destinations?** **Completely separate.** Two different processes,
two different mappings, ~134 MB apart in VA within any one process, and never in the same address space.

**3. Does either physical read touch the canonical SHM slot before a winner is known?** **There is no
canonical SHM slot for payload bytes, so no.** The only shared objects are the 1904 bytes of integer
metadata above. Neither `preadv` is even given a pointer into shared memory.

**4. When a rescue wins, exactly what copy/publication occurs?** **No copy of payload bytes occurs at
all.** Publication writes only integers: `winner[bid] = reader_id`, `winner_kind[bid] = 2`,
`winner_exit_ns[bid] = exit_ns`, `completed.value += 1`, `ownership[bid] = 2`. The rescue's bytes stay
in the rescue process's own mmap and are never moved anywhere.

**5. Can a late loser still reference or mutate the winning slot in any way?** **It cannot mutate any
winning data, because no data is shared.** A late loser can only take the `else` branch and increment
its private `stale` counter; `winner[bid]` is only written when it is still `-1`, so the first validated
winner is fixed. Structurally, a loser has no handle to the winner's buffer: different process,
different mapping.

## Consequence for interpretation

Because no payload bytes are ever copied, "rescue wins" in this harness means **"the rescue read
returned first"**, not "the rescue's bytes were published". The harness measures *timing and byte
counts*, never content movement. Any future step that needs real publication (a canonical SHM slot, a
winner copy, or direct-to-GPU staging) is **not yet implemented** and must be designed separately —
it must not be assumed to exist.

The practical implication for Step 3: a paired M0 rescue needs its own destination exactly as the
O_DIRECT rescue has one, and that is already structurally guaranteed by the per-process private
mapping. There is no aliasing risk to eliminate.
