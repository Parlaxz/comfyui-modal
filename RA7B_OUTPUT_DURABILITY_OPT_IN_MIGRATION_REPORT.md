# RA7B — Generated-Output Durability Opt-In Migration Report

**Date:** 2026-08-31  
**Lane:** RA7B runtime, validation, tests, and guidance  
**Validation owner:** orchestrator  
**Worktree rule:** MAIN worktree only; no branch/worktree, reset, stash, clean,
revert, or unrelated-file overwrite was performed.

## A. Scope and outcome

RA7B is complete. The interim statement that this lane changed documentation
only, with runtime, validator, and tests unchanged, was false. The current
worktree contains the complete mode-aware implementation and focused tests in
addition to the policy and guidance changes. The canonical policy is:

```text
docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md
```

Generated request-output durability is now explicitly selected with
`COMFYMODAL_OUTPUT_DURABILITY`. Missing or `off` selects the fast result-ready
endpoint; only explicit `strict` selects output Volume persistence and the
true-durable endpoint. This does not alter source publication durability or
the execution semantics of QD, sampling, or VAE stages.

## B. Discovery findings and conflict resolved

The pre-migration guidance presented one generated-output contract as
universal:

- `comfy-modal-core` described Python resume → true durable result as the
  primary endpoint and presented commit/reopen as a general contract.
- `comfymodal-golden-ops` required `true_durable`, reopen, and commit ordering
  for every accepted Golden run.
- `V2_OUTPUT_DELIVERY_CRITICAL_PATH_DESIGN.md` described deferred output commit,
  a background drain, deduplication, and post-result persistence as active
  design.

Those statements conflated generated-output durability with S4 publication.
Current guidance and executable paths now distinguish them. The historical
reports retain their original evidence and are classified in §§H-I rather than
being silently rewritten.

## C. Exact current configuration policy

`COMFYMODAL_OUTPUT_DURABILITY` accepts exactly `off|strict`.

| Input | Effective mode / result |
| --- | --- |
| missing or empty | `off` |
| `off` (case-insensitive, surrounding whitespace allowed) | `off` |
| `strict` (case-insensitive, surrounding whitespace allowed) | strict opt-in |
| any other explicit value | configuration error |

The exact invalid-value wording is:

```text
configuration error: COMFYMODAL_OUTPUT_DURABILITY must be off or strict
```

The selector is implemented in
`comfymodal_runtime/output_durability.py` and consumed by Golden runtime and
mode-aware validation. There is no implicit strict mode, and an explicit
strict failure cannot silently downgrade to `off`.

## D. Current endpoint contract

### Default (`off`)

```text
encode -> observed SHA/bytes -> FIRST_RESULT_READY -> return
```

The default path performs no generated-output Volume write, fsync-to-Volume
publication, commit, reopen, or hash proof. It returns an inline validated
artifact with observed byte count and SHA. `FIRST_RESULT_READY` is not a
claim of Volume durability and must not be labeled
`TRUE_FIRST_DURABLE_RESULT`.

The result is usable without the **output-persistence Volume**. The Golden
adapter still requires its **runtime-state Volume** for restore/runtime state;
“without Volume” in the machine-readable field means only without a separate
generated-output persistence operation.

### Strict opt-in (`strict`)

```text
write/fsync -> Volume.commit -> reopen/hash proof
-> TRUE_FIRST_DURABLE_RESULT -> return
```

Strict requires the asset to be within the intended mount, a successful real
Volume commit, reopened-object stat/read/hash verification, and ordering
evidence before the true-durable marker. `GoldenSession.build_final_result`
rejects strict completion without committed pending durability and the marker.
No result event can claim strict durability early.

Neither mode adds a persistent output worker, background output worker,
deduplication shortcut, or shortcut around its required sequence.

## E. Golden acceptance interpretation

Golden acceptance remains strict about identity, exact output, routing,
seriality, snapshot state, loader invariants, teardown, and evidence. The
generated-output predicate is mode-dependent:

- `off`: require observed encoded SHA/bytes, result-ready evidence, and
  `FIRST_RESULT_READY`; do not require `true_durable`, commit, or reopen.
