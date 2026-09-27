# OpenCode Cost/Cache Tooling Installation + OMO Session-Isolation Audit

Status: PARTIAL / OPEN — implementation complete, live fresh-120 and child gates unproven due controlled ConPTY completion failure
Audit date: 2026-08-20
Host: Windows 10; validation owner: orchestrator

This report contains structural and token metadata only. It contains no private prompts, credentials, source contents, or unrelated environment values.

## Executive result

- **PASS — shared TUI-loader diagnosis/repair.** A normal OpenCode `1.18.19` TUI through the real Paseo node-pty imported and invoked both repaired cache plugins.
- The independent cache-hit timeline result remains **FAIL/OPEN at the collector stage**. It is not a plugin-loader failure and must not be conflated with plugin loading.
- The repair was configuration-local: cache-hit was aligned from `0.7.0` to `0.7.1`, and `tui.json` retains the OMO npm spec while using absolute `file:///` specs for the config-local cache-hit and visual-cache packages.
- No isolated OpenCode cache package copy was modified. No DCP, model, threshold, database, or repository source/config change was made by the runtime repair.

## Shared-failure diagnosis

OpenCode `v1.18.19` `PluginLoader`/`Npm.add` resolved npm TUI specifications into isolated cache package directories. The active cache copies did not have the required peer ancestry:

| Isolated package | Failure |
|---|---|
| cache-hit `0.7.1` | Absolute import failed `ERR_MODULE_NOT_FOUND @opentui/solid/jsx-dev-runtime` |
| visual-cache `1.6.3` | Absolute cache import failed `ERR_MODULE_NOT_FOUND @opentui/solid` |

The config-local copies resolve successfully against the one-copy config-context dependency tree. The repair therefore uses absolute config-local file URLs for the two cache plugins and leaves OMO as its npm specification. This is not an OpenCode core bug, and the isolated cache copies were not modified.

The controlled normal TUI had `OPENCODE_PURE` unset and loaded both repaired packages. This proves the shared loader diagnosis/repair independently of the later cache-hit collector failure.

## Exact v1.18.19 source path

All links below are pinned to the exact `v1.18.19` tag. The source is available upstream at these exact paths; readability of the installed native EXE is a separate issue.

| Area | Tagged source |
|---|---|
| TUI runtime | https://github.com/anomalyco/opencode/blob/v1.18.19/packages/opencode/src/plugin/tui/runtime.ts |
| TUI config | https://github.com/anomalyco/opencode/blob/v1.18.19/packages/opencode/src/config/tui.ts |
| Core flags | https://github.com/anomalyco/opencode/blob/v1.18.19/packages/opencode/src/flag/flag.ts |
| Plugin loader | https://github.com/anomalyco/opencode/blob/v1.18.19/packages/opencode/src/plugin/loader.ts |
| Plugin shared helpers | https://github.com/anomalyco/opencode/blob/v1.18.19/packages/opencode/src/plugin/shared.ts |
| Plugin install | https://github.com/anomalyco/opencode/blob/v1.18.19/packages/opencode/src/plugin/install.ts |
| TUI app | https://github.com/anomalyco/opencode/blob/v1.18.19/packages/tui/src/app.tsx |
| TUI plugin runtime | https://github.com/anomalyco/opencode/blob/v1.18.19/packages/tui/src/plugin/runtime.tsx |
| TUI plugin adapters | https://github.com/anomalyco/opencode/blob/v1.18.19/packages/tui/src/plugin/adapters.tsx |
| TUI command | https://github.com/anomalyco/opencode/blob/v1.18.19/packages/opencode/src/cli/cmd/tui.ts |
| Attach command | https://github.com/anomalyco/opencode/blob/v1.18.19/packages/opencode/src/cli/cmd/attach.ts |
| TUI layer | https://github.com/anomalyco/opencode/blob/v1.18.19/packages/opencode/src/cli/tui/layer.ts |

The relevant control flow is:

```text
pluginOrigins → loadExternal → resolve/install → entrypoint
             → readV1Plugin → resolvePluginId → activation
```

The `OPENCODE_PURE` branch records `records=[]`; pure mode consequently suppresses plugin records. That branch was not entered in the controlled normal TUI.

## Runtime environment flags

The current parent shell and the controlled node-pty child had the same safe-observed values:

