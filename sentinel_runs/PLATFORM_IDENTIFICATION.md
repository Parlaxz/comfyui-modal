# Platform Identification — Modal gVisor Sandbox

Read-only identification task. One fresh container used (`probe_platform`, CPU-only, no GPU, no model, no benchmarks). No deployment of sickness experiments, no Golden change.

Raw evidence: `sentinel_runs/platform_probe.json`
Probe: `e04_source_race_modal.py::probe_platform` (read-only shell, returns text)

Evidence labels: **[OBSERVED]** = measured in the container this task · **[SOURCE]** = authoritative gVisor/vendor docs · **[INFERRED]** = conclusion from [SOURCE] applied to our environment · **[UNRESOLVED]**

---

## 1. Executive answer

**Platform: systrap — [INFERRED] with high confidence (~85–90%). NOT positively observed.**

Per your decision rule ("only classify SYSTRAP if there is positive evidence"), I am **not** claiming a positive observation. The guest exposes **no platform artifact at all**, and I now believe it structurally *cannot*: every systrap-specific structure (stub process, sysmsg threads, `contextQueue`, shared regions) lives in the **Sentry/host address space or in stub host threads**, and guest procfs is virtualized by the Sentry. So the guest is the wrong vantage point for a direct read.

The classification rests on an authoritative, non-contradicted inference chain:

| # | evidence | source |
|---|---|---|
| 1 | Modal uses gVisor for sandbox isolation | **[SOURCE]** Modal blog/docs ("Modal uses gVisor for its sandbox isolation"; Sandboxes run on gVisor by default) |
| 2 | *"systrap replaced ptrace as the default platform in mid-2023"*; *"By default, the systrap platform is selected"* | **[SOURCE]** gVisor `docs/user_guide/platforms/` |
| 3 | ptrace *"is no longer supported and is expected to eventually be removed entirely"* | **[SOURCE]** same |
| 4 | KVM *"runs best on bare-metal"*; *"the systrap platform will often yield better performance"* inside a VM; KVM needs nested virt | **[SOURCE]** gVisor platform guide |
| 5 | Our sandboxes are GPU cloud instances on GCP/OCI/AWS, i.e. **inside VMs** (`MODAL_CLOUD_PROVIDER` observed as `CLOUD_PROVIDER_AWS`/`OCI`/`GCP`) | **[OBSERVED]** |
| 6 | No env var, mount, binary, or file exposes a platform override | **[OBSERVED]** |

Chain: Modal → gVisor → default systrap → running in a VM where systrap is the recommended choice → no evidence of an override. **No contradicting evidence was found.**

**Strongest single piece of evidence:** gVisor's own documentation states systrap has been the **default** since mid-2023 and that ptrace is **unsupported and slated for removal** — combined with the vendor confirming Modal runs gVisor and our environment being a VM. Using ptrace would require a deliberate, deprecated override, for which there is no trace.

---

## 2. Direct runtime metadata **[OBSERVED]**

```
uname -a : Linux modal 4.19.0-gvisor #1 SMP Sun Jan 10 15:06:54 PST 2016 x86_64 GNU/Linux
osrelease: 4.19.0-gvisor #1 SMP Sun Jan 10 15:06:54 PST 2016
which runsc        : (none)
runsc --version    : /bin/sh: 1: runsc: not found
/usr/local/bin     : 2to3, idle, pip, pydoc, python3.11, uv, uvx, wheel   (Python tooling only)
find /*runsc*|*systrap* (maxdepth 3): no hits
/proc/1/cmdline    : /bin/dumb-init -- python -u -R --check-hash-based-pycs never -m modal._container_entrypoint
```

**No runsc binary, no build ID, no gVisor build metadata, no platform flag.** As expected: `runsc` and its `--platform` flag are host-side. `4.19.0-gvisor` is the guest kernel ABI string and identifies neither commit nor platform.

`MODAL_*` env present: `MODAL_CLOUD_PROVIDER`, `MODAL_REGION`, `MODAL_IMAGE_ID`, `MODAL_TASK_ID`, `MODAL_SERVER_URL=unix:/run/modal.sock`, `MODAL_CONTAINER_ARGUMENTS_PATH=/__modal/.container-arguments/data.bin`, `MODAL_IS_REMOTE=1`, `MODAL_ENVIRONMENT`. **None exposes the runtime platform.**

---

## 3. Procfs findings **[OBSERVED]**

| probe | result | usable as platform evidence? |
|---|---|---|
| `TracerPid` (`/proc/self/status`, `/proc/1/status`) | `0` | **No** — gVisor virtualizes guest procfs; the Sentry is not the guest's tracer *in the guest's own view*, under either platform. Absence of a tracer is **not** proof of no ptrace (per your caution). |
| `Seccomp` (`/proc/self/status`) | `0` | **No** — this is the *guest's* seccomp state (emulated). systrap's seccomp filter is installed on **stub host threads**, not guest tasks. |
| `/proc/self/maps` | normal guest mappings only; no stub/contextQueue regions | **No** — `mapSharedRegions` maps `contextQueueFR` and the thread-context region into the **Sentry** address space and the stub, not the guest's. |
| `/dev/shm` | present, empty | **No** — generic to containers; systrap's shared memory is a `pgalloc.MemoryFile`, not guest `/dev/shm`. |
| `/proc/self/cgroup` | `7:pids:/ta-…`, `6:memory:/ta-…`, … `1:cpu:/ta-…` | **No** — Modal task cgroup, no platform. |
| `/proc` listing | guest PIDs `1, 2, 46, 47, 48` | **No** — only guest tasks; stub/sysmsg host threads are invisible. |
| `ps -eLf` | `ps: not found` | n/a — no procps in the image |

