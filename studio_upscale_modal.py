"""Phase 11 Upscale Modal deployment: SINGLE remote ``studio_upscale`` function.

Deployment definition only.  Do NOT touch ``web/*.js``; do NOT modify
``studio_upscale_run.py`` dispatch or tests (parallel lane owns those).

Entrypoint shape (matches the collapsed dispatch this file serves)::

    studio_upscale(payload: dict) -> dict

where ``payload`` carries exactly
``{image_b64, method, scale, seed, tile_size?, tile_overlap?, vae_tile_size?}``.
``method`` is revalidated server-side (exactly ``vosr2`` | ``seedvr2``,
``auto`` rejected).  Returns ``{status: 'ok', image_b64}`` or
``{status: 'error', message}`` — never raises across the Modal boundary,
so the dispatch lane's ``raw.get("status") != "ok"`` branch works unchanged.

Inference is NOT reimplemented here: the function imports the existing local
adapter callables (``upscale_vosr2`` / ``upscale_seedvr2``) shipped into the
image via ``add_local_file``.  VOSR2 is TRUE-COLD capable: container-level
``startup(snap=True)`` (below) performs the adapter's CPU-only static init
and returns ready for platform snapshot capture; ``restore(snap=False)``
re-runs the minimal post-snapshot path (mutable reset, CUDA init once, H2D
materialization).  Both are idempotent and are driven from the request path,
so a warm container's second call skips reload; the module-level ``_WARMED``
record plus the adapter's own ``studio_upscale_vosr2._VOSR2_STATIC`` state is
the observable proof hook (logged on hit).

────────────────────────────────────────────────────────────────────────────
TRUE-COLD SNAPSHOT LIFECYCLE (VOSR2 only — SeedVR2 shares nothing with it)
────────────────────────────────────────────────────────────────────────────
Golden mapping (comfymodal_runtime/modal_app.py — Modal CPU memory
snapshots, NOT GPU):

* ``startup(snap=True)`` ~ ``startup`` (10979): imports, args.json,
  path resolution, class construction, CPU state — quiescent, zero
  ``torch.cuda`` calls, zero network, zero subprocess.  Enabling param is
  ``enable_memory_snapshot=True`` on the ``studio_upscale`` function;
  capture is platform-side after startup returns ready.
* ``restore(snap=False)`` ~ ``restore`` (12674): mutable reset (stale
  rendezvous env dropped, eval re-asserted), CUDA init once, per-model H2D,
  ``forward_flexible`` rebind, request-ready.  Mirrors the Golden
  ``CpuSnapshotModels`` container pattern via the adapter's
  ``_VOSR2_STATIC`` record and the post-restore timing fields
  (``restore_entry_wall_unix_ns`` … ``restore_exit_wall_unix_ns``,
  per-model ``*_source_read_ms`` / ``*_cpu_materialize_ms`` / ``*_h2d_ms``,
  ``model_ready_ms``).
* Weight strategy behind ``COMFYMODAL_VOSR2_SNAPSHOT_MODE`` =
  ``"lean"`` (default: shells + paths snapshotted, weights re-read
  post-restore) | ``"cpu_weights"`` (weights resident CPU, snapshot
  captures them) so the operator can measure both.  NO Modal GPU
  snapshotting anywhere.
* Request timing decomposition is returned additively as ``vosr2_timing``
  in the ``ok`` response (existing ``status`` / ``image_b64`` keys
  unchanged; dispatch ignores the extra key): restore keys above plus
  ``seed_ms``, ``decode_ms``, ``dinov2_fwd_ms``, ``vae_encode_ms``,
  ``dit_onestep_ms``, ``vae_decode_ms``, ``color_correct_ms``,
  ``materialize_ms``, ``png_encode_ms``, ``request_total_ms`` and the
  effective tiling (``tiling`` ``full`` | ``tiled``).  Load + inference are
  never lumped.
* Tiling: outputs with long side <= 2048px take the full-image path
  (``tile_size = 0``, ``vae_tile_size = None``); larger outputs honor the
  caller's tiling knobs through the upstream tiled kernels.

────────────────────────────────────────────────────────────────────────────
WEIGHT PLACEMENT (operator step — weights are NOT downloaded by this lane)
────────────────────────────────────────────────────────────────────────────
Weights live in the EXISTING model Volume (no new artifact system):

    Volume name : ``comfyui-models``  (same ``VOLUME_NAME`` as comfyapp.py)
    Mount       : ``/root/models``    (same ``MODELS_PATH`` as comfyapp.py)

Layout inside the Volume::

    /root/models/upscale_models/VOSR/
        args.json  ema_model.safetensors  (+ bundled Qwen VAE + dinov2 files)
    /root/models/upscale_models/SeedVR2/
        seedvr2_ema_3b.pth  ema_vae.pth

Sources (verified 2026-10-14):

* VOSR bundle (~7GB):  https://huggingface.co/CSWRY/VOSR
  (``VOSR2/`` directory: ``args.json`` + ``ema_model.safetensors`` plus the
  bundled ``Qwen-Image-vae-2d`` and dinov2 files; place the ``VOSR2/``
  *contents* at ``upscale_models/VOSR/``).
  Upstream inference layout is ``preset/ckpts/...``-relative, so keep the
  filenames exact; code: https://github.com/cswry/VOSR
* SeedVR2 3B bundle (~28GB):  https://huggingface.co/ByteDance-Seed/SeedVR2-3B
  (``seedvr2_ema_3b.pth`` + ``ema_vae.pth`` at ``upscale_models/SeedVR2/``).
  Code: https://github.com/ByteDance-Seed/SeedVR

Stage with the ALREADY-DEPLOYED config-owned downloader (preferred — writes
straight to the Volume; nothing new invented), e.g. via the ``comfyui`` app::

    batch_download_models([
      {"url": "https://huggingface.co/CSWRY/VOSR/resolve/main/VOSR2/args.json",
       "filename": "args.json", "save_path": "upscale_models/VOSR"},
      {"url": "https://huggingface.co/CSWRY/VOSR/resolve/main/VOSR2/ema_model.safetensors",
       "filename": "ema_model.safetensors", "save_path": "upscale_models/VOSR"},
      {"url": "https://huggingface.co/ByteDance-Seed/SeedVR2-3B/resolve/main/seedvr2_ema_3b.pth",
       "filename": "seedvr2_ema_3b.pth", "save_path": "upscale_models/SeedVR2"},
      {"url": "https://huggingface.co/ByteDance-Seed/SeedVR2-3B/resolve/main/ema_vae.pth",
       "filename": "ema_vae.pth", "save_path": "upscale_models/SeedVR2"},
    ])

plus the remaining VOSR support files (Qwen VAE dir + dinov2 files) from the
same HF repo, preserving names.  The adapters resolve these paths via the
existing knobs ``COMFYMODAL_VOSR2_WEIGHTS`` / ``COMFYMODAL_SEEDVR2_WEIGHTS``
(defaulted into the image below to the Volume paths above).

────────────────────────────────────────────────────────────────────────────
DEPLOY (operator step — NOT run by this lane; destination is config-owned)
────────────────────────────────────────────────────────────────────────────
``v2ctl deploy`` only serves the Golden/comfyapp entrypoints, so there is no
``v2ctl deploy <file>`` spelling.  Deploy this sidecar module through the
v2ctl-resolved destination binding (workspace ``Testing 6`` per
``config/v2/modal_target.toml`` + active-workspace tokens from
``.modal_workspaces.json``).  NEVER bare ambient-profile ``modal deploy``
(it hits the WRONG workspace — docs §24.2)::

    python tools/v2ctl.py lock status
    python tools/v2ctl.py config            # confirm config-owned destination
    chcp 65001                              # Windows codec rule, docs §24.3
    $env:PYTHONUTF8 = "1"
    modal deploy -m studio_upscale_modal      # with v2ctl-resolved
                                            # MODAL_TOKEN_ID/MODAL_TOKEN_SECRET
                                            # in env, deploy lock held

Module: ``studio_upscale_modal`` (this file, repo root).
App: ``comfyui-modal-studio-upscale`` (override via COMFYMODAL_UPSCALE_APP_NAME;
the dispatch lane reads the same env var, defaulting to the config-owned app).
After deploy, set ``COMFYMODAL_UPSCALE_APP_NAME=comfyui-modal-studio-upscale``
where the dispatch lane runs.

────────────────────────────────────────────────────────────────────────────
CONCRETE BLOCKERS (verified in upstream source 2026-10-14 — no graph fallback)
────────────────────────────────────────────────────────────────────────────
B1. VOSR2 subprocess path (CLOSED 2026-10-14 — in-process adapter).
    ``studio_upscale_vosr2`` no longer shells out: it imports the upstream
    checkout (``inference_vosr_onestep`` helpers, ``LightningDiT``,
    ``LightDecoder``, ``VOSR``, ``encode_dispatch``/``decode_dispatch``,
    Qwen/SD2 VAE loader) and calls them in-process with the exact upstream
    call order (config -> construct -> CPU state -> .to(cuda) -> decode ->
    DINO -> VAE encode -> one-step DiT -> VAE decode -> color align).
    Static init is CPU-only (snapshot-capturable); there is no ``subprocess``
    or ``socket`` import left in the adapter.

B2. VOSR runtime download: upstream ``load_dinov2`` calls
    ``torch.hub.load('facebookresearch/dinov2', 'dinov2_vitl14')`` — a GitHub
    fetch at inference time.  Either pre-warm ``TORCH_HUB_DIR`` at image build
    or vendor the dinov2 files from the HF bundle; otherwise the first remote
    call needs egress.  (Adapter side: static init stages pre-warmed cache
    file-only and fails closed with ``VOSR2_UNAVAILABLE`` when absent — it
    never probes the network and never downloads.)
B3. SeedVR2 has NO importable entrypoint (owns: adapters/dispatch lane).
    Upstream provides NO ``seedvr`` package: inference is the cwd-relative
    CLI script ``projects/inference_seedvr2_3b.py`` with hardcoded relative
    paths (``./configs_3b/main.yaml``, ``./ckpts/seedvr2_ema_3b.pth``,
    ``pos_emb.pt`` / ``neg_emb.pt``).  ``studio_upscale_seedvr2`` does
    ``import seedvr`` then raises ``SeedVR2Unavailable`` unconditionally, so
    the SeedVR2 path can never serve until a wrapper exists (subprocess the
    CLI with cwd=checkout + staged configs/embs, or vendor a function).
B4. flash_attn / apex: upstream ``environment.yml`` (training env) pins
    ``flash-attn==2.5.9.post1`` + ``apex==0.1`` (py3.9 / torch2.4 / cu121
    era); neither appears in the inference ``requirements.txt`` surface nor
    in ``projects/inference_seedvr2_3b.py``'s direct imports.  Omitted from
    the image (below); if DiT internals hard-import flash_attn, add a
    cu130/py3.11 prebuilt wheel then — named check, not yet observed.

VERDICT: deployment definition READY.  No VRAM blocker (80GB class, justified
below).  No ComfyUI-node graph used or needed.  B1–B3 must be closed by the
adapters/dispatch lane before either method can serve; this file already
imports (never duplicates) the adapters so their fixes flow straight through.
"""

