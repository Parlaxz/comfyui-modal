# RTK Phase 2 recovery evidence

Date: 2026-08-20

## Scope and baseline

The repository was inspected before editing. It already had unrelated modified,
deleted, and untracked files. No RTK recovery file was present. The recovery
write scope was limited to:

- `C:\Users\parla\.local\bin\rtk.exe`
- `C:\Users\parla\.config\opencode\plugins\rtk-execfile.ts`
- `PHASE2_RTK_RECOVERY.md`

`C:\Users\parla\.config\opencode\opencode.json` and all other unrelated
configuration, cache, dashboard, CBM, OMO, DCP, model, session, and database
files were preserved. No Unix-shell or Bun `$` hook was installed.

## Official binary installation

Source: `https://github.com/rtk-ai/rtk/releases/tag/v0.45.0`

Windows asset:
`https://github.com/rtk-ai/rtk/releases/download/v0.45.0/rtk-x86_64-pc-windows-msvc.zip`

Checksum source:
`https://github.com/rtk-ai/rtk/releases/download/v0.45.0/checksums.txt`

Commands run:

```powershell
Invoke-WebRequest -Uri 'https://github.com/rtk-ai/rtk/releases/download/v0.45.0/rtk-x86_64-pc-windows-msvc.zip' -OutFile "$env:TEMP\rtk-v0.45.0-recovery\rtk-x86_64-pc-windows-msvc.zip"
Get-FileHash -LiteralPath "$env:TEMP\rtk-v0.45.0-recovery\rtk-x86_64-pc-windows-msvc.zip" -Algorithm SHA256
Expand-Archive -LiteralPath "$env:TEMP\rtk-v0.45.0-recovery\rtk-x86_64-pc-windows-msvc.zip" -DestinationPath "$env:TEMP\rtk-v0.45.0-recovery\extract" -Force
Copy-Item "$env:TEMP\rtk-v0.45.0-recovery\extract\rtk.exe" 'C:\Users\parla\.local\bin\rtk.exe' -Force
```

Evidence:

- Official archive SHA-256: `34cea9009a8099acdaf85147b971d95f65efabfa63fb3aea7d3e2b73e6f517c3`
- Installed binary SHA-256: `888ecfcc7ca6ceaf9170cf95027d196d6010c7d1a1892b3662b4bb61f18a3618`
- `C:\Users\parla\.local\bin\rtk.exe --version` → `rtk 0.45.0`
- `where.exe rtk` → `C:\Users\parla\.local\bin\rtk.exe`
- User PATH already contained `C:\Users\parla\.local\bin`; it was preserved.

## Plugin review and fix

The existing plugin already used `execFile`, a bounded timeout, a bounded
buffer, and fail-open handling for missing binaries, crashes, timeouts, and
unsupported rewrites. Its narrow defect was that the callback-based rewrite
attempt was not awaited by `tool.execute.before`; execution could therefore
proceed before the rewritten command was assigned.

`rtk-execfile.ts` now awaits each candidate in order and preserves the existing
fail-open behavior. The local plugin is auto-discovered by OpenCode; this was
confirmed without changing `opencode.json`:

```text
opencode debug config
plugin_origins:
file:///C:/Users/parla/.config/opencode/plugins/rtk-execfile.ts
```

## Verification

Direct RTK checks:

```text
rtk --version                         => rtk 0.45.0 (exit 0)
rtk rewrite "git status"              => rtk git status (exit 3)
rtk rewrite "rtk git status"          => rtk git status (exit 3)
rtk rewrite "echo safe-local-test"    => no output (exit 1)
rtk gain                               => No tracking data yet. (exit 0)
```

The exit-3 result with valid rewritten output is accepted by the existing
hook; unsupported commands exit 1 with no output and remain unchanged.

An inline Bun test (no test file written) exercised the actual TypeScript
plugin hook and passed:

```text
plugin_hook_tests=PASS
{"rewritten":"rtk git status","forced":"rtk git status","nonmatching":"echo safe-local-test","ignoredTool":"git status","failureFallback":"git status"}
```

The failure test temporarily moved the installed binary, cleared the test
process PATH, used a missing `RTK_BINARY`, verified the original command was
preserved, and restored the binary and environment in `finally`.

## Blockers / handoff

No implementation blocker remains. The orchestrator owns final validation,
including a fresh OpenCode process/tool invocation after any required process
restart.
