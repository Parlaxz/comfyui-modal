# CBM hook-augment forensics — 2026-08-20

Validation owner: **parent orchestrator**

## Scope and guardrails

- Tested the installed Codebase Memory MCP release **0.10.8** directly.
- Used the existing indexed target project; no graph rebuild, index mutation, or
  installed adapter/binary patch was performed.
- Grep and Glob were each run in a separate MCP session as **cold**, **warm**,
  and **second-warm** hook invocations.
- Payload values are intentionally omitted. The payload shape was the valid
  PreToolUse form: top-level `hook_event_name`, `tool_name`, and absolute `cwd`,
  plus `tool_input.pattern`. Grep used a known graph symbol token; Glob used a
  meaningful indexed filename token. The known project identity and cwd were
  validated but are not reproduced here.
- No response text, source text, prompts, or paths are recorded in this report.

## Direct hook result shape

All six positive direct invocations exited `0` and returned valid JSON.

| Tool | Run | Wall ms | Exit | stdout bytes | Valid JSON | Top-level keys/types | hookSpecificOutput keys/types | additionalContext bytes |
|---|---|---:|---:|---:|---|---|---|---:|
| Grep | cold | 1401.906 | 0 | 445 | yes | `hookSpecificOutput: object` | `additionalContext: string`, `hookEventName: string` | 366 |
| Grep | warm | 1627.187 | 0 | 445 | yes | `hookSpecificOutput: object` | `additionalContext: string`, `hookEventName: string` | 366 |
| Grep | second-warm | 1249.710 | 0 | 445 | yes | `hookSpecificOutput: object` | `additionalContext: string`, `hookEventName: string` | 366 |
| Glob | cold | 1395.575 | 0 | 1144 | yes | `hookSpecificOutput: object` | `additionalContext: string`, `hookEventName: string` | 1061 |
| Glob | warm | 1428.342 | 0 | 1144 | yes | `hookSpecificOutput: object` | `additionalContext: string`, `hookEventName: string` | 1061 |
| Glob | second-warm | 1396.528 | 0 | 1144 | yes | `hookSpecificOutput: object` | `additionalContext: string`, `hookEventName: string` | 1061 |

The context byte counts are UTF-8 byte counts, not character counts.

## Elapsed boundaries

The installed binary exposes no internal stage telemetry. The following are the
only measured boundaries, with no inferred stage values:

| Tool | Server spawn → MCP initialize ms | Run | spawn → main | project resolution | search_graph | first stdout → process close ms | total wall ms |
|---|---:|---|---|---|---|---:|---:|
| Grep | 4213.273 | cold | unavailable | unavailable | unavailable | 3.273 | 1401.906 |
| Grep | 4213.273 | warm | unavailable | unavailable | unavailable | 2.474 | 1627.187 |
| Grep | 4213.273 | second-warm | unavailable | unavailable | unavailable | 2.867 | 1249.710 |
| Glob | 3850.851 | cold | unavailable | unavailable | unavailable | 2.510 | 1395.575 |
| Glob | 3850.851 | warm | unavailable | unavailable | unavailable | 2.830 | 1428.342 |
| Glob | 3850.851 | second-warm | unavailable | unavailable | unavailable | 2.909 | 1396.528 |

`first stdout → process close` is an observed process boundary only; it is not
claimed to be the internal output stage. No `spawn → main`, project-resolution,
or `search_graph` timings were invented. A temporary source checkout was used
only for version-specific behavioral inspection and was removed; no instrumented
binary was built because this Windows environment had no compiler driver.

## Prior 188-byte response

The prior 188-byte result was structurally different from a successful hook
result:

- valid JSON: yes;
- top-level keys/types: `systemMessage: string`;
- `hookSpecificOutput`: absent;
- `additionalContext`: absent / 0 bytes.

It was the daemon-admission notice for a hook invocation without an active CBM
daemon, not a graph-result envelope. The current adapter parses JSON and reads
only `hookSpecificOutput.additionalContext`; therefore that response correctly
produces an empty augmentation and leaves the native tool output unchanged.

## Current adapter extraction and fail-open checks

The installed adapter was tested without modification. Its exact runtime path is:

1. lower-case native `grep`/`glob` selects the corresponding hook tool;
2. the hook receives `input.args` (not `output.args`);
3. only a string `hookSpecificOutput.additionalContext` is eligible;
4. augmentation is appended only when the native `output.output` is a string;
5. spawn, parse, timeout, malformed-result, and unsupported-output failures
   resolve to no augmentation.

Observed adapter checks (response text intentionally omitted):

| Case | Result |
|---|---|
| Grep with valid `input.args` | mutated native output; 371 output bytes from a 4-byte baseline |
| Grep with args present only on `output` | unchanged 4-byte output; fail-open after the adapter timeout boundary |
| Unsupported native tool | unchanged; no augmentation subprocess needed |
| Valid Grep args with non-string native output | unchanged; no throw |
| Glob with valid `input.args` | unchanged when the 1500 ms adapter timeout elapsed; no throw |

This confirms both the exact extraction source and fail-open behavior. No
installed adapter or binary was patched.
