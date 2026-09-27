# `h.fd >= 0` vs `h.fd < 0` — One-Bit Localization

Static source + existing-artifact audit. No deployment, no benchmark, no QD change, no Golden change, no probe run needed.

Labels: **[OBSERVED]** = already in our captured artifacts · **[SOURCE-CURRENT]** · **[PLAUSIBLE]** · **[UNRESOLVED]**

---

## 1. Executive answer

# **C. DIRECTFS / HOST FD CONFIRMED**

**Confidence: high (~90%).** Decisive evidence is a **gofer mount super-options string already present in our own captured artifacts**, which contains the literal token **`directfs`**, alongside `fstype: 9p` and `cache=remote_revalidating`.

**Decisive evidence [OBSERVED]** — `…/golden_p1_parallel_io_v2_c0_persistent_fds_022680017ab64931_evidence_2026-09-18/raw/0054_attempt_0.json`:

```json
{
  "mount_id": "33",
  "parent_id": "18",
  "major_minor": "0:26",
  "root": "/",
  "mount_point": "/__modal/mounts",
  "mount_options": "rw,nosuid",
  "fstype": "9p",
  "source": "none",
  "super_options": [
    "rw,trans=fd,rfdno=6,wfdno=6,aname=/,dfltuid=4294967294,dfltgid=4294967294,dcache=1000,cache=remote_revalidating,disable_fifo_open,directfs"
  ]
}
```

The same artifact contains `directfs` 50×, `remote_revalidating` 50×, `9p` 52×, `p9` 27× — and **`lisafs` 0×**.

**Why that settles it:**

1. **`directfs` is enabled on the models mount** → gVisor uses the `directfsInode` implementation, whose `readHandle()` is `return handle{fd: i.readFD.RacyLoad()}` — a **real host FD** held directly by the Sentry. That is directfs's entire design intent: skip the RPC for file data.
2. **`cache=remote_revalidating`** puts the mount in **`InteropModeShared`**, which in `regular_file.go` forces the direct path unconditionally:
   ```go
   if (rw.d.inode.mmapFD.RacyLoad() >= 0 && !rw.d.inode.fs.opts.forcePageCache) ||
      rw.d.inode.fs.opts.interop == InteropModeShared || rw.direct {
   	n, err := h.readToBlocksAt(rw.ctx, dsts, rw.off)
   ```
3. **`readToBlocksAt` then takes the host-FD branch** because `h.fd >= 0` under directfs:
   ```go
   if h.fd >= 0 {
   	ctx.UninterruptibleSleepStart(false)
   	n, err := hostfd.Preadv2(h.fd, dsts, int64(offset), 0 /* flags */)
   	ctx.UninterruptibleSleepFinish(false)
   ```

**So the D-state wall for our model reads is `hostfd.Preadv2` on a donated host FD — PATH A.** The lisafs/RPC fallback is not reached.

**Correction to my previous audit:** the RPC fallback is **9P**, not lisafs. The metric is literally named `GoferReads9P`, the mount `fstype` is `9p`, and `lisafs` appears **zero** times in our artifacts. My earlier Variant B (`lisafs.ClientFD.Read` → `SndRcvMessage(PRead)`) was the wrong protocol for this mount.

---

## 2. Exact model mount **[OBSERVED]**

