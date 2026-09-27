# Source-I/O optimization ledger

The no-repeat ledger as it stands today.

| Experiment / change | Speed effect | Tail effect | Current disposition |
|---|---|---|---|
| QD1→QD2→QD4 raw concurrency | Historical raw-host probes scaled dramatically | Not a tail cure | Proved concurrency matters, but old 30–40 GB/s numbers are not equivalent to current cold loader |
| Block-size sweeps 32/64/128/256 MiB | Different winners depending boundary; historically 32 MiB raw, 256 MiB enclosing loader | Geometry changes tail shape | No universal winner |
| Current H100 64 MiB / QD4 | ~5.8–6.0 GB/s class | Still occasional pathology | **CARRY** — current preadv geometry |
| QD5 | ~−1% vs QD4 | No trustworthy improvement | REJECT |
| QD6 | ~−9% | No trustworthy improvement | REJECT |
| QD7 | ~−7% | apparent clean tail confounded by region | REJECT |
| QD8 sustained | Worse service latency / throughput | Can become pathological | REJECT |
| Threads → 4 independent processes | ~+10–12% median within matched/provider analysis | Does not eliminate multi-second stalls | **CARRY** |
| 8 processes / 4 MiB old architecture | ~25–33% worse than old baseline | No cure | REJECT exact topology |
| Persistent FDs | Removes open churn | Sickness remains | **CARRY** for cleanliness only, not a cure |
| Eager workers | Removed a real ~3.4 s first-start serialization; worker ready ~1–2 ms | Tail remained | **CARRY** |
| Pinned vs pageable source destination | historical difference ~1% | No cure | REJECT as tail mechanism |
| Persistent registered pinned arena | Makes H2D cheap and reusable | Does not cure source sickness | **CARRY** for transport |
| Private source buffer → SHM split | Added copy, diagnostic only | Localized sickness inside preadv rather than copy | DIAGNOSTIC; don't use as speed optimization |
| Pretouch / page-fault theory | No useful gain | Did not remove clustered sickness | REJECT |
| Fresh anonymous/rehome copies | Fresh copy itself fast after data read | You still pay slow source read first | REJECT production rehome |
| Primers / leading reads / varying primer depth | Some small cohorts looked cleaner | Failed replication; catastrophic tails returned | REJECT as established fix |
| Persistent-FD + static region reader | Good healthy baseline | tails survive | **CARRY** baseline |
| Old central manager greedy allocator | ~13% regression | no demonstrated benefit | REJECT implementation |
| Manager bubble profiling | Found ~1.429 ms/block coordination bubble | — | Useful diagnosis |
| Self-service allocator | bubble cut to ~0.11 ms/block; effectively near static after placement | retains scheduler flexibility | **CARRY** / current flexible design |
| Globally interleaved allocator | initially slower | no balancing benefit in healthy runs | SUPERSEDED by self-service |
| Fixed ~2 GiB static ownership | Fast healthy path, ~6.0 GB/s recent median | cannot dynamically react to straggler | Fastest simple preadv control |
| Work-stealing study | little normal opportunity in old static-tail experiment | pathological reads dominated imbalance | Do not use as proof against newer allocator; diagnostic only |
| Same-range immediate race-N duplicates | no accepted-latency improvement | no tail cure | REJECT |
| Dedicated same-path hedge after bug fixes | functional | wins photo-finish by <~1 ms | Not useful as cure |
| 2×64 MiB rescue of 128 MiB block | — | pathological original and subreads photo-finished | REJECT |
| 4×32 MiB rescue | — | worse / no escape | REJECT |
| Old 150 ms O_DIRECT hedge | rescue mechanically worked | endpoint became substantially worse due loser/resource lifetime | REJECT unchanged implementation |
| Current prearmed O_DIRECT spare | healthy path preserved | did not cap tail in current single-spare topology | UNRESOLVED as independently paired rescue; do not call proven cure |
| ROTATE3/4 resource islands | real rescue wins; one historical save >23 s | bank exhaustion and H100 tails remained | Containment, not cure |
| SHAM → SPLIT/fresh resource | tail incidence dropped significantly in old integrated architecture | strongly implicated reused control/resource lifecycle | Mechanistic evidence, not final architecture |
| Fresh physical backing only | no consistent benefit | catastrophic carryover remained | REJECT as carrier fix |
| Fresh slot CUDA completion events | little healthy-path cost | strongest reduction of CLIP→UNET severe propagation | **CARRY** in integrated CUDA design |
| Fresh H2D stream only | — | weaker; severe tails remained | REJECT as sufficient cure |
| Fresh timing/span events | some benefit | weaker than completion events | Not sufficient |
| R41 source→ring→dispatcher→reaper separation | not remotely proven as throughput win | prevents source workers from waiting CUDA events | **CARRY** structural invariant |
| Direct VolumeGetFile2/block transport | ~0.092 GB/s UNET in tested path | avoided preadv, but unusably slow | REJECT |
| Volume V1 vs V2 mounted POSIX | roughly similar ~7.5 GB/s in historical RTX best geometry | no magical stabilization | V2 not a source-speed cure |
| Physical sharding / file sharding | did not produce stable target bandwidth | no durable cure | REJECT; do not revisit |
| M0 persistent mmap + C memcpy | historical small cohort 6.069 GB/s median, slightly ahead of preadv sample | worst block 443 ms; insufficient n | BEST alternate source candidate; needs 42-run @4 ms |
| M1 mmap + MADV_WILLNEED | 5.954 GB/s | worse worst block ~813 ms | REJECT |
| M2 MAP_POPULATE | 5.946 GB/s median | catastrophic ~6.4 s worst; merely moves cost | REJECT hard |
| M0 as paired rescue | — | 0 meaningful escapes in 53 ≥1 s events; median finish only ~1.4 ms from original | REJECT as rescue |
| Source-wall perfect profiler | found no giant hidden hole | ~97.4% of wall effectively explained by reads/concurrency | **CARRY** instrumentation |
| 4 ms pacing | recent 42-run median 5.818 GB/s | 0 ≥250 ms in that frozen cohort | **CURRENT WINNER** |
| 5 ms pacing | −5.9% median vs 4 | tails only in unique regions; no matched-region improvement | REJECT from current evidence |
| 6 ms pacing | −4.6% median vs 4 | same; no matched-region improvement | REJECT from current evidence |
| 7/8 ms pacing | not run | not needed unless 5/6 later prove beneficial | DO NOT RUN now |

## Current best configurations

| Purpose | Current config |
|---|---|
| Fastest simple H100 preadv source | 4 processes · QD4 · 64 MiB · 4 ms global start spacing · contiguous/static regions; recent frozen control median ~6.015 GB/s |
| Best flexible scheduler architecture | 4 processes · QD4 · 64 MiB · 4 ms · self-service allocator; old manager bubble essentially removed; recent pooled median 5.818 GB/s, with remaining difference heavily placement-sensitive |
| Best alternate primary source candidate | M0 persistent mmap + C memcpy, no WILLNEED/POPULATE; historical n≈12 median 6.069 GB/s, but not yet earned promotion |
| Best integrated CUDA lifecycle rule | persistent physical resources are okay candidates, but fresh/generation-scoped slot completion state, stale-attempt rejection, and source workers never waiting reusable CUDA completion events |
| Tail rescue status | no clean winner yet: same-range, split-range, M0 rescue all fail; O_DIRECT requires a better independently-paired topology before it can be closed or promoted |
| Pacing winner | 4 ms; current evidence says increasing it only buys extra waiting |
