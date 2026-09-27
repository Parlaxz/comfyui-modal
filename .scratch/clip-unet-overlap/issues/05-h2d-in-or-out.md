# H2D In-or-Out Overlap Boundary

Status: open
Type: grilling
Blocked by: 02-transport-lane-ownership.md, 04-allocator-oom-rule.md

## Question

Does UNET H2D stay inside the CLIP-forward overlap window or drain after forward completes: source + CPU-prep only vs source + CPU-prep + H2D, decided by measured CLIP-forward slowdown, UNET source/H2D dilation, and critical-path saving (CLIP-ready → both-ready vs serial CLIP-forward + UNET-load span), without optimizing UNET transport itself?
