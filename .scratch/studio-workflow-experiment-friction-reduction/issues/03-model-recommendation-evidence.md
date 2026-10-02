# Model Recommendation Evidence

Status: resolved
Type: research
Blocked by: none

## Question

What model library, preset, and dependency data currently exists, and which facts are available to power model-dropdown compatibility and “works best with” recommendations?

## Answer

Populate dropdowns from the model library and filter by model type and semantic role. Use explicit `compatible_models`, dependency metadata, executable prompt references, and installed/hash state for declared compatibility, required, and availability messaging. Do not call UNet/VAE/CLIP combinations “best”, “recommended”, or “compatible” based only on names, folders, co-location, or manifest hints. Until authoritative bundle metadata exists, show no compatibility recommendation.