- `strict`: require `true_durable=true`, commit-before-reopen ordering,
  reopened-object verification, and hash/byte-count proof.

`tools/v2_control/validation.py` resolves the selected mode from authoritative
result/telemetry/config surfaces, validates invalid selectors fail closed, and
does not upgrade selector-less modern evidence to strict. Its narrowly scoped
pre-selector compatibility recognizes only genuinely historical strict
artifacts. `tools/benchmark_v2_direct.py` applies the same conditional
endpoint and waterfall rules to Golden acceptance. The canonical ledger uses
the selected result endpoint rather than assuming the historical durable name.

## F. S4/source-publication invariant

S4 is not part of the generated-output opt-in. Shared custom-node publication
through the authoritative publisher, full published-content identity,
authoritative Volume readback, and receipt recovery remain mandatory in all
modes:

```text
generated output = optional strict durability proof
source publication = always-required durability/identity contract
```

RA7B does not weaken S4. A generated-output `off` result is not permission to
skip or reinterpret source publication.

## G. Files changed and current authority

The following are the actual RA7B files changed or created in the current
worktree. Shared files may also contain unrelated concurrent edits; those are
called out in §J.

### RA7B runtime, config/validation, benchmark, and tests

| File | Classification | Actual RA7B change |
| --- | --- | --- |
| `comfymodal_runtime/output_durability.py` | current runtime policy | created selector, fail-closed configuration error, and in-memory output identity artifact |
| `comfymodal_runtime/golden_serial.py` | current Golden runtime | added off/strict result branches, inline ready artifact, strict commit/reopen gate, mode evidence, and mode-aware final result |
| `comfymodal_runtime/modal_app.py` | current generic/Golden adapter | added generic off-mode no-persistence branch; preserved strict persistence task; resolved policy in the Golden adapter and retained runtime-state Volume requirement |
| `comfymodal_runtime/critical_path_ledger.py` | current timing implementation | changed the authoritative end boundary to the selected result endpoint; historical storage key is documented as compatibility storage |
| `tools/v2_control/validation.py` | current validator | added shared selector resolution, invalid-value fail-closed handling, off result-ready gates, strict durability gates, and conditional canonical-ledger validation |
| `tools/benchmark_v2_direct.py` | current benchmark validator | added output-mode scanning, default result-ready acceptance, strict-only commit/reopen/marker checks, and mode-aware waterfall output |
| `tests/test_ra7b_output_durability_runtime.py` | new RA7B test file | selector, artifact identity, off result delivery, strict commit/reopen, and off Golden no-write coverage |
| `tests/test_ra7b_output_durability_validation.py` | new RA7B test file | parser, off/strict acceptance, invalid selector, S4 separation, and canonical-ledger gates |
| `tests/test_ra7b_generic_request_output_durability.py` | new RA7B test file | generic off no filesystem/commit behavior and strict delegation coverage |
| `tests/test_p1_golden_serial.py` | existing P1 test file | added explicit `COMFYMODAL_OUTPUT_DURABILITY=strict` setup to tests that exercise the strict commit/reopen/true-durable contract |
| `tests/test_p2_golden_core_contract.py` | existing P2 test file | added explicit strict setup to top-level, commit/reopen, precondition, and containment tests; direct recorder strict mode is set where the test invokes strict APIs |

The existing P1 strict setup is visible at lines 344, 1790–2003, 2116, and
2169 in the current file. The existing P2 setup is visible at lines 108, 615,
696, 823, and 945, with direct `output_durability_mode="strict"` setup at
the corresponding recorder precondition tests. These changes make test intent
explicit; they do not make strict durability a default.

There is no separate RA7B selector implementation in `tools/v2_control/config.py`.
The runtime environment selector and validation resolver are the authority;
the current `config.py` worktree diff belongs to a concurrent deployment-receipt
change and was intentionally not altered by RA7B.

