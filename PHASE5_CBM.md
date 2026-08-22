# Phase 5 — Codebase Memory MCP (Windows/OpenCode)

Date: 2026-08-20  
Validation owner: orchestrator  
Scope: only `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`

## Guardrails and outcome

- Installed the official DeusData `codebase-memory-mcp` Windows x86-64 release, v0.10.8.
- Added one explicit local stdio MCP entry to the active OpenCode core config.
- Did not run the upstream installer or create its OpenCode plugin/augmentation, agents,
  skills, hooks, or other client integrations. The MCP server is used directly.
- `auto_index=false` and `auto_watch=false` are persisted in the private CBM config.
  Watcher functionality was not enabled or tested and is **not claimed functional**.
- No pre-existing DCP, model, reasoning, session, database, RTK/cache/dashboard/OMO project
  files were modified. The new CBM project index and CBM `_config.db` are confined to the
  allowed private CBM cache. No commit was made.
- This report records metadata and pass/fail summaries only; source snippets, query text,
  and chat contents are intentionally not copied here.

## Release and source evidence

Release: `https://github.com/DeusData/codebase-memory-mcp/releases/tag/v0.10.8`  
Source tag: `v0.10.8`, commit `46ae198fc11cda80e817acbc5f5908d7c2de7032`  
Release API: `https://api.github.com/repos/DeusData/codebase-memory-mcp/releases/tags/v0.10.8`

Official Windows artifact:

- URL: `https://github.com/DeusData/codebase-memory-mcp/releases/download/v0.10.8/codebase-memory-mcp-windows-amd64.zip`
- Installed archive: `C:\Users\parla\AppData\Local\CodebaseMemoryMCP\v0.10.8\codebase-memory-mcp-windows-amd64.zip`
- Archive SHA-256: `b43ad982994c4d829670749e08d3b622a74bb20041fc0a7d02bef6113f81c34d`
- Official `checksums.txt` SHA-256: `9d2e33bdf9c9dc8662079d5b9a1bbf716aa2e62e2ed6cc51cf4ae06d42498787`
- Extracted executable: `C:\Users\parla\AppData\Local\CodebaseMemoryMCP\v0.10.8\package\codebase-memory-mcp.exe`
- Executable SHA-256: `b4b403b1d7c4def3785f148b93f345ce8427858f4f5489ce28580c4387a336a6`
- Version output: `codebase-memory-mcp 0.10.8`
- Release evidence lists the shipped Windows executable as VirusTotal-clean under the
  same executable SHA-256.

The v0.10.8 source was inspected before configuration. `src/cli/cli.c:3644-3649`
defines the normal OpenCode MCP JSON entry, while `src/cli/cli.c:8746-8755` separately
installs `plugins/cbm-augment.ts`. `src/cli/client_adapter.c:188-244` generates that
plugin, and `src/cli/client_adapter.h:43-54` explicitly notes that its
`tool.execute.after` output mutation is not part of OpenCode's documented plugin
contract and can fail silently. Therefore only the direct MCP entry was used; the
automatic OpenCode augmentation was deliberately excluded.

## Actual installation and private locations

- Install root: `C:\Users\parla\AppData\Local\CodebaseMemoryMCP\v0.10.8\package`
- Stable cache: `C:\Users\parla\AppData\Local\CodebaseMemoryMCP\cache`
- Stable runtime: `C:\Users\parla\AppData\Local\CodebaseMemoryMCP\runtime`
- Supported variables used: `CBM_CACHE_DIR` and `CBM_RUNTIME_DIR`.
- Download command: `Invoke-WebRequest -Uri https://github.com/DeusData/codebase-memory-mcp/releases/download/v0.10.8/codebase-memory-mcp-windows-amd64.zip -OutFile C:\Users\parla\AppData\Local\CodebaseMemoryMCP\v0.10.8\codebase-memory-mcp-windows-amd64.zip`.
- Checksum command: `Get-FileHash -Algorithm SHA256 -LiteralPath C:\Users\parla\AppData\Local\CodebaseMemoryMCP\v0.10.8\codebase-memory-mcp-windows-amd64.zip`; it matched `checksums.txt` and the release API digest.
- Extraction command: `Expand-Archive -LiteralPath C:\Users\parla\AppData\Local\CodebaseMemoryMCP\v0.10.8\codebase-memory-mcp-windows-amd64.zip -DestinationPath C:\Users\parla\AppData\Local\CodebaseMemoryMCP\v0.10.8\package`.
- Version command: `codebase-memory-mcp.exe --version`; output: `codebase-memory-mcp 0.10.8`.
- CBM config commands run with those variables:
  - `codebase-memory-mcp.exe config set auto_index false`
  - `codebase-memory-mcp.exe config set auto_watch false`
  - `codebase-memory-mcp.exe config set ui_enabled false` (keeps the optional CBM UI
    disabled; no dashboard files were touched).
