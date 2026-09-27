# Baked SageAttention Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get Modal cold restore back near the earlier ~3s behavior by eliminating all restore-time SageAttention source download/compile work and making restore choose between a baked SageAttention 2.2.0 CUDA artifact and immediate Triton/PyTorch fallback.

**Architecture:** Keep `startup(snap=True)` fully CPU-only and snapshot-safe. Bake a pinned SageAttention 2.2.0 build into the Modal image, verify that the package contains compiled shared objects plus a working `_fused` import during image build, and then make `restore(snap=False)` do only four things: re-enable ComfyUI GPU state, warm CUDA, characterize the baked SageAttention package, and choose a sticky per-container mode (`baked_cuda`, `triton_fallback`, `disabled`). Patch KJNodes at `get_sage_func()` so workflows that request SageAttention immediately fall back to safe attention when the baked package is missing or unusable.

**Tech Stack:** Python 3.11, Modal image build/runtime hooks, ComfyUI in-process backend, SageAttention 2.2.0, comfyui-kjnodes, pytest/unittest.

**Current app version:** `COMFYAPP_VERSION = "2.3.9"`

---

## Research constraints this plan assumes

- Modal docs explicitly warn that `torch.cuda.is_available`, `torch.cuda.get_device_capability`, and similar calls during CPU-style snapshotting can initialize CUDA in an unusable state. No SageAttention CUDA probe/import is allowed in `startup(snap=True)`.
- Tolga Oğuz’s Modal + ComfyUI snapshot pattern still supports the <3s target: lie about GPU availability during snapshot creation and restore GPU access afterward.
- Recent Blackwell ComfyUI guidance consistently uses SageAttention **2.2.x** with the KJNodes patch node, not `--use-sage-attention` at global startup.
- Recent SageAttention / ComfyUI issue reports show that “package imports” are not enough proof. A usable install must include compiled `.so` artifacts and a working `_fused` import.
- Restore-time source builds are the current 120s regression and must be removed completely.

## File map

- Modify: `comfyapp.py`
  - remove restore-time rebuild path, add build-time SageAttention 2.2.0 bake commands, add baked-package characterization helpers, add sticky runtime mode selection, and patch KJNodes `get_sage_func` fallback policy
- Modify: `tests/test_comfyapp_packaging.py`
  - assert image build pins SageAttention `v2.2.0`, verifies compiled `.so` files, and verifies `_fused` import
- Modify: `tests/test_comfyapp_volume_lifecycle.py`
  - assert `startup()` never probes/imports Sage CUDA, `restore()` never compiles SageAttention, and `restore()` selects runtime mode after GPU state is restored
- Modify: `tests/test_modal_timing_trace.py`
  - keep trace expectations compatible with a fast restore path that does not spend minutes compiling
- Add: `tests/test_sageattention_restore_policy.py`
  - pure-Python tests for package characterization, runtime mode selection, and KJNodes `get_sage_func` fallback patch behavior

## Constraints

- `startup(snap=True)` must not download, compile, or import SageAttention CUDA modules.
- `_force_cpu_during_snapshot()` must continue to preserve both protections documented in `memory.md`:
  - the `torch.cuda` monkey-patch
  - the `sys.meta_path` CUDA-extension blocker
- `restore(snap=False)` must not invoke `pip install .`, source download, or runtime compilation.
- Prompt execution must never trigger SageAttention setup work.
- If the baked SageAttention package fails verification, fallback must happen once per container and remain sticky for that container.

## Runtime modes

- `baked_cuda`
  - SageAttention package contains compiled `.so` files, `_fused` imports, and the preferred KJNodes backend symbol is callable in a tiny CUDA smoke test
- `triton_fallback`
  - baked package missing or unusable; KJNodes Sage override is bypassed before execution
- `disabled`
  - explicit kill switch for debugging / rollback

### Task 1: Lock in the no-compile restore contract with failing tests

