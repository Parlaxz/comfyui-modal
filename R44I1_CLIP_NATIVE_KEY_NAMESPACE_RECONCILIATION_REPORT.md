# R44I1 — Native CLIP Checkpoint→Live Key-Namespace Reconciliation for Cast-Once FP16

Worktree: `../comfyui-modal-r42` · Branch `r42-golden-reconciliation` · HEAD `0c59f46e3238f421378e8852ebc548da815b70af` (no commits made)
Batch type: LOCAL analysis + implementation only. **No deploy, no Modal run, no paid request, no transport tuning, no sampler/Gantt behavior change.**
Concurrent lane: R44I2 (sampler/telemetry persistence) — zero file overlap (§14).

---

## 1. H3 failure reconstruction

R44H3 Run 1 (`v2-benchmark-0-476f84af0e92`, profile `r44-request-fastsafe`, deployment fingerprint `860408f3…`):

- FastSafe transport + native construction started; cast-once validation raised
  **`RuntimeError: missing_key:model.embed_tokens.weight`** inside
  `_validate_cast_once_bind`.
- The except-arm failed closed exactly as designed: partial patcher discarded, owners closed,
  physical-load claim released, sticky terminal reason recorded, `native_comfy` fallback observation
  published, original node method ran → RuntimeStatus DEGRADED
  (`loader_fallback_clip:fastsafetensors_direct_gpu->native_comfy`), Runs 2–3 correctly not spent.
- Canonical SHA still matched exactly through the fallback (`20b10e1f…e5260`) — output correctness was
  never at risk; only the fast arm's namespace assumption was false.

Mechanism (proven): the H1 validator built its live-tensor map from the OUTER wrapper —

```python
live = {name: t for name, t in csm.state_dict().items() ...}   # csm == cond_stage_model
...
t = live.get(key)                                              # raw staged key lookup
raise RuntimeError(f"missing_key:{key}")
```

but for the pinned FLUX/Qwen3_4B path `cond_stage_model.state_dict()` keys are
**`transformer.model.<checkpoint key>`** (§4), so every raw staged key missed. The first sorted
comparable failure surfaced as `missing_key:model.embed_tokens.weight`.

## 2. Why the H1/H3 local suites (hundreds of green tests) missed it

Proven deficiency — hypotheses #1 and #7 of the batch brief, both confirmed:

1. **Synthetic fixture used identical source/live key names.**
   `tests/test_r44h1_clip_cast_once.py` docstring states it explicitly:
   *"the fake TE module is FLAT so staged checkpoint keys equal final state_dict keys (the
   cast-once validator is name-keyed)"*, and `TinyTE` carries parameters directly named
   `weight/bias/logit_scale`.
2. **Wrapper prefixes differ from transformer prefixes; the fixture collapsed them.**
   The fake `CLIP.load_sd` stub called `cond_stage_model.load_sd(sd)` where `cond_stage_model`
   WAS the transformer. The real chain has TWO extra levels:
   `CLIP.load_sd → SDClipModel.load_sd → self.transformer.load_state_dict`, i.e. the actual
   `load_state_dict` recipient sits BELOW the `transformer.` wrapper prefix and itself nests a
   `model.` child (`Qwen3_4B.model = Llama2_`). The validator queried one level too high; the flat
   fixture made that indistinguishable from correct.

