# Phase 2 cache/dashboard verification

**Validation owner:** orchestrator  
**Date:** 2026-08-20  
**Scope:** verification of already-installed artifacts only. No package installation, model request, DCP/OMO/MCP/RTK/session/DB edit, or source-code edit was performed. The only repository write is this report. Smoke-test logs were written under the permitted dashboard tool directory.

## Result

| Claim | Result | Evidence / limitation |
|---|---|---|
| Active `tui.json` contains OMO and both requested cache plugins | **PASS** | Exact active configuration and parsed assertions below. |
| Package metadata and entrypoint resolution | **PASS** | Installed package metadata, `import.meta.resolve`, and in-memory Bun builds pass. |
| Runtime import of both TUI plugins | **PARTIAL** | Visual-cache and OMO import successfully. `opencode-cache-hit` direct Bun import fails in this environment while resolving `@opentui/solid/jsx-runtime.d.ts`; syntax/build and package resolution still pass. |
| Privacy-conscious cache-hit timeline configuration | **PASS by inspection** | Timeline is enabled; `toolSummary.allTools=false` and `bash=false`; record schema contains metrics, not prompt/file-content fields. |
| Dashboard binary and official SHA-256 | **PASS** | Binary exists at the requested path and matches the supplied hash exactly. |
| Local dashboard HTTP smoke | **PASS with endpoint latency limitation** | Loopback health/root and cache-session/session-detail routes returned structurally; `/api/usage` timed out at 120 s. |
| Test-process cleanup / loopback binding | **PASS** | Smoke listener was `127.0.0.1`; post-check found no dashboard process and no test-port connections. |
| Live-current-process TUI loading | **NOT CLAIMED** | A restart is required to make `tui.json` changes live in an already-running OpenCode process; this verification did not restart the user's TUI. |

## 1. Active TUI configuration

Command:

```powershell
$p='C:\Users\parla\.config\opencode\tui.json'
$j=Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
Write-Output ("TUI_PATH={0}" -f $p)
Write-Output ("TUI_PLUGINS={0}" -f ($j.plugin -join ' | '))
Write-Output ("HAS_OMO={0}" -f [bool]($j.plugin -contains 'oh-my-opencode-slim'))
Write-Output ("HAS_CACHE_HIT={0}" -f [bool]($j.plugin -contains 'opencode-cache-hit@0.7.0'))
Write-Output ("HAS_VISUAL_CACHE={0}" -f [bool]($j.plugin -contains 'opencode-visual-cache@1.6.3'))
```

Output:

```text
TUI_PATH=C:\Users\parla\.config\opencode\tui.json
TUI_PLUGINS=oh-my-opencode-slim | opencode-cache-hit@0.7.0 | opencode-visual-cache@1.6.3
HAS_OMO=True
HAS_CACHE_HIT=True
HAS_VISUAL_CACHE=True
```

The separate server config was not changed. `opencode debug config` reported OpenCode `1.17.20`; its `plugin_origins` output is for `opencode.json` and does not constitute live TUI loading proof. The TUI resolution evidence is in the next section.

## 2. Package metadata, resolution, and load/syntax checks

Installed package metadata:

```text
opencode-cache-hit: name=opencode-cache-hit version=0.7.0 type=module exports=.,./tui,./tui-panel
opencode-visual-cache: name=opencode-visual-cache version=1.6.3 type=module exports=./server,./tui
oh-my-opencode-slim: name=oh-my-opencode-slim version=2.2.14 type=module exports=.,./server,./tui
```

Exact resolution output from Bun:

```text
RESOLVE oh-my-opencode-slim/tui -> file:///C:/Users/parla/.config/opencode/node_modules/oh-my-opencode-slim/dist/tui.js
RESOLVE opencode-cache-hit/tui -> file:///C:/Users/parla/.config/opencode/node_modules/opencode-cache-hit/index.tsx
RESOLVE opencode-visual-cache/tui -> file:///C:/Users/parla/.config/opencode/node_modules/opencode-visual-cache/dist/tui.js
```

In-memory syntax/build check (Bun `write:false`, so no build artifact was written):

```text
cache-hit-entrypoint syntax_build_success=true outputs=1
visual-cache-tui syntax_build_success=true outputs=1
omo-tui syntax_build_success=true outputs=1
```

Direct import check:

