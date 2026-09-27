# Absorb Essential Legacy Function into Workflows, Then Remove Backend Preset

Status: claimed
Type: task
Blocked by: none

## Question

Migrate the remaining essential legacy behavior into the workflows domain, then remove the Backend/Preset concepts: which preset/run/submission helpers still serve the Shelf/Experiment flow, what is their workflows-domain equivalent, and what gets deleted once callers are moved.

## Notes

- Decided: core functionality that is needed and essential becomes part of workflows; the rest is deleted, not preserved.
- No second authority: WorkflowDomainStore/API remains the single durable owner; absorbed behavior adapts behind it.
- No old-data migration.
- Sequencing: run only after wave ready-5 (import/setup-to-wizard wiring) lands, since both touch the workflow creation paths.
- Evidence: full focused specs stay green plus scoped regression; each removal ships with proof of zero remaining callers.