The H1 report had pre-registered exactly this falsification condition (*"that outcome would falsify
the name-keyed assumption"*); R44H3 executed it.

## 3. Exact A–J key namespaces (pinned Comfy source, verified against a REAL tiny Qwen3_4B)

Pinned source: `ComfyUI June Install\ComfyUI\comfy\`. Live-namespace ground truth was proven by
constructing the REAL `comfy.text_encoders.llama.Qwen3_4B` with tiny dims (vocab 64 / hidden 16 /
1 layer, CPU, FP16) inside the new regression suite — its `state_dict()` returned exactly
`model.embed_tokens.weight`, `model.layers.0.{self_attn.{q,k,v,o}_proj, mlp.{gate,up,down}_proj,
input_layernorm, post_attention_layernorm}.weight`, `model.norm.weight` (13/13 parameters, ZERO
buffers, no `lm_head`).

| Stage | What it is | Key format for the failing tensor |
|---|---|---|
| A | raw safetensors header (398 tensors, uniform BF16, no transform markers, no quant metadata — R44E log lines 111–150, R44F gates) | `model.embed_tokens.weight` |
| B | FastSafe served state dict (verbatim CUDA staging; guard returns `dict(sd_cuda)`) | `model.embed_tokens.weight` (unchanged) |
| C | entering `comfy.sd.load_text_encoder_state_dicts` / `load_clip` | unchanged — no `prefix_to_remove`, no `state_dict_prefix_replace`, no `convert_text_enc_state_dict` on the QWEN3_4B branch (`sd.py:1590-1596`); the conditional `lm_head.weight→model.lm_head.weight` rename does not apply |
| D | after ALL native text-encoder state transformations | unchanged (there are none for this path) |
| E | dict passed into `<recipient>.load_state_dict(...)` (`sd.py:259-269` → `sd.py:414-428` full_model=False → `sd1_clip.py:308-310`) | `model.embed_tokens.weight` (VERBATIM) |
| F | the exact receiving module | `cond_stage_model.transformer` = `llama.Qwen3_4B` (`llama.py:1030-1037`); its OWN namespace is the raw checkpoint namespace |
| G | `receiving_module.state_dict()` | `model.embed_tokens.weight`, … (== A) |
| H | outer `cond_stage_model.state_dict()` | `transformer.model.embed_tokens.weight` (+ ctor param `logit_scale` OUTSIDE the recipient) |
| I | final `named_parameters()` | csm-relative == H names; recipient-relative == F names |
| J | aliases / tied weights | NONE — `Qwen3_4BConfig.lm_head = False` (`llama.py:207-228`) ⇒ no `lm_head` module, no tied registration; generation uses `embed_tokens.weight` directly (`llama.py:839-849`) |

### Full transformation chain for `model.embed_tokens.weight`

```
RAW header            model.embed_tokens.weight
  → FastSafe served   model.embed_tokens.weight                    (identity)
  → loadsd input      model.embed_tokens.weight                    (identity; captured by seam)
  → load_state_dict   model.embed_tokens.weight                    (recipient-relative target)
  → live parameter    transformer.model.embed_tokens.weight        (cond_stage_model-relative)
                      cond_stage_model.transformer.model.embed_tokens.weight  (CLIP-relative)
```

**Native key-transform functions: NONE exist for this path — the native transform is structural
nesting, not renaming.** The definitive functions are the delegation sites:
`comfy/sd.py:414-428` (`CLIP.load_sd`, full_model=False branch),
`comfy/text_encoders/sd1_clip.py:308-310` (`SDClipModel.load_sd` →
`self.transformer.load_state_dict(sd, strict=False, assign=can_assign_sd)`),
`comfy/text_encoders/llama.py:1030-1037` (`Qwen3_4B` assigning `self.model = Llama2_(...)`),
`comfy/text_encoders/llama.py:668-692` (`Llama2_` building `embed_tokens/layers/norm`).
`state_dict_key_replace` / `state_dict_prefix_replace` (`comfy/utils.py:195-211`) and
`convert_text_enc_state_dict` (`diffusers_convert.py:188-189`, identity) are NOT invoked here.

## 4. Chosen mapping architecture (per brief §7)

**Option A + B hybrid — capture + deterministic native-structure derivation; no invented mapping.**

1. **Capture (telemetry truth):** the cast-once `CLIP.load_sd` seam now records the EXACT
   post-transformation keyset handed toward the recipient (`loadsd_input_key_total`,
   `loadsd_input_keys_sample`) — proving remotely that loadsd keys == raw keys.
2. **Derive (validation truth):** new `_resolve_loadsd_recipients(csm, required_keys)` walks
   `cond_stage_model.named_modules()` and accepts as recipient exactly those modules whose OWN
   `state_dict()` contains EVERY comparable key VERBATIM — a faithful mirror of
   `torch.nn.Module.load_state_dict` key resolution. Because the root module always participates:
   - exactly ONE candidate ⇒ validate each source against `live[prefix + source_key]`
     (`prefix=""` ⇒ direct; else the single native wrapper prefix);
   - ZERO candidates ⇒ some required key exists nowhere in the live tree ⇒
     `missing_key:<first absent>` (fail closed);
   - MULTIPLE candidates ⇒ `ambiguous_live_key:<first sorted source>:<candidate_count>`
     (fail closed).
3. Validation then performs the unchanged H3 bounded structural/value proof on the MAPPED pair.

### Rejected heuristics (all banned by the brief, none used)

global `model.` strip · global `transformer.` add · suffix matching without uniqueness proof ·
first-match on ambiguous names · silently ignoring unmatched keys.

## 5. Full 398-tensor accounting (derived from native semantics; remote gate confirms)

Local `qwen_3_4b.safetensors` is a 0-byte placeholder (real bytes live on the Modal volume), so the
bucketing below is DERIVED from the R44E/R44F header evidence (398 tensors, uniform BF16, no
transform markers, no quant metadata, plain TE export) plus pinned-source semantics. Every one of
the 398 entries is classified:

| Bucket | Count | Bytes |
|---|---:|---:|
| checkpoint_tensor_count | 398 | 8,044,982,048 |
| native_loadsd_input_count | 398 (seam-captured remotely) | 8,044,982,048 |
| comparable (cast-once proven) | 398 | 8,044,982,048 |
| direct_match_count (csm-level verbatim) | 0 | 0 |
| remapped_count (ONE native wrapper prefix `transformer.`) | 398 | 8,044,982,048 |
| alias/tied destination count | 0 (lm_head=False; no tied registration) | 0 |
| transformed_exception_count | 0 | 0 |
| buffer/blob_count | 0 | 0 |
| missing_count | 0 (required) | 0 |
| ambiguous_count | 0 (required) | 0 |
| extra_live_parameter_count | 1 — `logit_scale` | 8 |
| extra_live_buffer_count | 0 (rope inv_freq computed per-forward, `llama.py:407-417`) | 0 |

`logit_scale` carve-out justification (native semantics, not a weakening): pinned
`sd1_clip.py` constructs `self.logit_scale = torch.nn.Parameter(torch.tensor(4.6055))` — a CONSTANT
init that `SDClipModel.load_sd` NEVER sources from any checkpoint (it only loads
`self.transformer`). The identical ctor code ran in our construction, so the value is bit-equal to
the native fallback's. It is counted + reported by name (`extra_live_parameter_sample`), never
fatal. Unbound parameters INSIDE the derived recipient remain hard-fatal
(`unbound_parameter:<live_key>`) — stricter than native `strict=False`, preserving H1/H3 policy.

## 6. Implementation (files/functions)

- `comfymodal_runtime/request_clip_fastsafe.py`
  - NEW `_resolve_loadsd_recipients(csm, required_keys)` — deterministic recipient derivation
    (verbatim containment over `named_modules()`, `(prefix, name, module)` tuples).
  - NEW constants `_PRIORITY_MAPPING_SAMPLE_KEY = "model.embed_tokens.weight"`,
    `_MAPPING_SAMPLE_LIMIT = 8`.
  - REWRITTEN `_validate_cast_once_bind` into four passes:
    P1 namespace-independent classification (blob / header-transformed / comparable — needs only
    staged payload + descriptor); P2 unique-recipient derivation per staged file (fail-closed
    `ambiguous_live_key:*` / `missing_key:*`); P3 mapped structural + bounded value proof (shape,
    dtype==expected FP16, device, `data_ptr` storage-independence, deterministic sample equality;
    direct/remapped/alias bucketing; mapping records); P4 extras accounting with the
    inside/outside-recipient unbound-parameter policy. Signature unchanged; error-string formats
    preserved (`missing_key:`, `aliasing_unexpected:`, `bind_*:`, `value_mismatch:`,
    `sample_count_mismatch:`, `meta_residual:`, `unbound_parameter:`) + new `ambiguous_live_key:`,
    `no_comparable_keys`. Accounting dict keeps EVERY legacy key and adds:
    `native_loadsd_input_count`, `live_parameter_key_count`, `live_tensor_key_count`,
    `recipient_module_names`, `direct_match_count`, `remapped_count`, `alias_count`,
    `buffer_blob_count`, `missing_count`, `ambiguous_count`, `extra_live_parameter_count`,
    `extra_live_parameter_sample`, per-bucket byte counts, `validation_mapping_mode`
    (`native_recipient_state_dict`), `mapping_samples` (bounded ≤8, `model.embed_tokens.weight`
    ALWAYS visible when present).
  - Cast-once seam `_load_sd_wrapper`: additive loadsd keyset capture (total + first-call sorted
    12-key sample). Parity-lane wrapper untouched.
  - `clip_fast_load_end` telemetry (additive; parity lane emits only the two generic counts):
    `raw_checkpoint_key_count`, `transformed_loadsd_key_count`, `loadsd_input_keys_sample`,
    `live_parameter_key_count`, `key_mapping_mode`, `validation_mapping_mode`,
    `direct_key_count`, `remapped_key_count`, `alias_key_count`, `missing_key_count`,
    `ambiguous_key_count`, `extra_live_key_count`, `recipient_modules`, `mapping_samples`.
- `tests/test_r44i1_clip_namespace.py` — NEW (§8).
- **Zero ComfyUI core edits. Zero transport edits. Zero sampler/Gantt edits.**

## 7. Bounded-validation preservation (H3 contract intact)

Same `_bounded_sample_cpu` deterministic stride sampling (default 256 elements/tensor), same deep
mode gated strictly behind `COMFYMODAL_CLIP_CAST_ONCE_DEEP_VALIDATION`, nominal
`validation_full_model_scan=false`, no added synchronize, no full-tensor CPU copies, no second
`load_state_dict`. The H3 source-inspection tests pass unmodified. For 398×256 elements the sample
budget stays ~203.8k elements per side, exactly as H3 reported.

## 8. Realistic Qwen regression suite (`tests/test_r44i1_clip_namespace.py`, 9 tests)

1. `test_real_pinned_qwen3_4b_live_namespace_matches_checkpoint` — REAL pinned
   `llama.Qwen3_4B` (tiny dims): recipient namespace == raw checkpoint namespace; state_dict ==
   named_parameters; zero buffers; no lm_head. (skipif pinned comfy unavailable)
2. `test_real_pinned_qwen_cast_once_validation_native_mapping` — REAL skeleton, REAL
   `load_state_dict(BF16, strict=False, assign=False)` single cast, wrapped in an SDClipModel-mirror
   (`transformer.` + constant-init `logit_scale`): full validator PASS; `remapped_count==N`,
   `direct==0`, `extra_live_parameter_count==1 ["logit_scale"]`, mapping sample triple
   `model.embed_tokens.weight → model.embed_tokens.weight → transformer.model.embed_tokens.weight`
   (`native_wrapper_prefix`), bit-exact single-cast proof.
3. Recipient derivation units: nested-unique (`transformer.`), flat-root (`""`).
4. `missing_key:model.embed_tokens…` fail-closed on a realistic renamed source.
5. `ambiguous_live_key:model.embed_tokens.weight:2` fail-closed (twin siblings).
6. `unbound_parameter:transformer.model.unused_head` fail-closed INSIDE recipient.
7. Producer END-TO-END through the scoped seams with the NESTED fixture and the REAL delegation
   chain (`CLIP.load_sd → csm.load_sd → transformer.load_state_dict`), authentic Qwen keys covering
   embedding / attention(q,k,v,o) / MLP(gate,up,down) / layernorms / final norm + blob key:
   publishes `cast_once_fp16`, asserts the complete R44I1 telemetry contract including
   `raw=13 / loadsd=13 / live_params=13`, `direct=0 / remapped=12 / alias=0 / missing=0 /
   ambiguous=0 / extra_live=1`, `recipient_modules=["transformer"]`, early non-destructive owner
   retirement, canonical-arm observation.
8. H3-class reproduction: served key absent from the live tree ⇒ transport happens, then fail-closed
   to native with sticky terminal reason; nothing published.

This is NOT another identical-names toy: source keys are authentic HF Qwen names, the live tree has
the real two-level wrapper nesting, and tests 1–2 execute the actual pinned constructor code.

## 9. Source-owner / failure ordering re-audit (brief §12)

Unchanged and re-audited: any failure BEFORE publication (now including the new P2 ambiguity arm)
raises into the single except-arm → `_detach_partial_owners` → `_discard_failed_clip`
(un-registers a patcher that pinned `sd.py:280-281` may have registered mid-construction) →
`_fail_closed` (closes owners, releases the physical-load claim, records sticky terminal reason +
`native_comfy` fallback observation, telemeters `clip_fastsafe_fallback` with the precise reason
string) → original node method. No stale loaded model, no leaked 8 GB staging owner, no
half-published CLIP. Retirement-failure fail-closed-before-publication (H3) untouched.

## 10. Static nominal-path copy audit (re-run post-fix)

Sweep of `request_clip_fastsafe.py` for
`.to( | .cuda( | copy_( | load_state_dict | manual_cast | model_patches_to | load_model_gpu |
model_load | clone | contiguous`:

| Hit | Class |
|---|---|
| L55/384/771/1131–1192/1855 `load_state_dict` mentions | documentation/comments only |
| L1381 `staged.detach().to(t.dtype).cpu()` | deep-mode validation temp (diagnostic-only path) |
| L1399 `staged_value.to(dtype=live_value.dtype)` | bounded SAMPLE dtype normalize (≤256 elems) |
| L1088–1099 `contiguous` mentions/check | bounded sampler docs/guard |

Nominal path still contains: ONE FastSafe source transfer + ONE native
`load_state_dict(assign=False)` BF16→FP16 conversion + ZERO later model-sized transfers + BOUNDED
validation only. Recipient derivation reads `state_dict()` KEY SETS (reference dicts — no tensor
copies). No full source cloning, no state-dict duplication, no extra load pass, no extra
model-sized compare. **`R44I1_HOT_PATH_EXTRA_MODEL_SIZED_COPY = NO`.**

## 11. Files changed

1. `comfymodal_runtime/request_clip_fastsafe.py` (modified in place; already-untracked R44F/H1/H3
   work fully preserved — additions only around the cast-once validator/seam/telemetry)
2. `tests/test_r44i1_clip_namespace.py` (NEW)
3. `R44I1_CLIP_NATIVE_KEY_NAMESPACE_RECONCILIATION_REPORT.md` (NEW, this file)

## 12. Exact local test evidence

- New R44I1 suite: **9 passed**.
- §15 battery (R44A determinism, R44B request-fastsafe, R44D proof-installation + env-passthrough,
  R44E durability, R44F zero-copy, R44H1 cast-once, R44H2 sampler-telemetry-gantt, R44H3
  bounded-validation + sampler-reset, R44I1 namespace, runtime-state reload guard, models-volume
  reload guard, v2 waterfall + waterfall contract): **260 passed / 0 failed** (15.31 s).
- `py_compile` on both touched .py files: OK. TOML parse
  `config/v2/profiles/r44-request-fastsafe.toml`: OK (profile unchanged).
- Pre-existing UNRELATED failure documented, NOT introduced by this batch:
  `tests/test_audit_round7.py::WaterfallCategoryTests::test_no_parent_child_double_count` fails
  because concurrently-modified `comfyapp.py` no longer matches the round7 source audit
  (`not in c` pattern absent). Verified failing independent of my changes; `comfyapp.py` is another
  lane's dirty file and was left untouched. A full `pytest tests` run additionally hangs somewhere
  outside the §15 battery (pre-existing; not chased per lane discipline).

## 13. Concurrent-file overlap assessment (vs R44I2)

R44I2 owns: `sampler_telemetry.py`, `dynamic_gantt.py`, `tools/render_dynamic_gantt.py`,
`tests/test_r44g1_dynamic_gantt.py`, `tests/test_r44h2_sampler_telemetry_gantt.py`,
`tests/test_r44i2_direct_boundary_telemetry.py`, `R44I2_AUTHORITATIVE_SAMPLER_BOUNDARY_TELEMETRY_REPORT.md`.
R44I1 wrote ONLY the three files in §11. **Zero overlap.** Shared-worktree dirty state preserved;
`request_clip_fastsafe.py` sections were reread immediately before each edit; no foreign edits were
observed or clobbered during the batch.

## 14. Checklist for the ONE future remote proof gate

Profile `r44-request-fastsafe` (UNCHANGED), same workflow/workload as R44E/F/H3, single cold run,
stop rule after Run 1. Gate-valid requires ALL of:

1. Deployment fingerprint recorded; no code/config change after the paid request starts.
2. Canonical SHA exact match: `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`.
3. No `clip_fastsafe_skip`; `bind_mode="cast_once_fp16"`; `adoption_mode="cast_once_fp16"`;
   `checkpoint_dtype="BF16"`; `expected_runtime_dtype="torch.float16"`;
   `live_parameter_dtype="torch.float16"`.
4. Namespace reconciliation fields on `clip_fast_load_end`:
   `raw_checkpoint_key_count==398`; `transformed_loadsd_key_count==398`;
   `live_parameter_key_count==399` (398 + `logit_scale`);
   `key_mapping_mode=="native_recipient_state_dict"`; `direct_key_count==0`;
   `remapped_key_count==398`; `alias_key_count==0`; `missing_key_count==0`;
   `ambiguous_key_count==0`; `extra_live_key_count==1`; `recipient_modules==["transformer"]`.
5. `mapping_samples` contains
   `{source_key:"model.embed_tokens.weight", loadsd_key:"model.embed_tokens.weight",
   live_key:"transformer.model.embed_tokens.weight", mapping_kind:"native_wrapper_prefix"}`.
6. `cast_once_count==398`; `transformed_count==0`; `exception_count==0`;
   `duplicate_weight_bytes_before_forward==0`; `owners_retired==1`; `owners_failed==0`.
7. `cuda_allocated_after_source_release_bytes ≈ cuda_allocated_after_construction_bytes − 8.045 GB`;
   `model_sized_movement_detected=false`; residency registered.
8. `RuntimeStatus=NOMINAL`; observed CLIP loader `fastsafetensors_direct_gpu`; UNET control
   unchanged (453/453 same-storage, D15 ordering intact).
9. ANY deviation ⇒ stop rule; analyze `mapping_samples` / `loadsd_input_keys_sample` / terminal
   reason before any retry. Do NOT use fallback timing as cast-once performance evidence.

---

R44I1_H3_MISSING_KEY_ROOT_CAUSE_PROVEN = YES
R44I1_EMBED_TOKENS_RAW_KEY = model.embed_tokens.weight
R44I1_EMBED_TOKENS_LOADSD_KEY = model.embed_tokens.weight
R44I1_EMBED_TOKENS_LIVE_KEY = transformer.model.embed_tokens.weight
R44I1_NATIVE_KEY_TRANSFORM_REUSED = YES
R44I1_CHECKPOINT_KEYS_CLASSIFIED = 398/398
R44I1_MISSING_KEYS_LOCAL = 0
R44I1_AMBIGUOUS_KEYS_LOCAL = 0
R44I1_EXTRA_LIVE_KEYS_LOCAL = 1
R44I1_VALIDATION_FULL_MODEL_SCAN = NO
R44I1_HOT_PATH_EXTRA_MODEL_SIZED_COPY = NO
R44I1_CAST_ONCE_NAMESPACE_FIX_IMPLEMENTED = YES
R44I1_FAIL_CLOSED = YES
R44I1_REMOTE_RUN_PERFORMED = NO
R44I1_READY_FOR_RECONCILIATION = YES