from __future__ import annotations

import os
import sys

import modal

UPSCALE_APP_NAME = os.environ.get(
    "COMFYMODAL_UPSCALE_APP_NAME", "comfyui-modal-studio-upscale"
).strip() or "comfyui-modal-studio-upscale"

VOLUME_NAME = os.environ.get("COMFYMODAL_MODELS_VOLUME", "comfyui-models")
MODELS_PATH = "/root/models"
VOSR2_VOL_DIR = f"{MODELS_PATH}/upscale_models/VOSR"
SEEDVR2_VOL_DIR = f"{MODELS_PATH}/upscale_models/SeedVR2"

# Upstream checkouts baked into the image (source only — weights stay on the
# Volume).  Shallow clones keep the layer small; the VOSR path is consumed via
# COMFYMODAL_VOSR2_REPO, the SeedVR path via PYTHONPATH (its imports are
# cwd-relative: ``from projects...``, ``from common...``, ``from data...``).
VOSR_REPO_URL = "https://github.com/cswry/VOSR"
SEEDVR_REPO_URL = "https://github.com/ByteDance-Seed/SeedVR"
VOSR_REPO_DIR = "/opt/upstream/VOSR"
SEEDVR_REPO_DIR = "/opt/upstream/SeedVR"
ADAPTER_DIR = "/opt/studio_upscale"

