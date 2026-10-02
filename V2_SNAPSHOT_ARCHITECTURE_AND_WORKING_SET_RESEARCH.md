# V2 Snapshot Architecture, Working-Set, and Restore Optimization Research

Baseline: `V2_10_COLD_RUNS_35S_COOLDOWN.md` (deployment `b557b2401f293223`, 10/10 valid cold runs, 35 s cooldown, UNET excluded from CPU snapshot, RTX PRO 6000 / 12 CPU / 32768 MB).

| Metric | min | median | max |
|---|---|---|---|
| Pre-Python snapshot restore | 0.809 s | 3.509 s | 6.487 s |
| Python/application restore | 0.387 s | 0.616 s | 1.535 s |
| Production-adjusted TOTAL WALL | 15.018 s | 15.582 s | 26.471 s (outlier) |

---

## Evidence status

This section fixes what is measured, derived, estimated, inferred, and unknown. **Nothing below equates RSS with pages-file bytes.**

**MEASURED** (from repository artifacts, no new runs):
- Restored RSS of the UNET-absent (clip_vae) snapshot design: **VmRSS 13133.75–13133.76 MiB ≈ 12.826 GiB**, cgroup memory.current 13592.96 MiB (secondary) — 6 restore-only probes, GCP/us-east4, Aug 11 (`FAST_DISK_SNAPSHOT_RESTORE_REPORT.md:88,120-122`).
- Restore-side VmRSS in another restore-only container: restore_start 11853.8 → restore_complete 13412.1 MiB; peak_execution 25153.6 MiB (during UNET H2D) (`d2_construction.log:7,23,53`).
- Capture RSS of a **full-model** deployment (not the baseline): `before_capture rss_kb=26600620` (GCP, ≈25.37 GiB) and `26573108` (AWS, ≈25.34 GiB); mappings 2885/2884; **anon=705/704 and file=2180 are mapping COUNTS, not bytes**; modules=10452; gc_objects≈1.226 M (`deploy1_all.log:241,492`).
- VAE retained-model storage accounting: `storage_bytes=167639366` ≈ **160 MiB** (bounded 64-storage; `d2_construction.log:1076`).
- Pre-Python restore distribution Aug 13 baseline: 0.809 / 3.509 / 6.487 s; Aug 11 same-design probes: 5.448 / 6.480 / 9.754 s (`FAST_DISK…:130`).
- Client-side submission→python-resume variance 10.67 / 22.76 / 203.19 s (`V2_REMAINING_OPTIMIZATION_DIAGNOSTICS.md:173`).
- FULL-snapshot reference (user-provided): pre-Python 1.9 / 4.7 / 7.4 s; Python 0.48 / 1.33 / 3.81 s; restored RSS 21–23 GiB (`FAST_DISK…:142-143`).
- **smaps_rollup is unavailable inside the sandbox** (every eviction line shows `smaps_* = absent`; `FAST_DISK…:121`: "smaps rollup unavailable (`source=unavailable`)"). cgroup readable in some runs, absent in others.

**STRONGLY SUPPORTED** (public architecture + our code):
- Modal CPU snapshots are gVisor/runsc checkpoint-restore; restore is described by Modal as byte-throughput-bound; Modal preloads the entire pages file into host page cache; background restore lets Python resume before all pages are hydrated (gVisor `--background`).
- Our capture contains CLIP + VAE anonymous CPU copies (`DISABLE_MMAP=True`, `modal_app.py:8451`) and no UNET (evicted pre-capture, `:8751-8762`); conditioning/prompt caches are empty at capture.
- Our post-restore validation walks are metadata-only (`_check_tensor_devices`, `cpu_snapshot_models.py:1136-1172`); CLIP weight bytes are first touched on conditioning-cache miss.
- The 0.8–6.5 s distribution is **consistent with** a byte-throughput model at ~2 GiB/s for a multi-GiB pages file — not proven by it (see §5).

**INFERRED**:
- Clean file-backed pages are not serialized into the pages file (gVisor MemoryFile contents = private/anonymous; filesystem state is captured separately).
- The "restore duration = pages bytes / throughput" model and the host-variance story (page-cache warmth, tail network < 2 GiB/s, cgroup CPU stalls) — Modal's own blog names the same tail causes.
- Capture-time mapping counts (705 anon / 2180 file) suggest anonymous memory is concentrated in few VMAs.

**UNKNOWN** (explicit, do not treat as facts):
- **Actual pages-file (pages.img) size: unmeasured.** No artifact measures it; Modal 1.4.3 exposes no checkpoint-size API (`restore_state_probe.py:6-10`).
- **Capture anonymous bytes: unmeasured.** smaps_rollup is unreadable in the sandbox; VmRSS includes file-backed pages. The Anonymous/Private_Dirty/Shared_* split has never been observed.
- Whether the Aug 13 baseline's capture matches the Aug 11 restored RSS exactly (same design, different deployments/dates).
- Whether pre-Python restore ends before, during, or after background page hydration (Modal/gVisor public material does not fix this boundary).
- Whether gVisor's `--exclude-committed-zero-pages`, compression, or `--direct` are used by Modal.
- R1 import-deferral removable bytes (see §11): unmeasured.

---

## 1. Executive findings

1. **Modal CPU memory snapshots are gVisor (`runsc`) checkpoint/restore of the whole sandbox, with memory pages serialized into one "pages file" that Modal stores in its distributed FUSE filesystem and aggressively preloads into host page cache.** Modal: "most of the performance is won or lost on how fast the main process's memory mappings can be brought into the operating system's page cache" `[FACT FROM MODAL]`. Our 0.8–6.5 s pre-Python restore is **consistent with** Modal's documented restore range for GiB-scale pages files — but the numerator (actual serialized bytes) is unmeasured, and one cross-experiment comparison (UNET-absent, −8 to −10 GiB RSS: pre-Python 5.4–9.8 s vs FULL 1.9–7.4 s) shows host/scheduling variance can dominate any byte effect (§5.3).

2. **Our captured footprint is dominated by the base runtime, not CLIP+VAE — as RSS.** Restored RSS 12.826 GiB (MEASURED) decomposes roughly as base runtime ≈ 10.4 GiB (DERIVED by subtraction) + CLIP ≈ 1.5–2.5 GiB (ESTIMATED) + VAE ≈ 0.4 GiB resident (storage accounting 160 MiB MEASURED). The anonymous (serialized) split is **UNKNOWN** — RSS ≠ pages.img bytes. CLIP+VAE are anonymous CPU copies (`DISABLE_MMAP=True`), so their bytes *likely* serialize; clean file-backed base-runtime pages *likely* do not.

3. **Our post-restore code touches almost no model weight content.** Validation walks are metadata-only; CLIP content is first touched on cache miss. Our early working set is small; restore latency is dominated by platform-side byte transfer + host variance, not by our touch order. **Touch reordering is secondary; byte reduction is the lever — but the byte-reduction lever's magnitude is itself partially unmeasured (import-deferral) or platform-side (compression, zero-page exclusion).**

**Strongest application-controlled optimization:** capture-time allocator hygiene (`gc.collect()` + `malloc_trim(0)` before `startup()` returns) — the only lever that plausibly reduces serialized pages-file bytes without new platform support, at LOW risk (see §11 R2a). **R1 import deferral may be larger but its magnitude is unmeasured; do not budget it until measured.**

