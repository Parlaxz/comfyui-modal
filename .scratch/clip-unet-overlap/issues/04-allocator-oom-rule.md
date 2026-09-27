# Allocator Headroom and OOM Fail-Closed Rule

Status: resolved
Type: research
Blocked by: none

## Question

What allocator evidence admits the overlap window and what fails it closed: free-memory/headroom threshold, combined peak allocated/reserved sampling, no `empty_cache()` purges, no global peak-reset contamination during CLIP forward, and explicit OOM/degraded classification — without claiming UNET-only deltas while CLIP is active?

## Answer

Admission requires post-operation combined peak headroom: `free_bytes >= required_peak_bytes + safety_margin_bytes` using `mem_get_info()` free/total plus allocated/reserved and both peak counters at every boundary. No `empty_cache()`, purges, GC, unloads, or `reset_peak_memory_stats()` inside the active overlap window; peaks are combined-device evidence, never UNET-only while CLIP is active. `torch.cuda.OutOfMemoryError` is `oom`; missing/stale/ambiguous telemetry or non-OOM allocator failure is `degraded`; both fail closed with no retry or success claim. Full evidence: `../research/04-allocator-oom-rule.md`.

## Comments

Resolution recorded from completed research lane; no source, branch, scheduling, or dirty state modified.