# Inference-only dependency surface (verified against upstream sources):
# - VOSR requirements.txt: torch/torchvision (+cu121 pins NOT honored, see
#   image build below), diffusers, transformers, safetensors, einops,
#   timm, Pillow, numpy, opencv, tqdm (+ basicsr/bitsandbytes/fairscale/wandb:
#   training-only, omitted).
# - SeedVR requirements.txt: torch/torchvision, diffusers, transformers,
#   einops, omegaconf, rotary-embedding-torch, opencv (+ mediapy: used by the
#   SeedVR2 inference script for image IO; notebook-only otherwise).
# - Deliberately OMITTED: torch/torchvision (pinned to cu130 in the image
#   build step, never from the default index), flash-attn + apex (training-era
#   pins, blocker B4), bitsandbytes/fairscale/xformers (train-only).
UPSTREAM_PIP_DEPS = (
    "diffusers",
    "transformers",
    "safetensors",
    "einops",
    "timm",
    "Pillow",
    "numpy",
    "opencv-python-headless",
    "omegaconf",
    "rotary-embedding-torch",
    "tqdm",
    "mediapy",
    # Genuine inference import: models/rmsnorm.py does
    # `import fairscale.nn.model_parallel.initialize` at module import.
    "fairscale",
    # NOTE (SeedVR2 BLOCKED 2026-10-14): models/dit_v2/attention.py does
    # `from flash_attn import flash_attn_varlen_func` with no fallback, and
    # no prebuilt flash-attn wheel resolves for torch 2.9/cu130/py3.11
    # (source dist fails: build backend needs torch at build time).
    # Deliberately NOT listed: it breaks the image build.  Re-add only with
    # a verified wheel or a bounded source-build recipe.  SeedVR2 meanwhile
    # fails closed with the precise ModuleNotFoundError.
)

