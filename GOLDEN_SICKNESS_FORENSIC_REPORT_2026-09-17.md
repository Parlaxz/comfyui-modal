# Golden Sickness Forensic Report — 2026-09-17

**Scope:** offline-only forensic report over already-retained artifacts. No deploy, no
network, no Modal request, no runtime/source/test edit, no existing report edit at the
time of the original pass. This file is the only new repository artifact produced by that
pass. The later correction below touches only the derived analysis tool, its derived
outputs, and this report.

**Correction (offline, recomputed 2026-09-17):** a material defect was found in the
first derived pass: the one `computed_valid=false` sham attempt
(`golden-p1-0-9ceed22e46e8`, bundle `golden_p1_parallel_dual_sham_252bc1b6bdd2440e_evidence_2026-09-16`,
failed check `no_output_warning`) was included in the 142-attempt inferential
denominators. Every derived rate, threshold, onset, conditional, provider/region,
allocation, time, concentration, severity, correlation, and statistical test in this
report has been **recomputed over `computed_valid=true` rows only**
(`all_attempts_n=142`, `valid_n=141 = 55 sham + 86 split`), and the derived tool
`tools/analysis/golden_sickness_derived.py` was updated to enforce this. The canonical
`per_request.json` still retains all 142 attempts for audit and canonical `per_read.csv`
retains all 88892 reads; the invalid request's 626 reads (clip 243 / unet 370 / vae 13)
are excluded only from derived statistics and derived per-read outputs. The invalid
attempt remains listed in the exclusions. Numbers reconstructed from raw attempts or
the historical population are labelled as such and are unchanged.

**Repository:** `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`
**Primary raw worktree:** `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\resource-local-carryover-sep14`
**Starting commit (campaign):** `390e7d87bec77a995471f8c15f841cf88ed2b8c0` (`bundle`, 2026-09-16)
**Observed worktree HEAD:** `0ee60b07aecd140861016a089bf35464366d85d8` (`fix: route parallel Golden output contract`); main-tree HEAD `a36d1f1b1e4a6b1a211d569fd2b4d5d29fd30211`
**Resulting commit:** none — this report and the pre-existing canonical corpus are left uncommitted (`reports/golden_sickness_forensic_2026-09-17/` is untracked; no commit was created by this pass).

**Primary canonical inputs (`reports/golden_sickness_forensic_2026-09-17/`):**
`per_request.json`, `per_request.csv`, `per_read.csv`, `onset.csv`, `counts.json`,
`derived_counts.json`, `derived_counts.csv`, `derived_conditional.json`,
`derived_onset.json`, `derived_transport_decomposition.json/.csv`,
`derived_time_ordering.json`, `derived_conditioning.json`,
`derived_resource_order.json`, `derived_concentration.json`,
`derived_stage_severity.json`, `derived_tests.json`, `derived_evidence_matrix.json`,
`exclusions.json`, `field_availability.csv`, `raw_artifact_index.csv`,
`source_hashes.json`, `provider_region_summary.json`, `threshold_summary.json/.csv`,
`dual_transport_decision_ledger.csv`, `derived_requests.json`, plots under `plots/`.
Canonical tool: `tools/analysis/golden_sickness_forensic.py`
(sha256 `269bd2aa5bc15062f39cc5cfc0b99bf977169b4d9f6197c753082ab9350489cc`);
derived tool: `tools/analysis/golden_sickness_derived.py`.

**Historical secondary inputs (root, must not be mixed with the dual corpus):**
`GOLDEN_HISTORICAL_RUNS_MASTER.csv/.json`, `GOLDEN_HISTORICAL_READS_MASTER.csv`,
`RAW_EVIDENCE_INDEX.csv`, `GOLDEN_EXPERIMENT_ARCHAEOLOGY.md`.

**Analysis commands actually used this pass (read-only):**
```text
python tools/analysis/golden_sickness_forensic.py \
  --corpus-root .slim/worktrees/resource-local-carryover-sep14 \
  --out reports/golden_sickness_forensic_2026-09-17      # canonical generation (pre-existing)
python tools/analysis/golden_sickness_derived.py         # derived generation (regenerated valid-only in the correction; all derived_* + DERIVED_ANALYSIS.md rewritten)
# this pass, independent reproduction (temp scripts outside the repo):
python C:\Users\parla\AppData\Local\Temp\opencode\repro.py       # counts, thresholds, per-read recompute
python C:\Users\parla\AppData\Local\Temp\opencode\cases.py       # pathological cases, onset, recovery
python C:\Users\parla\AppData\Local\Temp\opencode\rawinspect.py  # raw attempt JSON inspection
python C:\Users\parla\AppData\Local\Temp\opencode\e27raw.py      # E27 predicate failure raw check
```

**Raw-to-derived mapping (one line):** each `per_request.json` record is built from one
`raw/<n>_attempt_0.json` plus its sibling `_manifest.json`, `_summary.json`,
`*_attempt_0_events.json`, and `*.v2ctl-provenance.json`; `per_read.csv` is the
`golden_telemetry.stages[golden_clip_load|golden_unet_load].details.transport_stats.actual_source_events`
stream flattened per role; `onset.csv` is the same stream reduced per `(bundle, role)`;
`derived_*` are pure functions of the canonical outputs, never a raw reparse
(`derived_evidence_matrix.json.instructions`).

**Exclusions (2 of 143 bundles; `exclusions.json`):**
1. `golden_p1_parallel_dual_sham_252bc1b6bdd2440e_evidence_2026-09-16` — `raw_valid_label_but_computed_invalid`;
   failed check `no_output_warning`; retained attempt `golden-p1-0-9ceed22e46e8`
   (sham, GCP/us-east1, class NEITHER). **This attempt is excluded from every derived
   statistic below** (all derived denominators are `computed_valid=true` only) but is
   preserved in canonical `per_request.json` / `per_read.csv` and in this exclusion list.
2. `golden_p1_parallel_dual_sham_bab378e130d843ea_evidence_2026-09-16` — `raw_attempt_missing` (no `*_attempt_0.json`; 197 retained raw files are deploy logs/other-JSON).

**Population warning:** the inferential corpus below is the *current dual-transport
corpus, `computed_valid=true` rows only* — **141** requests (**55** sham / **86** split)
out of **142** retained attempts, with the one invalid sham above excluded. Canonical
corpus totals (`142` attempts, `88892` per-read rows) are stated where the audit record
itself is the subject. Historical master rows (`1,367` rows / `1,354` unique requests
across other worktrees, commits, profiles) are a **different population** and are
labelled comparable / partial / not-comparable in §9. They are never pooled into the
rates here.

---

## 1. Executive answer: A SOURCE and B LOCATION/CARRIER

Two candidate answers were tested:

**A. SOURCE (the read/source path is where the sick time is spent).** Confidence: **MODERATE.**
The excessive time is inside the positioned-read syscall seam. The read-syscall union
(`SOURCE_SYSCALL_UNION_BUSY_MS`) is ~70% of `clip_load_ms` (median syscall fraction of load
`0.7110` sham CLIP, `0.7032` split CLIP; `0.8885`/`0.8872` UNET), and `SOURCE_TOTAL_WALL_MS`
tracks it within ~2–4 ms median (`source_minus_syscall_ms` median `2.4489` ms CLIP sham,
`2.2724` split). The strongest single correlate of the severity score is `clip_max_preadv_ms`
(Spearman `0.8971`, permutation p `0.0002`, n=141 valid).

**B. LOCATION/CARRIER (a resource-local, request-scoped carrier transmits sickness from
CLIP to UNET).** Confidence: **LOW–MODERATE.** The directional signal exists
(P(UNET sick | CLIP sick) = `0.625` sham vs `0.167` split; UNET hard-sick `8/55` valid sham
vs `4/86` valid split, Fisher p `0.0609`, bootstrap diff 95% CI `[-0.2096, 0.0036]`), but it
is small-n, arm is imbalanced across provider/region, and after provider×region
standardization the CLIP-sick rates converge (sham `0.1040` vs split `0.0867`). It is a
real directional signal, not a decisive effect.

**Honest bottom line:** the corpus proves *where the wall time sits* (inside the read
syscall, on the CLIP→UNET golden load stages) and *that a same-resource arm shows more
UNET sickness than a switched-resource arm*. It **cannot** separate, from raw fields,
whether the syscall latency is generated at the remote source (volume/object store/kernel
read path) or at the local destination (page/allocation/copy into the pinned destination
buffer). The canonical schema has no field that splits one `preadv` into source service
time vs destination-side time.

### Conclusion C1 — the sick time is inside the read syscall, not in the surrounding stage
- **SUPPORTING EVIDENCE:** `SOURCE_SYSCALL_UNION_BUSY_MS ≈ SOURCE_TOTAL_WALL_MS`
  (median residual `2.4489` ms CLIP sham / `2.2724` split, `2.1399`/`1.8015` UNET);
  syscall fraction of `load_ms` median
  `0.7110`/`0.7032` (CLIP sham/split), `0.8885`/`0.8872` (UNET); in `BOTH_SICK` CLIP the
  syscall fraction median is `0.8344`/source fraction `0.8355`. `clip_max_preadv_ms` is the
  top severity correlate (`0.8971`, p `0.0002`, n=141). Raw attempt `0167b0745ad1` CLIP:
  `SOURCE_TOTAL_WALL_MS=5386.03`, `SOURCE_SYSCALL_UNION_BUSY_MS=5375.90`, `H2D_TOTAL_WALL_MS=5164.32`,
  max syscall 2627.66 ms with `physical_provenance=golden_serial._read_at`.
- **COUNTEREVIDENCE:** `load_ms - SOURCE_TOTAL_WALL_MS` is a large *unlabelled* residual
  (median `473.6` ms CLIP sham, `525.9` ms CLIP split), and the schema does not decompose it.
  The syscall seam wraps only one physical `os.preadv`; the syscall duration includes both
  source service and the copy into the caller's destination buffer, so "inside the syscall"
  is **not** the same as "at the source".
- **WHAT THIS PROVES:** the anomalous time is bounded by the read syscall seam, and the
  stage wall is dominated by that seam; no separate stage (restore, clip_forward, sampling,
  VAE) carries the spike.
- **WHAT THIS DOES NOT PROVE:** it does not locate the latency inside the syscall, and does
  not distinguish remote-source time from destination-write/copy time.

### Conclusion C2 — a request-local resource carrier may transmit CLIP→UNET sickness
- **SUPPORTING EVIDENCE:** arm-assigned resource relation is exactly the experiment
  (CLIP and VAE always on resource X; UNET on X in `sham`, on Y in `split`; X is chosen by
  SHA-256 of the request id so both arms are assignment-identical). UNET hard-sick
  `8/55` valid sham vs `4/86` valid split (Fisher p `0.0609`, bootstrap diff `-0.0989`, CI
  `[-0.2096, 0.0036]`); `both_sick` `5/55` vs `1/86` (Fisher p `0.0335`, CI
  `[-0.1636, -0.0066]`); P(UNET sick|CLIP sick) `0.625` vs `0.167`. The `split` Y resource
  is verified pristine before UNET in `86/86` valid split requests
  (`other_resource_before_unet_verified=True`, max source fills before UNET `0`,
  `assert_other_pristine` in
  `dual_transport_carryover.py:453-489`). All `141/141` valid requests (`142/142` canonical)
  prove `both_live_through_unet=True` and `arena_data_ptrs_distinct=True`.
