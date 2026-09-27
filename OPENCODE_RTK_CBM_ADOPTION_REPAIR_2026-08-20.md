# OpenCode RTK + Codebase Memory Adoption Repair — 2026-08-20

## Executive result

- **RTK:** runtime rewriting and canonical installation are both **PASS**. No further RTK work is part of this pass.
- **CBM MCP, guidance/skill presence, and parent graph-first behavior:** **PASS**. Presence and hash evidence do not by themselves prove that an artifact was loaded or adopted by a child.
- **Fresh Explorer, Fixer, and Oracle natural CBM adoption:** **FAIL**. Each fresh child used native discovery and made zero CBM tool calls.
- **Positive automatic Grep/Glob augmentation:** **FAIL**. The hook remained bounded and fail-open, but the trace produced no non-empty context.
- **Freshness:** synthetic watcher behavior, real currentness, and fresh-session automatic freshness are **FAIL**. The installed watcher semantics and a real incremental `index_repository` refresh were observed, but the requested automatic change-event proof was not established.

## Status table

| Capability | Status |
|---|---|
| RTK runtime rewriting | PASS |
| RTK canonical installation | PASS |
| CBM MCP | PASS |
| CBM guidance/skill | PASS |
| CBM parent natural adoption | PASS |
| CBM Explorer natural adoption | FAIL |
| CBM Fixer natural adoption | FAIL |
| CBM Oracle natural adoption | FAIL |
| CBM Grep/Glob positive augmentation | FAIL |
| CBM augmentation fail-open | PASS |
| CBM synthetic watcher | FAIL |
| CBM real graph currentness | FAIL |
| CBM fresh-session automatic freshness | FAIL |

## Corrected RTK wording

“RTK was runtime-functional before this pass, but its OpenCode installation was noncanonical and RTK's own discovery check did not recognize the custom Windows-safe filename. This pass canonicalized the path, removed the duplicate, and reconfirmed transparent rewriting.”

No further RTK work is claimed here.

## Actual OpenCode after-hook shape

OpenCode 1.18.19 runtime `tool.execute.after(input, output)` was inspected for both native Grep and native Glob:

- `input` keys: `tool`, `sessionID`, `callID`, `args`, `attachments`, `metadata`, `output`, `title`.
- `output` keys did not include `args`.
- `input.args` contained sanitized path/pattern fields; `output.args` was absent.

The adapter changed only `output?.args` to `input?.args`. Its 8,192-byte cap, 1,500 ms timeout, in-flight guard, and fail-open behavior were unchanged.

## CBM augmentation before/after

Before:

```text
tool.execute.after(input, output) -> augment(tool, output?.args)
```

After:

```text
tool.execute.after(input, output) -> augment(tool, input?.args)
```

This corrected the runtime argument source identified above. It did not change the cap, timeout, in-flight guard, or fail-open behavior.

## Positive augmentation trace

The temporary diagnostic did not prove positive automatic augmentation:

- Native Grep: child exited 0; response was 188 bytes; context was 0; the invalid-response fallback was used; elapsed time was 1,488 ms.
- Native Glob: timed out at the 1,500 ms limit; elapsed time was 1,507 ms.
- Native results were retained in both cases.
- The target project existed in the target-context run.
- There were no CBM tool calls, one Grep and one Glob, and no recursion or duplicates.
- Augmentation was 0 bytes / 0 tokens, with no non-empty context.

**Result: FAIL for positive automatic augmentation.** The state-protocol/latency blocker must not be called PASS. The separate fail-open behavior is PASS.

## Child session/tool table

These were natural fresh child exports. Tool names and arguments are shown only in sanitized order; loading a skill or enumerating resources is not a CBM tool call.

| Role / session ID | Sanitized tool order | CBM calls | Edits |
|---|---|---:|---|
| Explorer / `ses_fdf327860ffeYCsgnNmVZldMoG` | `ast_grep_search → grep → glob → read` | 0 | None |
| Fixer / `ses_fdf3277f6ffegZhJAtjQOUQ6b8` | loaded `codebase-memory` skill; `grep → grep → glob → read → ast_grep_search → grep → grep` | 0 | None |
| Oracle / `ses_fdf3277c2ffeTLdWndiNFWbGdJ` | loaded `codebase-memory` skill; resource enumeration; `grep → glob → read → ast_grep_search → grep → read` | 0 | None |

Explorer's first source-discovery tool was `ast_grep_search`. Fixer and Oracle loaded the skill but still used native discovery; resource enumeration for Oracle was not a CBM tool call. These results are **FAIL** for natural child adoption, not evidence that the configured surfaces were absent.

The parent/orchestrator did use CBM graph-first navigation and is **PASS** for the required parent natural-adoption row.

## OMO instruction delta (unchanged/not needed)

