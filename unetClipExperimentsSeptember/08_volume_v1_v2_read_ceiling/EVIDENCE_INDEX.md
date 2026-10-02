# Evidence Index

All raw benchmark artifacts remain in the sibling `modal-volume-read-ceiling` workspace. The files in this directory are a report and handoff summary; they do not replace or rewrite raw evidence.

## Authoritative raw and ledger files

| Role | Path | Use |
|---|---|---|
| Preserved attempt ledger | `../../../modal-volume-read-ceiling/results/ledger.json` | Retained attempt inventory, validity, geometry, and raw result references |
| Block-search and confirmation evidence | `../../../modal-volume-read-ceiling/results/raw_ceiling/` | Primary source-ceiling measurements; includes V1/V2 block-search and confirmation attempts |
| Full-RAM evidence | `../../../modal-volume-read-ceiling/results/full_ram/` | Six-run final-RAM materialization cohorts for V1 and V2 |
| Smoke/capability evidence | `../../../modal-volume-read-ceiling/results/smokes/` | Capability receipts, source-read smoke results, and retained failed capability attempt |

## Identity and setup

| Role | Path | Use |
|---|---|---|
| Deployment identity | `../../../modal-volume-read-ceiling/results/setup/deployment_identity.json` | Workspace, app, image, Volume IDs, source-file hash, function shape, and artifact pointers |
| Volume setup | `../../../modal-volume-read-ceiling/results/setup/volumes.json` | V1/V2 Volume names, IDs, and requested versions |
| V1 setup receipt | `../../../modal-volume-read-ceiling/results/setup/setup_v1.json` | Version-pinned V1 hydrate/setup receipt |
| V2 setup receipt | `../../../modal-volume-read-ceiling/results/setup/setup_v2.json` | Version-pinned V2 hydrate/setup receipt |

## Derived analysis

| Role | Path | Use |
|---|---|---|
| Corrected analyzer | `../../../modal-volume-read-ceiling/analyze.py` | Recomputes conclusions from preserved local artifacts only |
| Standalone report | `../../../modal-volume-read-ceiling/results/REPORT.md` | Analyzer-generated report; corrected geometry and CPU interpretation |
| Standalone summary | `../../../modal-volume-read-ceiling/results/summary.json` | Analyzer-generated machine-readable summary |

## Key raw selections

- Block-search best geometry: V1 and V2 both `134217728` bytes (`128 MiB`) with QD `2`.
- Confirmation geometry: V1 and V2 both `128 MiB/QD2`.
- Full-RAM geometry: V1 and V2 both `128 MiB/QD2`.
- Secondary common geometry: `32 MiB/QD8`.
- Source file: `12309866400` bytes with SHA-256 `2407613050b809ffdff18a4ac99af83ea6b95443ecebdf80e064a79c825574a6`.

## Preservation rule

Raw directories, ledger, setup receipts, and runtime source were not modified for this handoff. The generated report and summary are derived artifacts and can be regenerated locally with `python analyze.py` from the analysis workspace.