- **COUNTEREVIDENCE:** arm is imbalanced across provider/region (e.g. `us-east1` is
  `33 valid sham / 22 valid split`, `eu-south-2` is `3/26`); raw CLIP-sick arm difference is
  not significant (Fisher `0.1590`). Standardized CLIP-sick rates converge (`0.1040` vs
  `0.0867`). The UNET conditional in `split` (`0.167`) rests on 1 joint-sick request.
  Provider/region are themselves confounded with arm.
- **WHAT THIS PROVES:** within this corpus, same-resource routing is associated with more
  UNET hard-sickness than switched-resource routing, and the split arm's fresh resource is
  objectively clean before UNET.
- **WHAT THIS DOES NOT PROVE:** causality, and it does not prove the carrier is the pinned
  arena vs page cache vs H2D stream — those are not separable in the canonical schema.

---

## 2. What the corpus PROVES (independently reproduced)

All headline counts below were independently recomputed this pass from
`per_request.csv` + `per_read.csv` (not read from `counts.json`), and match. Canonical
totals (all attempts) and the valid-only inferential population are stated separately;
every rate below uses `computed_valid=true` rows only.

- **143** dual evidence bundles present = **57** `_dual_sham_` + **86** `_dual_split_`.
- **142** attempts retained (one sham bundle has no `*_attempt_0.json`), **142** records
  (`all_attempts_n=142`).
- **141** computed-valid analysis rows: **55** SHAM / **86** SPLIT (`valid_n=141`;
  `counts.json`: sham attempts 56, computed_valid 55, raw_valid_label 56; split
  86/86/86). The single excluded invalid attempt is
  `golden-p1-0-9ceed22e46e8` (`no_output_warning`, class NEITHER).
- Exclusions: **2** (see header). `unclassified_arm=0`; `decision_files_inspected=121`,
  `parse_failures=0`; `raw_artifact_rows=31722`; canonical `per_read_rows=88892`
  (clip 34506 / unet 52540 / vae 1846); valid-only derived reads **88266**
  (clip 34263 / unet 52170 / vae 1833; the invalid attempt contributes 626 reads and is
  excluded); canonical `onset_rows=426`, valid-only `423` (282 clip+unet role rows
  reconciled); `field_paths=961`.
- **14 hard CLIP / 12 hard UNET** (frozen rule `max_preadv_ms >= 1000 OR load_ms >= 5000`),
  reproduced two ways: from `per_request` flags and by recomputing per-read maxima, reads
  identical in both (set equality `True`). Valid classes: BOTH_SICK **6**, CLIP_SICK_ONLY
  **8**, UNET_SICK_ONLY **6**, NEITHER **121** (canonical 142-attempt classes are
  BOTH_SICK 6 / CLIP 8 / UNET 6 / NEITHER 122; the invalid attempt is NEITHER, so the
  hard-sick headline 14/12 is unchanged).
- Corpus validity invariants (canonical, all 142 attempts): `true_cold=True 142/142`,
  `dnf=False 142/142`, `restore_count=1 142/142`, `single_use_enabled=True 142/142`,
  `gaps_count=0 142/142`, `manifest_gap_seconds=35.0 142/142`.
  Valid-only allocation/routing (computed_valid=true): CLIP arena `CREATED 141/141`,
  UNET arena `REUSED 55 / CREATED 86` (canonical 56/86), `arena_data_ptrs_distinct=True
  141/141`, `both_live_through_unet=True 141/141`,
  `other_resource_before_unet_verified=True 86/False 55` (canonical False 56).
- Read-stream integrity: `retry>0 = 0`, `short_read=False 88892/88892` (canonical),
  `error empty 88892/88892`, `duplicate_read_count=0`, `physical_provenance` constant
  `golden_serial._read_at`, duration recomputed from raw ns values matches CSV exactly
  (`duration_ms` mismatches = 0). Valid-only reconciliation: 0 role-read mismatches
  between the derived model and canonical per-read rows, 0 onset read-count mismatches.
- Syscall ordering (valid-only): `read_seq` vs `syscall_enter_monotonic_ns` inversions =
  **0 / 87843** adjacent pairs across 423 request-role groups (canonical 0 / 88466 across
  426).

**Every conclusion in this report that uses the above carries the four-part
SUPPORTING/COUNTER/WHAT-PROVES/WHAT-DOES-NOT block inline; §1 does this for C1/C2, and
later sections do it for their main conclusions.**

---

## 3. What is STRONGLY SUGGESTED

- **Stage asymmetry:** CLIP load is the dominant driver; `clip_load_ms` correlates with
  severity at `0.8370` (p `0.0002`, n=141) while `unet_load_ms` is `0.5196`;
  `clip_max_preadv_ms` `0.8971` vs `unet_max_preadv_ms` `0.3825`. Cross-role
  `clip_load_ms ↔ unet_load_ms` `0.7193` suggests a shared request-level factor in
  addition to role-specific spikes.
- **Transience:** every `>=500 ms` read episode clears before the final read
  (`strongest_residual_cases=[]`); all sick reads are clustered episodes, not a permanently
  slow tail. 0 read-sequence residual cases; the only "residual" sickness is
  `load_ms >= 5000` with reads `< 1000` in 2 split/sham UNET cases (below).
- **Provider/region concentration (valid-only):** GCP `us-east1` carries most sickness
  (CLIP sick `10/55`, UNET sick `9/55`, both `5`); AWS contributes CLIP sickness
  (`3/48`) but zero UNET hard-sickness. `us-east-2` has CLIP sick `2/14`, `us-west1`
  `1/10` (1 UNET), `eu-south-2` `1/29`, `us-west4` `0/2` CLIP but `1/2` UNET.
- **Severity scale is continuous, not binary:** the severity score (log-style composite)
  has overall median `4.3174`, p75 `4.6446` (n=141); all 14 CLIP-sick and 12 UNET-sick
  requests sit above p75, but 15 `NEITHER` requests are also above p75 — the hard
  threshold is a discretization of a continuous tail.

### Conclusion C3 — CLIP is the primary carrier stage and the tail is transient
- **SUPPORTING EVIDENCE:** stage correlations above; `clip_forward_total_ms` only `0.4125`
  and `restore_total_ms` `0.4800`, `sampling` `0.3189`; recovery classes show
  `single_episode` 5 (sham CLIP) / 3 (sham UNET) / 1 (split CLIP) / 1 (split UNET) at T=500.
- **COUNTEREVIDENCE:** `unet_load_ms` still correlates at `0.5196`; 6 requests are
  UNET_SICK_ONLY with healthy CLIP; `clip_max_vs_unet_max` only `0.4134`, so CLIP and UNET
  spikes are not the same event.
- **WHAT THIS PROVES:** the CLIP stage is the most sensitive and most correlated detector of
  the sickness, and spikes are episodic rather than sustained.
- **WHAT THIS DOES NOT PROVE:** it does not prove CLIP *causes* UNET sickness; the shared
  request-level factor (host, container, region) is an alternative explanation for the
  cross-role correlation.

---

## 4. What is RULED OUT or WEAKENED

- **RULED OUT — short reads / retries / read errors:** `short_read 0/88892`,
  `retry_number>0 = 0`, `error` empty for every read; `duplicate_read_count=0`; read
  destination correspondence validates in-record (recomputation mismatch 0). The sickness
  is not retry storms, partial reads, or EIO.
- **RULED OUT — worker/producer imbalance inside the fixed 4-way split:** producer count is
  constant `4.0` for every request-role; producer HHI is constant `0.250013` (CLIP) /
  `0.250007` (UNET); top share constant `0.2510`/`0.2514`; per-producer read counts in the
  inspected raw attempt are `60/61/61/61` (CLIP) — near-perfect balance. Sickness is not a
  hot producer.
- **RULED OUT — resource A/B side or split direction:** CLIP resource A `79` valid requests
  (8 CLIP-sick / 8 UNET-sick) vs B `62` (6/4); direction A→B `45` (UNET-sick 3, rate 0.0667)
  vs B→A `41` (1, 0.0244), Fisher p `0.6177`. No side/direction effect.
- **RULED OUT — arm effect on CLIP sickness:** crude valid sham `8/55` vs split `6/86`,
  Fisher p `0.1590`, bootstrap diff `-0.0757` CI `[-0.1899, 0.0320]`. The CLIP stage is not
  arm-dependent at conventional levels.
- **RULED OUT — restore count / coldness / DNF / gaps / snapshot gaps as the mechanism:**
  all 141 valid requests (`142/142` canonical) are `true_cold`, `restore_count=1`,
  `dnf=False`, `gaps_count=0`, `manifest_gap_seconds=35.0` constant. `restore_total_ms` is
  higher in sick classes (UNET_SICK_ONLY median `1837.4` vs NEITHER `849.6`) but is a
  weak-moderate correlate (`0.4800`) and is not a discriminating constant.
- **WEAKENED — pure remote-source-only explanation:** if the sickness were purely a
  property of the source files, switching the UNET destination resource should not reduce
  UNET sickness; yet UNET hard-sick is `8/55` valid sham vs `4/86` valid split. This is a
  directional weakening, not a refutation (confounded, small n).
- **WEAKENED — pure page-cache explanation:** the page cache is shared by both arms, so a
  purely global page-cache mechanism predicts equal carryover in both arms; the observed
  conditional difference weakens (does not kill) it.
- **WEAKENED — O_DIRECT-specific mechanism:** the current dual corpus runs the static-E27
  instrumented `os.preadv` path (`golden_serial._read_at`), not the O_DIRECT shadow path
  (that is a separate 18-row historical derived table).
- **UNRESOLVED / NOT RULED OUT — CPU fault/context-switch/scheduler facts are absent:**
  the canonical corpus contains only two diagnostic leaves, both RSS
  (`snapshot_manifest.process_rss_bytes` = `5106581504`, `snapshot_manifest_restore...` =
  `1247105024`), and the raw attempt's `clip_page_faults` is an **empty dict `{}`**. There
  are no per-worker page-fault, `nvcsw`/`nivcsw`, CPU-tick, `utime`/`stime`, or cgroup
  throttle counters in the retained conflict. Any theory requiring those facts is
  untestable here (see §11).

### Conclusion C4 — read-integrity, producer-balance, and side/direction explanations are dead
- **SUPPORTING EVIDENCE:** counts above (0 short/retry/error/duplicate; producer HHI
  0.250 constant; direction Fisher `0.6177`).
- **COUNTEREVIDENCE:** none found in the corpus; the only caveat is that destination
  `slot_index` is schema-missing, so *slot-level* imbalance cannot be tested.
- **WHAT THIS PROVES:** the mechanism is not in the read-integrity/ownership layer that is
  instrumented, and not in producer assignment or A/B side.
- **WHAT THIS DOES NOT PROVE:** it does not prove balance at the OS scheduler level nor at
  the destination-slot level (no data).

---

## 5. Exact onset: BORN_SICK vs BECOMES_SICK

Frozen onset definition (`derived_onset.json.definitions`): a role is `born_sick` at
threshold T when the first read sequence index with `duration_ms >= T` is `<= 1`;
`becomes_sick` when it is `> 1`. `first_ge_*_seq` is the index of the first qualifying read.

**Request-level counts (denominator = `computed_valid=true` requests with >=1 read for the
role; valid sham n=55, valid split n=86):**

