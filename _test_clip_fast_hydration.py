"""Local synthetic proof harness for clip_fast_hydration.

Runs the capability gates, assessment, all hydration modes, the bounded
multi-file scheduler, and forward-parity checks against a CPU fp16 reference
using tiny synthetic CLIP-like text encoders.  Exit code 0 = all sections
pass.  CUDA sections are skipped (with SKIP notes) when CUDA is unavailable.

No Modal usage, no network, no paid runs — purely local.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import tempfile
import time

import torch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "comfymodal_runtime"))

import clip_fast_hydration as cfh

RESULTS: list[tuple[str, bool, str]] = []


def section(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name}" + (f" — {detail}" if detail else ""))


def expect(cond: bool, msg: str = "") -> bool:
    if not cond:
        print(f"    assertion failed: {msg}")
    return cond


CUDA_OK = torch.cuda.is_available()
DEVICE = "cuda" if CUDA_OK else "cpu"


class TinyBlock(torch.nn.Module):
    def __init__(self, dim: int = 64, dtype: torch.dtype = torch.float32, device: str = "cpu"):
        super().__init__()
        self.ln1 = torch.nn.LayerNorm(dim, dtype=dtype).to(device)
        self.ff1 = torch.nn.Linear(dim, dim, dtype=dtype).to(device)
        self.ln2 = torch.nn.LayerNorm(dim, dtype=dtype).to(device)
        self.ff2 = torch.nn.Linear(dim, dim, dtype=dtype).to(device)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.ff1(self.ln1(x))
        x = self.ff2(self.ln2(x))
        return x


class TinyTextEncoder(torch.nn.Module):
    def __init__(self, dim: int = 64, dtype: torch.dtype = torch.float32, device: str = "cpu"):
        super().__init__()
        self.emb = torch.nn.Embedding(512, dim, dtype=dtype).to(device)
        self.blocks = torch.nn.ModuleList([TinyBlock(dim, dtype, device) for _ in range(2)])
        self.ln_final = torch.nn.LayerNorm(dim, dtype=dtype).to(device)
        self.text_projection = torch.nn.Linear(dim, 32, dtype=dtype).to(device)

    def forward(self, ids: torch.Tensor) -> torch.Tensor:
        x = self.emb(ids)
        for b in self.blocks:
            x = b(x)
        x = self.ln_final(x)
        x = x.mean(dim=1)
        return self.text_projection(x)


def make_model(dtype: torch.dtype = torch.float16, device: str = "cpu") -> TinyTextEncoder:
    return TinyTextEncoder(dtype=dtype, device=device)


def make_meta_model(dtype: torch.dtype = torch.float16) -> TinyTextEncoder:
    return TinyTextEncoder(dtype=dtype, device="meta")


def legacy_transform(sd: dict) -> dict:
    out = dict(sd)
    w = out.pop("encoder.emb.weight")
    out["emb.weight"] = w
    tp = out.pop("text_projection")
    out["text_projection.weight"] = tp.transpose(0, 1).contiguous()
    return out


def make_legacy_sd(sd: dict) -> dict:
    out = dict(sd)
    w = out.pop("emb.weight")
    out["encoder.emb.weight"] = w
    tp = out.pop("text_projection.weight")
    out["text_projection"] = tp.transpose(0, 1).contiguous()
    return out


def inputs(seed: int = 7) -> torch.Tensor:
    g = torch.Generator().manual_seed(seed)
    return torch.randint(0, 512, (2, 8), generator=g)


def reference_forward(sd: dict, dtype: torch.dtype = torch.float16) -> torch.Tensor:
    model = make_model(dtype=dtype)
    model.load_state_dict(sd, strict=False)
    model.eval()
    with torch.no_grad():
        return model(inputs())


def parity_check(model: torch.nn.Module, ref: torch.Tensor, label: str) -> bool:
    model.eval()
    ids = inputs()
    if next(model.parameters()).is_cuda:
        ids = ids.cuda()
    with torch.no_grad():
        out = model(ids)
    out = out.detach().cpu() if out.is_cuda else out.detach()
    ok = torch.allclose(out, ref, rtol=1e-2, atol=1e-2)
    if not ok:
        print(f"    parity mismatch for {label}: max diff "
              f"{float((out - ref).abs().max())}")
    return ok


def build_fixtures(tmpdir: str) -> dict:
    import safetensors.torch

    dtype = torch.float16
    model = make_model(dtype=dtype)
    sd = {k: v.detach().clone() for k, v in model.state_dict().items()}

    identity_path = os.path.join(tmpdir, "identity_fp16.safetensors")
    safetensors.torch.save_file(sd, identity_path)

    legacy_sd = make_legacy_sd(sd)
    legacy_path = os.path.join(tmpdir, "legacy_fp16.safetensors")
    safetensors.torch.save_file(legacy_sd, legacy_path)

    quant_sd = dict(sd)
    quant_sd["blocks.0.ff1.comfy_quant"] = torch.zeros(64, 64, dtype=torch.uint8)
    quant_path = os.path.join(tmpdir, "quant_marked.safetensors")
    safetensors.torch.save_file(quant_sd, quant_path)

    mixed_sd = dict(sd)
    mixed_sd["blocks.1.ff2.weight"] = mixed_sd["blocks.1.ff2.weight"].float()
    mixed_path = os.path.join(tmpdir, "mixed_dtype.safetensors")
    safetensors.torch.save_file(mixed_sd, mixed_path)

    second_path = os.path.join(tmpdir, "identity_fp16_b.safetensors")
    safetensors.torch.save_file(sd, second_path)

    return {
        "sd": sd,
        "identity_path": identity_path,
        "legacy_path": legacy_path,
        "quant_path": quant_path,
        "mixed_path": mixed_path,
        "second_path": second_path,
        "file_size": os.path.getsize(identity_path),
    }


def safe_section(name: str, fn) -> None:
    try:
        fn()
    except Exception as exc:
        section(name, False, f"exception {type(exc).__name__}: {str(exc)[:200]}")


def main() -> int:
    import safetensors.torch

    tmpdir = tempfile.mkdtemp(
        prefix="clip_fh_",
        dir=r"C:\Users\parla\AppData\Local\Temp\opencode"
        if os.path.isdir(r"C:\Users\parla\AppData\Local\Temp\opencode")
        else None,
    )
    fx = build_fixtures(tmpdir)
    sd = fx["sd"]
    ref = reference_forward(sd)

    # ── A. gates ───────────────────────────────────────────────────────────
    ok = True
    g = cfh.gate_plain_tensor_storage(sd)
    ok &= expect(g.passed, f"plain_tensor_storage identity: {g.detail}")
    g = cfh.gate_plain_tensor_storage({**sd, "spiece_model": b"blob"})
    ok &= expect(not g.passed, f"plain_tensor_storage non-tensor: {g.detail}")
    g = cfh.gate_uniform_dtype(sd)
    ok &= expect(g.passed, f"uniform_dtype identity: {g.detail}")
    g = cfh.gate_uniform_dtype(safetensors.torch.load_file(fx["mixed_path"], device="cpu"))
    ok &= expect(not g.passed, f"uniform_dtype mixed: {g.detail}")
    g = cfh.gate_no_quant_transform(sd)
    ok &= expect(g.passed, f"no_quant identity: {g.detail}")
    g = cfh.gate_no_quant_transform(safetensors.torch.load_file(fx["quant_path"], device="cpu"))
    ok &= expect(not g.passed, f"no_quant quant-marked: {g.detail}")
    g = cfh.gate_no_quant_transform(sd, metadata={"_quantization_metadata": {"x": 1}})
    ok &= expect(not g.passed, f"no_quant metadata: {g.detail}")
    g = cfh.gate_transform_identity(sd, dict(sd))
    ok &= expect(g.passed, f"transform_identity identity: {g.detail}")
    legacy_sd = safetensors.torch.load_file(fx["legacy_path"], device="cpu")
    g = cfh.gate_transform_identity(legacy_sd, legacy_transform(legacy_sd))
    ok &= expect(
        not g.passed
        and "renamed_keys" in g.detail
        and "new_tensor_keys" in g.detail,
        f"transform_identity legacy: {g.detail}",
    )
    cpu_model = make_model()
    g = cfh.gate_assign_compatible(cpu_model, sd)
    ok &= expect(g.passed, f"assign_compatible identity: {g.detail}")
    g = cfh.gate_assign_compatible(cpu_model, safetensors.torch.load_file(fx["mixed_path"], device="cpu"))
    ok &= expect(not g.passed, f"assign_compatible mixed-dtype: {g.detail}")
    g = cfh.gate_meta_compatible(make_meta_model())
    ok &= expect(g.passed, f"meta_compatible meta: {g.detail}")
    g = cfh.gate_meta_compatible(make_model())
    ok &= expect(not g.passed, f"meta_compatible cpu: {g.detail}")
    g = cfh.gate_direct_cuda_compatible(sd)
    ok &= expect(g.passed == CUDA_OK, f"direct_cuda_compatible: {g.detail}")
    g = cfh.gate_patch_state_absent(None)
    ok &= expect(g.passed and "patch/LoRA" not in g.detail, f"patch_state none: {g.detail}")
    g = cfh.gate_patch_state_absent({"patches": {"something": object()}})
    ok &= expect(g.passed and "patch/LoRA" in g.detail, f"patch_state present: {g.detail}")
    section("A gates", ok)

    # ── B. assessment ──────────────────────────────────────────────────────
    ok = True
    ass = cfh.assess_candidate(sd, cpu_model, file_path=fx["identity_path"])
    ok &= expect(ass.eligible, f"assess identity eligible: {ass.reason}")
    ok &= expect(
        ass.preferred_hydration_mode in ("fastsafetensors", "safetensors_cuda"),
        f"assess identity preferred: {ass.preferred_hydration_mode}",
    )
    ok &= expect(ass.capabilities["transform_identity"], "capability transform_identity")
    meta_model = make_meta_model()
    ass = cfh.assess_candidate(
        legacy_sd, meta_model, transform=legacy_transform, file_path=fx["legacy_path"]
    )
    ok &= expect(ass.eligible, f"assess legacy eligible: {ass.reason}")
    ok &= expect(not ass.capabilities["transform_identity"], "legacy transform_identity False")
    ok &= expect(ass.preferred_hydration_mode == "meta_assign", f"legacy preferred: {ass.preferred_hydration_mode}")
    ass = cfh.assess_candidate(safetensors.torch.load_file(fx["quant_path"], device="cpu"), cpu_model)
    ok &= expect(not ass.eligible, f"assess quant ineligible: {ass.reason}")
    ok &= expect(ass.preferred_hydration_mode == "cpu_standard", "quant fallback cpu_standard")
    ass = cfh.assess_candidate(safetensors.torch.load_file(fx["mixed_path"], device="cpu"), cpu_model)
    ok &= expect(not ass.eligible, f"assess mixed ineligible: {ass.reason}")
    section("B assessment", ok)

    # ── C. fallback (current Comfy semantics) ──────────────────────────────
    ok = True
    model = make_model()
    before_ptr = {k: p.data_ptr() for k, p in model.state_dict().items()}
    model, rep = cfh.hydrate_cpu_standard(model, sd)
    after_ptr = {k: p.data_ptr() for k, p in model.state_dict().items()}
    ok &= expect(rep.mode == "cpu_standard", f"fallback mode: {rep.mode}")
    ok &= expect(all(before_ptr[k] == after_ptr[k] for k in before_ptr), "fallback identity preserved")
    ok &= expect(all(p.device.type == "cpu" for p in model.parameters()), "fallback params on cpu")
    ok &= expect(not rep.zero_copy, "fallback not zero-copy")
    ok &= expect(parity_check(model, ref, "cpu_standard"), "fallback parity")
    section("C fallback cpu_standard", ok)

    # ── D. meta + assign (zero-copy, CUDA) ─────────────────────────────────
    def section_d():
        if not CUDA_OK:
            section("D meta_assign zero-copy", True, "SKIP (no CUDA)")
            return
        ok = True
        meta_model = make_meta_model()
        sd_cuda = safetensors.torch.load_file(fx["identity_path"], device="cuda")
        meta_model, rep = cfh.hydrate_meta_assign(meta_model, sd_cuda)
        ok &= expect(rep.zero_copy, f"meta_assign zero_copy: {rep.zero_copy_evidence}")
        ok &= expect(all(p.device.type == "cuda" for p in meta_model.parameters()), "meta_assign params cuda")
        ok &= expect(parity_check(meta_model, ref, "meta_assign"), "meta_assign parity")
        section("D meta_assign zero-copy", ok)

    safe_section("D meta_assign zero-copy", section_d)

    # ── E. safetensors_cuda ────────────────────────────────────────────────
    def section_e():
        if not CUDA_OK:
            section("E safetensors_cuda", True, "SKIP (no CUDA)")
            return
        ok = True
        model = make_model()
        model, rep = cfh.hydrate_safetensors_cuda(fx["identity_path"], model)
        ok &= expect(all(p.device.type == "cuda" for p in model.parameters()), "st_cuda params cuda")
        delta = rep.peak_cuda_alloc_delta_bytes or 0
        ok &= expect(0 <= delta <= 2 * fx["file_size"] + 8 * 1024 * 1024, f"st_cuda delta sane: {delta}")
        ok &= expect(rep.zero_copy, f"st_cuda zero_copy: {rep.zero_copy_evidence}")
        ok &= expect(parity_check(model, ref, "safetensors_cuda"), "st_cuda parity")
        section("E safetensors_cuda", ok)

    safe_section("E safetensors_cuda", section_e)

    # ── F. fastsafetensors ─────────────────────────────────────────────────
    def section_f():
        if not CUDA_OK or importlib.util.find_spec("fastsafetensors") is None:
            section("F fastsafetensors", True, "SKIP (no CUDA or not installed)")
            return
        ok = True
        model = make_model()
        model, rep = cfh.hydrate_fastsafetensors(fx["identity_path"], model)
        ok &= expect(rep.zero_copy, f"fastsafe zero_copy: {rep.zero_copy_evidence}")
        ok &= expect(all(p.device.type == "cuda" for p in model.parameters()), "fastsafe params cuda")
        ok &= expect(hasattr(model, cfh._FASTSAFE_OWNER_ATTR), "fastsafe owner attached")
        ok &= expect(parity_check(model, ref, "fastsafetensors"), "fastsafe parity")
        section("F fastsafetensors", ok)

    safe_section("F fastsafetensors", section_f)

    # ── G. pinned staging ──────────────────────────────────────────────────
    def section_g():
        if not CUDA_OK:
            section("G pinned_staging", True, "SKIP (no CUDA)")
            return
        ok = True
        model = make_model()
        model, rep = cfh.hydrate_pinned_staging(fx["identity_path"], model, qd=2)
        ok &= expect(all(p.device.type == "cuda" for p in model.parameters()), "pinned params cuda")
        ok &= expect(rep.zero_copy, f"pinned zero_copy: {rep.zero_copy_evidence}")
        ok &= expect(parity_check(model, ref, "pinned_staging"), "pinned parity")
        section("G pinned_staging", ok)

    safe_section("G pinned_staging", section_g)

    # ── H. auto + fallback ─────────────────────────────────────────────────
    ok = True
    model = make_model()
    model, rep, ass = cfh.hydrate_auto(fx["quant_path"], model)
    ok &= expect(not ass.eligible, f"auto quant eligible False: {ass.reason}")
    ok &= expect(rep.mode == "cpu_standard", f"auto quant fallback mode: {rep.mode}")
    ok &= expect(all(p.device.type == "cpu" for p in model.parameters()), "auto quant params cpu")
    if CUDA_OK:
        model = make_model()
        model, rep, ass = cfh.hydrate_auto(fx["identity_path"], model)
        ok &= expect(ass.eligible, f"auto identity eligible: {ass.reason}")
        ok &= expect(
            rep.mode in ("fastsafetensors", "safetensors_cuda", "pinned_staging"),
            f"auto identity mode: {rep.mode}",
        )
        ok &= expect(all(p.device.type == "cuda" for p in model.parameters()), "auto identity params cuda")
    section("H auto + fallback", ok)

    # ── I. multi-file scheduler ────────────────────────────────────────────
    ok = True
    p1 = cfh.plan_qd_budget(1, qd_base=8)
    ok &= expect(p1.per_file_qd == 8 and p1.total_cap == 8, f"budget n=1: {p1}")
    p2 = cfh.plan_qd_budget(2, qd_base=8)
    ok &= expect(p2.per_file_qd == 4, f"budget n=2: {p2.per_file_qd}")
    p3 = cfh.plan_qd_budget(3, qd_base=8)
    ok &= expect(p3.per_file_qd == 2, f"budget n=3: {p3.per_file_qd}")
    p4 = cfh.plan_qd_budget(4, qd_base=8)
    ok &= expect(p4.per_file_qd == 2, f"budget n=4: {p4.per_file_qd}")
    p8 = cfh.plan_qd_budget(8, qd_base=2, min_per_file=1)
    ok &= expect(p8.per_file_qd == 1 and p8.total_cap == 4, f"budget min-clamp: {p8}")

    def factory(name: str) -> TinyTextEncoder:
        return make_model()

    results, total_ms = cfh.hydrate_many(
        [fx["identity_path"], fx["second_path"]], factory, qd_base=4
    )
    ok &= expect(len(results) == 2, f"hydrate_many count: {len(results)}")
    ok &= expect(
        [r.name for r in results] == ["identity_fp16", "identity_fp16_b"],
        f"hydrate_many order: {[r.name for r in results]}",
    )
    ok &= expect(
        all(r.assessment is not None and r.assessment.eligible for r in results),
        "hydrate_many assessments eligible",
    )
    ok &= expect(
        all(parity_check(r.model, ref, f"many/{r.name}") for r in results),
        "hydrate_many parity",
    )
    ok &= expect(total_ms > 0, f"hydrate_many total wall: {total_ms} ms")
    section("I multi-file scheduler", ok)

    # ── K. summary table ───────────────────────────────────────────────────
    print("\n--- mode timing table ---")
    for mode in ("cpu_standard", "meta_assign", "safetensors_cuda", "fastsafetensors", "pinned_staging"):
        print(f"  {mode:<18} (per-section results above)")
    print()

    failures = [r for r in RESULTS if not r[1]]
    if failures:
        print(f"FAILURES: {[f[0] for f in failures]}")
        shutil.rmtree(tmpdir, ignore_errors=True)
        return 1
    print(f"ALL PASS ({len(RESULTS)} sections, tmp {fx['file_size']} bytes/file)")
    shutil.rmtree(tmpdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    t0 = time.perf_counter()
    code = main()
    print(f"elapsed {time.perf_counter() - t0:.1f}s")
    sys.exit(code)
