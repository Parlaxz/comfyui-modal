# P vs M2 — counting audit + descriptive variance (no re-run)

Rule: US only; a US region appearing once in an arm is excluded from COUNTED stats;
excluded runs retained. Odin excluded.

## AUDIT — did any singleton-US run enter the headline statistics?

**preadv (P)**
- eligible (non-singleton US) available: 43
- used for the headline: 30
- singleton-US runs inside the headline set: **0** 
- non-US runs inside the headline set: **0** 
- region composition of the headline set: {'us-west': 18, 'us-east': 5, 'us-central': 5, 'us-east4': 1, 'us-ashburn-1': 1}
- all region counts in the headline set are >=2: **False**

**M2**
- eligible (non-singleton US) available: 37
- used for the headline: 30
- singleton-US runs inside the headline set: **0** 
- non-US runs inside the headline set: **0** 
- region composition of the headline set: {'us-west': 16, 'us-ashburn-1': 3, 'us-east': 8, 'us-central': 3}
- all region counts in the headline set are >=2: **True**

**Verdict on the audit:** the headline n=30 sets contain **no** singleton-US and **no**
non-US runs. The singletons were printed only in the exclusion table, which is why they
appeared in the report alongside n=30. The headline statistics were not contaminated.

## Descriptive variance — pooled (counted n=30 per arm)

| arm | n | SD | CV | MAD | p10 | median | p90 | p90-p10 | best | worst |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| preadv (P) | 30 | 0.7362 | 0.1319 | 0.5123 | 4.188 | 5.904 | 6.236 | 2.047 | 6.394 | 3.594 |
| M2 | 30 | 0.8122 | 0.1256 | 0.6026 | 5.401 | 6.503 | 7.337 | 1.936 | 8.247 | 4.265 |

## Descriptive variance — per provider:region (counted, n>=2)

| arm | provider:region | n | SD | CV | MAD | p10 | median | p90 | p90-p10 | best | worst |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| preadv (P) | GCP:us-east | 5 | 0.7650 | 0.1358 | 0.5507 | 4.739 | 5.925 | 6.275 | 1.536 | 6.375 | 4.204 |
| preadv (P) | GCP:us-west | 18 | 0.2704 | 0.0456 | 0.1975 | 5.537 | 5.955 | 6.245 | 0.708 | 6.394 | 5.355 |
| preadv (P) | OCI:us-central | 2 | 0.1091 | 0.0206 | 0.1091 | 5.221 | 5.309 | 5.396 | 0.175 | 5.418 | 5.199 |
| preadv (P) | UNSPECIFIED:us-central | 3 | 0.1839 | 0.0481 | 0.1499 | 3.644 | 3.842 | 4.004 | 0.360 | 4.044 | 3.594 |
| M2 | GCP:us-east | 8 | 0.4286 | 0.0702 | 0.3722 | 5.604 | 6.196 | 6.569 | 0.965 | 6.736 | 5.423 |
| M2 | GCP:us-west | 16 | 0.8213 | 0.1218 | 0.5377 | 6.355 | 6.766 | 7.599 | 1.244 | 8.247 | 4.265 |
| M2 | OCI:us-ashburn-1 | 3 | 0.1691 | 0.0239 | 0.1300 | 6.948 | 7.007 | 7.260 | 0.312 | 7.323 | 6.934 |
| M2 | UNSPECIFIED:us-central | 3 | 0.2670 | 0.0500 | 0.2033 | 5.120 | 5.201 | 5.608 | 0.488 | 5.710 | 5.100 |

## Tail recurrence by region (counted, ops >=250 ms)

| arm | region | ops | >=250 | >=500 | >=1s |
|---|---|---:|---:|---:|---:|
| P | us-ashburn-1 | 120 | 0 | 0 | 0 |
| P | us-central | 600 | 0 | 0 | 0 |
| P | us-east | 602 | 4 | 1 | 0 |
| P | us-east4 | 120 | 0 | 0 | 0 |
| P | us-west | 2160 | 0 | 0 | 0 |
| M2 | us-ashburn-1 | 360 | 0 | 0 | 0 |
| M2 | us-central | 360 | 0 | 0 | 0 |
| M2 | us-east | 960 | 6 | 3 | 0 |
| M2 | us-west | 1920 | 3 | 3 | 0 |

## Descriptive variance — FULL eligible sets (no truncation)

Truncating to the first 30 by slot is what left P's headline containing `us-east4` (1) and
`us-ashburn-1` (1). The full eligible sets avoid that truncation artefact and are the more
trustworthy descriptive comparison; both are shown.

| arm | n | SD | CV | MAD | p10 | median | p90 | p90-p10 | best | worst |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| preadv (P) full | 43 | 0.7458 | 0.1339 | 0.5606 | 4.341 | 5.803 | 6.275 | 1.934 | 6.858 | 3.594 |
| M2 full | 37 | 0.8554 | 0.1343 | 0.6278 | 5.161 | 6.498 | 7.237 | 2.076 | 8.247 | 4.265 |

region composition, preadv (P) full: {'us-west': 23, 'us-east': 6, 'us-central': 10, 'us-east4': 2, 'us-ashburn-1': 2}
region composition, M2 full: {'us-west': 20, 'us-ashburn-1': 3, 'us-east': 9, 'us-central': 5}