| T (ms) | sham clip born/becomes | sham unet born/becomes | split clip born/becomes | split unet born/becomes |
|---|---|---|---|---|
| 250 | 9 / 11 | 6 / 12 | 1 / 14 | 2 / 4 |
| 500 | **4 / 11** | **5 / 6** | **1 / 6** | **0 / 6** |
| 1000 | **1 / 7** | **3 / 4** | **1 / 5** | **0 / 3** |

(Denominators: at T=500/1000 the "neither" counts are sham clip 40/47, sham unet 44/48,
split clip 79/80, split unet 80/83 — from `derived_onset.json.per_role_by_arm`, valid-only.
The canonical 142-attempt denominators were 41/48, 45/49, 79/80, 80/83.) Note the
250 ms band is noisier: split UNET has 2 born-sick at 250 but 0 at 500/1000, so the clean
"split never starts sick" statement is threshold-specific and strongest at ≥500 ms.

**The exact onset split:** CLIP is almost always *becomes-sick*, not born-sick — only one
sham CLIP (`golden-p1-0-20ffd3348a64`, first `>=1000` at seq 1) and one split CLIP
(`golden-p1-0-f5508707fe42`, seq 1) are born-sick at T=1000. UNET is *born-sick more often
than CLIP in sham* (`3/7` at 1000: `053b292b0476` seq 1, `0b56ab29f792` seq 0,
`49cd54fb17f9` seq 1) and is **never born-sick in split at ≥500 ms** (`0/3` at T=1000 and `0/6` at T=500; all
qualifying reads are becomes-sick or load-only), though at the noisier 250 ms band split
UNET shows `2` born-sick. This is the single cleanest asymmetry in the
corpus: *a freshly created switched resource never starts sick; a reused same-resource arena
does, sometimes, at the first UNET read.*

**First qualifying read sequence per pathological case (T=1000):**

| request | arm | provider/region | class | clip first1000 seq | unet first1000 seq |
|---|---|---|---|---|---|
| golden-p1-0-0167b0745ad1 | sham | GCP/us-east1 | BOTH | 56 | 13 |
| golden-p1-0-126cf4cbe4a8 | sham | GCP/us-east1 | CLIP_ONLY | 99 | — |
| golden-p1-0-7fdd4ac76369 | sham | GCP/us-east1 | BOTH | 43 | 32 |
| golden-p1-0-989a779e3893 | sham | UNSPEC/us-central1 | UNET_ONLY | — | — (max 860, load_only) |
| golden-p1-0-053b292b0476 | sham | GCP/us-east1 | BOTH | 2 | 1 |
| golden-p1-0-bca55ee4d4f5 | sham | AWS/us-east-2 | CLIP_ONLY | 20 | — |
| golden-p1-0-49cd54fb17f9 | sham | GCP/us-east1 | BOTH | 19 | 1 |
| golden-p1-0-20ffd3348a64 | sham | AWS/us-east-2 | CLIP_ONLY | 1 | — |
| golden-p1-0-5ae9efa67e60 | sham | GCP/us-east1 | UNET_ONLY | — | 3 |
| golden-p1-0-907303a11d5c | sham | GCP/us-east1 | UNET_ONLY | — | 6 |
| golden-p1-0-0b56ab29f792 | sham | GCP/us-east1 | BOTH | 2 | 0 |
| golden-p1-0-b451904156c4 | split | AWS/eu-south-2 | CLIP_ONLY | 62 | — |
| golden-p1-0-51fd5230eeee | split | GCP/us-east1 | CLIP_ONLY | 175 | — |
| golden-p1-0-3826114a6c00 | split | GCP/us-east1 | UNET_ONLY | — | — (max 997, load_only) |
| golden-p1-0-5f9470cfb95a | split | GCP/us-east1 | UNET_ONLY | — | 177 |
| golden-p1-0-cf4f240d3d6c | split | GCP/us-west4 | UNET_ONLY | — | 3 |
| golden-p1-0-f5508707fe42 | split | GCP/us-east1 | CLIP_ONLY | 1 | — |
| golden-p1-0-f18b437f0d56 | split | GCP/us-west1 | BOTH | 199 | 41 |
| golden-p1-0-1742b7c9b560 | split | GCP/us-east1 | CLIP_ONLY | 46 | — |
| golden-p1-0-d8df15190c1e | split | GCP/us-east1 | CLIP_ONLY | 12 | — |

Trigger classes valid-only (`onset.csv`, computed_valid requests): CLIP
`both=6 / preadv_only=8 / none=127`; UNET `both=2 / load_only=2 / preadv_only=8 / none=129`
(canonical 142-attempt values: CLIP none=128; UNET none=130).

### Conclusion C5 — at ≥500 ms, split UNET never starts sick; sham UNET sometimes does
- **SUPPORTING EVIDENCE:** born/becomes table; `0/6` and `0/3` born in split UNET at
  T=500/1000; `5/6` born at 500 and `3/7` at 1000 in sham UNET; the split Y resource is
  independently proven pristine before UNET in all 86 requests.
- **COUNTEREVIDENCE:** totals are tiny (born counts 0–5); "born" uses `seq <= 1`, and a
  read can be slow for host-wide reasons unrelated to resource reuse.
- **WHAT THIS PROVES:** if a reused arena carries a transient state, it manifests at the
  *start* of the next (UNET) load, which is exactly what "born-sick" means; a fresh arena
  does not.
- **WHAT THIS DOES NOT PROVE:** it does not prove the arena (as opposed to global page
  cache, host memory pressure, or timing within the request) is the carried state.

---

## 6. Locality

Localisation claims available in the corpus, from strongest to weakest:

1. **Stage-local:** the spike is in `golden_clip_load` (and secondarily `golden_unet_load`);
   `golden_restore`, `golden_clip_forward`, `golden_sampler_prepare`, `golden_sampling`,
   `golden_vae_decode` do not carry it (correlations `0.27–0.41` vs `0.84`).
2. **Seam-local:** inside the `actual_source_events` stream, i.e. the per-`preadv` seam
   (`golden_serial._read_at`, `syscall_enter/exit_monotonic_ns`). Syscall order is
   internally consistent (0/87843 valid-only inversions; canonical 0/88466).
3. **Request-local:** the composite severity correlates with request-level fields
   (`duration_ms 0.3654`, `restore_total_ms 0.4800`) but the shared cross-role correlation
   (`clip_load ↔ unet_load 0.7193`) also points to a request/host-level co-factor.
4. **NOT resource-side-local:** A/B side and A→B vs B→A direction show no effect
   (Fisher `0.6177`), so it is not one arena instance being physically bad.
5. **NOT worker-local / region-local (untestable at read level):**
   `region_id == producer_id` for **88892/88892** canonical rows (86433 valid-only clip+unet
   reads), and `slot_index` is empty for **88892/88892** canonical rows. Worker and region
   attribution are *not separable* in per-read data; destination offsets are near-fully
   distinct per request-role (median distinct = read count: 243 CLIP / 370 UNET).
6. **Destination-local at the offset level:** every request-role has a distinct destination
   offset range; there is no shared destination-offset collision across requests.

### Conclusion C6 — locality is proven at stage/seam/request level, unproven at worker/slot/region level
- **SUPPORTING EVIDENCE:** stage correlations, syscall ordering, constant producer balance,
  `slot_index` 100% missing, `region_id==producer_id` 100%.
- **COUNTEREVIDENCE:** none contradicting; the absence of slot/region variation is a schema
  limitation, not positive proof of uniformity.
- **WHAT THIS PROVES:** the only defensible localisation is to the read seam and the
  request/role stage, plus the arm-level resource relation.
- **WHAT THIS DOES NOT PROVE:** any per-worker, per-slot, per-region, or per-offset
  attribution. Any report claiming a hot worker/slot from this corpus is unsupported.

---

## 7. Time / regime

- **Dispatch ordering:** 141/141 valid requests have `timestamps.dispatch_unix_ms`
  (canonical 142/142).
- **Inter-request gap (ms):** n=140, min `50`, q1 `19738`, median `46594.5`, q3 `62681`,
  p90 `96957.7`, p95 `236537.65`, p99 `945735.35`, max `8026986`, mean `127342.95`.
- **Clusters** (>600000 ms gap, valid-only): **5** clusters; sick rate per cluster
  `0.20 / 0.09375 / 0.0 / 0.25 / 0.142857`; spans 0–2.09e6 ms. The largest cluster
  (n=64, sham 30 / split 34) has sick rate `0.09375`; the split-only cluster n=20 has
  `0.25`.
- **No regime field:** `timestamps.gap_before` is present in **0/141** valid requests
  (canonical `0/142`); `manifest_gap_seconds` is constant `35.0` in all 141 valid requests,
  `gaps_count=0`.
- **Autocorrelation:** sickness-indicator lag-1 Pearson `0.0170` (descriptive only) — no
  evidence of temporal clustering of sickness at adjacent dispatches.
- **Intra-request ordering:** CLIP reads always begin before UNET reads (pipeline order);
  for the 6 BOTH_SICK requests the CLIP first-`>=1000` read is earlier than UNET's, but by
  5–10 s because the stages are sequential, so intra-request role ordering is dominated by
  pipeline order, not a beacon.

### Conclusion C7 — no demonstrated time-of-run regime; clusters are scheduling artifacts of gaps
- **SUPPORTING EVIDENCE:** lag-1 `0.0170`; missing `gap_before`; constant manifest gap;
  all requests cold/single-use.
- **COUNTEREVIDENCE:** non-trivial per-cluster sick-rate spread (0 to 0.25) with tiny
  cluster n (1–64), so an orchestration/regime effect cannot be excluded.
- **WHAT THIS PROVES:** there is no in-corpus evidence that sickness is a function of
  wall-clock period, cooldown, or adjacency.
- **WHAT THIS DOES NOT PROVE:** cluster-level host/hardware identity is not retained, so
  "different cluster, different host" remains an untested confounder.

---

## 8. Source / offset / worker / slot, and allocation A/B

- **Source:** all reads flow through `golden_serial._read_at` with
  `physical_provenance=golden_serial._read_at` (88892/88892 canonical). Over valid-only
  rows, `E27_SOURCE_MECHANISM_PROVEN` is `YES` for UNET `141/141` and for CLIP `140/141`
  (canonical `142/142`, `141/142`); the one CLIP `NO`
  (`golden-p1-0-716326690293`, sham, GCP/us-central1, healthy) fails **20 predicates** in the
  raw attempt (`fixed_contiguous_regions`, `fixed_ownership`, `monotonic_reads`,
  `coverage_exact`, `read_destination_correspondence`, `gaps`,
  `actual_syscall_qd_telemetry_complete`, `max_actual_source_inflight`,
  `source_total_wall_present`, `qd_occupancy_present`, `h2d_reconciliation_complete`,
  `source_h2d_bytes_reconciled`, `quiescence_checkpoint_history`, `checkpoint_fields`,
  `bind_checkpoint`, `source_completion_checkpoint`, `final_completion_checkpoint`,
  `checkpoint_order`, `quiescence`, `required_evidence_persisted`) even though that attempt's
  raw `actual_source` values look normal (`SOURCE_TOTAL_WALL_MS=1313.67`,
  `max_actual_source_inflight=4`, `quiescence=true`). This is an evidence-extraction
  inconsistency, not a demonstrated runtime fault; it means the E27 "proven" flag is
  **not 100% reliable** and the failing request must not be over-interpreted.