| Variable | Parent shell | Controlled child |
|---|---|---|
| `OPENCODE_PURE` | unset | unset |
| `OPENCODE_TUI_CONFIG` | unset | unset |
| `OPENCODE_CONFIG_DIR` | unset | unset |
| `OPENCODE_DISABLE_PROJECT_CONFIG` | unset | unset |
| `OPENCODE_CONFIG` | unset | unset |
| `OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS` | `true` | `true` |

No `--pure` was passed. Existing pre-existing Paseo/OpenCode process environment blocks were not observable with safe built-in APIs, so no stronger claim is made about those unrelated processes. `OPENCODE_PURE` was not the cause in the controlled normal TUI.

## Effective TUI config precedence

The exact source precedence is **global → override → project → `.opencode` → config-dir**, followed by later merge/de-duplication.

| Source/inventory | Effective result |
|---|---|
| Global `C:\Users\parla\.config\opencode\tui.json` | Exists; SHA-256 `9409DAFEFED081173D213AAE5BA2BE528630AB307013359C67F3BB5E64281F76`; `plugin=yes` |
| `OPENCODE_TUI_CONFIG` | Unset; no file |
| Project root-to-leaf TUI files | None |
| `.opencode` TUI files | None |
| `OPENCODE_CONFIG_DIR` | Unset; no additional TUI file |
| `C:\Users\parla\.config\opencode\tui.json.bak`, `C:\Users\parla\.config\opencode\tui.json.pre-phase2-20260820.bak` | Backups only; not applied configs |

The effective global file contains:

```json
{
  "plugin": [
    "oh-my-opencode-slim",
    "file:///C:/Users/parla/.config/opencode/node_modules/opencode-cache-hit",
    "file:///C:/Users/parla/.config/opencode/node_modules/opencode-visual-cache"
  ]
}
```

## Effective plugin origins

These origins are reconstructed from the exact config and tagged source behavior because the native status command did not expose plugin records.

| Order | Origin | Scope | Source |
|---:|---|---|---|
| 1 | `oh-my-opencode-slim` | global | `tui.json` |
| 2 | `file:///C:/Users/parla/.config/opencode/node_modules/opencode-cache-hit` | global | `tui.json` |
| 3 | `file:///C:/Users/parla/.config/opencode/node_modules/opencode-visual-cache` | global | `tui.json` |

## Runtime plugin status

Native user-facing plugin status was not exposed. The rows below are evidence-qualified, not claims of a native status API.

| Plugin | Source | Spec | Target/status | Enabled | Active callback evidence |
|---|---|---|---|---|---|
| cache-hit `0.7.1` | file | exact config-local file URL | local package directory | yes | yes |
| visual-cache `1.6.3` | file | exact config-local file URL | local package directory | yes | yes |
| OMO `2.2.14` | npm | `oh-my-opencode-slim` | not exposed | not exposed | absent in normal-TUI sentinel run |

The prior OMO import/init/health claim was not proof of OMO TUI activation. Unless the exact TUI module is shown, that evidence is classified as server/core runtime evidence. The current normal TUI showed no OMO TUI marker; it did show cache-hit and visual-cache import/callback markers.

## Package-resolution table

| Package | Exact path | Version | Exports | Default ID | Hashes |
|---|---|---:|---|---|---|
| cache-hit | `C:\Users\parla\.config\opencode\node_modules\opencode-cache-hit` | `0.7.1` | `.` → `./index.tsx`; `./tui` → `./index.tsx`; `./tui-panel` → `./src/tui-panel/index.ts` | `opencode-cache-hit` | `package.json` `54B87C68FD0EC1BF3746C5BC99CFF5EAB9B1E230FD5132BE2E89AF75FD7791BE`; `index.tsx` `D9FD670E4E2AD6296089CD21795CC55E4337995998EB4080E5904DCA274AB41D`; `src/plugin.tsx` `850F5D3A6414B9BCB155C4251EBF920A886BE3FE1D6FEFA6A6AC9BD8F03821EC` |
| visual-cache | `C:\Users\parla\.config\opencode\node_modules\opencode-visual-cache` | `1.6.3` | `./server` import → `./dist/server.js`; `./tui` import → `./dist/tui.js` (enabled) | `opencode-visual-cache` | `package.json` `EE8BF5928400AA83EE0355B3D2AEE897B39F0613FC064B2E98AACC3BCD41C194`; `dist/tui.js` `E38C0D0FF253515F8C8E9704C4A7664026978E698FAA437CDA8989A3B1BEF4E2` |
| OMO-slim | `C:\Users\parla\.config\opencode\node_modules\oh-my-opencode-slim` | `2.2.14` | `.` import → `./dist/index.js`; `./server` import → `./dist/server.js`; `./tui` import → `./dist/tui.js` | `oh-my-opencode-slim:tui` | `package.json` `A5EC24563D81F7DC99F05FA283C9D200B22304991351F282506B1D4C8B58B7A5`; `dist/tui.js` `F43E3BDFE202CF26AC235C182F32978A6EE774B1BBDBD8DBE1208C3A9ED231EE` |

