# Persistence Authority Audit

Status: resolved
Type: research
Blocked by: none

## Question

What durable workflow-configuration stores currently exist versus localStorage drafts, which single authority should own durable configuration, and what cleanup is required to enforce that authority?

## Answer

`WorkflowDomainStore` and its workflow-domain JSON collections (`.studio_workflows.json`, `.studio_workflow_versions.json`, `.studio_workflow_mappings.json`, `.studio_workflow_presets.json`), together with `/run-context`, are the durable authority. localStorage is limited to drafts, navigation/session recovery, and derived cache; IDs are authoritative, while stored names are display-only. Retire legacy `.studio_presets.json` and `/studio/presets` as callers move. Durable save must be explicit: local drafts must never silently mutate or submit as saved configuration. Per the user decision, add no old-data migration.
