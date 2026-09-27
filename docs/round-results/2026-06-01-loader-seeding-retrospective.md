# Loader Seeding Retrospective — Rounds 1b to 1e

Date: 2026-06-01

---

## User Priority

Optimize for **cold-container production behavior** with infrequent traffic.

Priority order:

1. Keep cold restore / startup fast for real customer requests
2. Do not regress snapshot-restore time
3. Improve first real prompt latency only if it does not materially hurt restore time

---

## Baseline That Matters

The important baseline branch had roughly:

- restore around **~0.05s to ~0.25s** after snapshot restore
- first real prompt around **~12s to ~14s**

This was the “fast snapshot / slower first prompt” branch.

---

## Experiments Tried

### 1. Lazy live loader-object cache populated after real requests

**Idea:** Cache live outputs of `VAELoader`, `CLIPLoader`, `UNETLoader`, `DualCLIPLoader` after a real request so later requests reuse the same objects.

**Why:** Remove repeated CLIP/VAE/UNET object construction cost.

**Observed result:**

- initial implementation had a cache-clearing bug
- fixed implementation worked only inside the same live process
- it did **not** help cross-restore cold-container behavior because the cache was filled **after** snapshot creation, not before

**Conclusion:**

- useful only for same-process warm reuse
- **not useful** for the user’s cold-container priority

---

### 2. Full in-process warmup during `startup(snap=True)`

**Idea:** Run a real warmup workflow during snapshot creation so the snapshot already contains a warmed runtime and live model state.

**Observed result:**

- warmup ran successfully during snapshot build
- later restore crashed with:
  - `Runner segmentation fault (SIGSEGV), exit code: 139`

**Conclusion:**

- **Do not retry** full warmup / real workflow execution during `snap=True`
- snapshotting post-inference GPU / Comfy state was not safe in this setup

---

### 3. Snapshot-safe loader seeding during `startup(snap=True)`

**Idea:** Instead of full inference, replay only loader nodes during snapshot creation and store live loader objects in the snapshot.

Variants tried:

- loader seeding without `torch.inference_mode()`
- loader seeding with `torch.inference_mode()`

**Observed result:**

- could produce `loader_cache_hit` on later restored requests
- but snapshot weight / restore timing regressed materially
- customer-visible cold start got worse even when prompt time improved

At one point this branch got first prompt time near **~9.8–10.0s**, but the snapshot/restore path became too expensive overall.

**Conclusion:**

- **Do not retry** startup loader seeding under `snap=True`
- even when technically safe, it made cold-container behavior worse end-to-end

---

### 4. Restore-time loader priming during `restore(snap=False)`

**Idea:** Keep snapshot light, but immediately rebuild loader cache during restore so the first real prompt hits the cache.

Variants tried:

- restore-time priming without `torch.inference_mode()`
- restore-time priming with `torch.inference_mode()`

**Observed result:**

- without inference mode: first real prompt failed with
  - `RuntimeError: Cannot set version_counter for inference tensor`
- with inference mode: the crash was fixed
- but restore time ballooned badly, often by several seconds

Representative restore-prime costs observed:

- ~3.7s
- ~6.3s
- ~12.1s

This violated the user’s higher-priority constraint: keep cold restore fast.

**Conclusion:**

- **Do not retry** restore-time loader priming
- even the safe variant regressed the cold restore path too much

---

## What We Learned

1. **Live loader-object caching is fundamentally aligned with warm-process reuse, not cold-container optimization.**
2. **Full warmup during `snap=True` is unsafe** in this ComfyUI + GPU snapshot configuration.
3. **Loader seeding / priming can reduce first prompt latency**, but it does so by increasing either:
   - snapshot creation cost and/or snapshot heaviness
   - restore-time cost
4. For this project, **customer-visible cold restore latency matters more** than shaving a few seconds off the first prompt.

---

## Final Decision

Rollback loader seeding entirely.

Keep only:

- CPU state-dict preload during `startup(snap=True)`
- fast CUDA wakeup during `restore(snap=False)`

Do **not** revisit these approaches unless the user explicitly asks to trade restore time for prompt time:

- full workflow warmup during `snap=True`
- loader seeding during `snap=True`
- loader priming during `restore(snap=False)`
- any live-object snapshot strategy that increases cold restore time

---

## Rule For Future Iterations

Future optimizations must satisfy this guardrail:

> **Do not increase snapshot restore time.**

Only pursue optimizations that preserve the fast restore path and attack other parts of the cold request lifecycle.