**Biggest unresolved unknowns:** (a) actual pages-file bytes (in-sandbox smaps unavailable; no Modal API); (b) whether pre-Python restore ends before/during/after background hydration; (c) Modal's exact runsc restore flags (`--background` implied; compression/zero-page/`--direct` unknown).

---

## 2. Modal snapshot architecture

### 2.1 What it is built on

- `[FACT FROM MODAL]` "Container snapshotting functionality is an outgrowth of the 'checkpoint/restore in userspace' (CRIU) kernel technology… for security reasons Modal uses the gVisor container runtime `runsc`… gVisor's core `kernel.go` file contains checkpoint/restore code and at least eighteen system components implement checkpoint/restore functionality in `save_restore.go` files." — https://modal.com/blog/mem-snapshots
- `[FACT FROM MODAL]` "A Modal memory snapshot is a couple of files that represent the entire state of a Linux container right before it was about to accept a request. We capture the container's filesystem mutations and its entire process tree." — https://modal.com/blog/mem-snapshots
- `[FACT FROM MODAL]` GPU snapshots layer on "our existing gVisor checkpoint/restore system" — https://modal.com/blog/gpu-mem-snapshots. Not used by us (CUDA disabled at capture).
- `[FACT FROM MODAL]` Snapshots are created on-demand per worker type; CPU-only functions need ~6 snapshots for coverage; restore falls back to normal start on failure. — https://modal.com/blog/mem-snapshots, https://modal.com/docs/guide/memory-snapshots
- `[FACT FROM MODAL]` "Memory Snapshots use the same high-performance distributed filesystem that delivers Modal Images and Modal Volumes" — https://modal.com/docs/guide/memory-snapshots

### 2.2 Snapshot file structure

- `[FACT FROM GVISOR]` Image path contains `checkpoint.img` (sentry object graph), `pages_meta.img` (MemoryFile metadata), `pages.img` (raw 4 KiB / huge-page contents); newer split-filesystem checkpoints add an FS manifest + multi-tar. — https://github.com/google/gvisor/blob/master/pkg/sentry/state/checkpointfiles/checkpointfiles.go
- `[FACT FROM GVISOR]` Restore reads state, then page metadata, then page file; pages file is "page-aligned… so it can be opened with `O_DIRECT`." — https://github.com/google/gvisor/blob/master/runsc/sandbox/sandbox.go
- `[FACT FROM MODAL]` Pages files are "typically 100MiB-10GiB" — https://modal.com/blog/mem-snapshots
- `[INFERENCE]` Modal uses the standard `checkpoint.img` + `pages_meta.img` + `pages.img` layout (no public Modal gVisor fork exists).

### 2.3 How restore happens

- `[FACT FROM GVISOR]` `runsc restore --background`: "the application can start execution as soon as the kernel state is loaded. The remaining application memory and file data are restored asynchronously in the background… If the application accesses a memory page that has not yet been restored, gVisor prioritizes loading that page immediately to unblock the application thread." Without `--background`, all page reads complete before `Kernel.LoadFrom()` returns. Feature is upstream (commit `41f01d8`, Dec 2024). — https://gvisor.dev/docs/user_guide/checkpoint_restore/, https://github.com/google/gvisor/commit/41f01d8f9c5aee4f7a31ec6183fb50bbc6f9b851
- `[FACT FROM GVISOR]` Background loading uses a goroutine pool issuing `pread64` (no io_uring); the pages-file FD stays open until full restore (`runsc wait --restore` exists).
- `[FACT FROM MODAL]` "we aggressively preload the entire pages file into page cache as early as we can." Worst case: fault finds neither page-cache nor host disk → FUSE networked read "which takes 10s of milliseconds." — https://modal.com/blog/mem-snapshots
- `[FACT FROM MODAL]` FUSE tiers: FUSE server → host page cache → SSD → AZ cache → CDN → blob (~2.5 GiB/s single-file; read-ahead 32 MB; page cache deliberately enabled). — https://modal.com/blog/jono-containers-talk
- `[FACT FROM MODAL]` "The current restore implementation is performance-constrained by how fast the virtual memory of the main process, sometimes GiBs of data, can be loaded off disk (or over the network) and into memory." — https://modal.com/blog/mem-snapshots
- `[UNKNOWN]` Whether our "pre-Python snapshot restoration" ends before, during, or after page hydration. gVisor semantics allow Python to resume after kernel-state load while pages hydrate; Modal's preload runs "as early as we can." The boundary is not publicly fixed. **Do not assume all pages finish loading before Python resumes.**

### 2.4 What Modal exposes publicly

- `[FACT FROM MODAL]` Public knobs only: `enable_memory_snapshot=True`; `@modal.enter(snap=True/False)`; `experimental_options={"enable_gpu_snapshot": True}`. No compression, zero-page, background, `--direct`, page-cache, or size controls. — https://modal.com/docs/guide/memory-snapshots
- `[FACT FROM GVISOR]` runsc itself exposes `--compression=none|flate-best-speed` (none default, required for background), `--exclude-committed-zero-pages` ("can significantly reduce the checkpoint size for applications that have large, zero-filled memory regions (like LLMs)"), `--direct`, `--background`, `--leave-running`, `--cuda-checkpoint-path`, `dev.gvisor.internal.cpufeatures`. — https://gvisor.dev/docs/user_guide/checkpoint_restore/
- `[INFERENCE]` Modal almost certainly uses `--background` + uncompressed pages; zero-page/`--direct` usage unknown.

### 2.5 Slow-restore tails Modal has identified

- `[FACT FROM MODAL]` "CPU pressure as it eagerly loads hundreds of thousands of 4KiB pages. CPU stalling is going as high as 900/ms/s" (cgroup startup tuning).
- `[FACT FROM MODAL]` "in the tail we're observing much less effective throughput" than ~2 GiB/s network download.
- `[FACT FROM MODAL]` Docs: "Memory Snapshots do not speed up model loading from storage"; KV-cache guidance: discard unfilled buffers before snapshot rather than "writing and then reading… meaningless pages." — https://modal.com/docs/guide/memory-snapshots

---

## 3. gVisor/runsc mechanics

- `[FACT FROM GVISOR]` No host `userfaultfd` in gVisor restore (syscall unimplemented in Sentry); demand paging is internal pgalloc async loading. Contrast: CRIU lazy migration and Firecracker `Uffd` backend use real userfaultfd.
- `[FACT FROM GVISOR]` Faults on not-yet-loaded ranges get elevated priority (commit 41f01d8) — app first-touch order sets fault priority, but the whole pages file is still read eagerly in the background.
- `[FACT FROM GVISOR]` Zero pages: `--exclude-committed-zero-pages` skips committed-but-zero pages at checkpoint (costs checkpoint CPU). `[FACT FROM CRIU]` CRIU stores zero pages as size-0 images (`criu/page-xfer.c`).
- `[FACT FROM GVISOR]` App-driven C/R exists upstream (`/proc/gvisor/checkpoint`), not exposed by Modal `[INFERENCE]`.

**Restore-cost model:** restore_time ≈ serialized_pages_bytes / effective_restore_throughput + fixed/platform overhead — **with the numerator unmeasured for our system** (see Evidence status). State-file parse is fast; page transfer dominates; tails from cold page cache (FUSE faults, 10s of ms), cgroup CPU pressure, and tail network throughput.

---

## 4. Relevant systems research

### Catalyzer (ASPLOS 2020)
Lazy recovery of user + system state; `sfork` COW sharing; <1 ms best case. Same design lineage as gVisor restore. App influence: only capture-time committed set. — https://dl.acm.org/doi/10.1145/3373376.3378512