upscale_image = (
    # Same CUDA/Python floor as comfyapp.py _FOUNDATION_IMAGE
    # (nvidia/cuda:13.0.0-devel-ubuntu24.04 + python 3.11).
    modal.Image.from_registry(
        "nvidia/cuda:13.0.0-devel-ubuntu24.04",
        add_python="3.11",
    )
    .entrypoint([])
    .apt_install(
        "git",
        "libgl1",
        "libglib2.0-0",
        "ffmpeg",  # torchvision.io video IO used by the SeedVR2 script
        "build-essential",
        "ninja-build",
        "clang",
    )
    # CONFLICT RESOLUTION (torch): upstream pins (VOSR torch==2.5.1+cu121,
    # SeedVR torch==2.4.0+cu121) are training-era and incompatible with CUDA
    # 13.0 / Blackwell.  Honor the foundation instead: latest cu130 torch,
    # installed here from the PyTorch index — identical to
    # comfyapp.py:8483-8488 — and NEVER list torch/torchvision in
    # .pip_install (default-index torch would clobber this).
    # DO NOT pin torch 2.9 / torchvision 0.24 for SeedVR2's video IO here:
    # torch 2.9 rejects the explicit dtype=None/device=None that timm
    # 1.0.30's Mlp passes into torch.empty, breaking VOSR2 construction
    # (torch 2.14 accepts it; VOSR2 is proven on 2.14).  SeedVR2 is parked
    # this pass; its video-IO + flash_attn needs stay documented BLOCKEDs.
    # Inference uses stable torch APIs only.
    .run_commands(
        "python -m pip install --upgrade --no-input "
        "torch torchvision "
        "--index-url https://download.pytorch.org/whl/cu130",
    )
    .pip_install(*UPSTREAM_PIP_DEPS)
    .run_commands(
        f"rm -rf {VOSR_REPO_DIR} {SEEDVR_REPO_DIR} && "
        f"git clone --depth=1 {VOSR_REPO_URL}.git {VOSR_REPO_DIR} && "
        f"git clone --depth=1 {SEEDVR_REPO_URL}.git {SEEDVR_REPO_DIR} && "
        f"git -C {VOSR_REPO_DIR} log -1 --format='vosr=%H' && "
        f"git -C {SEEDVR_REPO_DIR} log -1 --format='seedvr=%H' && "
        # dinov2 torch.hub source pre-warmed at build so upstream load_dinov2
        # runs offline (adapter _ensure_dinov2_offline returns early; only the
        # .pth + trusted_list still come from the Volume).
        f"mkdir -p {VOSR_REPO_DIR}/preset/ckpts/torch_cache && "
        f"rm -rf {VOSR_REPO_DIR}/preset/ckpts/torch_cache/facebookresearch_dinov2_main && "
        "git clone --depth=1 https://github.com/facebookresearch/dinov2.git "
        f"{VOSR_REPO_DIR}/preset/ckpts/torch_cache/facebookresearch_dinov2_main",
    )
    # Ship the existing local adapters (imported, never duplicated).
    .add_local_file(
        "studio_upscale_vosr2.py",
        f"{ADAPTER_DIR}/studio_upscale_vosr2.py",
        copy=True,
    )
    .add_local_file(
        "studio_upscale_seedvr2.py",
        f"{ADAPTER_DIR}/studio_upscale_seedvr2.py",
        copy=True,
    )
    .env(
        {
            # Existing adapter knobs, defaulted to the Volume layout above.
            "COMFYMODAL_VOSR2_WEIGHTS": VOSR2_VOL_DIR,
            "COMFYMODAL_SEEDVR2_WEIGHTS": SEEDVR2_VOL_DIR,
            "COMFYMODAL_VOSR2_REPO": VOSR_REPO_DIR,
            # SeedVR adapter resolves its checkout via this knob (B3: no
            # importable seedvr package; the CLI runs with cwd=checkout).
            "COMFYMODAL_SEEDVR2_REPO": SEEDVR_REPO_DIR,
            # Pre-warmed torch-hub cache (dinov2 source + vitl14 weights +
            # trusted_list, staged per the adapter docstring) so upstream
            # load_dinov2 runs offline.
            "COMFYMODAL_VOSR2_DINOV2": f"{MODELS_PATH}/upscale_models/torch_cache",
            # Snapshot weight strategy under measurement (see acceptance
            # cohort): "lean" re-reads weights post-restore, "cpu_weights"
            # keeps them CPU-resident through the snapshot (H2D-only
            # restore).  Production keeps exactly one; this line selects
            # the arm under test.
            "COMFYMODAL_VOSR2_SNAPSHOT_MODE": "cpu_weights",
            # NOTE: VOSR_REPO_DIR is deliberately NOT on PYTHONPATH.  Both
            # checkouts ship top-level `models/` (and `common/`, `data/`)
            # packages; VOSR's are regular packages (__init__.py) while
            # SeedVR's rely on namespace resolution, so a shared path lets
            # VOSR's `models/` shadow SeedVR's and breaks
            # `from models.dit_v2 import ...` with ModuleNotFoundError.
            # VOSR needs no path entry: its adapter drives the upstream CLI
            # via subprocess with cwd=checkout (script-dir-first resolution).
            # SeedVR's CLI likewise resolves its own tree via SEEDVR_REPO_DIR.
            "PYTHONPATH": f"{ADAPTER_DIR}:{SEEDVR_REPO_DIR}",
        }
    )
)