RA7B-adjacent files intentionally left with respect to this lane are
`tools/v2_control/backend.py`, `tools/v2_control/cli.py`,
`tools/v2_control/source_probe.py`, `tools/v2_control/deployment_receipt.py`,
`tests/test_v2ctl_backend.py`, `tests/test_v2ctl_cli.py`,
`tests/test_v2ctl_deployment_receipt.py`, `tests/test_golden_core_invariant_shield.py`,
and `tests/test_golden_qd_transport.py`. Their current-worktree changes or
creation belong to concurrent deployment-receipt, invariant-shield, or QD
lanes, not RA7B output durability.

### Current guidance and policy authority

| File | Classification | Action |
| --- | --- | --- |
| `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md` | current canonical policy | created |
| `.opencode/skills/comfy-modal-core/SKILL.md` | current architecture guidance | scoped result endpoints and strict-only output proof; S4 retained |
| `.opencode/skills/comfymodal-golden-ops/SKILL.md` | current Golden runbook | made acceptance and timing boundaries mode-aware |
| `docs/V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md` | current control-plane guidance | added mode-aware generic validation guidance; unrelated concurrent receipt hunk retained |
| `RA7B_OUTPUT_DURABILITY_OPT_IN_MIGRATION_REPORT.md` | current audit record | finalized by this edit |
| `.opencode/skills/benchmark-modal/SKILL.md` | current benchmark guidance | intentionally left in this worktree; it already points to the canonical policy and has no current diff |

### Historical guidance notices added, body preserved

These files received concise supersession notices and retain their original
evidence/classification:

| Artifact | Historical classification |
| --- | --- |
| `V2_BATCH_E29_GROUND_TRUTH_CRITICAL_PATH_AND_RESTORE_MAP.md` | historical critical-path report |
| `V2_BATCH_E13_MODAL_STORAGE_AUDIT.md` | historical storage audit; storage facts preserved |
| `E36_FULL_CRITICAL_PATH_REPORT.md` | historical timing report |
| `E38A_SNAPSHOT_REACHABILITY_AND_CLIP_EXCLUSION_AUDIT.md` | historical audit |
| `E38B_CANONICAL_TIMING_AND_VALIDATION_CONTRACT_AUDIT.md` | historical audit |
| `E38C_CONFLICTING_IMPLEMENTATIONS_AND_CANONICAL_PATH_AUDIT.md` | historical audit |
| `E38L_INDEPENDENT_FULL_REPOSITORY_AUDIT.md` | historical audit |
| `E38M_INDEPENDENT_FULL_REPOSITORY_AUDIT.md` | historical audit |
| `E38O_INDEPENDENT_FULL_REPOSITORY_AUDIT.md` | historical audit |
| `E38S_INDEPENDENT_FULL_REPOSITORY_AUDIT.md` | historical audit |
| `E38_01_INDEPENDENT_FULL_REPOSITORY_AUDIT.md` | historical audit |
| `E39_COMFYAPP_GOLDEN_PATH_PRUNING_REPORT.md` | historical Golden pruning report |
| `golden path plan Aug 26.md` | historical plan |
| `GOLDEN_SUITE_GATE_REPORT.md` | historical gate evidence |
| `R0_FUTURE_AGENT_GOLDEN_OPS_CONTRACT.md` | historical operational contract |
| `R0_GOLDEN_OPERATIONS_HARDENING_REPORT.md` | historical R0 evidence |
| `OC6_OUTPUT_DURABILITY_TIMING_COMPLETENESS_2026-08-25.md` | historical output-timing audit |
| `OC7_TEARDOWN_TIMING_COMPLETENESS_2026-08-25.md` | historical teardown audit |
| `RA7_DURABLE_COMMIT_VARIANCE_AND_DECOMPOSITION_REPORT.md` | historical measurement/decomposition |
| `RA10A_EMPTY_CACHE_MODEL_MANAGER_FORENSICS_REPORT.md` | historical Golden forensics |
| `RA2B_SNAPSHOT_RESTORE_CONTENT_TRUTH_REPORT.md` | historical Golden evidence |
| `RV1_SHARED_GOLDEN_DIAGNOSTIC_RECONCILIATION_REPORT.md` | historical reconciliation |
| `K1_GOLDEN_RESTORE_QUIESCENCE_SEAM_RECOVERY_REPORT.md` | historical experiment |
| `V2_OUTPUT_DELIVERY_CRITICAL_PATH_DESIGN.md` | historical output-delivery design; active background-drain interpretation superseded |
| `V2_RESULT_HANDOFF_RESTORE_AND_SETUP_RESEARCH.md` | historical result-handoff research |