No OMO instruction delta was needed for this report-only reconciliation. Effective artifact presence/hash evidence is recorded below, but presence does not mean an artifact was loaded or adopted:

| Artifact | SHA-256 |
|---|---|
| `AGENTS.md` | `2B5886D4ED87E64316D348CD460DAE17046C3159A6E5846B06A47A20748D1340` |
| `skills/codebase-memory/SKILL.md` | `8EFE4AA10EFA92B52148CCE5840ABAC552B92E5DC3AF567E5D167A5E33624DB1` |
| Active OMO config | `FDECE5E446539C963BEE38E266C6B00688F2B5EC35D088C63E3DF2B93C76EA96` |
| Orchestrator append | `D3750591F131BD7C681321549BA6AE5959F75888B82F4BFD130311A72E3AFE2E2` |

## Installed-version freshness semantics

Installed CBM 0.10.8 uses a shared watcher with a 5,000 ms base adaptive interval, increasing by 1,000 ms per 500 tracked files, capped at 60,000 ms. Detection is Git-based status/HEAD/mtime-size detection, not `fsnotify`. Changed, added, and deleted files go through incremental removal, reparse, and republish.

Prior indexed-project registration requires a normal session, an existing database, and `auto_watch`. New-project automatic indexing depends on the `auto_index` settings. There is no public refresh API beyond `index_repository`. `metadata_changed` means the stored mtime/size differs; it does not necessarily mean file content changed.

## Synthetic watcher timeline

The test used a unique disposable repository and cache; cleanup completed.

| Event | Observation |
|---|---|
| Initial, `20:38:04.549` | 23 nodes / 36 edges |
| Relationship commit, `20:38:04.687`; waited until `20:38:10.188` | Unchanged |
| Add commit, `20:38:10.612`; waited until `20:38:16.113` | Unchanged; no `extra.py` |
| Delete commit, `20:38:16.270`; waited until `20:38:21.772` | Unchanged |
| Fresh normal OpenCode, started `20:38:21.819`, exited `20:38:40.185` | Could list the already-indexed synthetic project and status without manually starting the watcher; no generation field was exposed |

**Synthetic watcher: FAIL.** The mutation sequence did not show refresh, and brand-new auto-index was not separately exercised. The fresh-session observation is not automatic freshness proof.

## Real project refresh proof

- Pre-refresh generation: `2026-08-20T14:36:04Z`; 45,681 nodes; 245,456 edges; 358,023,168 bytes.
- Four selected coverage paths were all `metadata_changed`.
- One existing-project `index_repository` call took approximately 16,983 ms and was recognized as incremental.
- Post-refresh ready generation: `2026-08-20T20:45:51Z`; 45,721 nodes; 245,576 edges; 358,154,240 bytes.
- Post-refresh diagnostics reported one skipped parse-timeout and one parse-partial.
- The same four paths still reported `metadata_changed`.
- No files-processed count was exposed.
- Reversible fixture cleanup restored the real project state.

**Real graph currentness: FAIL.** This proves an explicit existing-project refresh, not automatic watcher currentness.

## Real watcher proof

No watcher event/change proof is claimable from the real project run. The reversible fixture cleanup was restored, but it did not establish that the watcher observed and processed the change. No stronger real-watcher claim is made.

## Fresh-session proof

The fresh normal OpenCode session could list the already-indexed synthetic project and status without manually starting a watcher. That does not prove a newly created project is auto-indexed, does not expose a generation field, and does not prove that changed files are automatically current in a new session.

**Fresh-session automatic freshness: FAIL.**

## Files changed

- `OPENCODE_RTK_CBM_ADOPTION_REPAIR_2026-08-20.md` — this report.
- `C:\Users\parla\.config\opencode\plugins\cbm-augment.ts` — installed adapter narrowed from `output?.args` to `input?.args`; its existing bounds and fail-open behavior were preserved.

No cache/TUI audit, repository source, graph database, or unrelated file was changed.

## Backups

Runtime proof created and retained these external backups/evidence files:

- `C:\Users\parla\AppData\Local\Temp\opencode\cbm-augment.ts.pre-runtime-proof-20260820.bak`
- `C:\Users\parla\AppData\Local\Temp\opencode\cbm-runtime-proof-20260820.jsonl`
- `C:\Users\parla\AppData\Local\Temp\opencode\cbm-runtime-safety-20260820.jsonl`
- `C:\Users\parla\AppData\Local\Temp\opencode\cbm-augment-diagnostic.jsonl`

Previously recorded RTK/CBM backups were not modified.

## Rollback

Rollback of the report change means restoring only this report from the repository’s prior revision, for example:

```powershell
git restore -- OPENCODE_RTK_CBM_ADOPTION_REPAIR_2026-08-20.md
```

