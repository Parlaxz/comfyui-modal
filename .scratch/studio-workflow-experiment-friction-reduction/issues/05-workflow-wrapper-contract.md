# Workflow Wrapper Contract

Status: resolved
Type: grilling
Blocked by: none

## Question

What is the Studio workflow wrapper contract as one user-facing wrapper around one ComfyUI workflow, including how clutter is hidden, which fields are exposed, and how future workflow types can define their own mandatory roles?

## Answer

A Studio workflow is one user-facing wrapper around one static, copied ComfyUI graph. Import copies the selected graph into that wrapper permanently; the wrapper projects a clean field surface without mutating the graph. A changed graph requires a new import/wrapper rather than silently changing the existing one.

Every bound role or input produces a field card. Unbound graph inputs produce no card. The wrapper uses reusable typed advanced-field definitions rather than bespoke UI for each node: shared types such as text, number, dropdown, and custom input describe accepted values and provide generic behavior. Experiment operations such as random, increment, and decrement belong to the number type, not specifically to seed.

Prompt and primary output remain visible anchors. Advanced cards can be shown, hidden, grouped, and reordered in the saved layout without being unbound or changing their captured value/default behavior. Binding determines whether a card exists; presentation determines how it is arranged and exposed.

The wizard and wrapper are workflow-type agnostic. Each workflow type supplies a role profile declaring its mandatory and optional roles, their stable field types, and output rules. T2I is the first profile. Model components remain independently selectable, with declared model-set relationships and evidence-based compatibility/status hints only.

Mapping and preset concepts are internal compatibility details, not separate user-facing setup steps. The wrapper is the single durable product concept and the existing experiment engine may be adapted behind it until its intermediaries can be removed.
