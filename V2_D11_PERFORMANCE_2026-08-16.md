# V2 D11 Performance Report — Canonical Batch Deploy + One True-Cold Request

Date: 2026-08-16 · Schedule: `deploy_and_run_v2_single.bat` + `run_v2_single.bat --conditioning-cache-nonce <fresh uuid>` (D10 profile, `V2_D10_INTEGRATION_VALIDATION=1`)
Source logs: `v2_d11_deploy_1.log`, `v2_d11_request_1.log` · Run dir: `comfymodal-data/benchmarks/runs/v2_2026-08-16_18-18-11/`

---

## Headline Numbers

| Metric | Value |
|---|---|
| Command → response (bat window) | **32.291 s** |
| Command → response (reconciled waterfall) | **27.253 s** |
| Command (without scheduling) → response | **23.548 s** |
| Modal scheduling time | **3.705 s** |
| Model deploy (V2 app, new identity) | **86.629 s** |
| Registry-proof prime (deploy-time, one-time) | 22.065 s (registry load, `prime_ok=true`) |
| Result image | 1088×1920, 3,129,718 B, `sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` |

Headline decomposition of the request path (host-reconciled):
- **Platform wall** (submission → remote Python resume): **8.895 s** (32.7 %)
- **Controllable application wall**: **17.128 s** (62.9 %)
- Global residual: 6.8 ms (0.0 %) — reconciliation **OK**

---

## Environment / Deployment Identity

| Field | Value |
|---|---|
| Cloud / region | GCP / us-east4 |
| GPU | RTX PRO 6000 Blackwell, VRAM 97,250 MiB, CUDA 13.0, CC 12.0 |
| CPU | AMD Family 191 Model 2, visible = 28 |
| Runtime shape (deployed == requested) | 12 CPU / 32768 MiB, baselines 12/32768, TBASE, O0, fingerprint `f504e296c398bdcb2c4c07e2` |
| Instance | `cd685f3ceb4a4105a9d73d2ee43b69ed` (restore session `66ffd73de5164cde98a959790fdf7c54`) |
| Peak RSS | 34.85 GiB |
| Freshness | **Fresh: YES** (restore_count=1, request_count=1, cold snapshot restore) |
| Deploy identity | `2305b0b3bbdf3fbe…` (new; v44 `7064c683e2dd141f` replaced), comfyui 0.24.0, core match=1 |
| Registry-proof store | `D1_PROOF_COVERS=true`, `store_hit=yes`, zero-gap (no registry re-import) |

---

## Cold-Start Waterfall (host-reconciled, run 1)

| # | Stage | Duration | Cum. | % |
|---|---|---|---|---|
| 1 | Modal pre-Python snapshot restoration | 6.413 s | 6.413 s | 27.24 % |
| 2 | Python/application restore | 783.9 ms | 7.197 s | 3.33 % |
| 3 | Restore-to-method entry | 30.5 ms | 7.228 s | 0.13 % |
| 4 | Remote method setup (graph start 1.609 s, graph setup 335.2 ms, residual 100.3 ms) | 1.945 s | 9.172 s | 8.26 % |
| 5 | PromptExecutor / cache setup (exec → cached 5.614 s, cached → first node 1.005 s) | 6.620 s | 15.792 s | 28.11 % |
| 6 | Pre-sampler execution | 995.1 ms | 16.787 s | 4.23 % |
| 7 | Sampler node to sampling | 122.2 ms | 16.909 s | 0.52 % |
| 8 | Sampling | 4.785 s | 21.694 s | 20.32 % |
| 9 | Post-sampling / VAE transition | 932.1 ms | 22.626 s | 3.96 % |
| 10 | VAE decode | 402.5 ms | 23.029 s | 1.71 % |
| 11 | Output encode / descriptor (PNG 163.1 ms) | 255.4 ms | 23.284 s | 1.09 % |
| 12 | Remote result handoff | 242.5 ms | 23.527 s | 1.03 % |
| 13 | Local result handling / caller return | 15.0 ms | 23.542 s | 0.06 % |
| — | Reconciliation | 6.77 ms | — | — |

---

## Model / Cache / Encode Detail

### Conditioning exact-hit cache (semantic-neutral nonce `31c0eb09-0178-4e59-8691-ea2f87d012bb`)
| Metric | Value |
|---|---|
| Decision | **miss_stored** (fresh nonce ⇒ deterministic miss, single encode) |
| Lookup wall | 1.03 ms |
| Key build / lock / entry lookup | 0.238 / 0.002 / 0.134 ms |
| Manifest entries | 63 (memory hit) |
| Prefetch | requested=1, join 115.2 ms, wall 492.9 ms, payload entries 3 (full) |

### CLIP (lumina2, loader CLIPLoader node 67)
| Metric | Value |
|---|---|
| Encode calls | **1** (7.473 s incl. loader wait) |
| CLIP raw encode | 7,446.9 ms |
| CLIP cold scheduled encode | 7,448.4 ms |
| CLIP cold forward | 2,585.8 ms |
| CLIP tokenize | 14.1 ms |
| CPU-snapshot CLIP load | 3,409.7 ms (snapshot part 1,496.3 ms) |
| Object id / holder source | `47094363197456` / direct (parity across all checkpoints) |
| Graph wait | 0.08 ms |

### UNET (z_image_turbo_bf16.safetensors, cpu_snapshot_mode=reuse)
| Metric | Value |
|---|---|
| UNET prepare | 6,961.4 ms |
| CPU-snapshot UNET load | 4,676.4 ms (snapshot part 3,953.1 ms) |
| get_model | 2,885.1 ms |
| `unet_work_completed_before_demand_ms` | **2,529.3 ms** (completed before demand) |
| Actual graph wait | 0.006 ms |
| Activation mode | late (prefill lanes critical, prefill_wait_for_unet=0) |

### VAE / Output
| Metric | Value |
|---|---|
| VAE load/H2D | 958.6 ms |
| VAE decode | 402.5 ms |
| PNG encode / compress | 163.1 / 154.6 ms (level 1) |

---

## Host / Submission / Startup Detail

| Metric | Value |
|---|---|
| Command start → python first line | 644.6 ms |
| Python first line → local receive | 487.6 ms |
| Local receive → modal submission | 94.0 ms (plan build 62.0 ms, handle lookup 16.0 ms, payload 19,896 B) |
| Scheduling (Modal app log) | 2,481.8 ms |
| Submission → remote Python resume | 8,895.2 ms |
| Restore method | 783.9 ms |
| Restore → method entry | 30.5 ms |
| Method entry → executor | 1,944.5 ms |
| Method entry → first remote event | 1,728.6 ms |
| First remote event → final result | 14,571.0 ms |
| Backend startup (container) | 19,510.9 ms |
| Snapshot restore (container) | 727.6 ms (GPU state 206.0 ms, CUDA init 217.2 ms) |
| Folder warm / input-types warm | 780.8 ms (29 folders) / 2,483.0 ms (31 classes) |
| Process start → response | 26,609.9 ms |

---

## Budget & Integrity

- MODAL_DEPLOYS=1 · MODAL_REQUESTS=1 · DIRECT_PYTHON_BENCHMARK_USED=NO
- Preflight before request: FINAL_REQUEST_PREFLIGHT=PASS (target match, 12/32768/baselines parity, fingerprint `f504e296c398bdcb2c4c07e2` == deployed, D1 covers, RUN_COUNT=1)
- Bat exit codes: deploy 0, request 0. No reruns, no retries.