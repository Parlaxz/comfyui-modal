# Studio Workflow & Experiment Friction Reduction

## Destination

Implement in place a low-friction Studio workflow wrapper and experiment-authoring flow for supported T2I workflows. Completion includes a handoff-ready spec sheet, implementation checklist, Unlazy acceptance gates, and focused Playwright E2E proving real graph capture/import through the existing experiment/history path.

## Notes

Domain is ComfyUI Studio workflow wrappers, T2I field configuration, and experiments. Consult `comfy-modal-core`, `domain-modeling`, `design-taste-frontend`, `accessibility-review`, `verification-planning`, and `unlazy`. Execution is in scope after decisions. The existing experiment/history contract is canonical. One Studio workflow is a wrapper around one ComfyUI workflow, not a multi-version product concept. Workflow content and layout autosave durably; experiment-only state is local draft/session recovery. No migration effort. Remove clutter and legacy APIs after audit. Accounts/collaboration, broad analytics, and exhaustive node-specific integrations are out of scope.

## Decisions so far

- [Legacy Studio Audit](issues/01-legacy-studio-audit.md) — Legacy surfaces remain while `/studio/run`, unreachable branches, and legacy preset authority are retired after replacement with no migration.
- [Persistence Authority Audit](issues/02-persistence-authority-audit.md) — WorkflowDomainStore/API is the sole durable authority and localStorage is drafts/session only.
- [Model Recommendation Evidence](issues/03-model-recommendation-evidence.md) — Model choices use declared compatibility/dependency/availability facts and never inferred best-fit claims.
- [Role-Binding Wizard Contract](issues/04-role-binding-wizard-contract.md) — Import opens one wrapper wizard; explicit exact bindings are required for T2I prompt, output, seed, UNet, VAE, and CLIP, while sampler and negative prompt remain optional.
- [Workflow Wrapper Contract](issues/05-workflow-wrapper-contract.md) — One wrapper owns a static copied graph and its typed field-card projection; advanced cards are reusable, layout-controlled, and role profiles keep the wizard workflow-type agnostic.
- [Field-Card Experiment Prototype](issues/06-field-card-experiment-prototype.md) — Approved Shelf baseline: left field controls with drag/group/autosave layout, explicit Experiment mode with workflow comparison and axes/pills, and persistent output on the right.
- [Durable Save Import Export Contract](issues/07-durable-save-import-export-contract.md) — Workflows autosave durable content/layout; experiment state stays a local draft; imports create new static Workflows and bundles exclude history/output artifacts.
- [Implementation Acceptance Contract](issues/08-implementation-acceptance-contract.md) — The complete import-to-run-to-experiment journey is proven with focused Playwright, real graph capture evidence, existing matrix/history surfaces, cleanup checks, and Unlazy gates.

## Not yet specified

- Final canonical advanced-field/binding schema.
- Implementation sequence and ownership.

## Out of scope

- Accounts/collaboration.
- Broad analytics.
- Exhaustive node integrations.
- Migration of old saved data.
- Non-T2I workflow implementation in this effort.