```text
CACHE_IMPORT
SyntaxError: Export named 'Fragment' not found in module 'C:\Users\parla\.config\opencode\node_modules\@opentui\solid\jsx-runtime.d.ts'.
VISUAL_TUI_IMPORT
visual-cache/tui import keys=default
OMO_TUI_IMPORT
omo/tui import keys=default,getContrastForeground,getSidebarAgentNames,readCompactSidebar,readConfigInvalid,splitSidebarModelId
```

Interpretation: both requested package names resolve to installed entrypoints and all three entrypoints pass syntax/build parsing. Visual-cache and OMO load directly. The cache-hit direct-import failure is a real environment/package-loader compatibility blocker for a stronger runtime-load claim; it is not silently treated as a pass. No dependency was installed or changed to work around it.

## 3. Cache-hit timeline privacy and metrics

Active file: `C:\Users\parla\.config\opencode\cache-hit.json`

Relevant exact values:

```json
"timeline": {
  "enabled": true,
  "dir": "~/.local/share/opencode/logs/cache-hit",
  "flushIncomplete": false,
  "logSummaryMessages": true,
  "maxMemoryRows": 50,
  "maxLinesPerFile": 100000,
  "rotateMaxBytes": 16777216,
  "retainRotated": 5,
  "maxAgeDays": 30,
  "maxLogFiles": 20,
  "toolSummary": {
    "allTools": false,
    "bash": false
  }
}
```

Evidence from installed source:

- `src/plugin-config.ts:71-79` documents tool summaries as privacy-sensitive hints and says `false` records only tool and duration, while bash input may contain credentials/tokens/paths.
- `src/timeline/records.ts:60-90` emits timestamps, IDs, model/provider IDs, token counters, cost, hit percentage, timing, finish, and optional tool durations; it has no prompt, assistant text, or file-content field.
- `src/tool-timing.ts:126-135` only creates a summary when `isSummaryEnabled(tool)` is true. With active `allTools=false`, no tool summaries are enabled, including bash/read/write/edit.
- `src/timeline/types.ts:4-40` defines the JSONL record shape and contains no text/file-content field.

Therefore the active configuration enables timeline/cache/token/timing metrics while disabling bash and file/tool summaries. `logSummaryMessages=true` does not change the record schema into a chat transcript; it controls whether eligible assistant summary messages are considered by the collector.

No timeline directory currently exists at `C:\Users\parla\.local\share\opencode\logs\cache-hit`, so no new JSONL record was generated by this read-only verification. This is expected without a live restarted TUI process receiving assistant events.

## 4. Dashboard artifact and database

Command:

```powershell
$p='C:\Users\parla\.local\share\opencode\tools\opencode-token-dashboard-v1.3.0.exe'
$i=Get-Item -LiteralPath $p
Get-FileHash -LiteralPath $p -Algorithm SHA256
```

Output:

```text
FILE=C:\Users\parla\.local\share\opencode\tools\opencode-token-dashboard-v1.3.0.exe
LENGTH=9764733
FILE_VERSION=
PRODUCT_VERSION=
SHA256=9113a3b7c8207abd525a47ec2a85ae11bd2494f92a8d9237551e01b457a944eb
```

The requested official SHA-256 is an exact match. The PE version-resource fields are empty; the filename is the available `v1.3.0` artifact identity.

Database:

```text
PATH=C:\Users\parla\.local\share\opencode\opencode.db
EXISTS=True
LENGTH=76233867264 bytes (observed during structural query)
DB_READ_ONLY=True
```

The database was opened with SQLite URI `mode=ro` and `PRAGMA query_only=ON`. No row values containing titles, prompts, message text, paths, or file contents were selected.

Structural schema and historical aggregate evidence:

```text
COUNT table=project rows=7
COUNT table=session rows=5996
COUNT table=message rows=231447
COUNT table=part rows=1100231
COUNT table=session_input rows=0
COUNT table=session_message rows=0
first_session_utc=2026-05-04 05:19:04
last_session_utc=2026-08-20 14:46:51
assistant_messages=206188
input_sum=1902596230
output_sum=79173095
reasoning_sum=78091005
cache_read_sum=30627336511
cache_write_sum=10623673
assistant_with_cache_read=197584
assistant_with_cache_write=795
sessions_with_assistant=5811
sessions_with_assistant_cache_read=5411
sessions_with_assistant_cache_write=4
assistant_messages_with_cache_miss_input=204414
```

This establishes historical session, token, and cache structural visibility without exposing content. The dashboard and DB totals can differ in naming/aggregation (for example, dashboard `totalExpected` includes its own cache-miss calculation), so they are not asserted as identical.