**Files:**
- Modify: `tests/test_comfyapp_packaging.py`
- Modify: `tests/test_comfyapp_volume_lifecycle.py`
- Modify: `tests/test_modal_timing_trace.py`
- Modify: `comfyapp.py`

- [ ] **Step 1: Extend lifecycle tests so `startup()` and `restore()` cannot do Sage runtime rebuild work**

Add assertions to `tests/test_comfyapp_volume_lifecycle.py`.

```python
def test_startup_does_not_probe_or_import_sage_cuda(self):
    startup = _get_method("startup")
    startup_source = ast.get_source_segment(COMFYAPP_PATH.read_text(encoding="utf-8"), startup) or ""
    self.assertNotIn("downloading sageattention source from GitHub", startup_source)
    self.assertNotIn("compiling sageattention CUDA kernels", startup_source)
    self.assertNotIn("_import_sage_cuda()", startup_source)
    self.assertNotIn("get_device_capability", startup_source)


def test_restore_selects_sage_runtime_mode_without_runtime_build(self):
    restore = _get_method("restore")
    restore_source = ast.get_source_segment(COMFYAPP_PATH.read_text(encoding="utf-8"), restore) or ""
    self.assertIn("self._select_sage_runtime_mode()", restore_source)
    self.assertNotIn("downloading sageattention source from GitHub", restore_source)
    self.assertNotIn("compiling sageattention CUDA kernels", restore_source)
    self.assertNotIn("pip install", restore_source)
```

- [ ] **Step 2: Add packaging tests for pinned bake + explicit verification**

Extend `tests/test_comfyapp_packaging.py`.

```python
def test_image_pins_sageattention_220(self):
    source = COMFYAPP_PATH.read_text(encoding="utf-8")
    self.assertIn("git+https://github.com/thu-ml/SageAttention.git@v2.2.0", source)


def test_image_verifies_compiled_sageattention_artifacts(self):
    source = COMFYAPP_PATH.read_text(encoding="utf-8")
    self.assertIn("glob('*.so')", source)
    self.assertIn("import sageattention._fused", source)
```

- [ ] **Step 3: Add a timing regression test that keeps restore fast-path expectations**

Extend `tests/test_modal_timing_trace.py`.

```python
def test_summary_supports_fast_restore_without_build_stage(self):
    trace = Trace(prompt_id="abc", t0=100.0)
    trace.mark("t2_local_dispatch", 100.020)
    trace.mark("t3_modal_entry", 102.900)
    summary = trace.summary()
    self.assertEqual(summary["deltas_ms"]["t2_to_t3"], 2880.0)
```

- [ ] **Step 4: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_comfyapp_packaging.py tests/test_modal_timing_trace.py tests/test_comfyapp_volume_lifecycle.py -v
```

Expected: failures because `restore()` still uses runtime Sage setup and no explicit bake-verification logic exists.

- [ ] **Step 5: Commit the red tests**

```bash
git add tests/test_comfyapp_packaging.py tests/test_modal_timing_trace.py tests/test_comfyapp_volume_lifecycle.py
git commit -m "test: lock in fast sage restore contract"
```

### Task 2: Add package-characterization helpers for baked SageAttention 2.2.0

**Files:**
- Modify: `comfyapp.py`
- Add: `tests/test_sageattention_restore_policy.py`

- [ ] **Step 1: Write failing tests for package characterization and mode selection**

Create `tests/test_sageattention_restore_policy.py`.

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from comfyapp import list_sageattention_extension_files, choose_sage_runtime_mode


class SageAttentionRestorePolicyTests(unittest.TestCase):
    def test_list_sageattention_extension_files_finds_any_compiled_extension(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "sageattention"
            root.mkdir(parents=True)
            (root / "_fused.cpython-311-x86_64-linux-gnu.so").write_bytes(b"x")
            files = list_sageattention_extension_files(str(Path(tmp)))
            self.assertEqual([p.name for p in files], ["_fused.cpython-311-x86_64-linux-gnu.so"])

    def test_choose_sage_runtime_mode_uses_fallback_when_extensions_missing(self):
        mode, reason = choose_sage_runtime_mode(enabled=True, extension_files=[], import_ok=False, smoke_ok=False)
        self.assertEqual(mode, "triton_fallback")
        self.assertEqual(reason, "compiled-extensions-missing")

    def test_choose_sage_runtime_mode_requires_smoke_test(self):
        mode, reason = choose_sage_runtime_mode(
            enabled=True,
            extension_files=[Path("/tmp/sageattention/_fused.so")],
            import_ok=True,
            smoke_ok=False,
        )
        self.assertEqual(mode, "triton_fallback")
        self.assertEqual(reason, "smoke-test-failed")
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_sageattention_restore_policy.py -v
```

