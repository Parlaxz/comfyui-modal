# Can we decouple the hedge from the original? — No, not this way

**Short answer: not by changing our process/FD/thread structure (there is no coupling left in our code), and not by reading a different inode on the same Volume (it stalls too). The coupling domain is the shared volume/mount, not the inode.**

## 1. Code audit — there is no coupling in our implementation

| coupling candidate | present? |
|---|---|
| hedge process receives/uses the pacer (`last_launch_ns`) | **No** |
| hedge calls `_mw_gate_launch` (gated launch) | **No** |
| hedge touches `hedge_slot` (shared state) | **No** |
| hedge takes any lock | **No** |
| hedge shares the reader's FD or buffer | **No** — own process, own FD, own 64 MiB buffer |
| hedge issues its own `preadv` | **Yes**, ungated |

The one failure mode that *would* be our bug — the hedge being blocked **before** entering `preadv` — is excluded by measurement: `h_enter − trigger = 0.30 ms` in the clean case. The hedge enters the syscall immediately; the time is spent **inside** it.

So your instinct was reasonable, but the audit says the coupling is not ours.

## 2. Resource-diversity test — hedge reads a DIFFERENT inode

Hedge pointed at `/root/models/diffusion_models/z_image_turbo_bf16.safetensors` (a different file, different inode) instead of the primary model, at the same 125 ms threshold.

Run `im-09.json`, `unspecified:eu-north`, worst primary read **6837.1 ms**:

| original ms | trigger ms | receive→enter ms | hedge enter rel original | hedge ms | winner | saved ms |
|---:|---:|---:|---:|---:|---|---:|
| 1551.6 | 125.7 | 5107.88 | 5233.57 | 42.11 | original | 0.00 |
| 1368.8 | 1368.9 | 2.25 | 1371.10 | **7313.09** | original | 0.00 |
| 907.2 | 125.4 | 0.24 | 125.65 | **834.27** | original | 0.00 |
| 636.4 | 125.7 | 4905.05 | 5030.72 | 40.01 | original | 0.00 |
| 364.8 | 126.1 | 5120.81 | 5246.89 | 130.47 | original | 0.00 |

- **hedge on a different inode stalled for 7313.09 ms** and 834.27 ms.
- 0 / 5 wins, 0 ms saved.
- hedge-process canary max gap **11.3 ms** — the process was fully schedulable the whole time.

**A read on a different inode, in a different process, with its own FD, stalled for 7.3 seconds.** So the stall is **not** a property of the model file's inode, and a different inode does **not** decouple it.

## 3. Important limitation of this test

Both files live on the **same Modal Volume** (`/root/models`). A different inode on the same VolumeFS/FUSE mount still goes through the **same mount, the same host client, and the same underlying resource pool**. So this test separates *inode* but **not** *underlying resource*.

Therefore:

| coupling domain | tested | result |
|---|---|---|
| process / FD / buffer / launch gating | yes (audited + measured) | **not the cause** |
| inode (different file, same Volume) | yes (this test) | **not the cause — still stalls 7.3 s** |
| volume / mount / host client | **no** | **untested — now the prime suspect** |
| host / node / network | no | untested |

The historical ROTATE4 "pristine resource island" meant a **different resource**, not a different file on the same mount. That specific lever remains untested, and it is now the only one left.

## 4. A real defect I introduced, which confounds part of this

The hedge process serves requests **serially** — one `preadv` at a time. While it was stuck for 7313 ms, the other queued requests waited behind it. That is why three events show `receive→enter ≈ 4900–5121 ms`: pure queueing behind the 7.3 s hedge, **not** a coupling measurement.

Consequences:
- the ~5 s `receive→enter` values are an artifact of my single-server design, not evidence about the source;
- `max_pending = qd` (4) lets several requests queue behind one slow hedge, which makes the hedge process a new bottleneck;
- this must be fixed (a small pool of hedge workers, or dispatch only one at a time and drop the rest) before any further hedge timing can be trusted.

## 5. Conclusions

| question | answer |
|---|---|
| Is the coupling a bug in our implementation? | **No** — audited; the hedge has no shared lock, pacer, FD, buffer, or state with the reader. |
| Can we decouple by changing process/FD/thread structure? | **No** — already fully separated, and it still couples. |
| Can we decouple by reading a different inode? | **No** — a different file on the same Volume stalled for 7.3 s. |
| Is there any lever left? | **Only a genuinely different underlying resource** (a different volume/mount, or a second copy served from a different backend). That is untested and is the last remaining candidate. |

**Recommendation:** fix the serial-hedge bottleneck first (it currently invalidates the `receive→enter` measurements), then test the one remaining lever — a hedge served from a **different mount/volume**, not merely a different file. If that also stalls, same-container resource diversity cannot rescue hedging and the direction should be closed out.