## H. Historical Golden inventory and disposition

Historical evidence is not current policy. The notices above direct a fresh
agent to §C–F and the canonical policy. The following were intentionally left
without body rewrites because they are evidence/raw logs, are owned by another
lane, or are already explicitly historical:

| Artifact(s) | Classification / disposition |
| --- | --- |
| `7-17-26 prompt.txt` | older generic V2 implementation prompt; unchanged and not current Golden guidance |
| `S4_CUSTOM_NODE_FULL_CONTENT_PUBLICATION_TRUST_REPORT.md` | current S4 source-publication evidence; unchanged because S4 remains mandatory |
| `RA5_*`, `RA6_GOLDEN_SAMPLING_DECOMPOSITION_REPORT.md`, `RA8_*` | historical diagnostics/raw evidence; no current output-policy authority |
| `OC1_RESTORE_*` through `OC5_VAE_*`, `OC8_GOLDEN_CANDIDATE_*` | historical stage/telemetry audits; evidence only |
| `RA11A_*`, `RA11C_*`, `RA11D_*`, `RA11E_*` | concurrent/untracked RA11 artifacts; ownership preserved |
| `RA6R_*`, `RA9B_*`, `RA9F_*` | concurrent/untracked RA6/RA9 evidence; ownership preserved |
| `RV2_*`, `RV2B_*`, `S1_*`, `S2_*`, `R41_*` | historical or concurrent Golden evidence; no body rewrite |
| `E39_REMOTE_GATE_RAW_LOG.txt`, `E40_CONTROL_REMOTE_RAW_LOG.txt`, `app_logs_agents*.txt` | raw logs, not guidance |
| `V2_CONDITIONING_CACHE_CRITICAL_PATH_DESIGN.md` | separate conditioning-cache durability design |
| product `PHASE_*` reports and `docs/superpowers/*` plans | product/history semantics, not generated-output authority |

No current reusable prompt was edited. The verified historical-prompt
supersession count is therefore zero; the unchanged `7-17-26 prompt.txt` is
not a current authority and is explicitly identified as such above.

## I. Search commands and final match classification

The final audit used these read-only searches from the repository root. The
first command is the intended full-tree command; this Windows checkout did not
have `rg` on PATH, so equivalent repository content search was also completed
with the native content-search tool:

```powershell
rg -n --glob '*.md' --glob '*.txt' "true_durable\s*(==|=)|TRUE_FIRST_DURABLE_RESULT|Volume\.commit|commit/reopen|first durable|durable result|COMFYMODAL_OUTPUT_DURABILITY" .
rg -n --glob '*.md' --glob '*.txt' "must .*durab|durab.*must|durability.*required|required.*durab|universal.*durab|for every.*Golden" .
rg -n --glob '*.md' "background drain|background output|dedup|persistent output|must complete before bytes" .
```

Every policy-significant remaining mandatory-looking match is individually
classified below. `STRICT_MODE_CURRENT` means a current conditional strict
requirement (or the separate all-mode S4 invariant explicitly marked as such),
`HISTORICAL_WITH_SUPERSESSION` means a historical body with a controlling
notice, `IMPLEMENTATION_DETAIL` means executable/test/storage evidence rather
than universal policy, `FALSE_POSITIVE` means a separate meaning or unrelated
use, and `BUG` means an actual current policy violation.

