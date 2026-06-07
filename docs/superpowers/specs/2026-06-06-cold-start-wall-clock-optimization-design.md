# Cold-Start Wall-Clock Optimization Design

Date: 2026-06-06

## Goal

Reduce real cold-run latency for `comfyui-modal` with emphasis on **whole wall clock**, not just internal restore timings.

This round should:

- measure baseline and post-change performance using fresh cold containers
- capture both **full wall clock** and internal timing breakdowns
- apply pure wins automatically in the working tree for this round
- test larger restore/prompt trade-offs in a controlled way
- report exactly what changed, what won, what lost, and what remains uncertain

## Success Criteria

Primary success metric:

- lower **whole cold wall clock** from request submission to verified completed outputs

Wall-clock definition:

- full wall clock starts immediately before the benchmark harness submits the job/request
- full wall clock ends only after all expected output artifacts are received, written, and verified by the benchmark harness

Required supporting metrics:

- `restore_total_ms`
- `t3b_to_t8`
- prompt/inference timings from trace data
- per-run wall clock seconds
- median and per-run comparison across 3 cold runs
- per-fix before/after cost and savings estimates

User-approved decision rules for this round:

- **Pure win**: apply automatically
- **Net wall-clock win with startup -> prompt shift <= 300ms**: apply automatically
- **Net wall-clock win with startup -> prompt shift > 300ms**: stop and ask before applying
- **Net wall-clock win with prompt -> startup shift**: apply automatically
- **Any total wall-clock regression**: reject

An additional guardrail is required for multi-prompt behavior:

- if a change slows prompt execution, record that explicitly so repeated prompts can be evaluated separately from first-cold-run wins
- for every accepted change, report whether median prompt-side time increased, decreased, or stayed within noise
- if prompt-side time increases, estimate repeated-prompt impact separately from first-cold-run wall-clock impact

## Non-Goals

This design does **not** include:

- a broad architectural rewrite of the Modal runtime
- snapshot strategy changes that require a new product direction
- speculative optimizations without benchmark evidence
- optimization of every execution-stage node in the workflow
- UI changes
- git commits unless explicitly requested by the user

## Constraints

- Benchmark on **RTX PRO 6000 / Blackwell** only.
- Use **3 valid cold runs with 10s gaps** per configuration.
- Save every run as timestamped JSON artifacts.
- Compare **like-for-like workflow payloads**.
- Respect the user's trade-off rules above.
- Favor low-risk, no-downside wins first.
- If an apparent win may be caused by cold-cache variance, do not treat it as confirmed without repeated runs.

## Cold-Run Validity

A benchmark run counts only if it is validated as a fresh cold run.

Requirements:

- each run must include evidence that the cold lifecycle path occurred
- logs must contain the expected cold markers, including Modal startup/restore markers and `restore()` execution
- if a run reuses a warm container, skips restore, or has unclear lifecycle evidence, preserve the artifact but mark it invalid
- invalid cold-run attempts should be replaced until the benchmark set contains **3 valid cold runs**
- benchmark sets must not be compared unless both sets contain 3 valid cold runs

The 10s gap is a collection protocol, not proof of coldness. Coldness must be verified from lifecycle evidence.

## Bridge-Faithful Benchmark Requirement

`_run_benchmark.py` must measure the same runtime path and timing semantics as the Modal bridge path used by real prompt execution.

That means:

- use the same Modal class entrypoint shape as bridge-backed prompt execution
- pass client-side trace seed data into `run_prompt()` so server-side trace can compute bridge-relevant deltas
- treat the `run_prompt()` return payload, `trace`, `_restore_timing`, `_t8b_breakdown`, and output payload as the source of truth for run validation
- avoid claiming accuracy from mixed-clock derived fields unless they are explicitly marked derived/uncertain
- preserve invalid attempts as artifacts instead of silently discarding them

The benchmark harness does not need to call the browser or local ComfyUI UI layer, but it must produce the same timing model and cold/warm classification guarantees expected from the bridge path.

## Current Findings Driving This Round

From the analyzed cold run:

- Modal snapshot restore before `restore()` starts is about `7.7s`
- `restore_total_ms` is about `11.0s`
- the largest restore costs are:
  - CPU preload: about `6.55s`
  - direct warmup: about `2.96s`
  - custom-node sync: about `1.07s`

Known likely pure wins from code inspection:

- duplicate `custom_nodes_vol.reload()` calls in both `restore()` and `run_prompt()` paths
- redundant custom-node filesystem scans for sync and state collection
- misleading "early overlap" path-resolution flow that is currently sequential

Known uncertainty that should **not** be guessed at:

- whether direct UNET warmup produces enough real first-prompt benefit to justify its restore cost
- whether removing duplicate reloads changes custom-node freshness semantics between restore and first prompt

## Approaches Considered

### 1. Safe cleanup only

Apply only obvious redundancy removals and improve benchmarking.

Pros:

- lowest risk
- almost guaranteed correctness preservation