- **Offsets:** source and destination offsets are fully populated and distinct per
  request-role; no cross-request destination collisions. `source_offset`/`destination_offset`
  are absolute within the mapped model file/arena; the residual
  `load_ms - SOURCE_TOTAL_WALL_MS` is not decomposed (explicit unknown).
- **Worker:** `producer_count=4` constant; `producer_balance.read_counts = 60/61/61/61`
  (CLIP) in the inspected attempt; valid-only `producer_alternations` medians are
  CLIP `238` sham / `239` split and UNET `363` sham / `366` split (range ~238–366); the only
  worker-ish severity signal is a **negative** correlation of `producer_alternations` with
  severity (CLIP `-0.4905`, UNET `-0.3407`) — more producer switching ↔ less severe, likely
  a proxy, not a cause.
- **Slot:** `slot_index` is empty/null for **88892/88892** per-read rows and null in every
  raw `blocks[].slot_index` as well (the runtime hardcodes `"slot_index": None` at
  `golden_serial.py:6074`); `slot_count=8`, `slot_bytes=33554432` constant. **There is no
  slot-level evidence in this corpus.**
- **Region:** `region_id` is set to `producer_id` at construction
  (`golden_serial.py:6002`, `{"producer_id": producer_id, "region_id": producer_id, ...}`),
  and `region_id == producer_id` for 88892/88892 rows. Region and worker are the same
  number; **region effects are not separable**.
- **Allocation A/B (valid-only):** CLIP resource is deterministic SHA-256(request_id) → A
  or B (`dual_transport_carryover.py:104-111`); both arms use the same assignment. In the
  141 valid requests CLIP arena is `CREATED` in all 141; UNET arena is `REUSED` exactly in
  the 55 valid sham and `CREATED` exactly in the 86 valid split
  (`derived_resource_order.json`; canonical 142 and 56/86). Valid A count 79 (sham 34 /
  split 45), B count 62 (sham 21 / split 41). Direction: A→B 45, B→A 41, no UNET-sick
  difference (Fisher `0.6177`).

### Conclusion C8 — the transport resources are provably distinct and correctly routed; slot/region attribution is impossible from this schema
- **SUPPORTING EVIDENCE:** `arena_data_ptrs_distinct=True`, `arena_overlap=False`,
  stream/event/pool distinct in raw identity; `created_vs_reused` exactly matches the arm
  split; direction null result.
- **COUNTEREVIDENCE:** none; the one E27 `NO` clip is a telemetry-extraction inconsistency.
- **WHAT THIS PROVES:** the experiment routed exactly as designed (sham reuses, split
  creates), and there is no A/B instance effect.
- **WHAT THIS DOES NOT PROVE:** nothing about slot- or region-level behaviour, because
  neither exists as independent data.

---

## 9. Historical evidence (labelled comparable / partial / not-comparable)

### 9a. The five historical code paths inspected in the worktree
`comfymodal_runtime/` under `resource-local-carryover-sep14`:

| Script | Lines | Role | Comparability |
|---|---|---|---|
| `golden_serial.py` | 15,007 | The single-resource Golden control plane; owns `_read_at` (line 5083), `ActualSourceTelemetry`, the `os.preadv` seam, and the `blocks` record builder where `slot_index=None` is hardcoded | **Comparable** control-path source: this is the exact read seam captured by the dual corpus |
| `golden_parallel.py` | 449 | P1 parallel control plane; arms the dual experiment at lines 157–177 (`_activate_dual_transport`), asserts CLIP quiescence and `mark_unet_complete` | **Comparable**: defines the two arms under study |
| `golden_qd_transport.py` | 186,871 B | `GoldenTransferResources` (the arena/slot/H2D object) and syscall/H2D reconciliation | **Comparable** as the resource object; QD geometry itself varies across history |
| `e27_source_mechanism.py` | 1,196 | Stdlib evaluator for source/H2D mechanism provenance (`SourceReadEvent`, predicate set) | **Partial**: evaluator is comparable, but its input normalization can fail (the 1/142 CLIP `NO`) |
| `golden_io_process_v2.py` | 7,867 | Two-process C0 shared-backing reader (CUDA-sterile child) | **Not comparable**: the dual corpus explicitly fails closed on C0/loader/V2 process-shared (`dual_transport_carryover.py:88-101`); this is the strongest *clean-cohort* historical architecture, not the current one |

### 9b. Master / raw historical inventory
`GOLDEN_HISTORICAL_RUNS_MASTER.json.metadata.coverage`: rows_total **1367**
(raw_attempt 1312, c0_fd_ready 15, sep14_golden_standard 27, v2ctl_manifest_only 13);
unique requests from attempts **1354**; attempt files discovered **1519**; v2ctl run
manifests **1074**; evidence-index rows **6300**; read rows **18**. Scanned scopes: main
tree, `golden-io-v2`, `golden-p4-8-durability`, `golden-sep14-repro`, `odirect-shadow-sep14`,
`rx3`. Named cohorts: **Sep-14 Golden Standard 27 runs** (profile
`golden_p1_parallel_io_v2_c0_persistent_fds_preadv_sickness_v2`) and **C0-FD-ready 15 runs**
(profile `golden_p1_parallel_io_v2_c0_persistent_fds`, deployed commit `1784e640…`).

| Historical cohort | n | Status | Comparable to current dual corpus? |
|---|---|---|---|
| Sep-14 Golden Standard | 27 | 27/27 valid + true-cold + exact SHA; request wall 16.390–33.540 s (median 17.729 s) | **Partial**: same Golden contract and output SHA class, but C0 shared-arena/QD2-128 architecture and no dual arm. Not a rate comparison. |
| C0-FD-ready confirmations | 15 | 15/15 valid + true-cold + exact SHA; FRR ~9.95–35.32 s | **Not comparable**: old receipt `1784e640…`, 128 MiB slots, QD2/128, process/thread topology differs. |
| Sep-14 V1/V2 reproduction | 30 | 30/30 "no read ≥ 5 s" but **all observed SHA ≠ expected SHA** | **Not comparable**: correctness failure and different clean definition (≥5 s, not 250/500/1000/2000). |
| O_DIRECT-shadow per-read table | 18 read rows | derived-only event table (`SHARED_STALL`, `DIRECT_ESCAPE`, `DIRECT_ERROR`) | **Partial/derived**: not a raw per-read capture; only source of any O_DIRECT evidence. |
| E37 clean-lane QD4 | 1 | source wall 1,043.5 ms, H2D host 127.4 ms; residual reconciliation exceeded tolerance | **Not comparable**: n=1, not a full request. |
| post-eager-start private split | 8 | 8/8 UNET < 1.9 s in reported subset; separate 66.4 s outlier | **Partial**: diagnostic association only. |

### Conclusion C9 — history identifies a candidate "clean" architecture but not the mechanism
- **SUPPORTING EVIDENCE:** archaeology text + master metadata; the historical timeline
  places C0 shared-pinned + persistent FDs + QD2/128 as the shape of the cleanest exact-SHA
  cohorts; the 18-row O_DIRECT table shows buffered stalls (`SHARED_STALL`) co-exist with
  direct escapes, consistent with a destination/shared-buffer component.
- **COUNTEREVIDENCE:** the historical clean cohorts do not include the dual arms, use
  different source/deployment identities, and in one case (V1/V2 30) fail canonical output
  SHA; the O_DIRECT table is derived, not raw.
- **WHAT THIS PROVES:** the sickness is not novel to the dual experiment; the current
  corpus is the first that isolates same-vs-switched resource localisation.
- **WHAT THIS DOES NOT PROVE:** that C0/QD2/128/FD-reuse causes the clean behavior — the
  archaeology report explicitly says FD reuse was neutral/slightly worse and QD4/64
  worsened medians.

### 9c. Extended historical artifact-family census (offline-only supplement)

This subsection is an offline inventory only. It adds no request, deploy, or network
call, changes no runtime/source/test file, and **does not alter any current-corpus
number or conclusion in §1–§8, §10–§14**. It covers the older artifact families that
§9a–§9b did not enumerate, each classified against the current dual corpus
(`computed_valid=true`, 141 requests, static-E27 in-process `golden_serial._read_at`
`os.preadv`, §1–§8). Evidence tier is marked **RAW** (preserved attempt telemetry,
bundle, log, or code) or **DERIVED** (an analysis/report built from raw artifacts).
Comparability: **comparable** = same Golden read seam/contract usable as a control;
**partial** = mechanism-relevant but a different profile/commit/architecture, so it
must not be pooled into a rate; **not-comparable** = different architecture/population.