| Match location | Classification | Reason |
| --- | --- | --- |
| `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md:11-42` | `STRICT_MODE_CURRENT` | current selector and explicitly conditional off/strict endpoints |
| `.opencode/skills/comfy-modal-core/SKILL.md:454-467,488-537` | `STRICT_MODE_CURRENT` | selected endpoint and strict-only output proof; S4 explicitly separate |
| `.opencode/skills/comfymodal-golden-ops/SKILL.md:48-74,189-196,256-258` | `STRICT_MODE_CURRENT` | current mode-aware runbook |
| `docs/V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md:624-652` | `STRICT_MODE_CURRENT` | current mode-aware control-plane guidance |
| `comfymodal_runtime/output_durability.py:3-53` | `STRICT_MODE_CURRENT` | runtime selector, strict opt-in, and fail-closed invalid values |
| `comfymodal_runtime/golden_serial.py:883-936,3425-3579,6639-6883,7088-7224,7351-7398` | `STRICT_MODE_CURRENT` | strict commit/reopen/marker path and default in-memory ready path |
| `comfymodal_runtime/modal_app.py:16609-16714,17238-17393,21182-21279,21436-21464` | `IMPLEMENTATION_DETAIL` | generic persistence adapter and Golden runtime-state Volume plumbing implement the policy; they do not redefine it |
| `comfymodal_runtime/critical_path_ledger.py:1-39,87-109,734-751` | `STRICT_MODE_CURRENT` | serial ledger is bounded by the selected endpoint; historical key is compatibility storage |
| `tools/v2_control/validation.py:626-785,1205-1249,1308-1398` | `STRICT_MODE_CURRENT` | validator is explicitly mode-aware and strict-only where required |
| `tools/benchmark_v2_direct.py:10618-11229` | `STRICT_MODE_CURRENT` | benchmark scanner and Golden acceptance select the endpoint from mode |
| `tests/test_ra7b_*.py` | `IMPLEMENTATION_DETAIL` | focused executable proofs, not operator policy |
| `tests/test_p1_golden_serial.py:344,1790-2003,2116,2169` | `IMPLEMENTATION_DETAIL` | explicit strict fixtures for strict-only tests |
| `tests/test_p2_golden_core_contract.py:108,615,696,707,724,823,825,945,977` | `IMPLEMENTATION_DETAIL` | explicit strict fixtures/direct recorder setup |
| `S4_CUSTOM_NODE_FULL_CONTENT_PUBLICATION_TRUST_REPORT.md` and core S4 lines `191-205` | `STRICT_MODE_CURRENT` | current mandatory S4 invariant in every mode; not generated-output default durability |
| `V2_OUTPUT_DELIVERY_CRITICAL_PATH_DESIGN.md` | `HISTORICAL_WITH_SUPERSESSION` | active deferral/background-drain interpretation superseded; body preserved |
| `V2_RESULT_HANDOFF_RESTORE_AND_SETUP_RESEARCH.md` | `HISTORICAL_WITH_SUPERSESSION` | historical result-handoff wording; notice controls current use |
| `E36`, `E38A/B/C/L/M/O/S`, `E38_01`, `E39`, `E29`, `E13`, `golden path plan Aug 26.md` | `HISTORICAL_WITH_SUPERSESSION` | historical timing/design/identity evidence with notices |
| `GOLDEN_SUITE_GATE_REPORT.md`, `R0_*`, `OC6`, `OC7`, `RA7`, `RA10A`, `RA2B`, `RV1`, `K1` | `HISTORICAL_WITH_SUPERSESSION` | historical strict-gate, measurement, or forensic evidence with notices |
| `RA11*`, `RA6R*`, `RA9B*`, `RA9F*`, `RV2/RV2B`, `R41`, and raw logs | `IMPLEMENTATION_DETAIL` | concurrent/raw evidence intentionally not modified and not current policy |
| `REAL_CLIP_CACHE_MISS_REPORT.md`, `PHASE_D_FOLLOWUP_2_REPORT.md`, `V2_CONDITIONING_CACHE_CRITICAL_PATH_DESIGN.md` | `FALSE_POSITIVE` | Volume/commit terminology concerns cache or cross-container observation, not generated-output endpoint policy |
| product `PHASE_*` durable-history matches and unrelated uses of `strict` in tests | `FALSE_POSITIVE` | separate product/history or test semantics |
| Any current generated-output match asserting strict durability is universal | `BUG` | none found after the current source/guidance and validator audit |