## Dependency-resolution table

The one-copy config-context resolution passed:

| Dependency | Version | Physical path |
|---|---:|---|
| `@opencode-ai/plugin` | `1.18.19` | `C:\Users\parla\.config\opencode\node_modules\@opencode-ai\plugin` |
| `@opencode-ai/sdk` | `1.18.19` | `C:\Users\parla\.config\opencode\node_modules\@opencode-ai\sdk` |
| `@opentui/core` | `0.5.1` | `C:\Users\parla\.config\opencode\node_modules\@opentui\core` |
| `@opentui/solid` | `0.5.1` | `C:\Users\parla\.config\opencode\node_modules\@opentui\solid` |
| `solid-js` | `1.9.12` | `C:\Users\parla\.config\opencode\node_modules\solid-js` |

The isolated cache copies lacked the OpenTUI peers/ancestry required by their absolute imports. The successful config-context resolution is the direct contrast.

## Minimal-plugin control (only if needed)

A minimal-plugin control was not needed: package-specific shared-cache isolation was proven directly. Reversible sentinels were used instead.

Normal TUI ConPTY evidence: no `--mini`, terminal `120x40`, OpenCode `1.18.19`; cache-hit import plus callback and visual-cache import plus callback appeared. OMO markers were absent. The `--mini` run is invalid evidence for plugin activation because it is the minimal host and showed none.

## Cache-hit JSONL proof

**FAIL/OPEN — timeline gate only, not loader.** One normal persistent TUI process ran exactly one trivial controlled prompt; the stream and loop completed, and observation continued for more than two seconds. The target `C:\Users\parla\.local\share\opencode\logs\cache-hit` remained absent.

The collector trace found the first missing stage at `sidebar_content` invocation:

| Stage | Evidence |
|---|---|
| Plugin module import | occurred |
| TUI callback | occurred |
| Slot registration | occurred |
| `sidebar_content` invocation | did not occur; first missing stage |
| Collector | did not occur |
| Writer | did not occur |
| Writer error | did not occur |

Therefore the required next issue is collector/UI slot mounting, not loader repair. No unrelated configuration experiment is proposed.

## Visual Cache activation proof

**PASS.** The visual-cache callback marker appeared in the normal TUI after the config-local absolute-file repair. No screenshot was needed.

## OpenCode upgrade

OpenCode was upgraded from `1.17.20` to stable `1.18.19` with:

```powershell
bun add --global --exact opencode-ai@1.18.19
```

The executable and global package moved to `1.18.19`; optional Windows packages were verified. The existing database was opened read-only with `PRAGMA query_only=ON`; there was no migration, reset, delete, rebuild, or destructive rewrite. The active DB remains `C:\Users\parla\.local\share\opencode\opencode.db` (about 71 GiB), and v1 database compatibility was preserved.

## Corrected DCP interpretation

The active core declaration remains exactly `@tarquinen/opencode-dcp@latest`; `dcp.jsonc` was not changed. The exact npm tarball `v3.1.12` was research-only at `C:\Users\parla\AppData\Local\Temp\opencode\dcp-3.1.12-research`, SHA-256 `9D5CDE9D51ECCA5BFF3D7E4AF5875CF76027213A762F51F0B25D074B11D27F9A`. No DCP threshold or model change was performed.

## Corrected session taxonomy

Sanitized structural evidence contains `1324` roots (`parent_id IS NULL`) and `4681` children. Child role counts remain:

| Child role | Count |
|---|---:|
| fixer | 731 |
| explorer | 713 |
| oracle | 305 |
| librarian | 78 |
| designer | 27 |
| observer | 10 |
| orchestrator | 2 |
| councillor | 1 |
| unclassified | 2814 |

This is structural/session metadata, not a claim about prompt content. `CacheX` and adjacent-turn `cache_cliff`/`healthy_fresh_growth` labels remain descriptive heuristics, not causal findings.

## Historical cache table

The retained structural aggregates are classified from sanitized session evidence: roots are `session.parent_id IS NULL`, and child rows use persisted child roles. No root is relabeled as OMO-Orchestrator.