app = modal.App(UPSCALE_APP_NAME, image=upscale_image)

upscale_vol = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

# Module-level reuse record: set after a method's first successful inference
# in THIS container.  The heavy state itself lives in the imported modules
# (torch + upstream code stay imported; the vosr2 adapter caches its static
# CPU state plus restored CUDA executables in
# ``studio_upscale_vosr2._VOSR2_STATIC``), so a warm container's second call
# skips reload; this record is the observable proof hook (logged on hit).
_WARMED: dict[str, str] = {}


def startup(snap: bool = True) -> dict:
    """TRUE-COLD static init (Modal ``startup(snap=True)`` scope).

    CPU-only, quiescent, zero CUDA/network/subprocess: resolves the VOSR2
    bundle, reads ``args.json``, imports upstream modules, constructs model
    shells (``cpu_weights`` mode: full CPU-resident weights) and returns
    ready for platform snapshot capture.  Mirrors Golden ``startup``
    (``comfymodal_runtime/modal_app.py`` ~10979).  Idempotent.  SeedVR2
    shares nothing with this path.
    """
    if snap is not True:
        raise ValueError(f"startup requires snap=True, got {snap!r}")
    if ADAPTER_DIR not in sys.path:
        sys.path.insert(0, ADAPTER_DIR)
    from studio_upscale_vosr2 import vosr2_static_init

    return vosr2_static_init(snap=True)


