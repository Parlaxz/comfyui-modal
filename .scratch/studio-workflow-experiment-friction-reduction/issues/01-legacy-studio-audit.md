# Legacy Studio Audit

Status: resolved
Type: research
Blocked by: none

## Question

What legacy Studio UI, API, store, and test paths exist; what does each currently do; which callers and dependencies rely on them; what should be kept, replaced, or deleted; and which clutter can be removed without migration?

## Answer

The live surfaces are `studio-playground.js`, `studio-playground-state.js`, `studio-experiment-mode.js`, `studio-feature-registry.js`, `studio-workflows.js`, `studio-backend-api.js`, and the current tests; they must not be deleted wholesale. Preserve the public Playground, workflow, and experiment surfaces and modern `/studio/experiment-v2`. Replace or retire legacy `/studio/run` and unreachable legacy experiment branches only after callers and tests migrate. Treat legacy `.studio_presets.json` authority as cleanup target. Per the explicit no-migration decision, do not add old-data migration; delete retired clutter only after proving it is no longer needed.