**Nothing in guest procfs distinguishes the platform.** That is the expected result, not a failure of the probe.

---

## 4. Thread / process topology **[OBSERVED]**

- Guest-visible PIDs: `1` (`/bin/dumb-init -- python … modal._container_entrypoint`), `2`, `46`, `47`, `48` — all guest tasks.
- No stub process, no sysmsg thread, no ptrace helper visible.

**Entity distinction (important, and the reason topology cannot help):**

| entity | where it lives | guest-visible? |
|---|---|---|
| guest process / thread | inside the sandbox | **yes** |
| Sentry process | host | no |
| Sentry Go thread/goroutine | host | no |
| systrap **stub** process/thread | host (separate host process) | no |
| systrap **sysmsg** threads | host (stub) | no |
| ptrace tracee/helper | host | no |

Both platforms keep all of their machinery **host-side**, so guest topology is uninformative for either.

---

## 5. Systrap-specific evidence **[OBSERVED: none found]**

Checked for the artifacts current `pkg/sentry/platform/systrap` would imply and found none — and, importantly, **the source says none should be guest-visible**:

| source says | guest observation | confidence |
|---|---|---|
| stub process per sandbox | not visible (host process) | high — stubs are host-side |
| `sysmsgThreads` / `sysmsgStackPool` | not visible (host threads) | high |
| `contextQueue` shared region | mapped into **Sentry**, not guest (`mapSharedRegions`) | high |
| `usertrap` patches | applied to stub-side text | unresolved |
| seccomp `SECCOMP_RET_TRAP` on stub threads | not visible (stub-side) | high |

So **absence of systrap artifacts carries no evidential weight** — I explicitly do not treat it as evidence against systrap.

---

## 6. Ptrace-specific evidence **[OBSERVED: none found]**

| source says ptrace would imply | guest observation | weight |
|---|---|---|
| `PTRACE_SYSEMU` interception of guest syscalls | not observable from guest | none |
| tracer relationship | `TracerPid: 0` — but procfs is virtualized | **none** (explicitly not proof) |
| helper/tracee topology | not visible | none |
| higher syscall context-switch cost | see §8 — our measured cost is on the fast side | weak, see below |

**No positive ptrace evidence, and no negative evidence either.** Per your rule, I do not infer ptrace from any absence.

---

## 7. Modal / bundle metadata evidence **[OBSERVED]**

Searched existing logs, artifacts, bundle and image metadata for `systrap|ptrace|runsc|gvisor|platform=|sandbox|runtime|seccomp`:
- Only **unrelated** hits: a `google_drive` custom-node path and a `gvisor_marker: null` field in older evidence JSON.
- `MODAL_IMAGE_ID` identifies *our app image*, not the runtime build.
- No deployment log or bundle artifact exposes a runtime platform flag.

**Conclusion: Modal does not surface the gVisor platform into the guest or into our captured metadata.**

---

## 8. Source-backed discriminator table

| Signal | Expected under systrap | Expected under ptrace | Observed | Strength |
|---|---|---|---|---|
| guest-visible stub process | absent (host-side) | absent | absent | **0 — no signal** |
| `TracerPid` | 0 (virtualized) | 0 (virtualized) | 0 | **0 — not a discriminator** |
| guest `Seccomp` field | emulated, platform-independent | same | 0 | **0 — not a discriminator** |
| systrap shared regions in guest maps | absent (mapped into Sentry) | n/a | absent | **0 — no signal** |
| `runsc --platform` flag | host-side | host-side | not visible | **0 — no signal** |
| Modal env exposing platform | none expected | none expected | none | **0 — no signal** |
| **syscall interception cost** | seccomp-trap + shared-memory fast path → **low µs** | `PTRACE_SYSEMU`, 2 stops/syscall → **high µs** ("high context switch overhead") | `SYS_gettid` measured **2.1–5.7 µs** (n=4 runs) | **weak, consistent-with-systrap** — no ptrace baseline available, so not decisive |
| **documented default** | default since mid-2023 | deprecated, "no longer supported" | no override evidence | **strong (inferential)** |

**Net: exactly one non-zero observational signal (syscall cost), and it is weak. Everything else is structural silence.**

---

## 9. Version / generation status

**UNRESOLVED.** No `runsc` version, no build ID, no runtime revision metadata is reachable. `4.19.0-gvisor` does not date the build, and I am not inferring generation from the date.

**Outcome per your taxonomy: (B) platform = systrap, generation unresolved** — where "platform = systrap" is [INFERRED], not observed.

