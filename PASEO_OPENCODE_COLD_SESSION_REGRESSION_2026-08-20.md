# Paseo/OpenCode Cold Session Regression — 2026-08-20

## Executive result

The causal change was the CBM OpenCode augmentation plugin starting the shared CBM daemon during plugin construction. A cold daemon status/start path consumed approximately the same 10-second budget as Paseo's `session.create` watchdog.

Repair applied in `C:\Users\parla\.config\opencode\plugins\cbm-augment.ts`: plugin construction no longer starts CBM. `ensureDaemon()` is now awaited only by the Grep/Glob post-tool hook, after session creation.

The repaired enabled-plugin disposable server created a session in **1,143 ms** after **1,569 ms** server acquisition. The required three-agent Paseo cohort was not completed because the accessible workspace does not contain Paseo source and the live Paseo UI was not restarted to avoid disturbing active sessions. Two later disposable attempts hit their deliberately imposed 6-second cap; those are not acceptance evidence.

## Exact reproduction

Controlled no-model API sequence:

1. Start a disposable `opencode serve` with the normal global config.
2. Wait for `/global/health`.
3. POST `{}` to `/session`.
4. Stop the disposable server and verify its port.

Observed:

| State | Server acquisition | session.create | Result |
|---|---:|---:|---|
| CBM augmentation enabled, pre-repair | 1,682 ms | 11,943 ms | session eventually created; beyond Paseo deadline |
| Only `cbm-augment.ts` disabled | 1,698 ms | 1,624 ms | pass |
| CBM augmentation enabled, post-repair | 1,569 ms | 1,143 ms | pass |

No model prompt was sent.

## Recent change inventory

| Change | Approx. time | Could affect headless/new-session startup? | Why |
|---|---|---|---|
| `opencode.json`: OMO and CBM MCP enabled | Aug 20 09:34 | Yes | Changes plugin/MCP initialization surface. |
| OpenCode/plugin lock update to 1.18.19; cache-hit dependency | Aug 20 10:53 | Possible | Runtime/plugin compatibility boundary; not isolated by this test. |
| `tui.json`: OMO, cache-hit, Visual Cache | Aug 20 14:23 | Unproven | No evidence TUI plugins load in this headless path. |
| OMO routing/preset/permissions | Aug 20 14:26 | Possible | Startup configuration surface; not isolated as causal. |
| `cbm-augment.ts` daemon startup and Grep/Glob hook | Aug 20 17:13 | **Yes; isolated** | Its plugin factory synchronously initiated cold CBM daemon work. |
| RTK plugin | Aug 20 14:19 | Not implicated | No changes made; no evidence of startup blocking. |

## Cold vs warm process state

The direct daemon probe, with the daemon stopped, reported:

```text
daemon status: 6,397 ms, exit 1, daemon: not running
daemon start: 12,983 ms, exit 0, daemon: started
daemon status: 3,460 ms, exit 0, daemon: active
```

The daemon was stopped immediately afterward. The old plugin called status and, when cold, start from plugin construction. Each command had a 5,000 ms cap, creating a plausible ten-second cold boundary. The warm existing-agent workaround is consistent with the shared daemon already being established, but no paid prompt was used in this investigation.

## A/B/C waterfall

```text
PRE-REPAIR, CBM AUGMENT ENABLED
server acquire       1.682 s
server ready         yes
session.create       11.943 s  PASS eventually, Paseo timeout exceeded

TEST 1, CBM AUGMENT DISABLED ONLY
server acquire       1.698 s
server ready         yes
session.create        1.624 s  PASS

POST-REPAIR, CBM AUGMENT ENABLED
server acquire       1.569 s
server ready         yes
session.create        1.143 s  PASS
```

## What the existing-agent prompt warms

The exact warmed state was not directly observed through a live old-session prompt. The proven shared state is CBM daemon admission: cold `daemon status/start` is slow, while an active daemon removes that cold path. This is the supported explanation for the workaround, not an assertion that the prompt itself performs a specific hidden operation.

## Paseo 6767 correlation

At the time of inspection, Paseo daemon PID `10672` owned `127.0.0.1:6767`. The listener remained present while Paseo logged `session.create timed out after 10s`; therefore the WebSocket refusal is classified as reconnect noise, not the cause of this regression.

Paseo logs also show unrelated daemon restart/error events and historical session-create timeouts. The accessible workspace does not contain the requested Paseo TypeScript sources or timeout helper, so the exact internal Paseo timer start could not be inspected.

## CBM plugin A/B

Disabling only `cbm-augment.ts` reduced session creation from 11,943 ms to 1,624 ms while retaining CBM MCP registration, OMO, RTK, DCP, cache-hit, Visual Cache, providers, and model configuration. This isolates the augmentation plugin startup path.

## CBM MCP/daemon A/B

CBM MCP registration was not disabled. The daemon was tested read-only, then stopped. The result shows the plugin's daemon lifecycle was causal; no evidence requires disabling MCP itself.

## Known Paseo Git-saturation control