Expected: fail because the helpers do not exist yet.

- [ ] **Step 3: Add generic helpers in `comfyapp.py` that do not hardcode fp16/fp8 module filenames**

Add module-level helpers near the other utility functions.

```python
def list_sageattention_extension_files(site_packages_root: str) -> list[Path]:
    root = Path(site_packages_root) / "sageattention"
    if not root.is_dir():
        return []
    return sorted(root.glob("*.so"))


def choose_sage_runtime_mode(enabled: bool, extension_files: list[Path], import_ok: bool, smoke_ok: bool) -> tuple[str, str]:
    if not enabled:
        return "disabled", "explicitly-disabled"
    if not extension_files:
        return "triton_fallback", "compiled-extensions-missing"
    if not import_ok:
        return "triton_fallback", "compiled-extensions-unusable"
    if not smoke_ok:
        return "triton_fallback", "smoke-test-failed"
    return "baked_cuda", "compiled-extensions-usable"
```

- [ ] **Step 4: Re-run the new tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_sageattention_restore_policy.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the characterization helpers**

```bash
git add comfyapp.py tests/test_sageattention_restore_policy.py
git commit -m "feat: add sageattention package characterization helpers"
```

### Task 3: Bake SageAttention 2.2.0 into the image and verify real compiled artifacts

**Files:**
- Modify: `comfyapp.py`
- Modify: `tests/test_comfyapp_packaging.py`

- [ ] **Step 1: Add/extend a failing packaging test for pinned build + real file verification**

Update `tests/test_comfyapp_packaging.py`.

```python
def test_image_verifies_compiled_sageattention_shared_objects(self):
    source = COMFYAPP_PATH.read_text(encoding="utf-8")
    self.assertIn("list(pathlib.Path(site_root).joinpath('sageattention').glob('*.so'))", source)
    self.assertIn("import sageattention._fused", source)
    self.assertIn("raise SystemExit('no sageattention shared objects built')", source)
```

- [ ] **Step 2: Run the packaging tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_comfyapp_packaging.py -v
```

Expected: fail because the image still installs Triton-only SageAttention and performs no compiled-artifact verification.

- [ ] **Step 3: Replace Triton-only install with a pinned SageAttention 2.2.0 source build in the image**

Modify the `image = (...)` definition in `comfyapp.py`.

```python
SAGEATTENTION_GIT_REF = "v2.2.0"