### vHive / REAP (ASPLOS 2021)
Page faults ≈ 95% of function processing time; average contiguous faulted region only 2–3 pages (read-ahead useless); **97% of accessed pages identical across invocations**. REAP: record fault addresses, then eager sequential install of the recorded working set → eliminates 97% of faults, 3.7× cold-start reduction. Platform-side on Modal; Modal's whole-file preload is REAP's idea at the limit. App corollary: sequential first-touch reduces random-fault risk when preload lags. — https://arxiv.org/abs/2101.09355

### Firecracker (NSDI 2020 + docs)
MAP_PRIVATE memory-file mapping → runtime on-demand loading, COW on writes; `File` vs `Uffd` backends; restore latency depends on memory size, vCPUs, devices; cgroups V1 inflates restore latency. Platform-side. — https://github.com/firecracker-microvm/firecracker/blob/main/docs/snapshotting/snapshot-support.md

### CRIU lazy migration
Post-copy with `lazy-pages` daemon servicing faults from source; per-page RTT cost. Modal uses gVisor C/R, not CRIU. — https://criu.org/Lazy_migration

### FaaSnap (EuroSys 2022)
Compact loading sets for prefetch; concurrent paging (start before working set loads); up to 3.5× vs SOTA, 3.5% from in-memory. Lesson: restore latency ≈ working-set page-load time — shrink and pre-order. Platform-side. — DOI 10.1145/3492321.3524270

### SOCK (ATC 2018)
Fork-based Zygote + COW provisioning, 18×–45×. Python imports add ~100 ms — relevant to import-deferral math. — https://www.usenix.org/conference/atc18/presentation/oakes

### Faa$T (ATC 2018)
Pre-warm-on-reload caching; up to 92%. — https://arxiv.org/abs/2104.13869

### FaaSLight (arXiv 2022 / TOSEM 2023)
Load indispensable code eagerly, optional code on demand; code-loading down up to 78.95%. App-actionable: imports before the snapshot become serialized anonymous bytes. — https://arxiv.org/abs/2207.08175

### DeltaBox (arXiv 2026)
Full-state C/R duplication costs hundreds of ms–s; delta + fork-from-template: checkpoint 14 ms / rollback 5 ms. Confirms state volume dominates C/R latency. Platform-side. — https://arxiv.org/abs/2605.22781

### Sabre (OSDI 2024) — hardware-accelerated snapshot compression

- `[FACT FROM PAPER]` "Sabre: Hardware-Accelerated Snapshot Compression for Serverless MicroVMs", Lazarev, Gohil (MIT CSAIL), Tsai, Anderson, Chitlur (Intel Labs), Zhang (Cornell), Delimitrou (MIT); OSDI '24. https://www.usenix.org/conference/osdi24/presentation/lazarev · PDF https://www.usenix.org/system/files/osdi24-lazarev_1.pdf · code https://github.com/barabanshek/sabre
- **Target:** snapshot byte size as the limit on prefetch coverage and restore speed in Firecracker microVMs; on-demand paging yields many critical-path faults; software compression CPU cost is the blocker ("major source of datacenter tax").
- **Mechanism:** Intel IAA (In-Memory Analytics Accelerator, Sapphire Rapids) hardware DEFLATE — near-zero CPU cost; checkpoint side uses statistics-mode + "Canned" static DEFLATE with shared Huffman tables across small 4 KiB chunks; restore side decompresses overlapped with sequential disk I/O; pages installed via userfaultfd or DMA scatter.
- **Measured:** compression up to 4.5× (2.5× avg on diff snapshots); decompression ~10× faster than software; memory restoration up to 55% faster; end-to-end cold start −20% vs already-optimized (REAP-style) baselines; up to 60% lower cold-start overhead vs on-demand paging; near-zero CPU; decompression fully hidden behind I/O.
- **Lesson for us:** (1) platform-side almost entirely — Modal would compress/decompress the runsc pages file; not reachable from our code. (2) If Modal already preloads the whole pages file, Sabre's *prefetch-coverage* argument adds nothing; its *bytes* argument matters only for network-bound tails and storage footprint — i.e., exactly the tail Modal admits ("much less effective" than 2 GiB/s). (3) Firecracker-vs-gVisor caveat: Sabre operates on KVM guest-physical memory with dirty-page tracking; runsc serializes MemoryFile pages — same single-image dominant cost, different install mechanism; IAA availability on Modal hosts unknown. (4) It does NOT change our ranking: bytes-at-capture remains the app-side lever; compression-at-rest is a Modal-side lever. (5) Imitating from app code: compressing our own memory is impossible/pointless (serialized images are the platform's raw bytes); the closest app analog is **zero-page/dead-buffer elimination before capture** — which gVisor's own `--exclude-committed-zero-pages` rationale and Sabre's 2.5–4.7× ratios both point at.

### Spice / SHELF (OSDI 2026) — physical-layout vs virtual-layout snapshots

- `[FACT FROM PAPER]` "Rethinking Process Snapshots for Near-Warm Serverless Cold Starts", Holmes, Dinis, Honcharuk, Belay (MIT CSAIL), Fried (UPenn); OSDI '26. https://www.usenix.org/conference/osdi26/presentation/holmes · PDF https://www.usenix.org/system/files/osdi26-holmes.pdf · artifact https://github.com/JunctionOS/spice-ae
- **Core problem:** the I/O-optimal on-disk snapshot layout (pages in predicted-access order) does not match the virtual-address layout; prior systems reorder pages on disk, forcing "thousands of tiny non-contiguous mappings" (VMA count up to 32×; ~300 bytes kernel memory + tree-insert CPU per VMA) or scattered reads + explicit copies (CRIU) or a long fault tail. The OS lacks a page-granular mapping abstraction decoupling disk layout from virtual placement.
- **SHELF format:** ELF-inspired; working-set pages stored in time-of-access order in a contiguous array at the front (one big sequential read before any parsing); one program header per VMA with **interval-tree overlays** — "Any address range not covered by an interval is sourced from the backing memory (e.g., existing file-backed pages or anonymous zero pages)"; only **unreconstructible** pages are stored; offline rewriting removes unmodified file-backed pages and zero pages and dedups identical private ranges; embeds a per-page access trace. Capture-side hygiene: language shims run GC, drop caches, translate `MADV_FREE`→`MADV_DONTNEED`, trim stacks — reducing snapshot size (several MB on sub-100 MiB functions).
- **spliceVMA:** a mixed-source mapping whose pages come from the snapshot image or an underlying file/anon mapping; backed by pre-balanced interval trees mmap'd directly; fault handler reads from the snapshot at recorded offset or falls back to backing source; private pages materialized into fresh anonymous memory with a reserved page pool; kernel prefetch threads + PTE preinstall ("aggressively installs page-table entries rather than relying on minor faults"); metadata restored via bulk object-graph deserialization (0.9–7.5 ms vs CRIU 2.6–749 ms).
- **Measured:** restore-to-running from disk within **0.6–18 ms** of warm-invocation latency (vs 3.6–1197 ms existing); 7.5× (process) / 9.5× (VM) average end-to-end; **contiguous private pages prefetched at 5.2 M pages/s vs 0.6 M pages/s scattered** (~8× contiguity effect); page-cache sharing cuts storage bandwidth 20%. **Scale caveat: workloads are 1.5–146 MiB working sets — the millisecond numbers do not transfer to a 12.8 GiB process; only the mechanics do.**
- **Four-part applicability:**
  1. **Kernel/platform-only:** `reexec()`, spliceVMA, interval trees, PTE preinstall, page pool — on our platform these would live in the gVisor Sentry or Modal's stack; not requestable by us.
  2. **Imitable from app code:** GC/cache-drop before capture (Spice does this); don't snapshot reconstructible bytes (file-backed weights should stay file-backed); deterministic sequential first-touch; zero-page avoidance. All are *size or ordering* levers — no VMA-level control is possible from inside a gVisor sandbox (Python/torch allocators scatter VA; gVisor's dump order is unpublished).
  3. **Modal/gVisor already do similarly:** gVisor `--background` restore = reactive, fault-prioritized prefetch (Spice is proactive with traces); Modal's whole-file page-cache preload = Spice's "pack working set contiguously, one sequential read" taken to the extreme (preload everything); FUSE page-cache sharing of file-backed code = Spice's page-cache sharing mechanism.
  4. **Modal likely cannot expose:** VMA layout, spliceVMA-style splicing, read-ahead/preload policy, PTE preinstall, page-pool management. Our only knobs remain `snap=True/False` boundaries and what memory exists at capture.
