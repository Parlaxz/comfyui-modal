"""Test E — No memory snapshot Blackwell.

Same production image/GPU/volumes/workflow as Config D, but with
enable_memory_snapshot=False so every request is a true cold start.
"""

import os
import sys
import time

import modal

APP_NAME = "comfyui-platform-e"
N_RUNS = 5
GAP_S = 20

# Shared constants (same as comfyapp.py)
MODELS_PATH = "/root/models"
CUSTOM_NODES_PATH = "/root/custom_nodes_vol"

# Volumes referenced by name (Modal resolves from the deployed app's secrets)
vol = modal.Volume.from_name("comfyui-models", create_if_missing=True)
custom_nodes_vol = modal.Volume.from_name("comfyui-custom-nodes", create_if_missing=True)


def _load_workflow_with_images() -> tuple[dict, dict]:
    import json
    with open("latest_benchmark_workflow.json") as f:
        snap = json.load(f)
    payload = snap.get("payload", snap)
    workflow = payload.get("prompt", payload)
    input_images = {}
    for _nspec in workflow.values():
        if isinstance(_nspec, dict) and _nspec.get("class_type") == "LoadImage":
            _fn = _nspec.get("inputs", {}).get("image", "")
            if _fn and _fn not in input_images:
                input_images[_fn] = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    return workflow, input_images


app = modal.App(APP_NAME)

# Build the production image (copied from comfyapp.py to avoid import issues)
# Note: this is the same image definition used by production ComfyAPI classes
_prod_image = (
    modal.Image.from_registry("nvidia/cuda:13.0.0-devel-ubuntu24.04", add_python="3.11")
    .entrypoint([])
    .apt_install("git", "libgl1", "libglib2.0-0", "libsm6", "libxrender1", "libxext6",
                  "libgomp1", "libgoogle-perftools-dev", "curl", "wget", "unzip")
    .pip_install(
        "torch==2.7.0", "torchvision==0.22.0", "torchaudio==2.7.0",
        index_url="https://download.pytorch.org/whl/cu130",
    )
    .run_commands(
        "git clone --depth 1 --branch v2.2.0 https://github.com/saylorj/custom-sageattention.git sage_src",
        "cd sage_src && TORCH_CUDA_ARCH_LIST=12.0+PTX MAX_JOBS=4 python setup.py build_ext --inplace 2>&1 | tail -20",
        "cp sage_src/build/lib.linux-x86_64-cpython-311/sageattention/_fused*.so /usr/local/lib/python3.11/site-packages/sageattention/ 2>/dev/null; cp sage_src/build/lib.linux-x86_64-cpython-311/sageattention/_qattn*.so /usr/local/lib/python3.11/site-packages/sageattention/ 2>/dev/null; true",
        "assert os.path.isfile('/usr/local/lib/python3.11/site-packages/sageattention/_fused.cpython-311-x86_64-linux-gnu.so') or any(f.endswith('.so') for f in os.listdir('/usr/local/lib/python3.11/site-packages/sageattention/') if 'fused' in f), 'sageattention _fused .so not found'",
        "assert any(f.endswith('.so') for f in os.listdir('/usr/local/lib/python3.11/site-packages/sageattention/') if 'qattn' in f), 'sageattention _qattn .so not found'",
        gpu="a10g",
    )
    .run_commands(
        "python -X utf8 -c \"import sageattention._fused; print('sageattention._fused ok')\"",
        gpu="a10g",
    )
    .env({
        "TORCHINDUCTOR_CACHE_DIR": "/root/models/.inductor-cache",
        "TRITON_CACHE_DIR": "/tmp/triton_cache",
        "COMFYMODAL_SAGE_RUNTIME_MODE": "baked_cuda",
        "COMFYMODAL_SAGE_RUNTIME_PROBE_ON_RESTORE": "0",
        "COMFYMODAL_WARMUP_TEXT": "warmup",
    })
    .pip_install("comfy-cli==1.3.9")
    .run_commands(
        "comfy --skip-prompt install --nvidia 2>&1 | tail -5",
        "comfy --skip-prompt node install kjd7n3n 2>&1 | tail -5",
        "comfy --skip-prompt node install rgthree 2>&1 | tail -5",
        "comfy --skip-prompt node install ComfyUI-Impact-Pack 2>&1 | tail -5",
    )
    .add_local_python_source("gpu_catalog")
    .add_local_python_source("timing_trace")
)