Cons:

- may leave larger wall-clock wins untouched

### 2. Aggressive wall-clock optimization

Change preload and direct-warmup behavior immediately to chase the largest cold-run wins.

Pros:

- highest potential gain

Cons:

- easiest way to accidentally shift cost into prompt latency
- easier to misread because of cold-cache variance

### 3. Hybrid staged optimization **(recommended)**

First land pure low-risk wins, then use the benchmark harness to evaluate larger restore/prompt trade-offs under explicit decision rules.

Pros:

- captures obvious wins quickly
- keeps risky decisions evidence-based
- matches the user’s nuanced trade-off rules

Cons:

- takes more benchmark rounds than a single aggressive swing

## Recommended Shape

Two coordinated lanes:

1. **Implementation lane** for pure cleanup wins and benchmark-harness improvements
2. **Benchmark lane** for baseline, post-change validation, and controlled runtime-flag experiments

The benchmark script becomes the source of truth for final reporting and must make whole-wall-clock comparisons easy to inspect.

## Architecture

### 1. Implementation Lane

Focus on low-risk code changes first.

Expected targets:

- `comfyapp.py`
  - remove duplicate custom-node volume reloads
  - reduce duplicated custom-node scan work where straightforward
  - preserve current behavior for node visibility and runtime correctness
- `custom_node_sync.py`
  - share filesystem traversal results when possible instead of scanning twice
- `_run_benchmark.py`
  - capture full wall-clock timing explicitly
  - store configuration metadata per run
  - write clearer before/after summaries for baseline versus experiment versus final

These changes are intended to improve observability and remove obvious wasted work before any riskier tuning.

Behavior guard for duplicate-reload cleanup:

- removing duplicate reloads counts as a pure win only if custom-node visibility semantics remain equivalent for a fresh cold run
- if the second reload is required to pick up post-restore volume changes before first prompt, preserve a conditional reload or treat the change as a behavior-affecting trade-off instead of a pure cleanup

### 2. Benchmark Lane

The benchmark flow should support three classes of evidence:

1. **Baseline**
   - current deployed behavior
   - 3 valid cold runs

2. **Post-cleanup validation**
   - same workflow, same GPU class, same cold-run protocol
   - verifies pure code wins are real

3. **Controlled experiments**
   - runtime-flag or preload-mode variations tested one configuration at a time
   - accepted or rejected by the user’s trade-off rules

The harness should make it easy to inspect:

- wall clock per run
- restore time per run
- prompt-side time per run
- per-config median comparison
- exact flags/config used for each benchmark set

The harness must also mirror the bridge timing model by:

- sending a trace payload with client dispatch timestamps into `run_prompt()`
- distinguishing valid cold runs from warm-container reuse using restore markers, not sleep duration
- validating output completeness before accepting a run into a comparison set
- recording post-execution payload/enrichment overhead so benchmark wall time can be separated from model execution time

## Detailed Control Flow

### Phase 1: Baseline Capture

1. Deploy current code.
2. Run cold benchmark attempts with 10s gaps until 3 valid cold runs are collected.
3. Save JSON artifacts for each run.
4. Generate a small baseline summary containing:
   - wall-clock per run
   - restore metrics per run
   - prompt metrics per run
   - medians
   - spread / variance summary
   - cold-run validity status for each attempt

### Phase 2: Pure-Win Cleanup

1. Apply duplicate-reload cleanup.
2. Apply redundant-scan cleanup if it remains behaviorally simple.
3. Improve benchmark script output so future rounds are easier to judge.
4. Re-deploy and re-run the same 3-valid-cold-run benchmark set.

If wall clock improves and no protected trade-off rule is violated, keep the change.

### Phase 3: Controlled Runtime Experiments

If needed after cleanup, test limited runtime-config changes one at a time. Candidate areas include:

- preload worker count / preload mode
- direct warmup behavior
- CPU-cache-hit requirements for direct warmup

Each experiment must be evaluated as:

- baseline median vs experiment median
- first-prompt impact
- restore impact
- whether the trade-off rule requires user approval
- whether at least 2 of 3 valid cold runs improved
- whether the observed win clearly exceeds normal run-to-run spread

### Phase 4: Final Reporting

Produce a concise final report with:

- baseline vs final whole wall clock
- baseline vs final restore time
- baseline vs final prompt-side time
- repeated-prompt impact note when prompt-side time increases
- exact changes kept
- experiments rejected
- unresolved unknowns

## Benchmark Artifact Requirements

Each benchmark run artifact should include at minimum:

- timestamp
- benchmark set ID
- run index
- run label
- config label
- git commit or code version hash
- deployed app/function identifier
- container or lifecycle identifier if available
- cold/warm classification
- validation status (`valid_cold`, `invalid_warm_reuse`, `failed`, `incomplete`)
- full wall-clock seconds
- request submit timestamp
- output completion timestamp
- output count
- output byte size
- restore timing blob
- trace timing blob
- Modal lifecycle/log timing markers
- selected runtime flags / preload mode / GPU class
- workflow identifier or hash
- prompt/workflow payload hash
- error message or log excerpt if failed
- pricing inputs used for cost calculations
- derived cost per cold run
- derived savings versus comparison set when available

