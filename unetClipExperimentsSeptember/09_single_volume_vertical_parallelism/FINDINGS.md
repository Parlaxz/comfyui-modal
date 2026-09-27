# Findings

1. BASELINE_OPT is compared with all fixed 4 MiB arms; evidence status is complete.
2. The shared versus independent FD effect is the BASELINE_OPT→ONEFILE_THREADS comparison.
3. ONEFILE_THREADS versus ONEFILE_PROCESSES isolates backend at one file and eight workers.
4. ONEFILE_THREADS versus SHARDS_THREADS isolates layout for threads.
5. ONEFILE_PROCESSES versus SHARDS_PROCESSES isolates layout for processes.
6. SHARDS_PROCESSES is compared directly with BASELINE_OPT at each Volume.
7. V1/V2 deltas are reported for every arm in the comparison table.
8. Each complete arm/Volume row reports coordinated, worker-envelope, parent, client, startup, and practical-total walls plus a rate derived from each wall; worker rates are never summed.
9. Each complete arm/Volume row reports raw six-run values, mean, median, min, max, range, sample SD, and CV.
10. Fastest V1: SHARDS_PROCESSES (2.3545027198872823 GB/s); fastest V2: ONEFILE_PROCESSES (2.420636228261288 GB/s).
11. Process startup is retained separately from the coordinated read wall.
12. Practical total uses full-process wall for processes and coordinated wall for threads.
13. NINETY_OBSERVED_FIRST_TOUCH status: observed.
14. NINETY_CLASS_REPEATABLE status: observed; criterion is median >=80 and >=4/6 >=80 for SHARDS_PROCESSES per backend.
15. NINETY_WARM_ONLY status: unknown; the clean plan contains no warm-only arm.
16. Old claims are SUPERSEDED FOR DECISION-MAKING; only current clean diagnostics and decision rows are decision evidence.
17. The campaign stops at exactly 69 full-size timed reads; no additional phase is included.