.run_commands(
    "CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=12.0+PTX MAX_JOBS=4 "
    "python -m pip install --upgrade --force-reinstall "
    "git+https://github.com/thu-ml/SageAttention.git@v2.2.0 "
    "--no-build-isolation --no-deps",
    gpu="a10g",
)
.run_commands(
    "python -X utf8 -c \"import pathlib, site; "
    "site_root = next((p for p in site.getsitepackages() if 'site-packages' in p), site.getsitepackages()[0]); "
    "files = list(pathlib.Path(site_root).joinpath('sageattention').glob('*.so')); "
    "print([f.name for f in files]); "
    "raise SystemExit('no sageattention shared objects built') if not files else None\"",
    gpu="a10g",
)
.run_commands(
    'python -X utf8 -c "import sageattention._fused; print(\"sageattention._fused ok\")"',
    gpu="a10g",
)
```

- [ ] **Step 4: Remove image-build lines that intentionally skip CUDA build**

Delete the current Triton-only install path.

```python
"SAGEATTN_SKIP_CUDA_BUILD=1 pip install sageattention --force-reinstall --quiet"
```

- [ ] **Step 5: Re-run the packaging tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_comfyapp_packaging.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit the bake path**

```bash
git add comfyapp.py tests/test_comfyapp_packaging.py
git commit -m "build: bake sageattention 2.2.0 artifacts into image"
```

### Task 4: Remove restore-time rebuilds and select a sticky runtime mode

**Files:**
- Modify: `comfyapp.py`
- Modify: `tests/test_comfyapp_volume_lifecycle.py`
- Modify: `tests/test_sageattention_restore_policy.py`

- [ ] **Step 1: Add a failing test for sticky runtime mode selection**

Extend `tests/test_sageattention_restore_policy.py`.

```python
def test_choose_sage_runtime_mode_prefers_baked_cuda_when_extensions_exist_import_passes_and_smoke_passes(self):
    mode, reason = choose_sage_runtime_mode(
        enabled=True,
        extension_files=[Path("/tmp/sageattention/_fused.so")],
        import_ok=True,
        smoke_ok=True,
    )
    self.assertEqual(mode, "baked_cuda")
    self.assertEqual(reason, "compiled-extensions-usable")
```

- [ ] **Step 2: Run the targeted tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_sageattention_restore_policy.py tests/test_comfyapp_volume_lifecycle.py -v
```

Expected: fail because `restore()` still runs runtime Sage setup instead of a selector.

- [ ] **Step 3: Add restore-time selectors in `comfyapp.py`**

Implement focused helpers in `_ComfyAPIMixin`.

```python
def _verify_baked_sageattention_runtime(self) -> tuple[bool, list[str]]:
    import importlib
    import torch

    details = []
    extension_files = list_sageattention_extension_files("/usr/local/lib/python3.11/site-packages")
    if not extension_files:
        return False, ["compiled-extensions-missing"]

    try:
        import sageattention._fused  # noqa: F401
        importlib.invalidate_caches()
    except Exception as exc:
        return False, [f"_fused-import-failed:{type(exc).__name__}"]

    try:
        import sageattention
        backend = getattr(sageattention, "sageattn_qk_int8_pv_fp16_cuda", None) or getattr(sageattention, "sageattn_qk_int8_pv_fp8_cuda", None)
        if backend is None:
            return False, ["no-supported-kjnodes-backend-symbol"]
        q = torch.randn(1, 16, 8, 64, device="cuda", dtype=torch.float16)
        k = torch.randn(1, 16, 8, 64, device="cuda", dtype=torch.float16)
        v = torch.randn(1, 16, 8, 64, device="cuda", dtype=torch.float16)
        _ = backend(q, k, v, is_causal=False, attn_mask=None, tensor_layout="NHD")
        torch.cuda.synchronize()
    except Exception as exc:
        return False, [f"cuda-smoke-test-failed:{type(exc).__name__}"]

    return True, [p.name for p in extension_files]


def _select_sage_runtime_mode(self) -> tuple[str, str]:
    if getattr(self, "_sage_runtime_mode", None) is not None:
        return self._sage_runtime_mode, getattr(self, "_sage_runtime_reason", "sticky")
    ok, details = self._verify_baked_sageattention_runtime()
    mode, reason = choose_sage_runtime_mode(
        enabled=True,
        extension_files=list_sageattention_extension_files("/usr/local/lib/python3.11/site-packages"),
        import_ok=ok,
        smoke_ok=ok,
    )
    self._sage_runtime_mode = mode
    self._sage_runtime_reason = details[0] if details else reason
    print(f"[comfyapp] sage_runtime_mode={self._sage_runtime_mode} reason={self._sage_runtime_reason}")
    return self._sage_runtime_mode, self._sage_runtime_reason
```