Each benchmark set should also have a human-readable summary that shows:

- per-run values
- median values
- delta versus comparison set
- best/worst spread
- whether at least 2 of 3 runs improved
- keep/reject judgment

## Cost and Savings Matrix

Final reporting must include a matrix for each proposed fix or tested configuration.

Each row should include:

- fix/config label
- baseline benchmark set ID
- comparison benchmark set ID
- baseline median wall clock
- comparison median wall clock
- wall-clock delta in ms and percent
- baseline median `restore_total_ms`
- comparison median `restore_total_ms`
- baseline median prompt-side metric used for judgment
- comparison median prompt-side metric used for judgment
- best/median/worst spread for both sets
- number of valid cold runs in both sets
- benchmark validity judgment
- assumed GPU hourly cost and any other explicit pricing inputs
- estimated cost per cold start before and after
- estimated savings per cold start
- estimated savings for larger volumes such as 100 and 1,000 cold starts

Cost formulas must stay explicit in artifacts and summaries so the reported savings can be audited later.

## Output Correctness Validation

Each benchmark run must verify:

- expected number of output images/artifacts
- successful output transfer and save
- no server-side exception
- same workflow payload hash across compared runs

If output validation fails, the run cannot be used for performance acceptance.

## Error Handling

Failure states should stay explicit.

Possible benchmark outcomes:

- `deploy_failed`
- `benchmark_failed`
- `incomplete_run_set`
- `comparison_blocked_by_variance`
- `ok`

Rules:

- If deploy fails, stop and preserve logs.
- If any run fails, keep completed artifacts and mark the set incomplete.
- If the result is too noisy to justify a decision, do not claim a win.
- If a trade-off crosses the user’s approval threshold, stop and ask before applying it.

Acceptance logic:

- accept automatically only if median whole wall clock improves, output validation passes, and the applicable startup/prompt trade-off rule allows automatic acceptance
- reject if median whole wall clock regresses, output validation fails, or prompt-side regression needs approval and has not been approved
- mark `comparison_blocked_by_variance` if results are mixed, cold/warm classification is unclear, variance is larger than the observed win, or fewer than 2 of 3 valid cold runs improve without a clearly outsized median win

## Testing Strategy

Testing for this round has two layers.

### Code-correctness checks

- run targeted tests covering restore timing flow and custom-node sync behavior where relevant
- add or adjust tests only when implementation changes need protection

### Performance checks

- benchmark attempts with 10s gaps until 3 valid cold runs are collected
- same workflow and GPU class across comparisons
- compare medians and inspect per-run spread

## Repeated-Prompt Impact

For changes that reduce restore time by moving work out of startup, report whether prompt-side execution became slower.

If prompt-side median increases, include a separate note estimating impact on repeated prompts in the same warm container. First-cold-run wins and repeated-prompt regressions must be reported separately.

## Caching and Concurrency Guidance

Safe recommendations for this round:

- reuse resolved model paths within a restore/request instead of resolving the same model files repeatedly
- keep the existing CPU model cache and CLIP object cache, but improve evidence around hit rate and actual user-visible benefit before adding broader cache layers
- collapse custom-node sync and state capture into a single filesystem pass where possible
- prefer threads for FUSE and model-file I/O work
- overlap small independent I/O work, such as path resolution, with GPU-state and CUDA restore work when the lifecycle markers remain clear

Ideas to avoid unless strong evidence appears:

- moving model preload back into snapshot/startup if it inflates snapshot restore time
- multiprocessing for model preload or direct warmup
- parallel UNET and CLIP GPU loads in separate workers
- blindly increasing preload worker counts without benchmark proof

Top experiments after pure cleanup wins:

- benchmark CLIP-only direct warmup versus UNET+CLIP direct warmup
- benchmark reduced preload scope or budgeted preload modes paired with CPU-cache-hit requirements
- benchmark safer gating of prompt-time custom-node sync for repeated-prompt latency, only if correctness semantics remain protected

## Files Expected to Change

- `comfyapp.py`
- `custom_node_sync.py`
- `_run_benchmark.py`
- relevant tests if behavior or instrumentation requires coverage

## Open Questions Intentionally Deferred to Benchmark Evidence

These are not design blockers, but they are not to be assumed without data:

- whether direct UNET warmup is a net win for real first-prompt latency
- whether preload worker changes help or merely shift latency around
- how much of remaining cold time is dominated by Modal snapshot restore outside `restore()`

## Final Recommendation

Use the hybrid staged approach.

Start by landing pure cleanup wins and better benchmark reporting. Then use the improved harness to evaluate larger restore/prompt trade-offs under the user’s rules, with explicit stop points for cases that need approval.