## 5. Launcher/smoke scripts and controlled HTTP smoke

Static inspection of both scripts confirms:

```text
opencode-token-dashboard-start.ps1:20  $env:HOST = "127.0.0.1"
opencode-token-dashboard-start.ps1:21  $env:PORT = "$Port"
opencode-token-dashboard-smoke.ps1:21  $env:HOST = "127.0.0.1"
opencode-token-dashboard-smoke.ps1:22  $env:PORT = "$Port"
opencode-token-dashboard-smoke.ps1:108 Stop-Process -Id $process.Id -Force
```

The launcher is intentionally a long-lived start command; it refuses to attach to an existing dashboard. The smoke script owns and forcibly stops its test child in `finally`. No script fix was necessary.

### Official smoke script, unused port 18785

Command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\parla\.local\share\opencode\tools\opencode-token-dashboard-smoke.ps1 -Port 18785 -WaitSeconds 15 -ApiTimeoutSeconds 120
```

Output:

```text
PORT_18785_FREE=True
HTTP path=/health status=200 content_type=application/json bytes=11
LISTENER local=127.0.0.1:18785 pid=24744
HTTP path=/ status=200 content_type=text/html bytes=731
Invoke-WebRequest : The operation has timed out.
... opencode-token-dashboard-smoke.ps1:52 ... /api/usage ...
SMOKE_EXITCODE=1
DASHBOARD_PROCESS_COUNT=0
PORT_18785_CONNECTION_COUNT=0
```

The failure is an API latency limit, not a bind or process-cleanup failure. The corresponding logs were:

```text
C:\Users\parla\.local\share\opencode\tools\logs\dashboard-smoke-18785.out.log
  OpenCode token dashboard running at http://127.0.0.1:18785
C:\Users\parla\.local\share\opencode\tools\logs\dashboard-smoke-18785.err.log
  empty
```

### Structural cache API smoke, unused port 18787

A controlled read-only launcher queried only JSON structure and aggregate fields; it did not print response bodies, titles, prompts, message text, or file contents.

Output:

```text
HTTP path=/health status=200 content_type=application/json bytes=11
HTTP path=/api/cache-miss/sessions status=200 content_type=application/json bytes=1496512 seconds=40.01
STRUCTURE path=/api/cache-miss/sessions object_keys=range,totalMiss,totalExpected,sessions
CACHE_SESSIONS range=all session_count=5211 total_miss=1149077529 total_expected=31553545164
HTTP path=/api/cache-miss/session/<selected-id> status=200 content_type=application/json bytes=4986 seconds=46.73
STRUCTURE path=/api/cache-miss/session/<selected-id> object_keys=sessionId,title,provider,model,noCache,messages
CACHE_SESSION_DETAIL message_count=26 fields=sessionId,title,provider,model,noCache,messages
PROCESS_STOPPED=True
```

The opaque selected session ID is intentionally redacted in this report. The route returned a structural session detail successfully; no message-detail body was requested. Logs:

```text
C:\Users\parla\.local\share\opencode\tools\logs\dashboard-structural-18787.out.log
  OpenCode token dashboard running at http://127.0.0.1:18787
C:\Users\parla\.local\share\opencode\tools\logs\dashboard-structural-18787.err.log
  empty
```

Final cleanup check:

```text
DASHBOARD_PROCESS_COUNT=0
PORT_18787_CONNECTION_COUNT=0
PORT_18785_CONNECTION_COUNT=0
```

## Failures, blockers, and final boundary

1. **Cache-hit direct runtime import blocker:** Bun direct import of `opencode-cache-hit/tui` fails because the installed `@opentui/solid` resolution attempts to import the type declaration `jsx-runtime.d.ts` and cannot find runtime export `Fragment`. In-memory syntax/build and filesystem resolution pass; this should be resolved or rechecked by the validation owner before claiming a clean runtime-load pass.
2. **Dashboard `/api/usage` latency:** the official smoke script timed out after 120 seconds while scanning the existing 76 GB database. This does not refute database visibility: direct read-only aggregates and the cache-session/session-detail APIs succeeded.
3. **No live TUI claim:** the current OpenCode process was not restarted. Installed/resolved artifacts are verified; live sidebar loading in the current process remains unverified until restart and manual TUI inspection.

No edits were made to DCP, OMO, MCP, RTK, sessions, or the database. No broad installation or model request was performed.