The adapter correction can be rolled back separately by restoring `C:\Users\parla\AppData\Local\Temp\opencode\cbm-augment.ts.pre-runtime-proof-20260820.bak` to the installed plugin path. That rollback does not change the graph, cache, TUI, repository source, or other files.

## Remaining limitations

1. Positive automatic CBM augmentation remains unproven because the diagnostic produced 0 bytes / 0 tokens; the state-protocol/latency blocker remains.
2. The synthetic watcher did not refresh relationship, add, or delete mutations; brand-new auto-index was not separately exercised.
3. Real refresh was explicit and incremental, while the same four coverage paths remained `metadata_changed`; watcher event/change proof is not claimable.
4. No files-processed count or graph generation field was exposed in the relevant fresh-session checks.
5. Natural Explorer, Fixer, and Oracle sessions made zero CBM tool calls despite effective presence/hash evidence for guidance, skill, OMO config, and orchestrator append.
6. Child post-hook RTK telemetry is not exposed; transparent rewriting was reconfirmed at runtime, with no further RTK work undertaken here.

Validation owner: **parent orchestrator**.

## Batch O4 continuation — daemon lifecycle and OMO alignment

### Final status

| Capability | Status |
|---|---|
| CBM official daemon lifecycle | FAIL / not automatic in the tested native-only session |
| Grep automatic augmentation | FAIL by default; PASS only with an explicitly live daemon and propagated CBM environment |
| Windows hook deadline | UNRESOLVED; 300 ms was not proven causal |
| Watcher auto-freshness | PASS in synchronized synthetic lifecycle; real coverage remains blocked by checker false positive |
| Explorer structural CBM adoption | FAIL in current OMO process; append guidance is configured but not freshly validated after reload |
| Oracle structural CBM adoption | FAIL in current OMO process; append guidance is configured but not freshly validated after reload |
| Fixer appropriate on-demand CBM | PASS for role design; current natural tests made no CBM call because supplied tasks did not require missing impact context |

### Daemon lifecycle root cause

The execution classes are not equivalent:

| Operation | Starts daemon | Connects daemon | Requires daemon for graph context | Works without daemon |
|---|---|---|---|---|
| OpenCode MCP initialize | session/lifecycle-dependent | yes when a CBM session is actually admitted | for shared project/session state | initialize alone did not establish it in the tested native-only run |
| `hook-augment` | no per invocation | uses the shared runtime when available | yes for non-empty graph context | returns a valid admission/system response but no useful context |
| `cli search_graph` | no | no | no shared daemon path | direct CLI semantics are separate and may see no registered projects |
| watcher registration | no | daemon-owned | yes | no |
| normal parent CBM MCP call | official lifecycle starts/attaches the shared daemon | yes | yes | not applicable |

Observed causal A/B with the same sanitized payload:

- **A, daemon absent:** valid JSON admission response with `systemMessage` only; no `hookSpecificOutput` or `additionalContext`.
- **B, official daemon active with target project registered and CBM environment propagated:** valid envelope; Grep `additionalContext` 641 bytes and Glob 948 bytes; native results retained.
- **C, same daemon warm:** valid non-empty envelope again.

The first divergence in the default native-only path is before `hook-augment`: no shared daemon is admitted, and the plugin child does not inherit the MCP server’s `CBM_CACHE_DIR`/`CBM_RUNTIME_DIR` environment. The adapter therefore fails open rather than creating a daemon per Grep.

The installed adapter currently contains a guarded session-scoped `daemon status/start` assurance and explicitly propagates those configured environment variables. That change was left unverified after its validation process stopped without a terminal result; no daemon was left running.

### Exact hook protocol and Windows deadline

Successful direct v0.10.8 calls return:

```text
hookSpecificOutput: object
  hookEventName: string
  additionalContext: string
```

The prior 188-byte response was valid JSON with only `systemMessage: string`; it was a daemon-admission notice, not malformed JSON and not a graph-result envelope. The adapter correctly extracts only `hookSpecificOutput.additionalContext` and fails open for the admission response.

Direct active-daemon timings were 1,249–1,627 ms. They exceeded the Windows source constant `HA_DEADLINE_MS 300` yet completed successfully, so the 300 ms timer was **not proven causal** in this environment. No binary patch or upgrade was made. The adapter’s outer budget is 2,200 ms, with the original 8,192-byte bound and fail-open behavior preserved.

### Positive augmentation and latency

Direct active-daemon proof is positive: Grep produced 366 bytes and Glob 1,061 bytes of bounded context in valid envelopes. The default fresh native-only OpenCode path produced zero context because the shared daemon/environment lifecycle was absent. A final session-scoped validation attempt stopped without a terminal result, so automatic augmentation is not marked PASS.

### OMO × CBM source-level routing conflict