| property | value |
|---|---|
| mount point | `/__modal/mounts` (Modal's volume mount root; `/root/models` resolves inside it) |
| fstype | **`9p`** (gVisor gofer/p9 client) |
| major:minor | `0:26` |
| mount options | `rw,nosuid` |
| super options | `rw,trans=fd,rfdno=6,wfdno=6,aname=/,dfltuid=4294967294,dfltgid=4294967294,dcache=1000,`**`cache=remote_revalidating`**`,disable_fifo_open,`**`directfs`** |
| transport | `trans=fd` — gofer connection over an inherited FD (`rfdno=6,wfdno=6`) |
| cache mode | **`remote_revalidating`** → `InteropModeShared` |
| model file | `/root/models/text_encoders/qwen_3_4b.safetensors`, regular file, `st_dev=31` (same device as the other Volume file; tmpfs was `st_dev=18`) |

Consistent with an earlier finding that `mountinfo` shows no separate `/root/models` line: the models tree is a **subdirectory of the single 9p mount**, which also explains both Volume files sharing `st_dev=31`.

**[UNRESOLVED]** I did not re-verify this mount string against the *sentinel* campaign containers specifically; the artifact is from a Golden run in the same Modal environment. The `directfs` + `cache=remote_revalidating` policy is Modal's mount mechanism, not a per-run choice.

---

## 3. Open → handle call graph **[SOURCE-CURRENT]**

```
guest os.preadv(fd, …)
  ↓ vfs.PRead → regularFileFD.PRead                    pkg/sentry/fsimpl/gofer/regular_file.go
      start := fsmetric.StartReadWait()
      defer { if d.inode.readFD.Load() >= 0 { GoferReadsHost++ } else { GoferReads9P++ } }
  ↓
      rw := getDentryReadWriter(ctx, d, offset)
      if interop == InteropModeShared  ← TRUE for cache=remote_revalidating
          → h.readToBlocksAt(ctx, dsts, off)            pkg/sentry/fsimpl/gofer/handle.go
  ↓
      if h.fd >= 0 {                                     ← TRUE under directfs
          ctx.UninterruptibleSleepStart(false)          ← D STATE
          hostfd.Preadv2(h.fd, dsts, int64(offset), 0)  ← THE WALL
          ctx.UninterruptibleSleepFinish(false)
      }
  ↓
return → syscall return → systrap switchToApp() → contextQueue → waitOnState → guest userspace
```

`directfsInode.readHandle()` → `handle{fd: i.readFD.RacyLoad()}` — the host FD is stored **on the inode**.

---

## 4. FD donation conditions **[SOURCE-CURRENT]**

- Server side (`runsc/fsgofer/lisafs.go`): `case ftype == unix.S_IFREG: // Best effort to donate file to the Sentry (for performance only). hostFDToDonate, _ = unix.Dup(openHostFD)`.
- Client side: the donated FD becomes the inode's `readFD`; `handle.fd` reads it; `-1` means "no host FD".
- Under **directfs**, holding host FDs is the *design contract*, not a best-effort extra — which is why `directfs` in the mount options is strong positive evidence rather than a hint.

**Conditions that could leave `readFD < 0`:** `Dup()` failure on the gofer (transient resource exhaustion); a non-regular file (not our case); a mount policy that declines donation; and **restore** (below). I found no evidence of the first three applying here.

---

## 5. Snapshot / restore effect on `readFD` **[UNRESOLVED — the one real caveat]**

Host FDs are **not savable**. `handle` is documented as *"explicitly not savable"*, and host FDs cannot cross a checkpoint. So **after a restore, `readFD` must be re-established**; until it is, reads would fall to the 9P path.

**Why this matters for us specifically:**
- Our **diagnostic/sentinel campaigns** used fresh single-use containers with **no snapshot restore** → `readFD` is established at open → **PATH A live**. This is the case that produced the D-state pathology, so the localization holds for the measurements we have.
- **Golden** uses snapshot/restore. Whether the post-restore first read is on the 9P fallback before re-donation is **not resolved by this audit** — I did not retrieve `afterLoad`/re-donation source. It is a genuine possible difference between the pre-snapshot and post-restore read path.

I am flagging this rather than asserting the paths are identical, since you explicitly said not to assume pre-snapshot equals post-restore.

---

## 6. Existing metric / log evidence **[OBSERVED: not captured]**

The source exposes exactly the discriminator you identified:

```go
	if d.inode.readFD.Load() >= 0 {
		fsmetric.GoferReadsHost.Increment()
		fsmetric.FinishReadWait(fsmetric.GoferReadWaitHost, start)
	} else {
		fsmetric.GoferReads9P.Increment()
		fsmetric.FinishReadWait(fsmetric.GoferReadWait9P, start)
	}
```
**[SOURCE-CURRENT]**

**We have never captured these counters.** A targeted search of our artifacts for `GoferReadsHost|GoferReads9P|GoferReadWait|fsmetric|donated|hostfd` returned **zero hits** across the whole repo. The only `trans=fd` hits were the mount-option string quoted in §1, which is what actually decided the question.

So the metric route was not needed — the mount-policy string was already in our evidence and is decisive on its own.

---

## 7. Tiny probe required?

**No.** The fork was resolved from **existing artifacts + source**, with no container run. This satisfies your constraint to use the lightest evidence first.

*(Had it been needed, the probe would have been: read `GoferReadsHost`/`GoferReads9P` before and after one ordinary model read. Those counters live in the Sentry and are not exposed to the guest, so this route may not have been available anyway — the mount string was the better evidence.)*

---

## 8. Ownership table

| object | owner | shared across 4 workers? | survives restore? | relevant? |
|---|---|---|---|---|
| `regularFileFD` | per guest `open()` | no | n/a | no |
| **`inode.readFD`** (donated host FD) | **per inode** | **yes** — all opens of the same path converge on one inode | **no** (host FD, unsavable) | **YES — the shared object** |
| `inode.mmapFD` | per inode | yes | no | secondary (direct path is forced by `InteropModeShared` anyway) |
| `handle.fd` | derived from `inode.readFD` | yes | no | YES |
| `dentry` | per path in the mount | yes | re-established | indirect |
| 9P client connection (`trans=fd`) | per mount | yes | re-established | only on the fallback path |
| `Task` / D-state flag | per Task | no | n/a | no |
| host filesystem behind the FD | host-side external | yes | n/a | **immediate next owner** |

**Ownership correction carried forward, as you asked:** the correct wording is **shared per-inode read handle / donated host FD**, not "per-dentry". Source: `inode.readFD`, and `readHandle()` reads it from the inode. Multiple guest `open()`s of the same path converge on the same inode and therefore the same donated host FD.

**And the offset point, explicitly:** reads use **`hostfd.Preadv2(h.fd, dsts, int64(offset), 0)`** with an **explicit offset**. `preadv2` is stateless with respect to the file-position cursor, so **sharing the host FD does NOT serialize offsets** — I am not blaming a shared file-position cursor.

---

## 9. Direct answers

**Is `h.fd >= 0` during the actual model reads?**
**Yes — [PLAUSIBLE, high confidence]** for the fresh-container diagnostic runs that produced our measurements. `directfs` is in the mount options, `cache=remote_revalidating` forces the direct path, and directfs holds a host FD on the inode.

**Is `hostfd.Preadv2` the D-state wall?**
**Yes.** `readToBlocksAt`'s `h.fd >= 0` branch wraps `hostfd.Preadv2(h.fd, …)` in `UninterruptibleSleepStart/Finish(false)`, which is precisely the `D` state we observed.

**Or is `SndRcvMessage(PRead)` the D-state wall?**
**No** — and the fallback is **9P, not lisafs**. `lisafs` appears 0× in our artifacts; `fstype` is `9p`; the counter is `GoferReads9P`. My previous audit named the wrong protocol for this mount.

**Is the handle per inode or per open?**
**Per inode.** `inode.readFD`; `readHandle()` loads it from the inode.

**Do all four workers share the same donated host FD?**
**Yes** — all four open the same path, resolve the same inode, and read via that inode's `readFD`.

**Does sharing the FD serialize offsets?**
**No.** Every read is `preadv2` with an explicit offset; there is no shared file-position cursor to serialize on. Source-proven.

**Can snapshot/restore cause fallback to RPC?**
**Possibly — [UNRESOLVED].** Host FDs are unsavable, so `readFD` must be re-established after restore. I did not retrieve the re-donation path. This affects **Golden** (which snapshots); our diagnostic runs were fresh containers and are unaffected.

**What exact subsystem sits immediately below the winning path?**
**The host filesystem backing the donated FD** — i.e. the host-side mount that Modal presents for the model Volume (the gofer process's `openHostFD`). That is the next boundary and I deliberately did not go below it.

**What is now the narrowest defensible owner of source sickness?**
**`hostfd.Preadv2(inode.readFD, …)` — a host `preadv2` syscall issued by the Sentry on a per-inode donated host FD — with the wall in the host filesystem/backing store behind that FD.**

**What is the SINGLE best next diagnostic?**
**Identify the host filesystem type behind the donated FD** (the immediate next owner). That is the boundary at which the remaining wall lives, and it is answerable from the host-side mount spec for the Modal model Volume. Nothing in the guest or in Sentry source can resolve it further.

---

## 10. Evidence table

| finding | evidence | confidence | implication |
|---|---|---|---|
| Models mount is a **9p gofer mount with `directfs`** | **[OBSERVED]** captured super_options, `0054_attempt_0.json` | High | directfs host-FD path is live |
| `cache=remote_revalidating` ⇒ `InteropModeShared` | **[OBSERVED]** mount option | High | forces `readHandle()` direct path unconditionally |
| `readToBlocksAt` host branch wraps **`hostfd.Preadv2`** in `UninterruptibleSleepStart(false)` | **[SOURCE-CURRENT]** `gofer/handle.go` | High | this IS the D-state wall |
| `directfsInode.readHandle()` = `handle{fd: i.readFD}` | **[SOURCE-CURRENT]** (per user-provided source) | High | host FD is per inode |
| Metric split `GoferReadsHost` vs `GoferReads9P` keys on `inode.readFD >= 0` | **[SOURCE-CURRENT]** `regular_file.go` | High | confirms the binary and names the fallback **9P** |
| **`lisafs` = 0 occurrences; `9p` = 52** | **[OBSERVED]** artifact token counts | High | corrects my earlier "lisafs" claim |
| `preadv2` uses explicit offsets | **[SOURCE-CURRENT]** | High | shared FD does **not** serialize offsets |
| Host FDs unsavable ⇒ restore must re-donate | **[SOURCE-CURRENT]** (`handle` "explicitly not savable") | Medium | Golden post-restore path unresolved |
| `GoferReadsHost/9P` counters captured by us | **[OBSERVED]** zero hits repo-wide | High | metric route unavailable; mount string was decisive |
| Mount string applies to the sentinel containers too | **[UNRESOLVED]** | Medium | artifact is from a Golden run |
