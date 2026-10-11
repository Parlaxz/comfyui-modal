# Golden source experiment controls — Oct 07

The request contract is fail-closed and preserves selector absence. With no
source experiment keys, the existing Golden request and CURRENT source path
remain unchanged; the 4 ms floor is implicit. Experimental requests carry one
immutable effective-controls record at request/plan level.

Implemented selectors:

- `SOURCE_POLICY`: `CURRENT` or committed `PHASE_EXACT`. `PHASE_EXACT` requires
  four thread readers, native QD4, 64 MiB slots, and whole 64 MiB parents.
- `LAUNCH_GAP`: 4/6/8/10/15/20 ms, represented in nanoseconds. Unsupported
  values fail closed; there is no per-operation environment lookup.
- `MICROSCOPE`: `OFF` or
  `SUBDIVIDED64_RESIDENCY_FORENSIC_EXACT`. Its scope is three fixed full-parent
  ordinals per model, reconciled as 16 x 4 MiB subchunks, with probe/fault
  overhead classified as contaminated diagnostic work.
- `QD_MODE`: only `CURRENT` exists. `TRUE_QD1`, `TRUE_QD1_128`, `LRU8_EXACT`,
  and pure `SUBDIVIDED64_EXACT` are blocked and are not silently substituted.

The microscope requires Linux probes, a whole-file mapping, and three distinct
full 64 MiB parents. Selection and topology failures reject the request rather
than falling back to CURRENT.