| Family | Representative paths | Tier | Comparable to current dual corpus? |
|---|---|---|---|
| Original Golden serial/parallel | `comfymodal_runtime/golden_serial.py`, `golden_parallel.py`, `golden_qd_transport.py` | RAW code | **Comparable** as the exact seam; serial P4 baseline partial |
| C0 clustered preadv diagnostics + process/thread | `.slim/worktrees/golden-io-v2/REPORT_C0_PREADV_DEFINITIVE_ATTRIBUTION.md`, `REPORT_C0_PREADV_SICK_RUNS_TRIPWIRES.md`, `REPORT_C0_PREADV_DIRECT_VOLUME_V1_PROBE.md`, `comfymodal_runtime/c0_preadv_controls.json`, `tools/c0_preadv_control_manifest.py` | RAW bundles + DERIVED reports | **Not-comparable** as rates (different profile/app/commit, C0 child explicitly failed-closed by `dual_transport_carryover.py:88-101`); **partial** as mechanism |
| Source-only ceiling/oracle | `comfymodal_runtime/unet_salvage_probe.py`, `clip_fast_hydration.py`, `source_ceiling_oracle.py`, `e04_source_ceiling_modal.py`, `e16_source_io.py`, `e16_source_io_modal.py`; `V2_BATCH_E14_SOURCE_IO_BENCHMARK.md`, `V2_BATCH_E16_REMOTE_SOURCE_IO_PREFLIGHT.md`, `V2_BATCH_E16_RUN1.json`/`RUN2.json` | RAW code + RAW runs + DERIVED report | **Not-comparable** as rates (probe-local/different placement); **partial** for source-vs-destination |
| QD/E27 | `comfymodal_runtime/e27_source_mechanism.py`, `_e27_clip_qd_evidence.json`, `_e27_unet_qd_evidence.json`, `_e27_run1_out.txt`/`run2_out.txt`, `_e27_fastsafe_*_out.txt`, `_e27_ro_probe*.txt`; `RX7_E27_CONTIGUOUS_QD4_SOURCE_SCHEDULING_AB_REPORT_2026-09-01.md`, `RX7A_STATIC_E27_INTEGRATION_REPORT_2026-09-01.md`, `V2_BATCH_E27_FIVE_TARGET_CRITICAL_PATH_FORENSICS.md` | RAW + DERIVED | **Partial** (static-E27 is the current path's ancestor; RX7 cohort is different profile/commit/QD) |
| PRETOUCH vs control | `.slim/worktrees/pretouch-ab-control-sep14/`, `.slim/worktrees/pretouch-ab-pretouch-sep14/` (`comfymodal_runtime/golden_pretouch.py`, `c4_armA_*.log`); `.v2ctl/evidence/pretouch_ab_derived_20260916.csv`, `pretouch_corrected_derived_20260916.csv` | RAW code/logs + DERIVED CSV | **Not-comparable** as rates (serial Golden v1 A/B, not dual); **partial** as a direct fault/pretouch negative |
| Restored-page / physical-page / fresh-anonymous / copy | `V2_UNET_BACKING_AB_REPORT.md`, `V2_PROVIDER_AND_PAGE_PATH_FINAL_REPORT.md`, `V2_FINAL_OWNERSHIP_AND_REHOMING_REPORT.md`, `V2_SNAPSHOT_ARCHITECTURE_AND_WORKING_SET_RESEARCH.md`, `V2_BATCH_B_SNAPSHOT_HYGIENE_AND_STAGE13_REPORT.md` | RAW in-container probes + DERIVED reports | **Not-comparable** (old snapshot/UNET-transfer path); **partial** mechanism |
| Minimal restore / startup / first-request | `GOLDEN_MINIMAL_RESTORE_IMPLEMENTATION_2026-09-11.md`, `GOLDEN_RESTORE_ARCHAEOLOGY_MINIMAL_REBUILD_AUDIT_2026-09-11.md`, `GOLDEN_RESTORE_AUDIT_RECONCILIATION_2026-09-11.md`, `K1_GOLDEN_RESTORE_QUIESCENCE_SEAM_RECOVERY_REPORT.md`, `E38O_INDEPENDENT_FULL_REPOSITORY_AUDIT.md` §6.3 | RAW code + DERIVED audits | **Partial** (minimal restore is a current-corpus default; restore is not the carrier) |
| FD lifecycle / cache / hot-range | `GOLDEN_EXPERIMENT_ARCHAEOLOGY.md` timeline, `comfymodal_runtime/c0_preadv_controls.json`, `tools/c0_preadv_control_manifest.py`, `V2_BATCH_C9_FASTSAFETENSORS_INTEGRATION_REPORT.md`, `V2_BATCH_C12_SAFETENSORS_LAYOUT_SHARDING_REPORT.md`, `V2_BATCH_C13_NATIVE_FAST_DISK_FORENSIC_AUDIT.md` | RAW code + DERIVED | **Partial**; no FD/cache/hot-range field exists in the canonical schema |
| Transport cleanup | `V2_BATCH_E6_POST_RESPONSE_GPU_CLEANUP.md`, `OC7_TEARDOWN_TIMING_COMPLETENESS_2026-08-25.md`, `RX6_GOLDEN_LOG_CLEANUP_AND_POST_RESULT_TAIL_REPORT_2026-08-31.md`, `E40_CANONICAL_RUNTIME_TRUTH_AND_CLEANUP_REPORT.md` | DERIVED audits | **Not-comparable** to the read seam; partial lifecycle context |
| CPU / getrusage / fault / context-switch / wchan / scheduling | `.slim/worktrees/golden-io-v2/EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md`, `.slim/worktrees/golden-io-v2/CHATGPT_ARCHAEOLOGY_AUDIT.md:47`, `.slim/deepwork/v2-cold-runs.md:112-141`, `E38L_INDEPENDENT_FULL_REPOSITORY_AUDIT.md:178` | RAW telemetry + DERIVED audits | **Not-comparable** as corpus; **partial** as a negative on fault/CPU theories |
| Same-source/destination natural comparisons | `V2_UNET_BACKING_AB_REPORT.md:59,68`, `V2_PROVIDER_AND_PAGE_PATH_FINAL_REPORT.md:51`, `V2_FINAL_OWNERSHIP_AND_REHOMING_REPORT.md:125-129`, `V2_BATCH_E16_REMOTE_SOURCE_IO_PREFLIGHT.md:140-148`, `E38L_INDEPENDENT_FULL_REPOSITORY_AUDIT.md:490` | RAW paired probes + DERIVED | **Not-comparable** as rates; **partial/strong** as mechanism |

**9c.1 Original Golden serial/parallel control plane.** The current dual corpus's raw seam
is `comfymodal_runtime/golden_serial.py` (15,007 lines; `_read_at` at line 5083), whose
`blocks` record builder hardcodes `"slot_index": None` at line 6074 and sets
`region_id = producer_id` at line 6002 — the two schema facts that make slot/region
attribution impossible in §8 and §13. `golden_parallel.py` (449 lines) arms the dual
experiment at lines 157–177 (`_activate_dual_transport`), and `golden_qd_transport.py`
owns `GoldenTransferResources` (§9a). These are the same files in the current
worktree, so this family is **comparable** as source, not as a separate dataset. The
older P4 serial baseline (`GOLDEN_EXPERIMENT_ARCHAEOLOGY.md:116`: five-run serial
22.4–88.9 s, non-cold) is **partial** and descriptive only — it predates the dual arm
and the true-cold contract.

**9c.2 C0 clustered `preadv` diagnostics and process/thread architecture.** This is the
historical family the current report's §4/T23/T34 reference without naming. Raw bundles
under `.slim/worktrees/golden-io-v2/artifacts/c0_preadv_definitive_attribution/` and
`.../c0_qd2_viztracer_healthy_sick/` back two derived reports. The tripwire catalog
`.slim/worktrees/golden-io-v2/REPORT_C0_PREADV_SICK_RUNS_TRIPWIRES.md` records profile
`golden_p1_parallel_io_v2_c0_persistent_fds_preadv_sickness_diag`, app
`batch-golden-c0-preadv-sickness`, selector `COMFYMODAL_GOLDEN_C0_PREADV_SICKNESS_DIAG=1`,
control geometry **QD2/128, 2 workers, 4×128 MiB SHM, persistent FDs**, a 500 ms
first-only tripwire, and two accepted confirm batches (5-run with 1 sick, 6-run with 3
sick); all four sick runs are `valid`, `true_cold`, output SHA `ab3c08a9…`. Sick run 1
(lines 14–31) is a **CLIP dual-outstanding D-state** stall: request
`golden-p1-0-2b96d861c2e3`, offset `134263584`, len `134217728`, worker `c0-read_1`
TID 54, fd 6, `st_dev 30 / st_ino 71`, `outstanding_count: 2`, `minflt/majflt 0/0`,
and **`wchan`/`syscall`/`schedstat` null**, with a 533.6 ms helper heartbeat gap.

`REPORT_C0_PREADV_DEFINITIVE_ATTRIBUTION.md` (derived table
`artifacts/c0_preadv_definitive_attribution/sick_preadv_table.csv`) analyzes the one
five-run batch with `run4_sick = golden-p1-0-6ce0aaf26128` (158,635.771 ms). Section 3–5:
158 reads = CLIP 61 + UNET 93 + VAE 4; **25 pathological (19 CLIP + 6 UNET ≥ 1000 ms)**;
worst CLIP `record 0`, offset `45856`, 21,151.119 ms; UNET max 1,907.112 ms. Across all
158 reads `ru_minflt`/`ru_majflt`/`ru_nvcsw`/`ru_nivcsw` deltas are **all zero** and
`schedstat` is null 158/158. Section 6: live sampler states are **D=62, S=1, R=1**
(TID 51 D=30, TID 52 D=32), and `wchan`/`syscall`/`schedstat`/`stack` are null in all 32
observer records. Section 7: model paths resolve to **overlay**, not FUSE
(`fstypes = [9p, cgroup, devpts, overlay, proc, sysfs, tmpfs]`). Section 8: SHM 100 %
resident in all four slots; `cachestat` unsupported, so "no refetch" is **unproven**.
Section 10 classifies the wall as a **below-guest `preadv`/backend wait** and explicitly
refuses to assign storage/Modal/gVisor/filesystem ownership; the C0 report's own
§13.5 scheduling attribution is **retracted** in its appended reconstruction (lines
335–361).

*What this proves:* the historical C0 architecture (CUDA-sterile child process, two
reader threads `c0-read_0`/`c0-read_1` on TIDs 51/52–54, 512 MiB shared-pinned arena,
4 slots, persistent FDs) is the clearest record that the pathology is **off-CPU D-state
inside the positioned read with zero page-fault deltas**. *What it does not prove:* any
owner (source vs destination vs platform), and it does not transfer as a rate: the
current dual corpus runs the static-E27 in-process path and **fails closed on
C0/loader/V2 process-shared** (`dual_transport_carryover.py:88-101`, §9a). It also
**contradicts** the page-fault branch of T16/T36 for that architecture, while leaving
T1/T2/T3/T7/T8/T9 unresolved — the same posture this report reaches from the dual
corpus. The offsets pathological in the earlier batch6 request (`5905625888`,
`1879097120`, `11945426720`) are normal in `run4_sick` (§4), so the pathology is not
offset-specific.

**9c.3 Source-only ceiling/oracle.** `comfymodal_runtime/unet_salvage_probe.py`
(1,661 lines; contract lines 1–27) is a measurement-only probe of three host costs:
meta-construct/`to_empty`, `cudaHostRegister` of safetensors mmap ranges, and `os.preadv`
directly into preallocated pinned buffers (constants `_PREADV_*`/`_REG_*` lines 49–64).
`comfymodal_runtime/clip_fast_hydration.py` (1,884 lines) defines the generic hydration
modes A–F (lines 13–34), notes `fastsafetensors` tensors are zero-copy views over an
internal GPU buffer (lines 22–27), and records `DEFAULT_QD_BASE` as a **local NVMe QD8
preadv = 40.72 GB/s** probe value that "MUST be re-tuned against remote volume storage"
(lines 48–51). `comfymodal_runtime/source_ceiling_oracle.py` (1,407 lines; QD/block
constants and `SOURCE_ONLY_ARM` lines 24–38) is driven by
`e04_source_ceiling_modal.py` (74 lines; app `sept-unetclip-04-source-ceiling-oracle`,
CPU-only image, read-only volume, declared CPU 12, lines 12–18, 42–74).

The only raw-backed measured member is E16: `V2_BATCH_E16_REMOTE_SOURCE_IO_PREFLIGHT.md`
with preserved `V2_BATCH_E16_RUN1.json`/`RUN2.json`, harness `e16_source_io.py`, endpoint
`e16_source_io_modal.py`. Two requests used the same plan/image/source but **different
placements** (RUN1 AWS us-east-2, RUN2 GCP us-east1) — the report itself calls this out
and ends `RESULT = INCONCLUSIVE` with `cold_unknown` (lines 94, 181). Raw results:
CLIP 8,044,982,048 B, UNET 12,309,866,400 B; Linux `preadv` into pinned slabs proven
with `DIRECT_SOURCE_TO_PINNED_COPY_BYTES = 0` (lines 63–76); source-order wins on
RUN1 CLIP (−30.6 %) but loses on RUN2 CLIP (+9.4 %) and reverses per model on UNET
(+10.5 % / −23.1 %) (lines 100–118); MMAP sits in the same band; `/tmp` staging never
wins after copy-in; pageable vs pinned fill differs by −0.818 % mean (lines 141–148).
`V2_BATCH_E14_SOURCE_IO_BENCHMARK.md` is a **local 20-byte fixture** explicitly labelled
"not decision-useful" (lines 39–51) — it establishes the harness and cache labels
(`cold_unknown`/`process_cold`/`page_cache_warm`, lines 53–57), not a throughput.

*What this proves:* the direct positioned-read-into-pinned mechanism is real and has no
hidden second copy, and pinned vs pageable fill is not a material penalty (E16). *What it
does not prove:* any production rate — the 40–45 GB/s E27/E04 probe class is contradicted
as source-only/page-cache/overlap-local by `E38_01_INDEPENDENT_FULL_REPOSITORY_AUDIT.md:37,196,615`
and `GOLDEN_EXPERIMENT_ARCHAEOLOGY.md:115,165` (integrated CLIP QD4 ≈ 2.6–2.9 s, clean
lane 1.04 s). E14 is not usable as evidence at all. No family here decomposes one
`preadv` into source vs destination.

**9c.4 QD / E27.** The evaluator is `comfymodal_runtime/e27_source_mechanism.py`
(1,196 lines; `ActualSourceTelemetry`, `SourceReadEvent`, `mark_physical_syscall_provenance`
at line 166, the predicate set behind `E27_SOURCE_MECHANISM_PROVEN`). Raw E27 evidence
survives as `_e27_clip_qd_evidence.json`, `_e27_unet_qd_evidence.json`,
`_e27_run1_out.txt`/`run2_out.txt`, `_e27_fastsafe_clip_out.txt`/`unet_out.txt`,
`_e27_ro_probe1-3.txt`, `_e27_env_probe_result.txt`, `_e27_gantt_render.txt`. The
direct ancestor of the current path is the RX7 static-arm A/B:
`RX7_E27_CONTIGUOUS_QD4_SOURCE_SCHEDULING_AB_REPORT_2026-09-01.md` accepted
`static_e27` on a six-run/arm confirmation with exact SHA, true-cold, no fallback
(lines 42–44); median total request 21,877.9 ms vs control 27,485.2 ms (−20.4 %),
`golden_clip_load` −12.8 %, but `golden_clip_forward` **+13.9 %** (lines 46–68). The
report is explicit that source-QD occupancy and source-wall fields are **null**, so it is
not a bandwidth/QD-occupancy win (lines 8–19). `RX7A_STATIC_E27_INTEGRATION_REPORT_2026-09-01.md`
and `V2_BATCH_E27_FIVE_TARGET_CRITICAL_PATH_FORENSICS.md` are the integration/forensic
companions.

*Comparability:* **partial.** The current dual corpus does run the static-E27
instrumented `os.preadv` seam (this report §4, T14), and the same
`E27_SOURCE_MECHANISM_PROVEN` predicate is the one that fails for
`golden-p1-0-716326690293` (§8). But RX7 is a different profile/commit and its QD
geometry is not the current one, so its medians cannot be pooled. The E27 predicate is
therefore **partial** here for the same reason §9a gives: its input normalization can
fail (1/142 CLIP `NO`), so a `YES` is not by itself runtime proof.

**9c.5 PRETOUCH vs control.** Two isolated worktrees implement a self-selecting
post-restore OS-page pretouch arm: `.slim/worktrees/pretouch-ab-control-sep14/` and
`.slim/worktrees/pretouch-ab-pretouch-sep14/` (`comfymodal_runtime/golden_pretouch.py`,
841 lines). Activation is code-only by app identity — `APP_NAME_ENV = "COMFYMODAL_V2_APP_NAME"`,
marker `"pretouch"` (lines 43–48), `pretouch_enabled()` line 84; `touch_pages` line 127;
`enumerate_loader_ranges` line 348; `enumerate_transport_ranges` line 433;
`pretouch_transport_memory` line 545; `pretouch_loader_memory` line 696. The contract
(lines 1–32) is fail-closed per range and records per-process major/minor fault snapshots
before/after without inferring causality. The `c4_armA_*.log` / `c4_armA_console.log`
files in both worktrees are the control-arm deploy/validation logs (the emitted run
payload contains `pretouch={pretouch_enabled: 0, …}`).

The derived evidence is two CSVs. `pretouch-ab-control-sep14/.v2ctl/evidence/pretouch_ab_derived_20260916.csv`
has 31 rows (**15 `A_CONTROL` + 16 `B_PRETOUCH`**) with `clip_load_ms`, `unet_load_ms`,
`max_preadv_ms`, `pretouch_enabled`, `pretouch_ms`, `pretouch_pages`, and per-read fault
records plus `preadv_ge_{150,250,500,1000,5000}ms` counts.
`pretouch-ab-pretouch-sep14/.v2ctl/evidence/pretouch_corrected_derived_20260916.csv` has
10 corrected pretouch rows with `pages_touched_total = 65536`, `pretouch_wall_ms`
4.3–11.2 ms, `pretouch_to_first_preadv_ms` 2.38–3.50, and **`pretouch_minor_fault_delta = 0`,
`pretouch_major_fault_delta = 0` on every row**.

*Result and preserved contradiction:* the control block contains one large CLIP
(`golden-p1-0-ed95a70edd75`, `clip_load_ms 3911.2`, 12 reads ≥ 150 ms) and the pretouch
block contains one too (`golden-p1-0-c4d3f052aa84`, `clip_load_ms 3603.6`, 6 reads
≥ 150 ms); the corrected-pretouch block also contains a `max_preadv_ms 2319.8` row with
5 reads ≥ 1000 ms (`golden-p1-0-b3a9a965aef1`). Pretouching loader/transport pages did
**not** remove the clustered `preadv` sickness, and the zero fault deltas mean the
touched pages were already resident — so pretouch is not a mechanism for this pathology.
This is a direct negative on the first-touch/fault branch (T16/T36) and is consistent
with the C0 finding (9c.2). *Comparability:* **not-comparable** as a rate (serial Golden
v1 A/B, not dual arms, ~31 total rows); **partial** as a fault/pretouch negative. This
family also preserves a contradiction: the older restored-page work (9c.6) treated page
state as causal, while these fault deltas are zero under pretouch.

**9c.6 Restored-page / physical-page / fresh-anonymous / copy investigations.** Three
in-container, raw-backed reports and two audits. `V2_UNET_BACKING_AB_REPORT.md`: 14 valid
cold runs, per-storage `/proc/self/maps` classification shows the UNET is
**454/454 anonymous `[heap]`, 0 file-backed**, in both arms at snapshot-build and at
transfer time (lines 27–36); a fresh 2 GiB anonymous H2D is 88–126 ms @ 17–24 GB/s on
**every** run while the same-run real 12.31 GB transfer is 1.5–2.4 GB/s, and the Arm-B
fresh-anonymous clone (454/454, 12,309,821,472 B) gives no benefit (median A 5,932 ms vs
B 7,487 ms) (lines 42–72). `V2_PROVIDER_AND_PAGE_PATH_FINAL_REPORT.md`: mincore residency
is **1.0 before and after** the traversal, the real H2D records **zero major faults and
zero I/O**, and the synthetic contiguous/same-454-storage probes are fast (453–1,374 ms)
while the restored UNET is 5,176–6,035 ms on **both** AWS and GCP (lines 23–57) — so
hydration, total size, and copy structure are rejected and the "restored
snapshot/model-page path" is supported. `V2_FINAL_OWNERSHIP_AND_REHOMING_REPORT.md`:
fresh-clone H2D is always 571–748 ms, the original restored-storage H2D swings
583 ms → 19.05 s, and the clone's **parallel CPU memcpy inherits the slow restored-page
read** (0.5–3.9 s isolated; 7.0–14.8 s on affected containers; ~1.7 GB/s/core with
7 cores busy — "the *pages*, not the copy kernel, are slow"); rehome is rejected
(lines 104–132). Supporting structure: `V2_SNAPSHOT_ARCHITECTURE_AND_WORKING_SET_RESEARCH.md:155`
(spliceVMA mixed-source mapping) and `V2_BATCH_B_SNAPSHOT_HYGIENE_AND_STAGE13_REPORT.md:43`
(RSS delta is only a lower bound on anonymous pages returned).

*Exact absence in the current corpus:* there is no physical-page, THP/folio, mincore,
anonymous-ownership, or copy-split field retained. The only diagnostic leaves are the two
RSS values in `snapshot_manifest` (§4, §13.4) and the empty `clip_page_faults = {}`.
*Comparability:* **not-comparable** as rates (2026-08 snapshot/UNET-transfer path,
different profiles/images) but **partial** as mechanism: this is the strongest historical
evidence that "fresh memory fast / restored pages slow" is a real **destination-side**
property when the destination *is* Modal-restored memory. It does **not** describe the
current dual corpus's `preadv` destination (a Golden arena), so it cannot be transferred
into §1's source-vs-destination unknown — it only brackets that unknown.

**9c.7 Minimal restore / startup / first-request.** `GOLDEN_MINIMAL_RESTORE_IMPLEMENTATION_2026-09-11.md`
documents flag `COMFYMODAL_GOLDEN_MINIMAL_RESTORE` default `0` (line 30), routing seam
`comfymodal_runtime/modal_app.py:12860` (line 32), accessor `_golden_minimal_restore_enabled()`
(~3550), the four helpers at 12596–12836, and the OFF-path call graph (lines 57–68); the
legacy 2,293-line `restore()` body is unchanged. Companions:
`GOLDEN_RESTORE_ARCHAEOLOGY_MINIMAL_REBUILD_AUDIT_2026-09-11.md`,
`GOLDEN_RESTORE_AUDIT_RECONCILIATION_2026-09-11.md`, and
`K1_GOLDEN_RESTORE_QUIESCENCE_SEAM_RECOVERY_REPORT.md`. Derived audits confirm the
default-on state and the magnitudes: `E38O_INDEPENDENT_FULL_REPOSITORY_AUDIT.md:233-256`
§6.3 "Minimal restore (VERIFIED)" (`COMFYMODAL_MINIMAL_RESTORE` default `"1"`,
`modal_app.py:3051-3055`), and `E38S_INDEPENDENT_FULL_REPOSITORY_AUDIT.md:229`
(=`E38_01…:229`) records `restore:early 10.9 ms, eviction 8.5 ms, snapshot 4.2 ms`.
Raw-backed corroboration is in the C0 attribution's cohort tables: restore 4.5–31.4 ms
and child startup 0.9–1.9 ms across `artifacts/phase_p1_parallel_golden_v1/cohort_2026-09-14_03-*`
(the C0 report's §13.3–13.4 and appended reconstruction), including the 32.1 s
`dispatch→method` gap in the later cohorts that the C0 report explicitly declines to
assign to restore/startup.
*What this proves:* restore/startup is single-digit-millisecond and does not carry the
sickness; the current dual corpus's `restore_count=1` and coldness are consistent.
*What it does not prove:* a control for the read pathology. **Partial.**

**9c.8 FD lifecycle / cache / hot-range.** `GOLDEN_EXPERIMENT_ARCHAEOLOGY.md:119` records
the persistent-FD treatment: 12 exact/cold/DNF-free rows, opens fell **61→2 (CLIP)** and
**93→2 (UNET)**, but mean FRR *slightly worsened* 12,479→12,550 ms — FD reuse is proven
mechanically, not as a performance lever. The same 61 CLIP / 93 UNET read counts are the
`fd_telemetry.preadv_diagnostics` denominator in the C0 sick run
(`REPORT_C0_PREADV_DEFINITIVE_ATTRIBUTION.md:44`). The hot/cold-offset control set lives
in `comfymodal_runtime/c0_preadv_controls.json` (4 historical-fast + 1 tail offset per
CLIP/UNET) and is generated/checked by `tools/c0_preadv_control_manifest.py`. On the
cache/hot-range axis, `V2_BATCH_C12_SAFETENSORS_LAYOUT_SHARDING_REPORT.md:118` names
page-cache residency across requests as a separate axis, and
`V2_BATCH_C13_NATIVE_FAST_DISK_FORENSIC_AUDIT.md:23,167` records zero-copy
`torch.frombuffer` views and demand paging (~8 GB/s) beating preadv (4.07 GB/s) and
staging (3.6 GB/s). *Comparability:* **partial** only — the current canonical schema has
no FD-open-count, cachestat, or hot-range field, so this family cannot be tested from the
dual corpus; it is relevant only as background on why "FD reuse" is not assumed causal
(the archaeology explicitly says it was neutral/slightly worse).

**9c.9 Transport cleanup.** `V2_BATCH_E6_POST_RESPONSE_GPU_CLEANUP.md` is a read-only
lifecycle audit concluding `EXIT_ONLY_CLEANUP_POSSIBLE=YES`,
`CAN_KNOW_CONTAINER_WILL_EXIT_BEFORE_RESPONSE=NO`, and
`CALLER_VISIBLE_SAFE_BOUNDARY=local_result_received`, with the recommendation not to run
GPU-cache cleanup/full unload before the terminal result (lines 11–17, 23–60). Companions:
`OC7_TEARDOWN_TIMING_COMPLETENESS_2026-08-25.md` (historical teardown audit; supersession
notice redirects current durability semantics to `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md`),
`RX6_GOLDEN_LOG_CLEANUP_AND_POST_RESULT_TAIL_REPORT_2026-08-31.md` (commit `fdcb1be`,
`INTEGRATED=NO`), and `E40_CANONICAL_RUNTIME_TRUTH_AND_CLEANUP_REPORT.md`. *Comparability:*
**not-comparable** to the read seam; only **partial** lifecycle context. The dual corpus's
own read-integrity invariants (`retry>0 = 0`, `short_read 0/88892`, `duplicate_read_count=0`,
`gaps_count=0` in §2/§4) already bound cleanup out of the sick interval.

**9c.10 CPU / getrusage / fault / context-switch / wchan / scheduling.** Raw telemetry
existed historically: `.slim/worktrees/golden-io-v2/EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md`
carries `ru_nvcsw`/`ru_nivcsw`/`ru_minflt` and `delta_nvcsw`/`delta_nivcsw` (e.g.
`ru_nvcsw 93381`, `ru_nivcsw 0`, `ru_minflt 0`, with `delta_nvcsw` null), plus
`voluntary_context_switches`/`involuntary_context_switches`. `.slim/worktrees/golden-io-v2/CHATGPT_ARCHAEOLOGY_AUDIT.md:47`
records `_MinimalRestoreCanary()` at `modal_app.py:12840` probing
getrusage/`threading.enumerate`/`/proc`/cgroup with `probe_ns` 0.44–1.54 ms. The
`.slim/deepwork/v2-cold-runs.md:112-141` audit states CLIP prefill has **no encode-loop
thread fault/context-switch delta** and that the additive diagnostic captures
`RUSAGE_THREAD` faults/context switches, process/thread CPU, and I/O;
`E38L_INDEPENDENT_FULL_REPOSITORY_AUDIT.md:178` specifies how to prove/falsify with
runnable threads, native IDs, affinity, Torch/BLAS pools, queue waits, context switches,
and CPU time per stage. In the C0 sick run, `REPORT_C0_PREADV_DEFINITIVE_ATTRIBUTION.md:79,87,94`
shows all 158 per-read rusage deltas are **zero**, `schedstat` null 158/158,
`wchan`/`syscall`/`stack` null in all 32 samples, and live-sampler D=62/S=1/R=1.

*Comparability:* **not-comparable** as a corpus (different hosts/profiles), **partial** as
a negative. In the current corpus the only retained diagnostics are two RSS leaves and an
empty `clip_page_faults = {}` (§4, §13.4), so none of this is testable now. The historical
record *does* show the instrumentation existed and produced zero fault/context-switch
deltas plus null `wchan`/`schedstat`, which is the same posture the current report reaches
by absence (T32/T33/T35/T36 remain unresolved, not killed).

**9c.11 Same-source/destination natural comparisons.** Within-container paired probes are
the only historical measurements that physically separate "read of the source bytes" from
"copy into the destination": (i) `V2_UNET_BACKING_AB_REPORT.md:59,68` — a same-run
2 GiB anonymous H2D is fast (17–24 GB/s) while the restored 12.31 GB transfer is
1.5–2.4 GB/s; (ii) `V2_PROVIDER_AND_PAGE_PATH_FINAL_REPORT.md:51` — same container, same
moment, same sizes, same copy loop: fresh anonymous 12.31 GB contiguous 453–1,189 ms,
fresh 454-storage 551–1,374 ms, restored UNET 5,176–6,035 ms; (iii)
`V2_FINAL_OWNERSHIP_AND_REHOMING_REPORT.md:125-129` — fresh-clone H2D always 571–748 ms
vs original restored H2D 583 ms–19.05 s, and the clone CPU memcpy *also* slow at
~1.7 GB/s/core, so the cost follows the restored pages and not the transfer mechanism;
(iv) `V2_BATCH_E16_REMOTE_SOURCE_IO_PREFLIGHT.md:140-148` — pageable fill 574.6 ms vs
pinned fill 569.9 ms (−0.818 %), so destination pinnedness is not the cost. The
methodological boundary is stated in `E38L_INDEPENDENT_FULL_REPOSITORY_AUDIT.md:490`:
no latency/locality/failure claim should be attributed to Modal without a controlled
same-source/same-cache/same-region test — and E16 and the provider study are explicitly
**region-unpinned/mismatched**, which is exactly the confound the current report's
provider/region analysis (§3, §13.9) also carries.

*What this proves:* when the destination is restored snapshot memory, the slow step is the
read of those restored pages, independent of whether the copy is GPU DMA or CPU memcpy,
and independent of pinnedness. *What it does not prove:* anything about the current dual
corpus's source read, because the current destination is a Golden arena and the current
schema cannot split one `preadv`; these results **bracket** the §1/§13.1 unknown rather
than resolve it. **Not-comparable** as rates; **partial/strong** as mechanism.

**9c reconciliation note (no current-corpus change).** Adding §9c does not revise §1's
A/B answer, §2–§8 counts, §10's natural-experiment table, §11's kill list, or §13's
unknowns. Where the historical families are stronger than the current corpus they are
recorded as *partial mechanism* evidence only; where they contradict (zero fault deltas,
no offset specificity, pretouch non-effect, probe-local 40+ GB/s vs integrated
2.6–3 GB/s) the contradiction is preserved above rather than resolved. The only
cross-reference implication is that §9b's master inventory and §9a's five code paths
should be read together with this census; the current-corpus labels and denominators are
untouched.

---

## 10. Strongest natural experiments in the current corpus

| # | Contrast | Design | Result | Strength |
|---|---|---|---|---|
| N1 | Same vs switched resource for UNET (sham vs split) | SHA-balanced assignment; Y verified pristine 86/86 | UNET hard-sick 8/55 vs 4/86; conditional 0.625 vs 0.167 | **Strongest available**, confounded by arm×region, small n |
| N2 | Within-request healthy-CLIP → sick-UNET | 6 requests where CLIP healthy but UNET hard-sick | `cf4f240d3d6c`, `5f9470cfb95a`, `3826114a6c00` (split); `5ae9efa67e60`, `907303a11d5c`, `989a779e3893` (sham); `5ae9`/`9073` born-at-500 UNET | **Strong** for "UNET can sicken without a sick CLIP"; mostly sham, weakens simple carryover |
| N3 | Within-request sick-CLIP → healthy-UNET | 8 requests | `51fd5230eeee` 5252.7 ms CLIP / healthy UNET; `126cf4cbe4a8`, `20ffd3348a64`, `bca55ee4d4f5` (sham); `b451904156c4`, `d8df15190c1e`, `1742b7c9b560`, `f5508707fe42` (split) | **Strong** for "a huge CLIP spike does not always propagate" |
| N4 | Born-sick vs becomes-sick UNET in sham vs split | T=500/1000 onset | sham UNET born 5/3; split UNET born 0/0 | **Strong directional**, tiny counts |
| N5 | A vs B and A→B vs B→A | deterministic assignment | no effect (Fisher 0.6177) | **Clean null** |
| N6 | Provider contrast (GCP vs AWS) | crude + standardized | AWS CLIP sick 3/48, UNET sick 0/48; GCP 11/92, 11/92 | **Partial**, provider×arm confounded |
| N7 | Region contrast within GCP | per-region rates | `us-east1` 10/55 & 9/55; others ~0 | **Partial**, arm imbalance |
| N8 | Episodic recovery | peak ≥500 then clear | all 39 read-≥500 request-roles clear; strongest: `0b56ab29f792` CLIP 2550 ms single episode, `f18b437f0d56` UNET 1233 ms, `49cd54fb17f9` UNET 1017 ms | **Strong** for transience |
| N9 | Load-only severe cases (no read ≥1000) | `load_ms >= 5000` | `989a779e3893` UNET load 6147.99/max 860.17; `3826114a6c00` UNET load 6354.43/max 997.43 | **Strong** for "sickness is not only max-preadv" |
| N10 | Computed-invalid run | `252bc1b6bdd2440e` (`golden-p1-0-9ceed22e46e8`) | raw-valid label but no_output_warning → computed invalid; **excluded from every derived statistic** (all valid-only denominators) | Weak, n=1; retained for audit in canonical per_request/per_read |
| N11 | E27 extraction failure | `716326690293` | 20 failed predicates despite plausible raw values | Weak, n=1, but evidence-integrity relevant |
| N12 | Historical clean cohorts | Sep-14 27, C0-FD 15, V1/V2 30 | see §9 | **Not comparable** as designed |

**Evidence matrix (`derived_evidence_matrix.json.families`)** maps all 10 derived families to
canonical paths and missingness; its validation block self-checks 142 retained attempts /
141 valid records (55 sham / 86 split) / 14 hard CLIP / 12 hard UNET / 423 valid onset rows
(canonical 426) / 0 onset read-count mismatches, plus a valid-only per-read reconciliation
of 88266 rows (clip 34263 / unet 52170 / vae 1833) with 0 mismatches — all matching this
pass.

### Conclusion C10 — the strongest experiments support stage/asymmetry, not a clean carrier proof
- **SUPPORTING EVIDENCE:** N1, N4 support a resource-local transmission component; N2/N3
  bound its strength; N5/N8 are clean nulls/transience.
- **COUNTEREVIDENCE:** N2 (6 healthy-CLIP→sick-UNET) and the 6 UNET_SICK_ONLY requests show
  UNET can sicken without a sick CLIP, so a pure "CLIP poisons UNET" reading is too strong.
- **WHAT THIS PROVES:** the honest model is a shared per-request factor plus an
  arm-modulated UNET tail, not a deterministic one-way transfer.
- **WHAT THIS DOES NOT PROVE:** the physical identity of the shared factor.

---

## 11. Complete theory kill list (41 theories)

**Provenance note:** the offline corpus contains no file enumerating a 41-item list. The
list below is the enumerated candidate-mechanism space reconstructed from the campaign's own
vocabulary (source / carrier / worker / CPU-scheduler / geometry / orchestration /
measurement). Verdicts use only the evidence in this report. `KILLED` = contradicts observed
facts; `WEAKENED` = contradicted but not conclusively; `UNRESOLVED` = corpus cannot test it;
`SUPPORTED` = consistent and positively evidenced.

| # | Theory | Verdict | Evidence |
|---|---|---|---|
| T1 | Remote object-store network stall inside `preadv` | UNRESOLVED (best source candidate) | syscall ≈ source wall, but no network field |
| T2 | Modal Volume / FUSE latency | UNRESOLVED | no volume/FUSE latency field retained |
| T3 | NVMe / block-device tail | UNRESOLVED | no block-latency counters |
| T4 | Kernel readahead / page-cache miss | WEAKENED | split reduces transmission though cache shared; no cache counters |
| T5 | Page-cache eviction under memory pressure | UNRESOLVED | only 2 RSS leaves; no pressure series |
| T6 | Filesystem metadata / inode lookup stall | UNRESOLVED | no metadata counters; header_parse stable |
| T7 | TCP retransmit / congestion | UNRESOLVED | no network counters |
| T8 | Storage server-side queue/tail | UNRESOLVED | no server telemetry |
| T9 | Cloud noisy neighbour (shared fabric) | UNRESOLVED | region association only; no host identity |
| T10 | Source file fragmentation / non-contiguous extents | KILLED (locally) | E27 `fixed_contiguous_regions` true 141/142; `coverage_exact` true |
| T11 | Short reads / retries / EIO | KILLED | 0 short, 0 retry, 0 error, 0 duplicate |
| T12 | Hardlink/dedup contention on source | UNRESOLVED | no dedup counters |
| T13 | Transparent compression/decompression on read | KILLED (for this path) | raw safetensors `os.preadv`, no decompression seam |
| T14 | O_DIRECT vs buffered path difference | WEAKENED | current corpus is buffered static-E27; O_DIRECT only in 18-row derived history |
| T15 | Read amplification / double reads | KILLED | `duplicate_read_count=0`, bytes reconciled exactly |
| T16 | Pinned-arena first-touch page faults | UNRESOLVED | `clip_page_faults={}` empty; no fault counters |
| T17 | H2D copy-engine contention / event serialization | WEAKENED | `h2d_frac_of_load` 0.698/0.691 (CLIP), H2D wall < syscall wall in all pathological cases |
| T18 | Shared H2D stream between CLIP and UNET (sham reuse) | WEAKENED | resources' streams distinct; split still shows some UNET sickness |
| T19 | Destination-buffer/page writeback stall | UNRESOLVED | not separable inside syscall |
| T20 | memlock/rlimit pinning failure | KILLED (as a load failure) | all 141 valid create arenas (142 canonical), `arena_data_ptrs_distinct`, memlock stats present |
| T21 | Physical page allocation fragmentation | UNRESOLVED | no physical-page counters |
| T22 | NUMA-local vs remote memory | UNRESOLVED | no NUMA fields |
| T23 | Shared→pinned second copy | WEAKENED | dual path is E27 in-process, `c0_active=False`, privileged streaming |
| T24 | Slot exhaustion / ready-queue backpressure | KILLED (for this path) | `free_ready_depth`, quiescence evidence all true; 8 slots, 4 producers |
| T25 | H2D event re-record overhead | KILLED | `event_rerecord_count`/`fresh_cuda_event_per_copy_count` instrumented; not elevated in pathological cases |
| T26 | CUDA host-allocator contention | WEAKENED | host memory stats available; no alloc stall evidence |
| T27 | GPU copy-engine saturation | WEAKENED | GPU_COPY union < H2D wall; idle-inside-span present |
| T28 | Request-local resource carryover (arena) CLIP→UNET | SUPPORTED (directional) | N1, N4 |
| T29 | Producer/worker imbalance | KILLED | HHI 0.250 constant; balanced read counts |
| T30 | Too few / exactly-4 workers | UNRESOLVED (not a sickness mechanism here) | 4 constant across sick and healthy |
| T31 | Python GIL contention | UNRESOLVED | no GIL/hold counters |
| T32 | CPU oversubscription / cgroup throttling | UNRESOLVED | no throttle counters |
| T33 | Scheduler preemption / context switches | UNRESOLVED | no `nvcsw`/`nivcsw` counters |
| T34 | Thread-start stall (eager start) | KILLED (for current corpus) | no loader process / eager path in dual arms |
| T35 | CPU frequency / thermal throttling | UNRESOLVED | no thermal/freq counters |
| T36 | Page-fault handling in worker threads | UNRESOLVED | fault container empty |
| T37 | QD geometry (QD4/64 vs QD2/128) | WEAKENED | current corpus QD fixed; historical QD4/64 worsened medians |
| T38 | Block-size mismatch (32 MiB vs 128 MiB) | KILLED (for this corpus) | constant `slot_bytes=33554432` |
| T39 | Restore/snapshot side-effects | WEAKENED | `restore_count=1`, all cold, gaps 0; restore only weakly correlated (0.4800) |
| T40 | Provider/region shared fate | WEAKENED | region association exists but arm-confounded; us-east1 hosts both arms |
| T41 | Measurement/instrumentation artifact | WEAKENED | `read_seq` vs syscall order 0 inversions; durations re-derived exactly; but one E27 extraction failure and no CPU/network counters leave it alive |

**Surviving mechanism set after the kill list:** T1/T2/T3/T5/T6/T7/T8/T9/T12/T16/T19/T21/
T22/T31/T32/T33/T35/T36 (all *unobservable* in this corpus) plus the positively supported
T28 and the weakened T4/T17/T18/T37/T40/T41. That is the honest state: the surviving set is
dominated by **untestable** source/CPU theories, not by a proven one.

---

## 12. Causal model with arrow evidence levels

Arrow levels: **E1** = measured and independently reproduced; **E2** = measured association
with a plausible ordering; **E3** = inferred, not directly measured; **E4** = speculation.

```
                +---------------------------------------------------+
                | Host / cluster / region / provider (unmeasured)   |
                +------+--------------------------------------------+
                       | E3 (moderate: region association, but arm-confounded)
                       v
  [Request dispatch] --> [golden_restore] --E1 weak (0.4800)--> severity
                       |
                       v
             [golden_clip_load] --E1 strong (clip_max_preadv 0.8971; clip_load 0.8370)--> severity
                       |
                       | E1: syscall union ~= source wall; time is inside os.preadv seam
                       | E3: cannot split source-service vs destination-write
                       v
        (Read syscall) ---E2---> [CLIP sickness]
                       |
                       | E2 directional (sham conditional 0.625 vs split 0.167)
                       v
        [request-local resource state] ---E2---> [golden_unet_load] --E2 (0.5196)--> severity
                       ^
                       |
              E1: in sham the UNET arena is REUSED; in split it is
                  CREATED fresh and verified pristine before UNET.
```

- **E1 facts:** the syscall seam dominates load; `clip_max_preadv` is the top severity
  correlate; sham reuses / split creates; Y pristine; producer balance constant.
- **E2 facts:** same-resource arm has more UNET sickness; cross-role load correlation 0.7193;
  UNET can sicken with healthy CLIP (6 cases) and vice versa (8 cases).
- **E3 facts:** a host/cluster co-factor is required to explain the 0.7193 cross-role
  correlation and the region association; its physical identity is not measured.
- **E4:** none asserted. No arrow is labelled E4 in this model.

### Conclusion C12 — the causal graph is source-seam → CLIP, with an E2 arm-modulated local edge to UNET
- **SUPPORTING EVIDENCE:** E1/E2 facts above.
- **COUNTEREVIDENCE:** the arm edge is small-n and region-confounded; the healthy-CLIP→sick-UNET
  cases show the edge is not necessary.
- **WHAT THIS PROVES:** the only well-supported causal claim is that the read seam carries the
  sick time and CLIP is the most sensitive stage.
- **WHAT THIS DOES NOT PROVE:** any specific source-side vs destination-side physical cause.

---

## 13. Remaining unknowns (explicit)

1. **Source vs destination decomposition of one `preadv`.** No field splits syscall time into
   remote source service vs local destination write/copy. This is *the* central unknown.
2. **slot_index.** Empty for 88892/88892 rows, and hardcoded `None` in the runtime record
   builder. Slot-level attribution is impossible.
3. **region_id = producer_id.** Region and worker are the same integer; not separable.
4. **CPU fault / context-switch / scheduler counters absent.** `clip_page_faults={}`; no
   `nvcsw`/`nivcsw`, CPU ticks, cgroup throttle, NUMA, or thermal fields.
5. **Residual `load_ms - SOURCE_TOTAL_WALL_MS`** (valid CLIP median 473.6 ms sham / 525.9 ms
   split) is unlabelled and not decomposed by the schema.
6. **Host/cluster identity not retained**, so region association cannot be reduced to host.
7. **One computed-invalid sham run** (`252bc…` = `golden-p1-0-9ceed22e46e8`,
   `no_output_warning`; excluded from every derived statistic but retained in canonical
   `per_request.json`/`per_read.csv` and in the exclusions) and **one missing-attempt sham
   run** (`bab378…`) — no data.
8. **One CLIP E27 extraction failure** (`716326690293`) — 20 predicates fail despite normal
   raw values; the extractor's input normalization is not trustworthy for that one row.
9. **Provider/region × arm is structurally imbalanced**, so crude arm effects and
   region effects cannot be fully separated; standardization only partially corrects it.
10. **Historical population is not comparable**, so the "clean cohort" architecture
    (C0/QD2-128/FD-reuse) is a hypothesis, not a measured control for this corpus.
11. **No fault/thermal/pressure time series**, so all pressure-based theories stay alive but
    untested.
12. **Two load-only severe cases** (`989a…`, `3826…`) have reads below 1000 ms and are only
    visible through `load_ms >= 5000`; their mechanism is unknown.

---

## 14. Minimum additional experiment count (only after evidence exhausted)

The evidence above is exhausted for what the current corpus can distinguish. It can answer:
counts, thresholds, conditional association, onset, stage localisation, transience, A/B,
direction, provider/region association. It **cannot** answer the source-vs-destination split
or slot/worker/CPU attribution. Minimum additional work:

- **0 additional request-class experiments** are needed to sustain any claim already made
  here (the 141-valid-request corpus, from 142 retained attempts, is sufficient for those).
- **1 instrumentation change + a re-run of the existing corpus size** is the *minimum* to
  split source vs destination: emit, per physical read, a source-service time (e.g. from a
  kernel/`io_uring` completion or a source-side timestamp) and a destination-fill time, plus
  a real `slot_index` and an independent worker/region id. Without a code change, no number
  of additional requests can resolve §13.1–§13.4.
- **~270 additional fixed-seed requests (≈135 per arm), balanced across arm×provider_region**,
  is the minimum to test the primary arm contrast decisively. Basis: observed valid-only UNET
  hard-sick `0.1455` (sham, 8/55) vs `0.0465` (split, 4/86); a two-sided test at α=0.05 with
  80% power needs
  `n ≈ (1.96+0.84)^2 · (0.1243+0.0443) / (0.0989)^2 ≈ 135` per arm. The conditional
  transmission contrast (0.625 vs 0.167) needs only ~14 CLIP-sick per arm, i.e. ~140 balanced
  requests per arm given a ~10% CLIP-sick rate — consistent with the same ~270–280 total.
- **Recommended minimal design for those ~270 runs:** balanced `sham`/`split` within each
  provider_region; hold profile constant (static-E27 in-process, no C0/loader/V2); retain
  per-read raw events; add the instrumentation above. This yields one decisive arm test and
  the first separable source/destination decomposition. No other experiment is required to
  retire the surviving theory set.

**Honesty statement:** the raw corpus cannot, by itself, separate source from destination,
and no claim in this report does so. Any statement assigning the sickness to "the remote
volume" or "the local arena" without the instrumentation above is unsupported by the
retained data.
