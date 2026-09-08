# Role-Binding Wizard Contract

Status: resolved
Type: grilling
Blocked by: none

## Question

What is the wizard’s role-binding contract: how does import always open the wizard; how do suggestions point to likely bindings; how does the user explicitly confirm every mandatory T2I role; and how is save blocked until valid, concrete node/widget/input/output bindings exist?

## Answer

Import opens a unified, unsaved Studio workflow-wrapper wizard. The wrapper owns the captured ComfyUI graph, role bindings, exposed fields, layout, and experiment-ready configuration; users do not need to navigate separate Mapping and Preset setup. Existing preset payloads may remain as an internal adapter until the experiment engine is simplified, but presets are not a user-facing intermediary.

For the initial T2I contract, durable save and execution require confirmed bindings for positive prompt, primary image output, seed, UNet/diffusion model, VAE, and CLIP/text encoder. Sampler and negative prompt are optional. A workflow with multiple outputs requires one explicitly selected primary output; other outputs remain unexposed for this effort.

Suggestions point to likely candidates but never replace confirmation. Selecting a candidate counts as confirmation and shows a visible per-role confirmed state; ambiguous or destructive bindings may require an extra confirmation. For manual binding, the user activates a role’s Bind control, then clicks the exact node or field area to bind. Node-level selection must allow choosing the relevant widget/input, such as a sampler seed field, and the saved binding must retain concrete node, widget/input, and output metadata.

The wizard shows suggested, confirmed, missing, and invalid states. It validates referenced graph nodes and fields live and blocks durable save and execution until every mandatory role is valid. Incomplete work may auto-recover as a localStorage draft, but must never appear as a saved workflow or become runnable. Future workflow types define their own mandatory role sets.