OMO’s built-in Explorer prompt intentionally favors `ast_grep_search`, grep, glob, and read for fast navigation; Fixer is implementation-focused and says not to broaden research; Oracle receives native inspection guidance. This explains the observed zero-call behavior and is not permission filtering: active configuration exposes the CBM MCP tools, and Fixer/Oracle loaded the CBM skill in some exports.

The role model is now aligned with append-only prompt files:

- Explorer: CBM-first for structural symbols, callers/callees, dependencies, and cross-file relationships; native tools for literals/configs/coverage gaps/exact source.
- Oracle: CBM-first for architecture, impact, cross-file debugging, and coverage-aware verification; native exact checks afterward.
- Fixer: implementation-first; CBM only when missing structural impact/dependency context blocks safe implementation.

Append prompt fingerprints after alignment:

| File | Bytes | SHA-256 |
|---|---:|---|
| `explorer_append.md` | 283 | `C500F8741D6D8B7260329E74FFD2419148BF20C1BF68520DC95C3840A25CAB76` |
| `oracle_append.md` | 241 | `3E722558563E64C2A270F92DF1CB8A31277E5A70353730954403617458FF3235` |
| `fixer_append.md` | 268 | `0F223CB67649A452A592107605BF08B3291244FB5C24E08C158E26A2C94C220D` |

The current OMO parent process cached earlier prompt state; fresh child exports from that process still made zero CBM calls. A separately restarted normal OMO process is required to validate the append files. No child permission absence was inferred from zero calls.

### Watcher-registration proof and corrected synthetic timeline

The synchronized synthetic test is **PASS**. Before mutation it proved the MCP client and daemon alive, project registration, `watcher.watch`, `watcher.start interval_ms=multi-sec`, and the first completed `watcher.baseline`. Observed causal timeline:

```text
16:23:00.748  mutation relationship
16:23:05.972  watcher.changed
16:23:08.390  reindex complete; alpha -> gamma
16:23:08.408  mutation file add
16:23:13.643  watcher.changed
16:23:16.263  reindex complete; added() present
16:23:16.286  mutation file delete
16:23:21.520  watcher.changed
16:23:24.138  reindex complete; ephemeral() absent
```

The synthetic project, daemon, and artifacts were removed. This supersedes the earlier unsynchronized synthetic FAIL.

### Real metadata root cause and freshness blocker

For all four selected files, stored/live size, nanosecond mtime, FILETIME, content-hash prefix, project identity, database UID, and generation matched; five OneDrive stability samples also remained unchanged. The false `metadata_changed` result is caused by v0.10.8 comparing FILETIME-derived UTC nanoseconds captured by `cbm_path_info_utf8()` against Windows CRT `stat()` seconds/local-time-derived timestamps in `coverage_path_freshness()`.

Upstream issue #1714 remains open. The correct source repair is to use `cbm_path_info_utf8()` in the coverage checker and compare its canonical size/mtime fields. No supported Windows compiler toolchain is installed: MSYS2/MinGW/LLVM and GNU make are absent. MSVC/nmake is not the project’s supported reproducible build path. Therefore no binary replacement was attempted and real coverage currentness remains blocked without unsafe mutation.

### Files, hashes, backups, and rollback

Changed outside the repository:

- `C:\Users\parla\.config\opencode\plugins\cbm-augment.ts` — input argument correction, 2,200 ms evidence-backed bound, default export, explicit CBM environment propagation, and guarded session-scoped daemon assurance; SHA-256 `A59F545E13F703A6322BEC0F70B1C2FDC9523CCBF12F472CD2AE2A5593B6F5C6`.
- `C:\Users\parla\.config\opencode\oh-my-opencode-slim\explorer_append.md`, `oracle_append.md`, `fixer_append.md` — append-only role guidance above.
- Repository `AGENTS.md` — one workspace routing directive.
- `CBM_HOOK_AUGMENT_FORENSICS_2026-08-20.md` — direct forensic evidence.

Recorded adapter backups include `C:\Users\parla\AppData\Local\Temp\opencode\cbm-augment.ts.pre-runtime-proof-20260820.bak` and `cbm-augment.ts.pre-timeout-2200-20260820.bak`. The original v0.10.8 executable SHA-256 is `B4B403B1D7C4DEF3785F148B93F345CE8427858F4F5489CE28580C4387A336A`; it was not replaced. Roll back the adapter/config files from those backups or remove the append files and repository `AGENTS.md`; do not delete or rebuild the graph.

### Remaining blockers

1. Official daemon/session lifecycle is not yet proven automatic in a normal native-only OpenCode session; the session-scoped adapter assurance is unverified.
2. Automatic augmentation is positive with an explicitly live daemon and propagated environment, but not yet PASS for default fresh-session startup.
3. Explorer and Oracle append guidance needs validation in a newly restarted OMO process; current parent-process children remain zero-call failures.
4. Real `metadata_changed` requires a supported Windows source rebuild to repair the checker; the graph itself is current by stored metadata/content evidence.