- [ ] **Step 4: Change `restore()` so it never compiles SageAttention**

Replace the restore-time Sage setup sequence with:

```python
self._restore_in_process_gpu_state()
_stage = time.time()
self._warmup_cuda()
self._log_profile("restore_warmup", mode="cuda_warmup", duration_ms=self._profile_ms(_stage))
mode, reason = self._select_sage_runtime_mode()
self._log_profile("restore_sage_mode", mode=mode, reason=reason)
self._apply_sage_attention_policy()
```

and remove restore-time calls that trigger source download/build.

- [ ] **Step 5: Re-run the targeted tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_sageattention_restore_policy.py tests/test_comfyapp_volume_lifecycle.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit the restore selector**

```bash
git add comfyapp.py tests/test_comfyapp_volume_lifecycle.py tests/test_sageattention_restore_policy.py
git commit -m "feat: select baked sage runtime mode during restore"
```

### Task 5: Patch KJNodes at `get_sage_func()` so unsupported Sage modes fall back safely

**Files:**
- Modify: `comfyapp.py`
- Add: `tests/test_sageattention_restore_policy.py`

- [ ] **Step 1: Write a failing unit test for the `get_sage_func` factory patch**

Extend `tests/test_sageattention_restore_policy.py` with a synthetic module test.

```python
def test_patch_kjnodes_get_sage_func_uses_attention_pytorch_when_baked_cuda_unavailable(self):
    class FakeModule:
        def __init__(self):
            self.attention_pytorch = lambda *args, **kwargs: "pytorch"
        def get_sage_func(self, sage_attention, allow_compile=False):
            return lambda *args, **kwargs: "sage"

    module = FakeModule()
    patched = patch_kjnodes_get_sage_func(module, baked_cuda_available=False)
    self.assertTrue(patched)
    self.assertEqual(module.get_sage_func("sageattn_qk_int8_pv_fp16_cuda")(), "pytorch")
```

- [ ] **Step 2: Run the new factory-patch test and verify it fails**

Run:

```powershell
python -m pytest tests/test_sageattention_restore_policy.py::SageAttentionRestorePolicyTests::test_patch_kjnodes_get_sage_func_uses_attention_pytorch_when_baked_cuda_unavailable -v
```

Expected: fail because the patch helper does not exist yet.

- [ ] **Step 3: Add a `get_sage_func` patch helper in `comfyapp.py`**

Implement the patch against the actual KJNodes factory.

```python
def patch_kjnodes_get_sage_func(module, baked_cuda_available: bool) -> bool:
    original = getattr(module, "get_sage_func", None)
    fallback = getattr(module, "attention_pytorch", None)
    if original is None or fallback is None:
        return False
    if getattr(module, "_comfy_modal_get_sage_func_patched", False):
        return True

    def wrapped_get_sage_func(sage_attention, allow_compile=False):
        if not baked_cuda_available and sage_attention != "disabled":
            return fallback
        return original(sage_attention, allow_compile=allow_compile)

    module.get_sage_func = wrapped_get_sage_func
    module._comfy_modal_get_sage_func_patched = True
    return True
```

- [ ] **Step 4: Apply the patch after extra nodes init and again after restore mode selection**

Add a helper in `_ComfyAPIMixin`.

```python
def _apply_sage_attention_policy(self):
    baked_cuda_available = getattr(self, "_sage_runtime_mode", "triton_fallback") == "baked_cuda"
    for mod in list(sys.modules.values()):
        file_name = getattr(mod, "__file__", "") or ""
        if file_name.endswith("model_optimization_nodes.py"):
            patched = patch_kjnodes_get_sage_func(mod, baked_cuda_available=baked_cuda_available)
            if patched:
                print(f"[comfyapp] patched KJNodes get_sage_func baked_cuda_available={baked_cuda_available}")
            return patched
    return False
```

