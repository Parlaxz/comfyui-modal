# Cold Parallelism Forensics Harness

Run UUID: `4560eec83e2b4758818c5c98e52334c2`

This is Testing 7 only, against the existing clean App and pinned V1/V2 Volumes. Resources are 12 CPU / 16384 MiB / GPU=None. No cloud, region, H2D, deployment, or automatic measured-reader retry is allowed.

Writer preparation may use deterministic batches of at most eight workers. Readers and cleanup are serial. Every counted cold observation and cache branch receives a new corpus ID.

Raw attempt envelopes retain exact args, result/failure, deployment identity, container sessions, and raw path.

Unsupported and opaque layers are listed rather than filled with causal prose.