| Structural group | Sessions | Fresh input | Cache read | Cache write | Output | Reasoning | Cost | CacheX | Cache-read share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Parent/root | 1324 | 1,450,283,685 | 16,051,795,115 | 10,623,673 | 31,307,839 | 30,462,547 | 197.8911 | 11.0680 | 91.7136% |
| Fixer children | 731 | 95,093,523 | 7,291,903,808 | 0 | 16,317,586 | 17,952,111 | 32.7712 | 76.6814 | 98.7127% |
| Oracle children | 305 | 57,904,952 | 1,055,998,208 | 0 | 3,179,401 | 5,592,567 | 9.9397 | 18.2368 | 94.8016% |
| Explorer children | 713 | 97,801,098 | 1,980,286,080 | 0 | 7,434,761 | 6,745,765 | 16.2744 | 20.2481 | 95.2937% |
| Librarian children | 78 | 8,013,259 | 86,781,696 | 0 | 567,821 | 578,027 | 1.1329 | 10.8298 | 91.5467% |
| Designer children | 27 | 3,538,789 | 220,693,632 | 0 | 517,663 | 699,767 | 1.1669 | 62.3642 | 98.4218% |
| Observer children | 10 | 162,363 | 4,107,392 | 0 | 27,774 | 37,733 | 0.0526 | 25.2976 | 96.1974% |
| Orchestrator children | 2 | 601,512 | 3,427,840 | 0 | 16,958 | 7,034 | 0 | 5.6987 | 85.0717% |
| Councillor children | 1 | 139,318 | 3,720,448 | 0 | 8,245 | 9,329 | 0.0348 | 26.7047 | 96.3905% |
| Unclassified children | 2814 | 192,166,239 | 3,935,802,068 | 0 | 19,837,171 | 16,042,214 | 56.8976 | 20.4812 | 95.3448% |

The historical aggregates do not prove a cache-key, DCP, or plugin cause.

## OMO child-result injection

OMO `2.2.14` has no supported `freshSession` or `reuse:false` hard switch. Omitting `task_id` creates a new child; explicitly passing a prior `task_id` reuses it. The supported append preserves models, variants, permissions, skills, MCP access, and tools, but remains advisory. Earlier controlled isolation proof retained distinct child IDs and an explicit continuation reused the first ID; no child-result text is included here.

## Tests and historical integration evidence

- Upstream tests: `407` pass and `1` Windows path assertion fail across `408` tests.
- Targeted timeline tests: `53` pass and `0` fail.
- RTK passed one real OpenCode integration run; CBM passed one real OpenCode MCP query. CBM remains `auto_index=false`, `auto_watch=false`.
- The token dashboard UI and structural routes passed controlled browser verification; `/api/usage` remains slow against the large DB.

## Controlled post-upgrade result

The retained controlled post-upgrade experiment used root `ses_fe017f74fffepvjpOncvMF92uE`:

| Run | Structural result |
|---|---|
| A | Parent `tokens_input=19626`, `cache_read=0` |
| B | Parent `input=820`, `cache_read=18944`; one task call; child `ses_fe017ba16ffe1vFIy9PyzvE2Lc` classified fixer with `input=6580`, `cache_read=0`, `output=6` |
| C | Parent `input=1164`, `cache_read=18944`, `output=9`, `reasoning=0` |

DB token evidence is retained only as token evidence; it is not timeline JSONL evidence.

## Files changed

This evidence update changed only the repository Markdown report. Historical installation/runtime state also changed the external user configuration state:

- `C:\Users\parla\.config\opencode\tui.json`
- `C:\Users\parla\.config\opencode\package.json`
- `C:\Users\parla\.config\opencode\bun.lock`
- the local cache-hit package tree under `C:\Users\parla\.config\opencode\node_modules\opencode-cache-hit`

`package-lock.json` is unchanged. No repository source/config/database changes exist besides this report; no DCP/OMO/RTK/CBM state was changed by this report update.

## Temporary files removed

Temporary instrumentation and sentinels were removed/restored after validation. They are not production changes.

Retained sanitized evidence, listed separately from removed diagnostics:

- `C:\Users\parla\AppData\Local\Temp\opencode-cache-forensics\assistant-turns.jsonl`
- sanitized forensic logs under `C:\Users\parla\AppData\Local\Temp\opencode-cache-forensics\`

## Backups

- Repair backup: `C:\Users\parla\.config\opencode\repair-backups\20260820-cache-hit-071`
- Prior cache-hit backup: `C:\Users\parla\AppData\Local\Temp\opencode\cache-hit-forensics-backup-20260820\upgrade-0.7.0`
- Sentinel backup: `C:\Users\parla\AppData\Local\Temp\opencode\tui-plugin-sentinels-backup-20260820`
- No DB rollback copy exists.

## Rollback

Restore `tui.json`, `package.json`, `bun.lock`, and the local package tree from `C:\Users\parla\.config\opencode\repair-backups\20260820-cache-hit-071`; then restore the npm specifications in `tui.json`. Do not touch the cached forensic copies. No DB rollback is available. Validation owner: orchestrator.

## 2026-08-20 closure

**Final status: `PARTIAL / OPEN — implementation complete, live fresh-120 and child gates unproven due controlled ConPTY completion failure`.** This is not a claim of cache-hit timeline full PASS.

### Confirmed repair and root cause

- Loader PASS was already repaired; the cache-hit panel is PASS. Visual-cache import/callback evidence and both config-local absolute `file:///` paths remain intact.
- Root cause confidence is strong for mount coupling: OpenCode `v1.18.19` auto-shows the sidebar when `width > 120`, and the cache-hit `0.7.1` collector's `message.updated` subscription was owned by `sidebar-host`; timeline collection was therefore coupled to UI mounting. No documentation explicitly promised sidebar-only behavior.
- A `120x40` baseline and a forced `Ctrl-B` run initially produced no JSONL. At `140x40`, valid structural JSONL was produced. Internal sidebar signals were not observable. The differential supports mount coupling, but exact fresh-`120` behavior remained execution-limited.
- Repair is lifecycle-scoped runtime with one effective subscriber; `route.current` is the root authority; `state.session.get` uses a direct-child `parentID` predicate; UI hosting is sidebar-only; and `lifecycle.onDispose` performs cleanup. Existing collector/writer/rotation/memory semantics were preserved.

### Test evidence

- Corrected focused runtime/lifecycle/collector/child/plugin-config/module-load/panel suite: **71 pass / 0 fail / 155 assertions**.
- Build: **48 modules / 117.13 KB**, pass. Final module-load: **3 pass**.
- Prior package-wide result: **414 pass / 1 Windows path failure**. The upstream direct-dependency test path remains environment-limited; this does not turn the focused result into a package-wide PASS.

### Live evidence and limits

- `140` auto-visible: one record and panel passed. The enabled sequence observed **5 valid structural main records**, with no invalid/private fields. Restart `+1` and disabled-config `0 records` passed.
- Previously observed `120` open/hide transitions were `+1` each. The fresh `120` cold-start final run is **INCOMPLETE**: PTY exited code `-1` before assistant completion, not a proven timeline failure.
- OMO child behavior was not proven; the visual-cache renderer-less probe remains limited; and zero controlled orphans were observed.
- Root-cause confidence and product validation are separate: the former supports mount coupling, while the latter remains partial/open pending a completed fresh-`120` run and child gate.

### Repair files, backups, and rollback

The repair (not this Markdown closure) changed these installed config-local cache-hit source files:

- `C:\Users\parla\.config\opencode\node_modules\opencode-cache-hit\src\plugin.tsx`
- `C:\Users\parla\.config\opencode\node_modules\opencode-cache-hit\src\sidebar-host.tsx`
- `C:\Users\parla\.config\opencode\node_modules\opencode-cache-hit\src\timeline\collector.ts`
- `C:\Users\parla\.config\opencode\node_modules\opencode-cache-hit\src\timeline\runtime.ts`
- `C:\Users\parla\.config\opencode\node_modules\opencode-cache-hit\src\types.ts`

Matching retained temp upstream source/test work is under `C:\Users\parla\AppData\Local\Temp\opencode\opencode-cache-hit-v0.7.1`: the same five `src` paths plus `tests\timeline-runtime.test.ts`. No package reinstall was performed.

For rollback, restore the modified pre-repair source files from the retained `C:\Users\parla\AppData\Local\Temp\opencode\cache-hit-forensics-backup-20260820\upgrade-0.7.0\node_modules\opencode-cache-hit` copy, remove the new `src\timeline\runtime.ts` and runtime test, and restore the listed source state. The retained `C:\Users\parla\AppData\Local\Temp\opencode\cache-hit-collector-sentinels-backup-20260820` is historical instrumentation only, not a final-source rollback.

This closure changed only this Markdown file. No source, config, installed package, visual-cache, loader, `AGENTS.md`, RTK/CBM, OMO/DCP/models/providers/database, or unrelated file was touched by this update.