- **Does Spice strengthen or weaken "reduce anonymous bytes"?** **Strengthens.** Arithmetic consistency: 13 GiB @ ~2 GiB/s (Modal's stated expected restore throughput) ≈ 6.5 s ≈ our observed max; ~7 GiB ≈ our 3.5 s median. Spice's own capture-time size-reduction techniques are the same lever. Spice's layout argument is **neutralized for the preload phase** (Modal streams the whole file sequentially regardless of page order) but **order-sensitive in the tail** (if preload lags first-touch, fault-priority + scattered faults matter — REAP's 2–3 page fault runs). Falsifiable prediction: with byte volume held constant, flipping post-restore first-touch order (CLIP-then-VAE vs VAE-then-CLIP) changes tail variance only if preload lags.

### Verified-not-found (corrected)
The previous version's claim that Sabre, SHELF, and Spice are not verifiable was **wrong**; they are now verified above from primary sources. Still unverified: "Sequoia (SOSP 2021)" and "Medes" full text (dedup mechanism title-level only).

### Theme synthesis (updated)
1. Restore is a page-loading problem, not a deserialization problem (all sources).
2. **TOTAL RESTORE VOLUME ≠ TIME TO USEFUL PROGRESS.** Volume is bytes ÷ throughput (Sabre, Spice, Modal's own framing). Time-to-useful-progress is volume + first-touch order + fault-priority (REAP's 95% faults, Spice's 5.2M vs 0.6M pages/s, gVisor's prioritized faults). A small early working set matters even when the whole pages file is eventually read.
3. Zero pages / reconstructible bytes are pure waste (gVisor flag; Modal KV guidance; Spice sparse overlay; Sabre ratios).
4. Working-set stability (97%, vHive) makes prefetch sound.
5. CPU serialization during restore is a real platform tax (Modal 900 ms/s; Sabre's motivation).
6. Compression moves bytes off the network at near-zero CPU only with hardware (Sabre/IAA); software compression on the restore path is CPU-costly.

---

## 5. What likely causes our 0.8–6.5 s restore distribution

### 5.1 The byte-throughput hypothesis: consistent with, not proven by

`[FACT FROM MODAL]` Restore is constrained by loading "GiBs of data… off disk (or over the network)" at ~2 GiB/s expected. Our restored RSS is 12.826 GiB (MEASURED), of which the anonymous (serialized) fraction is UNKNOWN. If serialized bytes were ~7–13 GiB, 2–4 GiB/s effective would give ~2–6.5 s — **consistent with** our distribution. But:

- `[FACT FROM OUR ARTIFACTS]` Same-design deployment, different dates: Aug 11 probes pre-Python 5.448–9.754 s; Aug 13 baseline 0.809–6.487 s. Identical snapshot design, 8× spread of minima → **host/scheduling variance dominates the byte-driven floor**.
- `[FACT FROM OUR ARTIFACTS]` Cross-experiment: UNET-absent (−8 to −10 GiB RSS) showed **worse** pre-Python restore than FULL (5.4–9.8 vs 1.9–7.4 s) — not attributable (provider/region mix unknown), but it prevents claiming bytes→time proportionality in the pre-Python phase. The same comparison showed Python-restore improvement (0.611 vs 1.33 s median), consistent with less post-restore state to manage.
- `[FACT FROM OUR ARTIFACTS]` Client-side submission→python-resume variance 10.7–203 s (`V2_REMAINING…:173`) dwarfs everything — scheduling, snapshot download, container start are the giant variance terms.

**Conclusion:** a byte-throughput model is plausible and Modal-supported, but for OUR system it is **consistent-with, not proven**. The measured variance is dominated by host and scheduling effects (run 4's 6.487 s restore + 1.3 GB/s H2D on the same host; run 7's 0.809 s restore on a different region).

### 5.2 Phase semantics for us

- **Pre-Python restore (0.8–6.5 s):** sandbox boot + kernel-state load + page-cache preload progress before Python resumes. **Whether hydration has finished when Python resumes is UNKNOWN** (gVisor `--background` permits resume mid-hydration; Modal's "preload as early as we can" does not fix the boundary). App lever: shrink serialized bytes.
- **Python restore (0.39–1.54 s):** Modal entrypoint + our `restore()`: GPU-state re-init (CUDA libs are new file-backed loads — never loaded at capture), custom-node O(1) fast path, CPU-snapshot activation (metadata-only walks). CPU-bound; host variance visible (run 4: 1.5 s).
- **Pre-sampler (3.2–10.7 s):** UNET checkpoint mmap read (~1.0–1.2 s) + H2D (~2.2 s at ~5 GB/s; run 4: 9.2 s at 1.3 GB/s) — file-backed UNET path, not snapshot; shares the host-IO tail cause.

### 5.3 Run-by-run observations

| Run | Region | Pre-Python restore | Note |
|---|---|---|---|
| 1 | GCP/us-east4 | 3.452 s | |
| 2 | GCP/us-east4 | 3.856 s | |
| 3 | GCP/us-east1 | 3.272 s | scheduling 25.9 s |
| 4 | GCP/us-east4 | **6.487 s** | same run: H2D 1.3 GB/s (9.2 s) — host storage/network degradation |
| 5 | GCP/us-east4 | 3.514 s | |
| 6 | GCP/us-east1 | 4.895 s | |
| 7 | AWS/eu-south-2 | **0.809 s** | restore fastest of batch; scheduling 63.5 s |
| 8 | GCP/us-east4 | 2.560 s | |
| 9 | GCP/us-east4 | 4.153 s | |
| 10 | GCP/us-east4 | 3.503 s | |

`[INFERENCE]` The 8× spread across identical requests = host-side variance (page-cache warmth, host storage/network, cgroup CPU contention during eager load). Run 4 (slow restore AND slow H2D) and run 7 (fast restore, slow scheduling) both implicate host state, matching Modal's own tail admissions.

---

## 6. Our snapshot composition

All code evidence `[FACT FROM OUR CODE]`; memory numbers classified per Evidence status.

### 6.1 Capture mechanics

- Snapshot captured when `startup()` (`@modal.enter(snap=True)`, `modal_app.py:16954-16958`) returns; restore runs `restore()` (`snap=False`). Memory snapshot on by default (`:2767-2778`), `min_containers=0`, single-use cold.
- Capture under `_force_cpu_during_snapshot` (`comfyapp.py:17814-17848`): CUDA disabled → **zero CUDA state in snapshot**; GPU state re-created post-restore (`comfyapp.py:20363-20413`).
- Models built with `comfy.utils.DISABLE_MMAP = True` (`modal_app.py:8451`) → CLIP/VAE weights are anonymous CPU copies.
- Eviction before capture (`COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT`, `:8751-8762`, `:5982-6962`): evict all, `gc.collect()` ×2, reload only `clip_vae` retain role → **UNET=None at capture**. Build pools closed first (`:8750`).
- Instrumentation available: `_report_host_memory` (VmRSS/maxrss + cgroup-when-readable, `:3524-3675`), `_collect_process_memory` (smaps_rollup fields — **absent in practice inside the sandbox**, `:3684-3768`), gated `snapshot_build_manifest` (`:8804-8810`; mapping counts + per-role storage bytes).

### 6.2 What is in memory at capture (restore-only prod)

| Component | Status at capture | Size evidence | Classification |
|---|---|---|---|
| Base runtime (Python+torch+ComfyUI+custom nodes+Modal) | present | ≈ 12.826 GiB (restored RSS) − CLIP − VAE ≈ **10.4 GiB** | DERIVED (RSS-share); anonymous split UNKNOWN |
| CLIP text encoder (CPU, bf16) | present, retained | **1.5–2.5 GiB resident** | ESTIMATED (from composition analysis, `V2_REMAINING…:182`) |
| VAE (CPU, bf16) | present, retained | storage accounting **160 MiB**; ~0.3–0.5 GiB resident w/ allocator + page-cache residue | MEASURED (storage_bytes) / ESTIMATED (resident) |
| UNET | **evicted → None** | (would be ~12.3 GiB) | MEASURED by design (invariants `unet_present=0`) |
| ModelPatcher wrappers | present (CLIP/VAE) | small | — |
| Custom-node registry / NODE_CLASS_MAPPINGS | present | small–medium | — |
| ExactConditioningCache | **empty at capture** (request-time only) | 0 | FACT FROM OUR CODE |
| PromptSignatureCache | **empty at capture** (loaded at plan receipt, `modal_app.py:15836`) | 0 | FACT FROM OUR CODE |
| CUDA state | **none** | 0 | FACT FROM OUR CODE |
| mmap'd model files | **none** (DISABLE_MMAP) | 0 | FACT FROM OUR CODE |

Manifest evidence (full-model deployment, not baseline): before_capture RSS 25.3–25.4 GiB; mappings 2884–2885; **anon=704–705, file=2180 (mapping counts)**; modules 10452 (`deploy1_all.log:241,492`).

### 6.3 Category mapping (A–G)

- **A. Required immediately after resume:** gVisor kernel state; Python runtime + our `restore()`; GPU-state re-init (file-backed CUDA libs); snapshot activation metadata; plan/memo/prefill caches on first request.
- **B. Required later:** VAE weights (decode at end of every request); CLIP weights (cache-miss only); most of the base-runtime import heap (needed by request time, not in the first ~100 ms).
- **C. Required only on cache misses:** CLIP weight pages (encode path).
- **D. Reconstructable cheaply:** caches (already emptied at capture); GPU/CUDA state (re-init post-restore); UNET (already excluded; fast-disk ~3.4 s).
- **E. Probably dead after initialization:** transient load buffers (already gc'd); **allocator-held freed blocks (glibc arenas, torch CPU allocator) — never returned to the OS before capture**; page-cache residue of startup-read model files; registry intermediates (small).
- **F. File-backed/reopenable:** model safetensors on the Volume (but CLIP/VAE bytes exist as anonymous copies at capture — those copies are what serialize `[INFERENCE]`); python/.pyc from image FS (clean file pages not serialized `[INFERENCE]`).
- **G. Anonymous/private, likely serialized:** CLIP weights (~2 GiB est.), VAE (~0.2–0.5 GiB), the anonymous part of the ~10.4 GiB base-runtime RSS (interpreter heap, torch internals, allocator arenas, module code objects) — **magnitude UNKNOWN** (smaps unavailable).

**Bottom line:** restored RSS ≈ 12.8 GiB (MEASURED) = base runtime (~10.4 GiB, DERIVED) + CLIP+VAE (~2–3 GiB, ESTIMATED). The serialized pages-file bytes are a **subset of the anonymous portion and remain UNKNOWN**. The UNET exclusion already removed ~12.3 GiB.

---

## 7. Our likely early working set

Post-resume sequence (from `restore()` `modal_app.py:9074-10893`; request path `:15557-15911`):

1. **Snapshot restore (platform):** kernel-state load → Python may resume while pages hydrate in background `[UNKNOWN boundary]`.
2. **Python resume:** eviction boundary → lazy-init → memory report → `_configure_runtime`.
3. **bootstrap.restore()** (`runtime_bootstrap.py:1589-2078`): GPU-state restore + CUDA init (~236 ms); Sage O(1) identity; runtime-state reload; custom-node O(1) fast path; seed hydration.
4. **CPU-snapshot activation** (`modal_app.py:9593-10325`): identity match → `validate_cpu_snapshot_models` → `inspect_and_validate_snapshot_params` pre/post retarget → retarget (attr-only) → bridge publish → CacheDiT/res4lyf prepare (gated) → residency diagnostics (gated off).
5. **Request:** plan deserialize → memo load → **conditioning prefetch daemon** → binding → cache exact_hit (~35–95 ms) → **CLIP encode skipped on hit** → UNET fast-disk load + H2D → sampling → VAE decode.

**Early working set (first ~2 s of Python time):** runtime machinery, CUDA lib pages, plan/memo/prefill bytes (small), validation metadata walks, UNET file pages + H2D. **CLIP/VAE weight content is touched only by the background loader (unconditional) or cache-miss encode.**

`[FACT FROM OUR CODE]` `_check_tensor_devices` (`cpu_snapshot_models.py:1136-1172`) checks `is_meta`/`device`/`dtype` only — no byte reads; `collect_unet_runtime_state` reads the first parameter; `traverse_unet_pages`/mincore probes are gated off in prod. No avoidable full-model byte traversal exists in the restore path.

**TOTAL VOLUME vs TIME-TO-USEFUL-PROGRESS:** our early working set is small, so time-to-useful-progress (first cache lookup, first prefill) is not gated on model-byte hydration — **provided the background loader isn't CPU/IO-starved by our restore work**. The residual order-sensitivity lives in the tail (preload-lag faults), where gVisor's fault-priority already adapts to whatever we touch first. This is why touch reordering is secondary for us — but it is **not proven** to be irrelevant; the falsification experiment (§13.7) settles it.

---

## 8. Anonymous vs file-backed state

- `[FACT FROM GVISOR]` `pages.img` = MemoryFile (private/anonymous) page contents; clean file-backed mappings are served from the filesystem, not the pages file. `[INFERENCE]` Clean untouched file-backed pages add no pages-file bytes; anonymous copies (and touched private file-backed pages) do.
- `[FACT FROM OUR CODE]` CLIP/VAE anonymous copies (`DISABLE_MMAP=True`); the same weights remain on the Volume file-backed (residual read page cache inflates RSS, not the pages file).
- `[FACT FROM OUR ARTIFACTS]` smaps_rollup unavailable in-sandbox → the anonymous/file-backed byte split is **unobservable with current instrumentation**; mapping counts (705 anon / 2180 file) are the only structural signal.
- `[FACT FROM MODAL]` File-backed paths on Modal run at page-cache speeds (UNET mmap read ~1.0–1.2 s for 12.31 GB ≈ 10+ GB/s; H2D ~5 GB/s) — much faster than the ~2 GiB/s pages-file path; but Modal: snapshots "do not speed up model loading from storage."
- `[INFERENCE]` Our constraint (CLIP+VAE must remain snapshotted and immediately available) fixes their state as anonymous pages-file bytes. The file-backed alternative stays off the table for CLIP/VAE.

---

## 9. Dead/reconstructable memory candidates

Ranked by likely effect on **serialized bytes** (left column) vs **RSS/cgroup pressure** (right column):

| Candidate | Serialized-bytes effect | RSS/cgroup effect | Evidence |
|---|---|---|---|
| 1. Allocator slack (glibc arenas + torch CPU allocator) after build + eviction reload | **PLAUSIBLE reduction** (freed anonymous pages; magnitude UNKNOWN) | small | `cpu_snapshot_models.py:2551,2624` gc's; no trim anywhere `[FACT FROM OUR CODE]` |
| 2. Page-cache residue of startup-read model files (CLIP/VAE safetensors, .pyc) | **≈0** (clean file pages not serialized `[INFERENCE]`) | **REDUCTION** (0.5–3 GiB est.) | reads happen at startup under DISABLE_MMAP; no fadvise `[FACT FROM OUR CODE]` |
| 3. Request-time-only imported modules | **PLAUSIBLE reduction** (anonymous import heap; magnitude UNKNOWN — see §11 R1) | reduction | `V2_SOURCE_MODULES` (`modal_app.py:437-453`); modules=10452 at capture |
| 4. Zero-filled allocations (unfilled KV/workspace buffers) | small | small | no large preallocation found `[INFERENCE]` |
| 5. Threads/stacks | already handled | — | `_close_snapshot_build_pools` (`:5856-5896`) |
| 6. CUDA libs | not loaded at capture | — | — |

---

## 10. Restore/page-touch risks

1. **Preload-lag faults (platform):** if preload lags Python's first touches, cache-miss encode or validation walks pay per-fault FUSE reads (10s of ms worst case). Our early working set is small → risk concentrated in the unconditional background load.
2. **CPU/page-cache competition:** Modal admits CPU stalls to 900/ms/s during eager page load; our post-restore CUDA init + validation + prefetch daemon run concurrently with background restore — keep post-restore CPU work light in the first seconds.
3. **Run-4-style host degradation:** restore and UNET H2D share host storage/network; a degraded host inflates both. Platform-side; mitigations: fewer bytes, retries.
4. **Snapshot coverage:** ~6 worker-type snapshots per CPU-only function; fallback to cold start or on-demand creation on mismatch — not observable from our telemetry `[UNKNOWN]`.
5. **Correctness risk in future optimization:** any new post-restore code that touches weight *content* would convert metadata walks into full hydrations (demand-faulting CLIP/VAE in the first-touch window). Keep all post-restore validation metadata-only.
6. **Measurement risk:** smaps_rollup is unavailable in-sandbox; any optimization claiming "anonymous bytes reduced" must be evidenced via VmRSS deltas, mincore over known storages, or cgroup (where readable) — not smaps.

---

## 11. Ranked optimization ideas

**CLIP stays in the snapshot. Nothing here proposes removing it.** Estimates corrected per Evidence status: **bytes proven removable = 0 for every candidate** (no artifact measures serialized bytes); estimates are explicitly classified.

### R1. Import deferral of request-time-only modules to a post-restore background thread (FaaSLight pattern)
- **Mechanism:** modules imported at container start whose pages serialize into the snapshot are instead imported post-restore (background thread, overlapping hydration + UNET load). Plausible: imports execute pre-capture (`modal_app.py:427-453`); 10,452 modules loaded; FaaSLight shows code-loading is a real cold-start component; SOCK: Python imports ~100 ms each.
- **Bytes proven removable: 0. Bytes estimated removable: UNKNOWN** — the previous 1.5–4 GiB range was **not justified** by any module-attribution data (no tracemalloc/objgraph in the codebase; `_collect_process_memory` docstring explicitly avoids them). Python/torch/ComfyUI core may be required for snapshot construction (model loaders, comfy.sd, node registry at build time), so the deferrable fraction could be small. **R1 may be the largest application-controlled lever, but its magnitude is unmeasured.**
- **Est. median saving:** UNKNOWN (0.2–1.2 s if 1–4 GiB were deferrable; possibly ~0 if little is).
- **Confidence:** mechanism MEDIUM; removable bytes LOW.
- **Complexity:** MEDIUM-HIGH. **Correctness risk:** MEDIUM (imports must not be needed by `restore()`; registry must be complete before graph execution).
- **Improves:** median + tail. **Needs Modal:** no. **Requires implementation experiment:** yes (module-attribution measurement first).

### R2a. Capture-time allocator hygiene: `gc.collect()` + `malloc_trim(0)` (+ torch CPU allocator release) before `startup()` returns
- **Mechanism:** return freed anonymous heap to the OS so uncommitted pages are not in MemoryFile at capture → **plausibly reduces serialized pages-file bytes** (this is the only app lever with a direct serialized-bytes mechanism). gc alone doesn't return memory; malloc_trim(0) releases free top-of-heap via madvise → those pages leave the process.
- **Bytes proven removable: 0. Bytes estimated removable: 0.1–0.6 GiB (UNKNOWN magnitude)** — freed-but-mapped arena interior is not returned by trim; only reachable free space is.
- **Est. median saving:** −0.03 to −0.2 s (at ~2–4 GiB/s). **Tail effect:** small.
- **Confidence:** mechanism HIGH; magnitude LOW.
- **Complexity:** LOW. **Correctness risk:** LOW (glibc-only, no semantics change; guard for non-glibc).
- **Improves:** median. **Needs Modal:** no. **Experiment needed:** yes (VmRSS delta before/after trim; restore A/B).

### R2b. Clean file-page eviction: `posix_fadvise(DONTNEED)` on startup-read model files before capture
- **Mechanism:** drop clean file-backed pages of CLIP/VAE safetensors + .pyc read during startup.
- **SERIALIZED SNAPSHOT BYTES: ≈0** — clean file-backed pages are (inferred) not serialized; this does NOT shrink pages.img.
- **HOST/cgroup RSS + page-cache pressure: REDUCTION** (est. 0.5–3 GiB of reclaimable file pages out of cgroup accounting; less pressure competing with the restore-time preload). Two separate effects — do not combine them into one number.
- **Est. median saving on pre-Python restore:** ~0 (not on the critical path); protects against cgroup pressure/OOM margins. **Tail effect:** small indirect.
- **Confidence:** mechanism HIGH (POSIX semantics); magnitude MEDIUM.
- **Complexity:** LOW. **Correctness risk:** LOW (clean pages only; model copies are anonymous and unaffected).
- **Needs Modal:** no. **Experiment needed:** yes (measure cgroup/VmRSS drop at capture; verify no restore-time regression).

### R3. Defer/parallelize post-restore validation walks
- **Mechanism:** the full-parameter metadata walks (`validate_cpu_snapshot_models` `:9729`, `inspect_and_validate_snapshot_params` pre `:9778` / post `:9886`) hold the GIL and walk thousands of params; run in background after bridge activation (identity-match semantics preserved before model use).
- **Bytes: 0. Est. saving:** 50–250 ms of the Python-restore phase.
- **Confidence:** HIGH (metadata-only by design). **Complexity:** LOW-MEDIUM. **Risk:** LOW.
- **Improves:** median (Python-restore phase). **Needs Modal:** no. **Experiment needed:** yes (phase timing A/B).

### R4. Zero-page hygiene
- **Mechanism:** avoid preallocated zero buffers; keep caches empty at capture (already true); synergy with any platform zero-page exclusion.
- **Bytes proven: 0; est.: <0.1–0.5 GiB (UNKNOWN).** **Saving:** small. **Confidence:** MEDIUM. **Risk:** LOW.
- **Needs Modal:** no. **Experiment:** part of R2a run.

### R5. Early working-set / first-touch shaping
- **Mechanism:** keep post-restore CPU work light (stagger prefetch daemon), keep diagnostics gated off, deterministic sequential touches. Distinct from byte reduction: affects TIME-TO-USEFUL-PROGRESS and tail only if preload lags.
- **Bytes: 0. Saving:** tens of ms; protects tail. **Confidence:** MEDIUM; the preload-lag premise is UNTESTED.
- **Needs Modal:** no. **Experiment:** falsification test (§13.7) — hold bytes constant, flip first-touch order, watch tail variance.

### R6. Capture-hygiene of caches (regression protection)
- Caches are empty at capture; keep it that way (never prefill conditioning cache or force-load the memo during startup). Prevents regression, no expected gain.
- **Confidence:** HIGH. **Risk:** LOW.

### Platform unknowns (informational — NOT planned actions; no Modal contact planned)
Compression-at-rest (Sabre-style), `--exclude-committed-zero-pages`, warm-host scheduling, THP, `--direct`: all platform-side; would need Modal to implement. Documented in §14 for completeness; **our plan proceeds with app-visible telemetry + public architecture + our own experiments only.**

### Deliberately NOT recommended
- Pre-touch CLIP/VAE after restore (forces hydration of bytes that may never be faulted on cache hits; background loader loads them anyway).
- Removing CLIP from the snapshot (explicit constraint).
- Moving CLIP/VAE to file-backed mmap (violates immediately-available semantics; first-touch would pay FUSE faults on cache miss).
- UNET back into the snapshot (fast-disk path already beats it).

---

## 12. Ranked optimization table (corrected)

| Rank | Candidate | Mechanism | Bytes proven removable | Bytes est. removable | Est. median saving | Tail effect | Confidence | Needs implementation experiment? |
|---|---|---|---|---|---|---|---|---|
| 1 | R2a allocator hygiene (gc+malloc_trim) | uncommit freed anon heap before capture → fewer serialized bytes | 0 | 0.1–0.6 GiB (UNKNOWN) | −0.03 to −0.2 s | small | mech HIGH / magnitude LOW | yes |
| 2 | R2b clean file-page eviction (fadvise) | drop clean file pages → cgroup/RSS relief; **no serialized-bytes effect** | 0 | 0.5–3 GiB cgroup relief (not serialized) | ~0 on pre-Python | indirect protection | mech HIGH / magnitude MED | yes |
| 3 | R3 validation deferral | move metadata walks off GIL-critical path | 0 | 0 (bytes) | −0.05 to −0.25 s (Python phase) | small | HIGH | yes |
| 4 | R1 import deferral | request-only imports move post-restore | 0 | **UNKNOWN** (was 1.5–4 GiB — unjustified; downgraded) | UNKNOWN (0 to −1.2 s) | potentially large | mech MED / magnitude LOW | yes (attribution measurement first) |
| 5 | R4 zero-page hygiene | no preallocated zero buffers | 0 | <0.1–0.5 GiB (UNKNOWN) | small | small | MED | part of R2a |
| 6 | R5 first-touch shaping | light post-restore CPU; sequential touches | 0 | 0 | ~0 | protects tail if preload lags (UNTESTED) | MED | yes (falsification) |
| 7 | R6 cache capture-hygiene | keep caches empty at capture | 0 | 0 | prevents regression | — | HIGH | no |
| — | Platform unknowns (compression, zero-pages, warm hosts, THP) | Modal-side only | 0 (app) | potentially 2–4× fewer bytes / collapsed tail | −0.5 to −1.5 s possible | **−2 to −4 s possible** | LOW-MED (unverifiable from app) | no (informational only) |

Note: at ~2–4 GiB/s effective, each ~1 GiB of serialized bytes ≈ 0.25–0.5 s median — but proportionality is consistent-with, not proven (§5.1).

---

## 13. Experiments that would prove/disprove each idea

All measurement-only, shadow deployments; nothing runs here.

1. **Capture manifest on the baseline deployment** (`COMFYMODAL_V2_SNAPSHOT_MANIFEST=1`, `modal_app.py:8804`): yields before_capture VmRSS/VmHWM/VmSize, mapping counts, anon/file counts, modules, gc_objects, per-role `storage_bytes` (`snapshot_build_manifest.py`; `_capture_retained_models` `:256`). **First hard evidence for the baseline deployment.** (smaps fields will be absent — see contract below.)
2. **Restore-side measurement contract** (same run): at restore_start/restore_complete/prompt_executor_start record VmRSS, maxrss, cgroup-current-when-readable, rusage minor/major fault deltas; correlate pre-Python restore duration (banner→python-resume) vs capture VmRSS across ≥10 cold runs → tests byte-proportionality (expect: weak R² if host variance dominates; strong R² would upgrade the model).
3. **R2a A/B:** toggle pre-capture `gc+malloc_trim`; measure (a) VmRSS delta at capture, (b) pre-Python + Python restore deltas over ≥10 cold runs per arm.
4. **R2b A/B:** toggle `fadvise(DONTNEED)` on startup-read files; measure cgroup/VmRSS at capture and any restore regression.
5. **R1 attribution first:** one-off optional `tracemalloc`/module-heap snapshot at capture to attribute anonymous bytes per module family — decides whether deferral is worth it. If tracemalloc is too invasive, use the manifest's module list + a diff test (defer one module family, measure capture-RSS delta).
6. **R3 A/B:** move the two `inspect_and_validate_snapshot_params` walks post-bridge-activation; measure Python-restore phase; verify mismatch handling still trips before model use.
7. **R5 falsification (Spice prediction):** hold bytes constant; flip post-restore first-touch order (CLIP-then-VAE vs VAE-then-CLIP) across cold runs; if tail variance moves, preload lags (order matters); if not, whole-file preload neutralizes layout (Spice's argument fully neutralized for us).
8. **Early-working-set proof:** enable gated mincore residency (`cpu_snapshot_models.py:400-498`) for CLIP at restore_complete and again at first cache lookup; CLIP ~0% resident + fast lookup ⇒ hydration lags but doesn't matter; 100% resident ⇒ preload completed before Python resume (also answers the §7 boundary question).

---

## 14. Platform unknowns (informational appendix — no contact planned)

These questions remain open; per project direction, Modal will not be contacted, and the plan proceeds with app-visible telemetry, public architecture, and our own experiments. Documented so a later lane knows what is unanswerable from inside:

1. Is the pages-file size (bytes, page count, zero-page fraction) observable per snapshot? (1.4.3: no API; `restore_state_probe.py:6-10`.)
2. Which `runsc restore` flags: `--background`, `--compression=none`, `--exclude-committed-zero-pages`, `--direct`?
3. Does the "aggressive preload" complete before Python resumes, or does Python resume earlier and eat demand faults? (Determines byte-bound vs fault-bound; §13.8 partially answers from our side.)
4. Are restores scheduled with affinity to hosts whose page cache already holds the pages file (or FUSE AZ-cache tier)?
5. Is tail throughput below ~2 GiB/s correlated with host page-cache misses or cgroup CPU contention during eager load?
6. Are clean file-backed mappings excluded from `pages.img` and re-served from the image/Volume FS at restore?
7. Are committed zero pages skipped at capture (equivalent of `--exclude-committed-zero-pages`)?
8. Is THP/huge-page support active in the guest MemoryFile?
9. Are snapshot files compressed at rest/transfer?
10. How many worker-type snapshots cover RTX PRO 6000 CPU-only functions; can a restore silently fall back to cold start or trigger on-demand creation on mismatch?
11. Is restore page-loading CPU accounted against the function's cgroup (does our post-restore CUDA init compete with it)?
12. Is there any supported pattern to keep weights in the snapshot while excluding unused anonymous regions?

---

## 15. Measurement contract for the next lane (exact fields)

The next implementation/measurement lane must capture the snapshot manifest on the baseline deployment. Minimum required fields (all exist in current instrumentation — nothing new to implement):

**At pre-capture** (`capture_snapshot_manifest("before_capture")`, gated `COMFYMODAL_V2_SNAPSHOT_MANIFEST=1`):
- VmRSS, VmHWM, VmSize (kB) — from `/proc/self/status`
- mapping counts: total, anon, file (`/proc/self/maps`)
- modules count, threads, FDs, gc_objects
- per-role retained-model `storage_bytes` (CLIP, VAE, UNET absent) — `_capture_retained_models` (`snapshot_build_manifest.py:256`)
- mincore residency over CLIP and VAE storages (`cpu_snapshot_models.py:400-498`)
- **Expected unavailable (record as such, do not block):** smaps_rollup Anonymous / Private_Dirty / Private_Clean / Shared_Clean / Shared_Dirty / Pss — the sandbox does not expose them; cgroup memory.current — readable in some runs only (13592.96 MiB observed Aug 11), record when present.

**Before/after gc + malloc_trim** (same run, around the trim point): VmRSS delta (lower bound on returned anonymous pages; interior fragmentation not visible), rusage maxrss (ceiling).

**Model-specific known storage sizes:** CLIP storage_bytes, VAE storage_bytes (MEASURED 160 MiB), UNET absent (invariant).

**Module/import attribution:** not available from existing instrumentation (no tracemalloc/objgraph by design); if R1 targeting is required, add an optional gated tracemalloc snapshot — otherwise keep out.

**Restore side:** at restore_start / restore_complete / prompt_executor_start: VmRSS, maxrss, cgroup-when-readable, minor/major fault deltas; mincore CLIP/VAE at restore_complete and at first cache lookup; pre-Python restore duration (Modal banner → python-resume) per run; ≥10 cold runs at 35 s cooldown per arm for statistical parity with the baseline protocol.

---

## 16. Recommended next implementation order

0. **Measurement lane first (gates everything):** run the §15 contract on the baseline deployment — one gated manifest run + ≥10 cold runs correlating pre-Python restore vs capture VmRSS. Answers: actual baseline capture RSS, mapping structure, per-role storage bytes, and whether byte-proportionality survives host variance. No code risk.
1. **R2a + R2b (capture hygiene)** — lowest risk, independent: `gc` + `malloc_trim(0)` (serialized-bytes lever) and `fadvise(DONTNEED)` (cgroup/RSS lever), A/B against the §15 baseline. Expect small-but-real median gains; R2a is currently the only app lever with a direct serialized-bytes mechanism.
2. **R3 (validation deferral)** — contained, measured in the Python-restore phase.
3. **R1 (import deferral)** — ONLY after §13.5 attribution shows a meaningful deferrable mass; treat the previous 1.5–4 GiB estimate as unsupported until then.
4. **R5 (first-touch shaping)** — run the §13.7 falsification first; adopt only if preload-lag evidence appears.
5. **R6 (cache capture-hygiene)** — trivial regression protection; do alongside 1.
6. **Re-run the 10-cold-run protocol after each step** (same deployment lineage, 35 s cooldown, reconciliation checks) for comparability with `b557b2401f293223`.

Do not implement anything until this report is reviewed.

---

## Appendix: primary sources

- Modal docs – Memory Snapshots: https://modal.com/docs/guide/memory-snapshots · Cold start: https://modal.com/docs/guide/cold-start · Sandbox snapshots: https://modal.com/docs/guide/sandbox-snapshots
- Modal blog – Memory snapshots (Jan 2025): https://modal.com/blog/mem-snapshots · GPU Memory Snapshots (Jul 2025): https://modal.com/blog/gpu-mem-snapshots · Fast lazy container loading (Sep 2024): https://modal.com/blog/jono-containers-talk
- Modal client – `MODAL_ENABLE_SNAP_RESTORE`: https://github.com/modal-labs/modal-client/blob/main/py/modal/_container_entrypoint.py
- gVisor docs – Checkpoint/Restore: https://gvisor.dev/docs/user_guide/checkpoint_restore/ · commit 41f01d8: https://github.com/google/gvisor/commit/41f01d8f9c5aee4f7a31ec6183fb50bbc6f9b851 · checkpoint files: https://github.com/google/gvisor/blob/master/pkg/sentry/state/checkpointfiles/checkpointfiles.go · restore cmd: https://github.com/google/gvisor/blob/master/runsc/cmd/restore.go · sandbox restore: https://github.com/google/gvisor/blob/master/runsc/sandbox/sandbox.go · GCS gofer: https://github.com/google/gvisor/blob/master/runsc/checkpointgofer/gcs/gcs.go
- CRIU – lazy migration: https://criu.org/Lazy_migration · zero pages: https://github.com/checkpoint-restore/criu/blob/criu-dev/criu/page-xfer.c
- Firecracker – snapshot support: https://github.com/firecracker-microvm/firecracker/blob/main/docs/snapshotting/snapshot-support.md
- Sabre (OSDI '24): https://www.usenix.org/conference/osdi24/presentation/lazarev · PDF https://www.usenix.org/system/files/osdi24-lazarev_1.pdf · code https://github.com/barabanshek/sabre
- Spice/SHELF (OSDI '26): https://www.usenix.org/conference/osdi26/presentation/holmes · PDF https://www.usenix.org/system/files/osdi26-holmes.pdf · artifact https://github.com/JunctionOS/spice-ae
- Papers: Catalyzer ASPLOS 2020 https://dl.acm.org/doi/10.1145/3373376.3378512 · vHive/REAP ASPLOS 2021 https://arxiv.org/abs/2101.09355 · Firecracker NSDI 2020 https://www.usenix.org/conference/nsdi20/presentation/agache · FaaSnap EuroSys 2022 DOI 10.1145/3492321.3524270 · SOCK ATC 2018 https://www.usenix.org/conference/atc18/presentation/oakes · Faa$T https://arxiv.org/abs/2104.13869 · FaaSLight https://arxiv.org/abs/2207.08175 · DeltaBox https://arxiv.org/abs/2605.22781
- In-repo: `V2_10_COLD_RUNS_35S_COOLDOWN.md`, `FAST_DISK_SNAPSHOT_RESTORE_REPORT.md`, `V2_REMAINING_OPTIMIZATION_DIAGNOSTICS.md`, `deploy1_all.log` (snapshot manifest), `d2_construction.log` (host memory), `modal_app.py`, `cpu_snapshot_models.py`, `restore_state_probe.py`, `snapshot_build_manifest.py`