def restore(snap: bool = False) -> dict:
    """Post-snapshot restore (Modal ``restore(snap=False)`` scope).

    Minimal: mutable-state reset, CUDA init once, per-model source re-read
    (``lean`` mode only) + CPU materialize + H2D, then request-ready.
    Mirrors Golden ``restore`` (``comfymodal_runtime/modal_app.py`` ~12674).
    Idempotent — repeat calls return the cached restore timing.  NO Modal
    GPU snapshotting.
    """
    if snap is not False:
        raise ValueError(f"restore requires snap=False, got {snap!r}")
    if ADAPTER_DIR not in sys.path:
        sys.path.insert(0, ADAPTER_DIR)
    from studio_upscale_vosr2 import vosr2_restore

    return vosr2_restore(snap=False)


@app.function(
    image=upscale_image,
    # GPU JUSTIFICATION: SeedVR2 3B weights are ~28GB on disk — the 40GB class
    # is marginal once the bf16 working copy, DiT activations at the upscaled
    # target resolution, VAE decode, text embeds, and CUDA context are added
    # for a single image.  The 80GB class (A100-80GB) is the safe single-image
    # choice; H100 / RTX-PRO-6000 are equivalent-or-better substitutes.
    # A100-80GB over H100: cheaper, sm_80 mature under cu130 torch + triton.
    # VOSR2 (~7GB) fits anywhere; SeedVR2 drives this choice.
    gpu="A100-80GB",
    cpu=8,
    memory=65536,
    # TRUE-COLD CPU memory snapshots (NOT GPU): the platform captures the
    # container after CPU-resident static init (startup(snap=True)) returns
    # ready; post-snapshot work (CUDA init, H2D) runs in restore(snap=False).
    # This is the enabling param — capture itself is platform-side.
    enable_memory_snapshot=True,
    # Proven budget: matches UPSCALE_MODAL_TIMEOUT_S = 1800.0 in
    # studio_upscale_run.py (single-image diffusion upscale + cold load).
    timeout=1800,
    # Existing model storage only: the same comfyui-models Volume mounted at
    # the same MODELS_PATH as every comfyapp.py GPU function.
    volumes={MODELS_PATH: upscale_vol},
)
def studio_upscale(payload: dict) -> dict:
    """Single remote upscale entrypoint: {image_b64, method, scale, seed,
    tile_size?, tile_overlap?, vae_tile_size?} -> {status, image_b64?}."""
    import base64
    import io
    import sys

    if ADAPTER_DIR not in sys.path:
        sys.path.insert(0, ADAPTER_DIR)

    def _fail(message: str) -> dict:
        return {"status": "error", "message": message}

    if not isinstance(payload, dict):
        return _fail("UPSCALE_BAD_REQUEST: expected a JSON object payload")
    method = str(payload.get("method") or "").strip().lower()
    if method not in ("vosr2", "seedvr2"):
        return _fail(
            f"UPSCALE_UNKNOWN_METHOD: unknown upscale method "
            f"{payload.get('method')!r}: expected exactly 'vosr2' or 'seedvr2' "
            f"(no Auto)"
        )
    try:
        scale_value = float(payload.get("scale", 4))
    except (TypeError, ValueError):
        return _fail(
            f"UPSCALE_BAD_SCALE: scale must be a number >= 1, "
            f"got {payload.get('scale')!r}"
        )
    if not (scale_value >= 1):
        return _fail(f"UPSCALE_BAD_SCALE: scale must be >= 1, got {scale_value!r}")
    try:
        seed = int(payload.get("seed", 0 if method == "vosr2" else 666))
    except (TypeError, ValueError):
        return _fail(
            f"UPSCALE_BAD_OPTION: seed must be an integer, "
            f"got {payload.get('seed')!r}"
        )
    raw_b64 = payload.get("image_b64") or ""
    if not isinstance(raw_b64, str) or not raw_b64.strip():
        return _fail("UPSCALE_BAD_REQUEST: image_b64 is required")

    from PIL import Image

    try:
        rgb = Image.open(io.BytesIO(base64.b64decode(raw_b64))).convert("RGB")
    except Exception as exc:
        return _fail(f"UPSCALE_SOURCE_UNREADABLE: could not decode image_b64: {exc}")

    try:
        if method == "vosr2":
            from studio_upscale_vosr2 import VOSR2Unavailable
            from studio_upscale_vosr2 import get_last_vosr2_timing
            from studio_upscale_vosr2 import upscale_vosr2

            # TRUE-COLD lifecycle: static init once (CPU-only, idempotent),
            # restore once (mutable reset + CUDA init + H2D, idempotent),
            # then per-image execution.  Warm containers skip straight to
            # inference; the request path itself does no imports, no config
            # reads, no path scans, and no network.
            startup(snap=True)
            restore(snap=False)
            out = upscale_vosr2(
                rgb,
                scale=scale_value,
                tile_size=int(payload.get("tile_size", 512)),
                tile_overlap=int(payload.get("tile_overlap", 64)),
                vae_tile_size=int(payload.get("vae_tile_size", 256)),
                seed=seed,
            )
            vosr2_timing = get_last_vosr2_timing()
        else:
            from studio_upscale_seedvr2 import SeedVR2Unavailable
            from studio_upscale_seedvr2 import upscale_seedvr2

            vosr2_timing = {}
            out = upscale_seedvr2(rgb, scale=scale_value, seed=seed)
    except Exception as exc:  # fail-closed, never raise across the boundary
        code = getattr(exc, "error_code", None) or (
            "VOSR2_UNAVAILABLE" if method == "vosr2" else "SEEDVR2_UNAVAILABLE"
        )
        return _fail(f"{code}: {exc}")

    cache_note = ""
    if _WARMED.get(method):
        cache_note = f" (model cache hit: {_WARMED[method]})"
    print(f"[studio_upscale] method={method} served{cache_note}", flush=True)
    weights_env = (
        os.environ.get("COMFYMODAL_VOSR2_WEIGHTS", "")
        if method == "vosr2"
        else os.environ.get("COMFYMODAL_SEEDVR2_WEIGHTS", "")
    )
    _WARMED[method] = weights_env or "(default)"

    buf = io.BytesIO()
    import time as _time

    _png0 = _time.perf_counter()
    out.save(buf, format="PNG")
    _png_ms = round((_time.perf_counter() - _png0) * 1000, 3)
    response: dict = {
        "status": "ok",
        "image_b64": base64.b64encode(buf.getvalue()).decode("ascii"),
    }
    if method == "vosr2" and vosr2_timing:
        # Additive only: dispatch reads status/image_b64 and ignores this.
        vosr2_timing = dict(vosr2_timing)
        vosr2_timing["png_encode_ms"] = _png_ms
        response["vosr2_timing"] = vosr2_timing
    return response
