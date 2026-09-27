# Findings

## Decision

Use `128 MiB/QD2` as the common optimum represented by the preserved block-search and confirmation evidence. Do not claim a V2 read-throughput improvement from this campaign.

## Evidence-backed findings

- V1 and V2 independently selected `128 MiB/QD2` in block search.
- Six-run confirmation medians were V1 `7.529 GB/s` and V2 `7.500 GB/s`.
- The same-geometry V2 difference was `-0.382%`.
- Fastest valid individual observations were V1 `8.911 GB/s` and V2 `9.089 GB/s`; these are maxima, not repeatable ceilings.
- No approximately 40 GB/s result was observed or repeatable.
- Full-file final-RAM materialization also used `128 MiB/QD2`; V1 and V2 read-wall medians were `2519.336 ms` and `2508.937 ms`.
- The `32 MiB/QD8` result, where V2 was `-8.790%`, is a secondary comparison only.
- Modal requested exactly 12 CPUs. The capability receipt's affinity count of 28 is not used as an allocation claim.

## Interpretation limits

- These results describe the preserved raw source-read experiment, not the full ComfyUI loader path.
- The data does not establish why V2 was slightly slower at the common optimum.
- Full-RAM timing includes allocation, prefault, and materialization phases; it is not interchangeable with the raw source ceiling.
- No new remote work was performed during analysis correction.