Call it:

```python
self._event_loop.run_until_complete(nodes.init_extra_nodes())
self._apply_sage_attention_policy()
```

and again in `restore()` after `mode, reason = self._select_sage_runtime_mode()`.

- [ ] **Step 5: Re-run the policy tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_sageattention_restore_policy.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit the KJNodes policy patch**

```bash
git add comfyapp.py tests/test_sageattention_restore_policy.py
git commit -m "fix: patch kjnodes get_sage_func for restore fallback"
```

### Task 6: Final verification and version bump

**Files:**
- Modify: `comfyapp.py`
- Modify: `tests/test_comfyapp_packaging.py`
- Modify: `tests/test_comfyapp_volume_lifecycle.py`
- Modify: `tests/test_modal_timing_trace.py`
- Add: `tests/test_sageattention_restore_policy.py`

- [ ] **Step 1: Bump `COMFYAPP_VERSION` after implementation changes**

Update the version in `comfyapp.py`.

```python
COMFYAPP_VERSION = "2.3.10"
```

- [ ] **Step 2: Run the full targeted verification suite**

Run:

```powershell
python -m pytest tests/test_comfyapp_packaging.py tests/test_modal_timing_trace.py tests/test_modal_runtime_routes.py tests/test_modal_client_gpu_config.py tests/test_comfyapp_volume_lifecycle.py tests/test_sageattention_restore_policy.py -v
```

Expected: PASS.

- [ ] **Step 3: Run compile verification**

Run:

```powershell
python -m py_compile "timing_trace.py" "modal_client.py" "__init__.py" "comfyapp.py"
```

Expected: no output.

- [ ] **Step 4: Run a source-level sanity check for banned restore-time work**

Run:

```powershell
Select-String -Path ".\comfyapp.py" -Pattern "downloading sageattention source|compiling sageattention CUDA kernels|pip install .|SAGEATTN_SKIP_CUDA_BUILD"
```

Expected: no restore-time path contains these patterns; only image-build-time install logic remains.

- [ ] **Step 5: Commit the final state**

```bash
git add comfyapp.py tests/test_comfyapp_packaging.py tests/test_comfyapp_volume_lifecycle.py tests/test_modal_timing_trace.py tests/test_sageattention_restore_policy.py docs/superpowers/plans/2026-06-01-baked-sageattention-restore.md
git commit -m "feat: restore fast startup with baked sageattention policy"
```

## Self-review

- Spec coverage: the revised plan now covers Modal snapshot constraints, pinned SageAttention 2.2.0 baking, compiled-artifact verification, post-restore smoke testing, sticky runtime mode selection, and KJNodes fallback policy.
- Placeholder scan: no `TODO`, `TBD`, or `HEAD/main` placeholders remain.
- Consistency check: the plan consistently uses `baked_cuda`, `triton_fallback`, and `disabled`; the helper names are `list_sageattention_extension_files`, `choose_sage_runtime_mode`, `_verify_baked_sageattention_runtime`, `_select_sage_runtime_mode`, and `_apply_sage_attention_policy`.

## Expected outcome

After implementation:
- `startup(snap=True)` remains CPU-only and snapshot-safe
- `restore(snap=False)` no longer spends ~120s rebuilding SageAttention
- restore either:
  - uses the baked SageAttention 2.2.0 package immediately, or
  - falls back immediately to Triton/PyTorch attention without rebuild
- prompt execution never re-enters Sage setup and should no longer fail with `Input tensors must be on cuda` from the restore policy itself

Plan complete and saved to `docs/superpowers/plans/2026-06-01-baked-sageattention-restore.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