- Final config output: `auto_index=false`, `auto_watch=false`, `ui_enabled=false` (other
  CBM values were left unchanged).

## OpenCode configuration

Active core config inspected and modified:
`C:\Users\parla\.config\opencode\opencode.json`

OpenCode executable: `C:\Users\parla\.bun\bin\opencode.exe`  
OpenCode version: `1.17.20`

Phase backup:
`C:\Users\parla\.config\opencode\opencode.json.phase5-cbm-20260820.bak`

- Backup SHA-256: `b95e0628beefb14c875e49018db24a300fa8d395c422153f3715c9f7bc7eadef`
- Existing providers preserved: `opencode-go`, `omniroute`.
- Existing plugins preserved: `@tarquinen/opencode-dcp@latest`, `oh-my-opencode-slim`.
- Existing core MCP `playwright` preserved.
- Added only `mcp.codebase-memory-mcp` with `type=local`, `enabled=true`, direct
  executable command, and the three environment values `CBM_CACHE_DIR`,
  `CBM_RUNTIME_DIR`, `CBM_LOG_LEVEL=error`.
- JSON parse validation passed. `opencode mcp list` reported `codebase-memory-mcp`
  **connected**. The active runtime also showed existing `context7` and `gh_grep`
  connections; they were not changed.

## Index and verification

Command form used (with `CBM_CACHE_DIR` and `CBM_RUNTIME_DIR` set to the paths above):

```text
codebase-memory-mcp.exe cli --progress --json index_repository --repo-path "C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal"
```

Index result:

- Exit code: `0`
- Wall duration: `26,645 ms` (about `26.6 s`)
- Project identity: `C-Users-parla-OneDrive-Documents-AI-HUB-ComfyUI-June-Install-ComfyUI-custom_nodes-comfyui-modal`
- Nodes: `45,681`
- Edges: `245,456`
- `index_status`: `ready`
- Parse-partial files: `1`; skipped files: `0`
- The reported not-indexed files/directories are ignored by the repository's existing
  gitignore/skip rules; no ignore rules were changed.

Private cache/index size after indexing:

- Total files: `4`
- Total bytes: `358,039,195`
- Project DB: `358,023,168` bytes
- `_config.db`: `12,288` bytes
- `list_projects`: exit `0`, total `1`, returned `1`, matching the active project.

Tool checks were executed through the supported one-shot CLI with `--json`; only result
metadata was retained here:

| Check | Exit | Result |
|---|---:|---|
| `list_projects` | 0 | one active project |
| `index_status` | 0 | ready; 45,681 nodes / 245,456 edges |
| `get_architecture` | 0 | response received (4,977 bytes) |
| `search_graph` | 0 | Function search response received (345 bytes) |
| `query_graph` | 0 | read-only graph query response received (107 bytes) |
| `get_code_snippet` | 0 | snippet response received (21,263 bytes); source omitted from report |
| `trace_path` | 0 | bidirectional depth-2 response received (310 bytes) |
| `detect_changes` impact query | 0 | bidirectional depth-2 impact response received (39,772 bytes); diff contents omitted |

The snippet target was selected from a successful `search_graph` result, not hard-coded
from report content. The impact query examined the repository's existing working-tree
state; it did not modify it.

## Daemon/process and watcher state

- OpenCode MCP initialization: connected as reported by `opencode mcp list`.
- CBM runtime directory was created and used; daemon lifecycle log and project log were
  created under the private cache `logs` directory.
- After one-shot validation completed, active CBM process count was `0` (no standing
  daemon remained). This is consistent with no active MCP session after CLI validation.
- Runtime state was private under the configured runtime directory.
- Watcher: configured `false`, not enabled, not tested, and not claimed functional.

## Failures and fixes

1. The first PowerShell source-archive download exceeded the 120-second command timeout,
   leaving a partial ZIP; `Expand-Archive` then returned `End of Central Directory record
   could not be found`. The partial file was removed, the same v0.10.8 tag archive was
   downloaded with `curl.exe -L --fail --retry 3`, and extraction succeeded.
2. An initial `get_code_snippet` probe omitted its required `--project` flag and exited
   `1`. The supported help output identified the required flag; rerunning with the
   verified project identity exited `0`.

No other installation or verification failure remained.