No Git queue, long Git operation, or Git process was observed in the controlled API test. The direct causal A/B changed only the CBM augmentation plugin. Git saturation is therefore not supported as the explanation for this regression, though a live Paseo-specific Git pressure measurement remains unavailable without restarting/controlling the UI.

## Root cause

**Regression introduced by:** `C:\Users\parla\.config\opencode\plugins\cbm-augment.ts`, Aug 20 17:13 daemon-start augmentation wiring.

**Why cold creation failed:** `CodebaseMemory` awaited `ensureDaemon()` during plugin construction. `ensureDaemon()` sequentially ran CBM `daemon status` and potentially `daemon start`, each capped at 5 seconds. That startup dependency delayed OpenCode session creation beyond Paseo's fixed 10-second watchdog.

**Why prompting an old agent worked around it:** it allowed the shared CBM daemon/admission state to become established; later sessions skipped the cold daemon path.

**Minimal repair:** remove daemon work from plugin construction and await the existing shared promise only inside the Grep/Glob post-tool hook.

Cold session.create before repair: **11,943 ms** (eventual success after Paseo's timeout).

Cold session.create after repair: **1,143 ms** in the bounded enabled-plugin disposable-server check.

## Fix

Current lifecycle:

```ts
export const CodebaseMemory = async () => {
  return {
    'tool.execute.after': async (input: any, output: any) => {
      const tool = input?.tool === 'grep' ? 'Grep' : input?.tool === 'glob' ? 'Glob' : null;
      if (!tool) return;
      await ensureDaemon();
      const extra = await augment(tool, input?.args);
```

This does not increase Paseo's timeout, start a permanent workaround, remove CBM MCP, or alter RTK/OMO/cache/DCP/model settings.

## Cold-create validation

Completed bounded post-fix checks:

| Check | Server acquire | Session create | Result |
|---|---:|---:|---|
| Enabled plugin, disposable server | 1,569 ms | 1,143 ms | pass |
| Three-attempt batch, attempt 1 | 1,573 ms | >6,000 ms cap | inconclusive; not acceptance evidence |
| Three-attempt batch, attempt 2 | 1,889 ms | >6,000 ms cap | inconclusive; not acceptance evidence |
| Three-attempt batch, attempt 3 | 1,918 ms | 2,736 ms | pass |

The batch also exposed cleanup-process behavior; all six test-port server children were explicitly terminated and verified absent. A three-create cold Paseo validation after a normal UI restart remains outstanding.

## Non-regression validation

- RTK: file and prior adoption evidence retained; not modified.
- CBM MCP: registration retained; daemon CLI responded; no permanent daemon left running.
- CBM indexes: not modified.
- OMO routing: not modified.
- Cache-hit and Visual Cache: not modified.
- DCP: not modified.
- Models/providers/reasoning: not modified.
- Paseo 6767: listener remained healthy during inspection.
- Explorer/Oracle CBM access: configuration unchanged; live role interaction was intentionally avoided.

## Files/config changed

Only this OpenCode plugin was changed:

`C:\Users\parla\.config\opencode\plugins\cbm-augment.ts`

No Paseo source, Comfy Modal source, OpenCode database, session store, RTK, CBM index, OMO config, cache/TUI config, DCP config, or model/provider config was changed.

## Hashes before/after

| Artifact | SHA-256 |
|---|---|
| Current `cbm-augment.ts` | `B21B4290034F476D917B205FE790C1EEAB4E8638A05E9A86730A355A042E6B84` |
| Pre-first-fix backup | `A59F545E13F703A6322BEC0F70B1C2FDC9523CCBF12F472CD2AE2A5593B6F5C6` |
| Pre-hook-fix backup | `FF721D6B72D8D462FE7E3CD12E38FC9AB935656B042B254F20BFB7E519CCDEAF` |
| `opencode.json` baseline | `E75FF693D210E1AEF9021907455827AC46C6ED00B2AEB90B6B0320DB9C0CCD1B` |
| `tui.json` baseline | `9409DAFEFED081173D213AAE5BA2BE528630AB307013359C67F3BB5E64281F76` |
| `rtk.ts` baseline | `745FBC3DA9B9013465EA5567BFC19225E13683BE8286CDD2D883E679F3544AA1` |

## Backups

- `C:\Users\parla\.config\opencode\plugins\cbm-augment.ts.pre-cold-session-fix-20260820.bak`
- `C:\Users\parla\.config\opencode\plugins\cbm-augment.ts.pre-hook-lifecycle-fix-20260820.bak`

## Rollback

Stop new OpenCode servers, copy the desired backup over `cbm-augment.ts`, and restart only through the normal user path. Do not delete sessions or databases.

## Remaining limitations

The Paseo implementation source is absent from the accessible workspace, so Paseo's internal acquisition/session timer split could not be source-traced. A normal UI restart and three fresh Paseo agents were not run because active Paseo/OpenCode and Comfy Modal sessions were present. The direct no-model A/B proves the recent CBM plugin startup regression and validates the narrow repair, but the final Paseo cohort and full live non-regression gates require a quiet user-controlled Paseo restart.
