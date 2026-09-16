---
name: playwright-debug
description: Disciplined Playwright loop for debugging live UI wizard flows — inspect state, run one bounded spec, preserve artifacts, and prove the DOM and payload outcomes.
disable-model-invocation: true
---

# Playwright Debug

A disciplined loop for debugging live UI wizard flows with Playwright. The loop goes **red** on the bug first, and only goes green when a user-facing DOM assertion and the consequential-action payload both pass. Work the loop in order; each step ends on a completion bound.

## The loop

### 1. Pin the state

Drive the running app by hand to the failing step. Inspect the live DOM at that step and the network traffic going in and out of it — request body, response body, status.

Done when you can name the exact step, the element involved, and the request/response pair where behavior diverges from intent.

### 2. Label the evidence

Classify every observation as **mock** or **live** before reasoning from it. A flow can appear to pass while a stub answers every call.

- Mock evidence grounds claims about wiring and control flow only.
- Live evidence grounds claims about real behavior and payloads.

Done when every observation carries a mock/live label and no claim about live behavior rests on mock-only evidence.

### 3. Run one bounded spec

Bisect with a single spec file and an explicit timeout. Keep the rest of the suite out until that one spec is green.

Done when the single spec returns a verdict inside its timeout.

### 4. Name the timeout phase

When a spec hangs, split the run into phases: launch/context, navigation, readiness wait, action, assertion, teardown. Find the phase that spent the budget.

Done when the phase is named with artifact timestamps or trace spans as evidence — not a guess.

### 5. Preserve artifacts

Write screenshots, traces, console logs, and network logs to a run-specific directory (`<run-dir>/`). Artifacts from one attempt never stand in for another.

Done when the trace replays the failure and every artifact opens cleanly.

### 6. Prove at the user boundary

Two proofs are required, and both must pass:

1. **DOM proof** — an assertion on the user-facing element the flow was supposed to change, read after the action.
2. **Payload proof** — the consequential-action request body or result captured and asserted, so the outcome is proven end to end, not inferred.

Done when both the DOM assertion and the payload assertion pass on the same run.

### 7. Rerun after every change

After any code or runtime change, restart or reload the runtime so stale state cannot fake a result, then rerun the same single spec. Capture the red run before the change and the green run after.

Done when before/after artifacts exist for the same spec and the only difference is the intended change.

## Timeout phase reference

| Phase | What it covers | What a stall here points to |
|-------|----------------|------------------------------|
| launch/context | browser start, context, storage | environment or binary problem |
| navigation | page load and route change | app page, asset, or dev-server problem |
| readiness wait | waits for elements, state, or network idle | UI never reaches the awaited state |
| action | click, type, submit | element obscured, disabled, or detached |
| assertion | DOM or payload expectation | wrong behavior, not a timing fault |
| teardown | close, flush, artifact write | leaked handles or blocked artifact write |

## Trustworthy verdict

Call a verdict trustworthy only when the green run used the live path (or the mock is explicitly the target), ran a single bounded spec, preserved its artifacts, named and excluded the relevant timeout phases, and passed both proofs in step 6. Anything less is a provisional signal, not a result.