**Important consequence, and it is favourable:** the systrap per-subprocess accounting hook is present in **current** master. Whether the pre-removal build also had `t.p.PrepareSleep()` is **[UNRESOLVED]**. So:
- If post-removal → systrap per-subprocess candidate is the *only* per-park per-process mechanism.
- If pre-removal → the old `mm` path may exist **in addition**, and could also be live.

**The systrap candidate is therefore live under either generation**, which is why the generation ambiguity does not block progress.

---

## 10. Direct answers

**Is the deployed runtime systrap?**
**[INFERRED] yes, high confidence (~85–90%), not positively observed.** Modal runs gVisor; gVisor's default has been systrap since mid-2023; ptrace is deprecated/unsupported; our environment is a VM where systrap is the recommended platform; no override is visible.

**Is it ptrace?**
**No positive evidence for ptrace, and no evidence against it.** ptrace would be a deliberate, deprecated override with no trace in any channel I can see. I do not claim it is excluded with certainty.

**What positively proves that?**
**Nothing does.** There is no positive in-guest proof either way. The classification is inferential from authoritative defaults plus vendor confirmation. I am stating this plainly rather than manufacturing certainty.

**Which observations are merely consistent rather than decisive?**
- `SYS_gettid` at 2.1–5.7 µs (consistent with systrap's fast path; no ptrace baseline to compare).
- `TracerPid: 0` and `Seccomp: 0` (virtualized — carry no weight at all).
- Absence of stub/sysmsg/contextQueue artifacts (structurally expected to be absent under **both** platforms).
- Environment being a VM (supports systrap over KVM, says nothing about ptrace).

**Is the repaired systrap per-subprocess hypothesis still alive?**
**Yes — live, conditional on the (inferred) systrap classification.** It is the only per-subprocess mechanism in the current park/resume path.

**Is the old MemoryManager activation hypothesis relevant to this deployed runtime?**
**Not in the path I originally claimed** — current master's `prepareSleep`/`completeSleep` contain no `mm` call; that part of my prior audit was wrong and stays retracted. It could become relevant **only** if the deployed build predates `400d3ccd`, which is unresolved.

**⚠ But one new, source-backed observation materially complicates the picture — I am flagging it rather than burying it:**

Our earlier campaigns recorded the stalled **source workers in `D` state**. In gVisor, `StateStatus()` maps:
- `TaskGoroutineBlockedInterruptible` → **"S (sleeping)"** — this is what `Task.block()` sets (`prepareSleep` → `accountTaskGoroutineEnter(BlockedInterruptible)`)
- `TaskGoroutineBlockedUninterruptible` → **"D (disk sleep)"** — set by `UninterruptibleSleepStart/Finish`

**A task inside `Task.block()` should read `S`, not `D`.** We observed `D` for the source `preadv` stalls. That implies the **blocking `preadv` path uses `UninterruptibleSleep`, not `Task.block()`** — a *different* wrapper from the futex path.

Two consequences:
1. The bounded-futex canary (`Task.block` → `PrepareSleep`) and the source `preadv` (`UninterruptibleSleep`) may **not** share the `PrepareSleep` hook. My "single shared suffix = systrap `PrepareSleep`" claim is therefore **too strong** and needs re-checking: any common-suffix hypothesis must cover **both** wrappers.
2. Whether `UninterruptibleSleepStart` still calls `Deactivate` in current master is **unresolved** — I did not fetch it this session. If it does, a **generation-appropriate `mm` path could be live for the preadv wrapper specifically**, which would partially revive the old hypothesis in a *different* location than I originally placed it.

I am explicitly **not** promoting this to a conclusion. It is a discrepancy between a source-backed state mapping and our own earlier observation, and it should be resolved before the next mechanism claim.

---

## 11. Single best next action

**Do not instrument `contextQueue` counters yet — they are Sentry-side and unreachable from the guest, and §10 has just surfaced a prior discrepancy that could invalidate the target.**

The one action that should come first: **verify the block wrapper actually used by the blocking `preadv` path, and whether it reads `D` or `S`.**

Concretely, read current `task_block.go` for `UninterruptibleSleepStart`/`UninterruptibleSleepFinish` and confirm (a) whether they still call `Deactivate`/`Activate`, and (b) whether they call any `PrepareSleep`-equivalent platform hook. That single read either:

- **unifies** the futex and preadv wrappers (common suffix exists → the systrap per-subprocess candidate is the right target, and the next instrument is `waitOnState` duration), or
- **splits** them (two wrappers, possibly two mechanisms → the systrap `PrepareSleep` candidate covers only the futex path and cannot be the whole story).

If it unifies, the single most decisive counter to instrument is **`waitOnState` duration** — it directly measures the time a woken context spends waiting for sysmsg/stub servicing, which is precisely the hypothesised delay; if that duration tracks the excess wake delay, the candidate is confirmed, and if it is ~0 the delay is upstream and the candidate is falsified. I chose it over `numAwakeContexts`/`numActiveThreads`/`numActiveContexts`/`numThreadsToWakeup` because those are *inputs* to the `canKickSysmsgThread` gate, whereas `waitOnState` is where the delay would actually be *spent*.

**Not implemented, as instructed.**
