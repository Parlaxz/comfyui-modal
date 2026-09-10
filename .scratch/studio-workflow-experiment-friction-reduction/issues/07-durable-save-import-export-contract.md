# Durable Save Import Export Contract

Status: resolved
Type: grilling
Blocked by: 01-legacy-studio-audit.md, 02-persistence-authority-audit.md, 05-workflow-wrapper-contract.md

## Question

Once the audits and wrapper contract are known, what is the durable save/import/export contract: one durable workflow authority, explicit save, localStorage drafts only, portable workflow/config export, and no old-data migration?

## Answer

`WorkflowDomainStore` and its workflow-domain API remain the single durable authority. A Studio Workflow owns its static graph copy, bindable-input bindings, output binding, Workflow type, saved field values, layout profile, and allowed-options filters. Normal Playground content and layout changes autosave to that Workflow; there is no separate Save button. A small saving/saved state may communicate progress.

Experiment-only state—selected Workflows, common-field axes, value pills, and per-run experiment values—autosaves locally for recovery but does not overwrite the selected Workflows’ normal values. Experiment drafts remain separate from durable Workflow configuration.

Every imported file or link creates a new static Workflow. Import never silently replaces an existing Workflow; the creation wizard collects its name and folder. Updating a Workflow changes that one user-facing Workflow rather than creating user-visible versions; internal revision data may remain only where required by the persistence layer.

Export includes the static graph, Workflow type, bindable-input bindings, output binding, saved field values, layout, and Workflow Settings allowed-options filters. It excludes experiment drafts, generated images, and run history. Import restores the bundle through the workflow-creation wizard. No old-data migration is added.
