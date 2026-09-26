# Experiment 2 — can a split re-read escape a pathological 128 MiB fetch?

Primary: one ordinary buffered 128 MiB `preadv`. On a >=250 ms stall, a free worker
reconstructs the SAME logical block from contiguous subranges into a side buffer,
publishing only after the full 128 MiB is validated. No exact-size duplicate is issued.
Global 4 ms physical-start gate retained; QD4 unchanged.

**Correction:** an earlier interim claim that this architecture produced zero >=250 ms
reads was WRONG - it was based on batches that had completed before a later batch landed.
Pathological reads are common here; `exp2_2x64/im-28.json` reached an 8783 ms primary.

| arm | valid runs | odin excluded | eligible events | rescue wins | rescue losses |
|---|---:|---:|---:|---:|---:|
| A: 2x64 | 21 | - | 10 | 5 | 5 |
| B: 4x32 | 22 | - | 7 | 1 | 6 |

## Arm A: 2x64 — eligible events

| run | provider/region | primary ms | rescue start (+ms) | subread ms values | rescue total ms | winner | ms saved |
|---|---|---:|---:|---|---:|---|---:|
| im-13.json | CLOUD_PROVIDER_OCI:us-chicago-1 | 401.2 | 254.1 | [21.3, 116.3] | 137.6 | rescue | 9.51 |
| im-13.json | CLOUD_PROVIDER_OCI:us-chicago-1 | 267.4 | 262.9 | [37.8, 26.3] | 64.1 | primary | - |
| im-13.json | CLOUD_PROVIDER_OCI:us-chicago-1 | 386.6 | 367.2 | [97.0, 22.5] | 119.6 | primary | - |
| im-13.json | CLOUD_PROVIDER_OCI:us-chicago-1 | 322.9 | 250.7 | [24.7, 23.1] | 47.9 | rescue | 24.41 |
| im-13.json | CLOUD_PROVIDER_OCI:us-chicago-1 | 278.9 | 253.5 | [27.7, 26.7] | 61.2 | primary | - |
| im-18.json | CLOUD_PROVIDER_GCP:us-west | 635.6 | 253.0 | [21.7, 355.2] | 376.9 | rescue | 5.71 |
| im-18.json | CLOUD_PROVIDER_GCP:us-west | 655.5 | 364.8 | [19.5, 278.4] | 298.0 | primary | - |
| im-28.json | CLOUD_PROVIDER_UNSPECIFIED:eu-north | 5166.5 | 3213.7 | [17.5, 1935.2, 3583.9, 25.9] | 1952.7 | rescue | 0.03 |
| im-28.json | CLOUD_PROVIDER_UNSPECIFIED:eu-north | 8783.1 | 5175.2 | [17.5, 1935.2, 3583.9, 25.9] | 3609.8 | primary | - |
| im-28.json | CLOUD_PROVIDER_UNSPECIFIED:eu-north | 8345.8 | 5162.5 | [2876.7, 302.0] | 3182.8 | rescue | 0.48 |

- wins: 5/10; savings median 5.71 ms, max 24.41 ms
- **stalls >=1000 ms: 3 event(s); savings [0.03, 0, 0.48] ms** — the split finishes
  within a fraction of a millisecond of the original, i.e. a tie, not an escape.

- subread list lengths observed: [2, 4]

## Arm B: 4x32 — eligible events

| run | provider/region | primary ms | rescue start (+ms) | subread ms values | rescue total ms | winner | ms saved |
|---|---|---:|---:|---|---:|---|---:|
| im-18.json | CLOUD_PROVIDER_UNSPECIFIED:eu-north1 | 298.6 | 260.1 | [12.7, 12.1, 11.9, 12.6] | 49.4 | primary | - |
| im-21.json | CLOUD_PROVIDER_GCP:us-east | 621.9 | 269.0 | [49.9, 238.1, 40.9, 14.1] | 343.2 | rescue | 9.69 |
| im-21.json | CLOUD_PROVIDER_GCP:us-east | 329.6 | 264.5 | [20.2, 20.6, 10.0, 22.9] | 73.9 | primary | - |
| im-21.json | CLOUD_PROVIDER_GCP:us-east | 273.2 | 272.8 | [10.6, 14.0, 14.4, 11.7] | 50.8 | primary | - |
| im-23.json | CLOUD_PROVIDER_GCP:europe-west2 | 314.4 | 292.5 | [19.9, 12.5, 11.4, 10.7] | 56.9 | primary | - |
| im-23.json | CLOUD_PROVIDER_GCP:europe-west2 | 676.3 | 439.8 | [17.0, 190.5, 9.6, 17.5] | 237.0 | primary | - |
| im-23.json | CLOUD_PROVIDER_GCP:europe-west2 | 574.3 | 345.2 | [165.9, 30.2, 11.8, 20.8] | 232.1 | primary | - |

- wins: 1/7; savings median 9.69 ms, max 9.69 ms

- subread list lengths observed: [4]

## Stopping rule outcome

Rule per arm: stop on 4 SUCCESS EVENTS, OR on the FIRST eligible recovery attempt that
fails to beat the still-running primary.

| arm | first eligible event | outcome | rule fired |
|---|---|---|---|
| A: 2x64 | primary 401.2 ms -> rescue | SUCCESS | n/a |
| B: 4x32 | primary 298.6 ms -> primary | FAILURE | first eligible failure |

## Verdict

**Changing the request shape does not escape the pathological fetch.**

- Arm A (2x64) won 5 of 10 eligible races, but every win on a large stall was a
  photo-finish (0.03 ms and 0.48 ms on 5.2 s and 8.3 s primaries).
- Arm B (4x32) won 1 of 7, and its FIRST eligible event was a loss, ending the arm.
- In both arms the subreads stall together with the original rather than routing
  around it, which is the same same-range coupling seen in the earlier duplicate work.

## Caveats

- `subread_ms` in the arm-A runs was affected by a reporting bug (the list was not reset
  between successive rescues by one worker, so it could accumulate). The bug affected only
  the reported subread list, never the reads, geometry, winner, or timing. It was fixed
  before arm B ran, so arm-B subread lists are authoritative; arm-A lists may be long.
- Odin runs excluded and retained separately in the same directories.
- 250 ms threshold and split sizes were NOT tuned.