@app.cls(
    gpu="rtx-pro-6000",
    enable_memory_snapshot=False,
    cpu=4,
    memory=32768,
    timeout=600,
    min_containers=0,
    scaledown_window=4,
    volumes={MODELS_PATH: vol, CUSTOM_NODES_PATH: custom_nodes_vol},
    secrets=[modal.Secret.from_name("comfyui-warmup-dev")],
)
class PlatformTestE:
    """No memory snapshot — Comfy initialises from scratch each time."""

    def __init__(self):
        self._event_loop = None
        self._prompt_server = None
        self._http_client_obj = None
        self._last_restore_timing = {}
        self._backend_started = False

    @modal.enter()
    def startup(self):
        import time as _t
        _t0 = _t.time()
        self._startup_t = _t0

        def _log_mem(label):
            try:
                with open("/proc/self/status") as _f:
                    for _line in _f:
                        if _line.startswith("VmRSS:"):
                            _rss_kb = int(_line.split()[1])
                            print(f"[snapshot_mem] {label} rss_mb={_rss_kb / 1024:.1f} modules={len(sys.modules)}")
                            break
            except Exception:
                print(f"[snapshot_mem] {label} modules={len(sys.modules)}")

        _log_mem("startup_begin")
        self._start_backend(_log_mem)
        _log_mem("startup_done")
        print(f"[platform_e] startup done in {(_t.time()-_t0)*1000:.1f}ms")

    def _start_backend(self, log_mem=None):
        import sys as _sys
        # Add ComfyUI path (same as production startup)
        _comfy_path = "/root/comfy/ComfyUI"
        if _comfy_path not in _sys.path:
            _sys.path.insert(0, _comfy_path)

        import asyncio
        import time
        from comfy.cli_args import args

        if log_mem: log_mem("imports_comfy")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._event_loop = loop

        import execution
        import server
        import comfy.model_management
        import nodes
        if log_mem: log_mem("imports_custom_nodes")
        nodes.init_extra_nodes()
        if log_mem: log_mem("after_custom_nodes")

        sv = server.PromptServer(loop)
        self._prompt_server = sv
        sv.add_api_route("/comfymodal/benchmark/workflow", self._save_benchmark_workflow, methods=["GET", "POST"])
        sv.add_api_route("/comfymodal/prompt", self._modal_prompt_route, methods=["POST"])
        loop.run_until_complete(sv.start("/root/comfy/ComfyUI", port=8188, address="127.0.0.1"))
        if log_mem: log_mem("after_server_start")

        import folder_paths
        folder_paths.add_model_folder_path("checkpoints", os.path.join(MODELS_PATH, "checkpoints"))
        folder_paths.add_model_folder_path("diffusion_models", os.path.join(MODELS_PATH, "diffusion_models"))
        folder_paths.add_model_folder_path("unet", os.path.join(MODELS_PATH, "unet"))
        folder_paths.add_model_folder_path("vae", os.path.join(MODELS_PATH, "vae"))
        folder_paths.add_model_folder_path("text_encoders", os.path.join(MODELS_PATH, "text_encoders"))

        import comfy.utils
        comfy.utils.DISABLE_MMAP = True
        self._backend_started = True
        if log_mem: log_mem("backend_ready")

    def _save_benchmark_workflow(self):
        return {"status": "ok"}
    def _modal_prompt_route(self):
        return {"status": "ok"}

    @modal.method()
    def run_prompt(self, workflow: dict, input_images: dict | None = None) -> dict:
        import time as _t
        _entry = _t.time()

        from comfyapp import _materialize_input_images
        if input_images:
            _materialize_input_images(input_images)

        import execution
        import nodes
        import comfy.model_management as mm

        prompt_id = str(__import__("uuid").uuid4())
        outputs_to_execute = None

        with nodes.interrupt_processing(False):
            try:
                result = execution.execute(workflow, prompt_id, {"client_id": "platform_e"}, outputs_to_execute)
            except Exception as exc:
                print(f"[platform_e] execution failed: {exc}")
                raise

        images = []
        for node_id, node_outputs in result.get("results", []):
            for output in node_outputs:
                if isinstance(output, dict) and output.get("type") == "output":
                    images.append({"filename": output.get("filename",""), "subfolder": output.get("subfolder",""), "type": "output", "data": ""})

        _done = _t.time()
        print(f"[platform_e] prompt done in {(_done-_entry)*1000:.1f}ms")
        return {
            "images": images, "videos": [],
            "_restore_timing": {
                "startup_start_unix_s": self._startup_t,
                "startup_end_unix_s": _entry,
                "startup_ms": round((_entry - self._startup_t) * 1000, 1),
                "exec_ms": round((_done - _entry) * 1000, 1),
                "total_ms": round((_done - self._startup_t) * 1000, 1),
            },
        }


def main():
    cls = modal.Cls.from_name(APP_NAME, "PlatformTestE")()
    print(f"Test E — No memory snapshot Blackwell ({N_RUNS} runs, {GAP_S}s gaps)")

    _wf, _imgs = _load_workflow_with_images()
    all_results = []

    for i in range(N_RUNS):
        t0 = time.time()
        try:
            result = cls.run_prompt.remote(_wf, input_images=_imgs if _imgs else None)
        except Exception as exc:
            print(f"  [RUN-{i+1}] FAILED: {exc}")
            all_results.append({"run": f"RUN-{i+1}", "wall_ms": -1, "error": str(exc)[:200]})
            if i < N_RUNS - 1:
                time.sleep(GAP_S)
            continue
        t1 = time.time()
        rt = result.get("_restore_timing", {}) or {}
        total_wall = round((t1 - t0) * 1000, 1)
        startup_ms = rt.get("startup_ms", 0)
        exec_ms = rt.get("exec_ms", 0)
        entry = {"run": f"RUN-{i+1}", "wall_ms": total_wall, "startup_ms": startup_ms, "exec_ms": exec_ms}
        all_results.append(entry)
        print(f"  [RUN-{i+1}] wall={total_wall}ms  startup={startup_ms}ms  exec={exec_ms}ms")
        if i < N_RUNS - 1:
            time.sleep(GAP_S)

    print(f"\n{'='*60}")
    print(f"Test E — No snapshot Blackwell — {N_RUNS} runs")
    print(f"{'='*60}")
    for r in all_results:
        e = r.get("error")
        print(f"  {r['run']}: wall={r['wall_ms']}ms startup={r['startup_ms']}ms exec={r['exec_ms']}ms" + (f" ERROR: {e}" if e else ""))
    print("\nCompare with Config D (snapshot): platform_restore~12.5s + app_restore~4s + remote_exec~5.5s = ~22s total")


if __name__ == "__main__":
    main()
