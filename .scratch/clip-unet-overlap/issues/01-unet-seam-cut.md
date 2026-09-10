# UNET Seam Cut

Status: claimed
Type: grilling
Blocked by: none

## Question

Where is the minimal safe cut that makes UNET load non-monolithic while keeping Golden Serial scheduling byte-for-byte frozen: which lines/symbols become main-thread preflight (header/meta/skeleton), which become the joinable transport operation (source/H2D), and which stay as main-thread adoption/proof (`assign=True`, pointer identity, quiescence), with zero change to Serial order, ownership, or acceptance?