Thus stale policy matches are not left unclassified. The remaining strict
words in runtime and validation are intentional strict gates, implementation
evidence, or separate-scope terminology; none establishes strict as default.

## J. Concurrency and repository preservation

This report was the only file edited by this finalization pass. The current
worktree also contains unrelated concurrent modifications, which were not
reset, stashed, cleaned, reverted, deleted, or overwritten. They include:

- QD/CLIP/E31/RA9 work: `comfymodal_runtime/golden_qd_transport.py`, the
  QD portions of `golden_serial.py`, `clip_fast_hydration_wiring.py`,
  `clip_fp32_cast_once.py`, `speculative_clip_hydration.py`,
  `.commandcode/taste/taste.md`, and their RA9/CLIP tests and reports;
- deployment-receipt/control-plane work: `tools/v2_control/backend.py`,
  `tools/v2_control/cli.py`, `tools/v2_control/config.py`,
  `tools/v2_control/source_probe.py`, `tools/v2_control/deployment_receipt.py`,
  related v2ctl tests, and `R0C_GOLDEN_DEPLOYMENT_RECEIPT_AUTHORITY_REPORT.md`;
- RA11F generic-workflow work: `ra11f/*`, its tests, and RA11C/RA11D/RA11E
  artifacts;
- RA6R, RA9B, RA9F, RV2B, and remote raw evidence/log artifacts.

The shared `golden_serial.py` and `docs/V2_CANONICAL_DEPLOY_RUN_CONTROL_PLANE.md`
contain both RA7B hunks and unrelated concurrent hunks; only the RA7B portions
are described as RA7B above. QD, sampler, and VAE behavior were not changed by
RA7B. No remote deployment or remote integrated validation is claimed here.

## K. Exact required final fields

RA7B_COMPLETE=YES
DEFAULT_OUTPUT_DURABILITY=off
STRICT_DURABILITY_OPT_IN=YES
DEFAULT_VOLUME_OUTPUT_WRITE=NO
DEFAULT_VOLUME_COMMIT=NO
DEFAULT_REOPEN_VERIFY=NO
DEFAULT_TRUE_DURABLE_REQUIRED=NO
DEFAULT_RESULT_READY_SUPPORTED=YES
DEFAULT_RESULT_USABLE_WITHOUT_VOLUME=YES
DEFAULT_RESULT_DURABLE=NO
STRICT_VOLUME_COMMIT_PRESERVED=YES
STRICT_REOPEN_PROOF_PRESERVED=YES
STRICT_TRUE_DURABLE_PRESERVED=YES
DEFAULT_PERFORMANCE_BOUNDARY=FIRST_RESULT_READY
STRICT_PERFORMANCE_BOUNDARY=TRUE_FIRST_DURABLE_RESULT
CONFIG_SELECTOR=COMFYMODAL_OUTPUT_DURABILITY
CONFIG_MISSING_RESOLVES_TO=off
GOLDEN_CORE_SKILL_UPDATED=YES
GOLDEN_OPS_SKILL_UPDATED=YES
GOLDEN_REUSABLE_PROMPTS_UPDATED=0
HISTORICAL_PROMPTS_SUPERSESSION_MARKED=0
CANONICAL_POLICY_DOCUMENT_CREATED=YES
VALIDATORS_MODE_AWARE=YES
S4_PUBLICATION_DURABILITY_UNCHANGED=YES
QD_BEHAVIOR_CHANGED=NO
SAMPLER_BEHAVIOR_CHANGED=NO
VAE_BEHAVIOR_CHANGED=NO
STALE_POLICY_MATCHES_UNCLASSIFIED=0
FRESH_AGENT_CAN_MISTAKE_DURABILITY_AS_DEFAULT=NO
LOCAL_TESTS=449 passed, 23 skipped
REMOTE_DEPLOYS=0
POLICY_DOC=docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md
REPORT=RA7B_OUTPUT_DURABILITY_OPT_IN_MIGRATION_REPORT.md
VALIDATION_OWNER=orchestrator
FINAL_AUDIT_STATUS=PASS
