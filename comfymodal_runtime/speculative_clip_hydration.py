"""E25/E28 speculative-but-exact CLIP hydration lane.

Goal: start the CLIP GPU hydration (the direct-GPU fastsafetensors read +
optional FP32 cast-once) as soon as the exact model identity is known —
E28: from the RESTORE-TIME lifecycle (frozen manifest available ~+18-37 ms
after remote Python resume), long before plan receipt — so the unavoidable
restore/setup window hides it.  The lane is a *file read + transform*
speculative pipeline; the **bind** is deferred to demand time and always
runs inside the existing authoritative hydrator
(``clip_fast_hydration_wiring._try_fast_hydrate``), which is untouched for
numerical behavior: it still runs the source fence, the orchestration
records, the D15 critical bracket, the bind via Comfy's own dispatch, and
the sync.

Safety invariants
-----------------
* Exact identity: the lane starts ONLY when the request model identity
  (model key + loader spec + workflow hash + deployment hash + custom-node
  generation) matches the spec that will be bound at demand time.  At
  restore-time launch the identity is the frozen-manifest identity (the
  retained CLIP is authoritative at restore); the request-time launch point
  (plan receipt) REPLACES that identity with the exact request-derived
  identity when they differ (fail-closed: a changed manifest or request
  mismatch drops the restore-time lane and starts fresh).
* No duplicate hydration: demand takes the single-flight speculative tensors
  exactly once; the hydrator's own ``already_hydrated`` marker remains the
  authoritative no-duplicate guard.
* Source fence: the speculative reader joins (``before_demand_load``) BEFORE
  any demand-side file read, exactly like the existing checkpoint-prewarm
  fence; a failed fence aborts the fast path (unchanged semantics).
* Cancellation: a request that never consumes the model closes the
  speculative owners + runs ``torch.cuda.empty_cache`` at request end.
* Failure propagation: speculative failures are recorded and dropped; the
  demand-time hydrator re-runs its normal read (never observes a
  half-failed speculative state).
* No stale snapshot state: the lane is keyed per request; the module-level
  store is cleared when the request identity changes.
* D15: the speculative lane performs NO GPU mutation while the CLIP critical
  section is active; the D15 GPU-lane bracket wraps ONLY the bind/sync at
  demand time, exactly as the existing demand hydrator does today.
* E28 CUDA-readiness discipline: the restore-time lane waits on the minimum
  CUDA readiness condition (``torch.cuda.is_initialized()``, bounded) and
  records ``cuda_readiness_start/completable`` + ``clip_speculative_future_created``
  on the shared monotonic axis so the manifest→loader-start and
  CUDA-ready→loader-start left-shift is measurable.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from . import clip_fast_hydration as cfh
from . import clip_fast_hydration_wiring as _wiring

# ── Module-level single-flight store (one lane per request) ──────────────

_LOCK = threading.Lock()
# request_id -> _SpeculativeClipLane
_LANES: dict[str, "_SpeculativeClipLane"] = {}
# Release-once guard for the UNET prefetch release callback.  Separate from
# _LOCK because _drop_lane_locked is called while holding _LOCK (a plain
# non-reentrant Lock) and _signal_unet_release must not re-enter it.
_RELEASE_LOCK = threading.Lock()


@dataclass
class _SpeculativeClipLane:
    request_id: str
    identity: str  # exact identity key the lane was started under
    file_paths: tuple[str, ...] = ()
    clip_names: tuple[str, ...] = ()
    manifest_files: tuple[dict, ...] = ()
    # Loaded + transformed per-file tensors (GPU).  Held until demand takes
    # them or the lane is closed.
    per_file_sds: list = field(default_factory=list)
    owners: list[tuple[Any, Any]] = field(default_factory=list)
    started_mono_ns: int = 0
    finished_mono_ns: int = 0
    cancelled: bool = False
    record: dict[str, Any] = field(default_factory=dict)
    # Frozen manifest attached to the restored CLIP at capture; the SAME
    # manifest the authoritative demand-time hydrator verifies against.  The
    # speculative worker resolves its absolute source paths from here (never
    # folder_paths at plan receipt) so it cannot diverge from demand.
    manifest: Optional[dict] = None
    path_source: str = "none"  # "frozen_manifest" | "file_facts" | "fallback"
    # CLIP-first/UNET-second coordination: set when the CLIP source read has
    # definitively finished (success OR failure) so the controller may
    # release UNET source prefetch exactly once.
    unet_release_sent: bool = False
    release_callback: Any = None
    # E30: True when the QD reader produced this lane's tensors (vs the
    # fastsafe fallback).  Propagated into the take record as ``qd_used``.
    _qd_used: bool = False


def _clip_names_from_spec(model_spec: Any) -> tuple[str, ...]:
    """Extract the raw CLIP file names from the loader spec (no path
    resolution — paths are resolved lazily on the worker thread)."""
    try:
        names: list[str] = []
        if not isinstance(model_spec, dict):
            return ()
        loaders = model_spec.get("loaders") or {}
        clip_loaders = loaders.get("clip") or []
        if not isinstance(clip_loaders, list):
            return ()
        for entry in clip_loaders:
            if not isinstance(entry, dict):
                continue
            clip_name = str(
                entry.get("clip_name")
                or entry.get("clip_name1")
                or ""
            ).strip()
            if clip_name:
                names.append(clip_name)
        return tuple(names)
    except Exception:
        return ()


def _frozen_manifest_from_clip(clip: Any) -> Optional[dict]:
    """Return the frozen capability manifest attached to the restored CLIP.

    The manifest is attached at snapshot construction
    (``clip_fast_hydration_wiring.maybe_prepare_clip_snapshot_exclusion`` →
    ``cfh.attach_clip_manifest``).  It carries the authoritative per-file
    entries: ``files[].path`` (absolute source path at capture), size_bytes,
    mtime_ns, dtype, key_set, key_shapes, pipeline — the EXACT data the
    demand-time hydrator verifies against.  The speculative lane derives its
    source paths from here so it can never diverge from demand.
    """
    if clip is None:
        return None
    manifest = cfh.get_clip_manifest(clip)
    if not isinstance(manifest, dict) or not manifest:
        return None
    if not manifest.get("eligible"):
        return None
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        return None
    return manifest


def _manifest_absolute_paths(manifest: dict) -> tuple[str, ...]:
    """Extract authoritative absolute CLIP source paths from the frozen
    manifest (files[].path — absolute at capture).  Empty when the manifest
    carries no usable path (lane fails closed)."""
    paths: list[str] = []
    for entry in manifest.get("files") or []:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path", "") or "").strip()
        if path:
            paths.append(path)
    return tuple(paths)


def _clip_paths_from_file_facts(cpu_models: Any) -> tuple[str, ...]:
    """Fallback: derive CLIP absolute paths from the CPU-snapshot
    ``file_facts`` (roles clip1/clip2 carry the absolute capture-time path).
    Used only when the CLIP object's attached manifest is unavailable (e.g.
    a legacy container); still authoritative (frozen at capture), never a
    folder_paths scan."""
    if cpu_models is None:
        return ()
    try:
        paths: list[str] = []
        for fact in getattr(cpu_models, "file_facts", ()) or ():
            role = getattr(fact, "role", "")
            if role in ("clip1", "clip2"):
                path = str(getattr(fact, "path", "") or "").strip()
                if path:
                    paths.append(path)
        return tuple(paths)
    except Exception:
        return ()


def _manifest_identity_digest(manifest: dict) -> str:
    """Stable digest over the frozen-manifest file entries.

    Includes every relevant existing invariant the demand hydrator checks:
    absolute path, size_bytes, mtime_ns, dtype, key_set, key_shapes, and the
    transform pipeline.  Used to reject a stale manifest (capture-time facts
    that no longer match the on-disk file) BEFORE any speculative read.
    """
    import hashlib as _hashlib
    import json as _json

    try:
        payload = []
        for entry in manifest.get("files") or []:
            if not isinstance(entry, dict):
                continue
            payload.append(
                {
                    "path": entry.get("path", ""),
                    "size_bytes": entry.get("size_bytes", 0),
                    "mtime_ns": entry.get("mtime_ns", 0),
                    "dtype": entry.get("dtype", ""),
                    "key_set": entry.get("key_set", []),
                    "key_shapes": entry.get("key_shapes", {}),
                    "pipeline": entry.get("pipeline", []),
                }
            )
        raw = _json.dumps(payload, sort_keys=True, default=str)
        return _hashlib.sha256(raw.encode("utf-8")).hexdigest()
    except Exception:
        return ""


def _resolve_clip_paths(clip_names: tuple[str, ...]) -> tuple[str, ...]:
    """UNCHANGED FALLBACK: resolve CLIP file names to absolute paths using
    ``comfy.folder_paths``.

    Kept ONLY as the last-resort fallback when neither the frozen manifest
    nor the file_facts carry an authoritative path (legacy containers).  The
    frozen-manifest path is authoritative on the normal speculative fast path
    and no folder_paths scan runs there.
    """
    try:
        from comfy import folder_paths as _fp

        def _one(clip_name: str) -> str:
            resolved = _fp.get_full_path("text_encoders", clip_name)
            if not resolved:
                resolved = _fp.get_full_path("checkpoints", clip_name)
            if not resolved:
                resolved = _fp.get_full_path("clip", clip_name)
            if resolved and os.path.exists(str(resolved)):
                return str(resolved)
            # Direct-scan fallback: search the registered folder roots.
            try:
                roots = _fp.folder_names_and_paths.get("text_encoders", ([],))[0]
                for root in roots:
                    candidate = os.path.join(str(root), clip_name)
                    if os.path.exists(candidate):
                        return candidate
            except Exception:
                pass
            try:
                roots = _fp.folder_names_and_paths.get("checkpoints", ([],))[0]
                for root in roots:
                    candidate = os.path.join(str(root), clip_name)
                    if os.path.exists(candidate):
                        return candidate
            except Exception:
                pass
            # Models-root construction fallback: the models Volume is mounted
            # at ``<comfy_root>/models``; folder_paths.models_dir is the
            # authoritative root.  Covers the mounted-Volume layout where the
            # per-folder registration is not visible at this early point.
            try:
                models_dir = getattr(_fp, "models_dir", "") or ""
                for sub in ("text_encoders", "clip", "checkpoints"):
                    candidate = os.path.join(models_dir, sub, clip_name)
                    if os.path.exists(candidate):
                        return candidate
            except Exception:
                pass
            # Absolute container-root fallback: the demand-side manifest uses
            # the exact path ``/root/comfy/ComfyUI/models/<folder>/<name>``
            # (ComfyUI's base_path).  Try the same construction directly.
            try:
                base = getattr(_fp, "base_path", "") or ""
                if base:
                    for sub in ("text_encoders", "clip", "checkpoints"):
                        candidate = os.path.join(base, "models", sub, clip_name)
                        if os.path.exists(candidate):
                            return candidate
            except Exception:
                pass
            # Last-resort bounded recursive scan of the models root for the
            # exact file name.  Rare (one file), bounded depth 3, and only
            # reached after every structured lookup failed — the demand-side
            # manifest proves the file exists somewhere under the models tree.
            try:
                _roots = []
                if getattr(_fp, "models_dir", ""):
                    _roots.append(getattr(_fp, "models_dir", ""))
                if getattr(_fp, "base_path", ""):
                    _roots.append(os.path.join(getattr(_fp, "base_path", ""), "models"))
                # Fixed container-root fallback: comfyapp deploys ComfyUI at
                # /root/comfy/ComfyUI with the models Volume at
                # /root/comfy/ComfyUI/models (the demand manifest uses this
                # exact root).  Only checked when the folder_paths attributes
                # above are empty/unavailable.
                if not _roots:
                    _roots.append("/root/comfy/ComfyUI/models")
                for _root in _roots:
                    if not _root or not os.path.isdir(_root):
                        continue
                    for _dirpath, _dirnames, _filenames in os.walk(_root):
                        _depth = _dirpath[len(_root):].count(os.sep)
                        if _depth > 3:
                            _dirnames[:] = []
                            continue
                        if clip_name in _filenames:
                            return os.path.join(_dirpath, clip_name)
            except Exception:
                pass
            return ""

        paths: list[str] = []
        for clip_name in clip_names:
            resolved = _one(str(clip_name))
            if not resolved:
                return ()
            paths.append(resolved)
        return tuple(paths)
    except Exception:
        return ()


def _build_speculative_identity(
    *,
    model_key: Any,
    model_spec: Any,
    workflow_hash: str,
    deployment_hash: str,
    custom_node_generation: str,
) -> str:
    """Exact identity for the speculative lane.

    Contains every input that affects what the demand-time hydrator binds:
    the model key hash (clip identity + loader class + clip_type + dtype
    policy), the resolved loader file names, the workflow/deployment/custom-
    node identity, and the fastsafe config.  Prompt text, seed, conditioning
    and request IDs are never part of the identity.
    """
    try:
        import hashlib as _hashlib
        import json as _json

        key_hash = str(getattr(model_key, "stable_hash", "") or "")
        # The fastsafe config constants live in the wiring module (the same
        # module the demand hydrator reads them from).
        parts: dict[str, Any] = {
            "key": key_hash,
            "wf": str(workflow_hash or ""),
            "deploy": str(deployment_hash or ""),
            "nodegen": str(custom_node_generation or ""),
            "fastsafe": {
                "threads": _wiring._FASTSAFE_THREADS,
                "block_bytes": _wiring._FASTSAFE_BLOCK_BYTES,
                "nogds": _wiring._FASTSAFE_NOGDS,
                "use_buf_register": _wiring._FASTSAFE_USE_BUF_REGISTER,
            },
        }
        try:
            if isinstance(model_spec, dict):
                loaders = model_spec.get("loaders") or {}
                clip_loaders = loaders.get("clip") or []
                parts["clip_names"] = [
                    str(c.get("clip_name") or c.get("clip_name1") or "")
                    for c in clip_loaders
                    if isinstance(c, dict)
                ]
        except Exception:
            pass
        raw = _json.dumps(parts, sort_keys=True, default=str)
        return "e25clip:" + _hashlib.sha256(raw.encode("utf-8")).hexdigest()
    except Exception:
        return ""


def _start_speculative_clip_lane(
    *,
    request_id: str,
    model_key: Any,
    model_spec: Any,
    workflow_hash: str,
    deployment_hash: str,
    custom_node_generation: str,
    trace: Any = None,
    clip: Any = None,
    cpu_models: Any = None,
    release_callback: Any = None,
) -> Optional["_SpeculativeClipLane"]:
    """Start the speculative CLIP file-read lane for *request_id*.

    Fail-closed and best-effort: any missing input, ineligible flag, or
    exception returns None and the demand path is unchanged.  The lane is
    single-flight per request (a second call is a no-op).

    E26 path resolution: the CLIP source paths are resolved HERE at plan
    receipt from the frozen manifest attached to the retained CLIP object
    (``files[].path`` — the authoritative absolute capture-time path the
    demand hydrator later verifies against).  No folder_paths scan runs on
    this fast path.  If the manifest is absent/invalid the lane fails closed
    (normal demand hydration unchanged).

    *release_callback* — an optional zero-arg callable invoked EXACTLY once
    when the speculative CLIP source read definitively finishes (success OR
    failure) so the CLIP-first/UNET-second coordinator can release UNET
    source prefetch without waiting on the lane.

    Every gate that can reject the lane emits a ``clip_fh_speculative_skip``
    trace event with the exact reason so a run that did NOT exercise the lane
    is provably diagnosable (never silently absent).
    """

    def _skip(reason: str) -> None:
        if trace is not None:
            try:
                trace.emit("clip_fh_speculative_skip", phase="execution", metadata={
                    "request_id": request_id,
                    "reason": reason,
                })
            except Exception:
                pass

    if not request_id:
        return None
    # Hard gates: the direct-GPU fastsafetensors path must be the path the
    # demand hydrator will take.  When any gate is off the lane does nothing.
    try:
        if not _wiring.clip_fast_hydration_enabled():
            _skip("clip_fast_hydration_disabled")
            return None
    except Exception:
        _skip("clip_fast_hydration_gate_error")
        return None
    try:
        if not os.environ.get("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION", "1"):
            _skip("speculative_clip_hydration_disabled")
            return None
    except Exception:
        _skip("speculative_clip_hydration_gate_error")
        return None
    # ── E26: resolve the authoritative CLIP source paths AT PLAN RECEIPT ──
    # Priority: (1) the frozen manifest attached to the restored CLIP (the
    # SAME object the demand hydrator verifies against); (2) the CPU-snapshot
    # file_facts (absolute capture-time paths, still authoritative); (3) NO
    # folder_paths scan on the fast path — the manifest/file-facts are the
    # authoritative source.  The legacy folder_paths resolver remains only as
    # a worker-side fallback for manifest-less legacy containers.
    manifest = None
    path_source = "none"
    try:
        manifest = _frozen_manifest_from_clip(clip)
    except Exception:
        manifest = None
    if manifest is not None:
        paths = _manifest_absolute_paths(manifest)
        path_source = "frozen_manifest"
    else:
        paths = _clip_paths_from_file_facts(cpu_models)
        if paths:
            path_source = "file_facts"
    if not paths:
        # Fail-closed at plan receipt: no authoritative frozen path data.
        _skip("frozen_manifest_unavailable")
        return None
    # Freshness pre-check: the manifest must agree with the on-disk file at
    # read time.  The worker re-verifies, but a stat mismatch here is a cheap
    # early rejection that releases UNET immediately.
    if path_source == "frozen_manifest":
        for entry in manifest.get("files") or []:
            if not isinstance(entry, dict):
                continue
            _p = entry.get("path", "")
            _sz = entry.get("size_bytes")
            if _p and _sz is not None:
                try:
                    if not os.path.exists(_p):
                        _skip(f"manifest_missing_file:{os.path.basename(str(_p))}")
                        return None
                    if int(os.path.getsize(_p)) != int(_sz):
                        _skip(f"manifest_stale_size:{os.path.basename(str(_p))}")
                        return None
                except Exception:
                    continue
    clip_names = _clip_names_from_spec(model_spec)
    identity = _build_speculative_identity(
        model_key=model_key,
        model_spec=model_spec,
        workflow_hash=workflow_hash,
        deployment_hash=deployment_hash,
        custom_node_generation=custom_node_generation,
    )
    if not identity:
        _skip("identity_unavailable")
        return None
    # E26: fold the frozen-manifest digest into the lane identity so a
    # generation/manifest change between lane start and demand is caught by
    # the demand-side identity comparison as well as the manifest verify.
    if manifest is not None:
        _digest = _manifest_identity_digest(manifest)
        if _digest:
            identity = f"{identity}:mf:{_digest[:16]}"

    with _LOCK:
        existing = _LANES.get(request_id)
        if existing is not None:
            if existing.identity != identity:
                # Identity changed between calls for the same request: drop
                # the stale lane (fail-closed) and start fresh.
                _drop_lane_locked(request_id)
            else:
                return existing
        lane = _SpeculativeClipLane(
            request_id=request_id,
            identity=identity,
            file_paths=tuple(paths),
            clip_names=clip_names,
            manifest_files=tuple(
                e for e in (manifest or {}).get("files", []) if isinstance(e, dict)
            ),
            manifest=manifest,
            path_source=path_source,
            started_mono_ns=time.monotonic_ns(),
            release_callback=release_callback,
        )
        _LANES[request_id] = lane

    # ── E26: lane-started telemetry (best-effort; never raises) ──
    if trace is not None:
        try:
            trace.emit("clip_fh_speculative_lane_started", phase="execution", metadata={
                "request_id": request_id,
                "identity": identity[:24],
                "clip_names": list(clip_names),
                "path_source": path_source,
                "paths": list(paths),
                "lane_start_mono_ns": time.monotonic_ns(),
            })
        except Exception:
            pass

    def _worker() -> None:
        try:
            _run_speculative_read(lane, trace=trace)
        except Exception:
            # The demand path never observes a half-failed speculative state;
            # it simply re-runs the normal hydrator.
            pass
        finally:
            _signal_unet_release(lane)

    try:
        t = threading.Thread(
            target=_worker,
            daemon=True,
            name="comfymodal-speculative-clip-hydration",
        )
        t.start()
    except Exception:
        with _LOCK:
            _LANES.pop(request_id, None)
        _signal_unet_release(lane)
        return None
    return lane


def _signal_unet_release(lane: "_SpeculativeClipLane") -> None:
    """Release the coordinated UNET prefetch exactly once.

    Invoked when the speculative CLIP read definitively finishes — success,
    failure, or cancellation — so the CLIP-first/UNET-second schedule can
    start UNET source prefetch without waiting on the lane.  Idempotent and
    never raises.  Uses a separate release lock so it can be called from
    paths that already hold the lane store lock."""
    if lane is None:
        return
    with _RELEASE_LOCK:
        if lane.unet_release_sent:
            return
        lane.unet_release_sent = True
        cb = lane.release_callback
        lane.release_callback = None
    if cb is None:
        return
    try:
        cb()
    except Exception:
        pass


def _run_speculative_read(lane: "_SpeculativeClipLane", *, trace: Any = None) -> None:
    """Speculative phase: read every file to GPU and apply the transform
    pipeline.  Verification against the frozen manifest and the BIND both
    happen at demand time inside the authoritative hydrator.

    E26: the source paths come from the frozen manifest / file-facts resolved
    at plan receipt (lane.file_paths).  The worker does NOT scan folder_paths
    on the fast path; it only validates the on-disk stat against the manifest
    and reads.  If a file is missing or the manifest is stale the lane records
    a failed result and the demand path falls back — fail-closed."""
    import torch

    def _emit(name: str, metadata: dict[str, Any]) -> None:
        if trace is None:
            return
        try:
            payload = dict(metadata)
            payload.setdefault("request_id", lane.request_id)
            trace.emit(name, phase="execution", metadata=payload)
        except Exception:
            pass

    result: dict[str, Any] = {
        "ok": False,
        "mode": cfh.MODE_FASTSAFE,
        "reason": "not_run",
    }
    owners: list[tuple[Any, Any]] = []
    per_file_sds: list[dict] = []
    t0 = time.perf_counter()
    _read_start_mono_ns = time.monotonic_ns()
    # ── E28: CUDA-readiness instrumentation on the shared mono axis ──
    # The direct-GPU loader requires a live CUDA context on the calling
    # thread.  At restore-time launch CUDA may not be initialized yet; the
    # lane records readiness start/complete so the left-shift is measurable
    # (manifest -> loader start, CUDA-ready -> loader start).
    _cuda_readiness_started_mono_ns = time.monotonic_ns()
    try:
        from .gantt_telemetry import register_gantt_span as _reg_span

        _reg_span(
            "cuda_readiness_start",
            start_mono_ns=_cuda_readiness_started_mono_ns,
            end_mono_ns=_cuda_readiness_started_mono_ns,
            lane="GPU",
            metadata={"kind": "point"},
        )
    except Exception:
        pass
    _emit("clip_fh_speculative_read_start", {
        "clip_names": list(lane.clip_names),
        "path_source": lane.path_source,
        "paths": list(lane.file_paths),
        "read_start_mono_ns": _read_start_mono_ns,
    })
    try:
        # Wait briefly for CUDA to be initialized (bounded).  The lane is
        # started at restore-time — possibly before the runtime's first CUDA
        # init — and fastsafetensors requires a live CUDA context on the
        # calling thread.  Fail-closed: if CUDA never becomes ready within the
        # bound, the lane records a failure and the demand path falls back.
        try:
            _cuda_deadline = time.monotonic() + 5.0
            while not torch.cuda.is_initialized() and time.monotonic() < _cuda_deadline:
                time.sleep(0.02)
        except Exception:
            pass
        try:
            from .gantt_telemetry import register_gantt_span as _reg_span2

            _reg_span2(
                "cuda_readiness_complete",
                start_mono_ns=time.monotonic_ns(),
                end_mono_ns=time.monotonic_ns(),
                lane="GPU",
                metadata={"kind": "point"},
            )
        except Exception:
            pass
        paths = tuple(lane.file_paths or ())
        if not paths:
            raise RuntimeError("clip_paths_unresolved:no_frozen_manifest_paths")
        # Freshness validation against the frozen manifest: the on-disk file
        # must match the capture-time facts (absolute path + size).  Any
        # mismatch fails closed (demand re-reads + re-verifies).  This is the
        # authoritative path — no folder_paths scan.
        _manifest_by_path: dict[str, dict] = {}
        for entry in lane.manifest_files:
            _p = str(entry.get("path", "") or "")
            if _p:
                _manifest_by_path[_p] = entry
        lane.file_paths = tuple(paths)
        checkpoint_bytes = 0
        for path in paths:
            if not os.path.exists(path):
                raise RuntimeError(f"missing source file: {path}")
            _entry = _manifest_by_path.get(path) or {}
            _exp_size = _entry.get("size_bytes")
            if _exp_size is not None:
                try:
                    if int(os.path.getsize(path)) != int(_exp_size):
                        raise RuntimeError(f"manifest_stale_size:{os.path.basename(path)}")
                except RuntimeError:
                    raise
                except Exception:
                    pass
            # ── E30 seam: genuine-QD CLIP source read (default-OFF) ──
            # When COMFYMODAL_V2_CLIP_QD_READER is truthy, the E30 queued-
            # pread pipeline (bounded pinned staging -> async H2D -> zero-copy
            # views) replaces the fastsafetensors direct-GPU read for THIS
            # file.  clip_qd_load returns the same (sd, loader, fb) contract
            # the lane already consumes.  Fail-closed: any E30 error falls
            # back to the unchanged _fastsafe_load path (production behavior
            # with the flag OFF is byte-identical to E28).
            try:
                from .clip_qd_reader import clip_qd_load, clip_qd_reader_enabled

                if clip_qd_reader_enabled():
                    from .clip_qd_reader import resolve_launch_policy

                    print(
                        f"[v2.clip_qd] entering E30 seam path={os.path.basename(str(path))}",
                        flush=True,
                    )
                    try:
                        sd_raw, loader, fb = clip_qd_load(
                            path,
                            trace=trace,
                            launch_policy=resolve_launch_policy(),
                        )
                    except Exception as _e30_exc:
                        # Fail-closed with explicit telemetry: an E30 error
                        # must be diagnosable (never a silent fallback).  Only
                        # THIS branch may emit the E30 fallback event — a
                        # flag-OFF fastsafe failure must never be mislabeled
                        # as a QD fallback.
                        _emit("clip_qd_fallback", {
                            "reason": f"{type(_e30_exc).__name__}: {str(_e30_exc)[:200]}",
                            "path": str(path),
                            "qd_reader_enabled": True,
                        })
                        print(
                            f"[v2.clip_qd] fallback reason={type(_e30_exc).__name__}: "
                            f"{str(_e30_exc)[:200]} path={os.path.basename(str(path))}",
                            flush=True,
                        )
                        sd_raw, loader, fb = _wiring._fastsafe_load(path)
                    else:
                        print(
                            f"[v2.clip_qd] E30 load OK path={os.path.basename(str(path))} "
                            f"tensors={len(sd_raw)}",
                            flush=True,
                        )
                        lane._qd_used = True
                else:
                    sd_raw, loader, fb = _wiring._fastsafe_load(path)
            except Exception as _e30_exc:
                # The fastsafe fallback itself failed: propagate (the lane's
                # outer handler records the failed read and the demand path
                # falls back to the normal hydrator).  Never emit the E30
                # fallback event for a flag-OFF failure.
                raise
            owners.append((loader, fb))
            work = _wiring._blob_free(
                {k: v for k, v in sd_raw.items() if isinstance(v, torch.Tensor)}
            )
            # Use the FROZEN pipeline from the manifest when present (the
            # exact transform the demand hydrator replays) so the speculative
            # tensors are byte-identical to the demand path.
            pipeline = _entry.get("pipeline") or _wiring._select_pipeline(work)
            transformed = _wiring._apply_pipeline(work, pipeline, comfy_utils=None)
            per_file_sds.append(transformed)
            checkpoint_bytes += int(os.path.getsize(path))
        # ── E28 Target C: compute-ready FP32 cast-once ──
        # When the flag is on and the manifest is uniformly BF16, cast every
        # tensor once to FP32 (exact widening) BEFORE the bind so the final
        # resident representation is compute-ready and the per-forward cast
        # tax disappears.  Fail-closed: any ineligibility leaves the BF16
        # tensors untouched (normal demand path).
        _cast_record: dict[str, Any] = {}
        try:
            from .clip_fp32_cast_once import apply_cast_once, cast_once_enabled

            if cast_once_enabled():
                per_file_sds, _cast_record = apply_cast_once(
                    per_file_sds, list(lane.manifest_files), trace=trace
                )
        except Exception:
            _cast_record = {}
        lane.owners = owners
        lane.per_file_sds = per_file_sds
        lane.record = {
            "speculative_read_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            "checkpoint_bytes": checkpoint_bytes,
            "files": len(lane.file_paths),
            "gpu_tensors_held": True,
            # E30: explicit proof the QD reader produced the tensors (vs the
            # fastsafe fallback) so a QD-entered run is provable from the
            # record alone, and a non-QD run is provably not mislabeled.
            "qd_used": bool(getattr(lane, "_qd_used", False)),
            # E28: ALWAYS a dict (never None) so the demand-side consumer can
            # safely do ``record.get("cast_once", {}).get("applied", False)``.
            "cast_once": dict(_cast_record),
        }
        result = {
            "ok": True,
            "mode": cfh.MODE_FASTSAFE,
            "reason": "speculative_read_complete",
            "wall_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        }
        _emit("clip_fh_speculative_read_complete", {
            "read_wall_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            "checkpoint_bytes": checkpoint_bytes,
            "files": len(lane.file_paths),
            "path_source": lane.path_source,
            "read_complete_mono_ns": time.monotonic_ns(),
        })
        # E27 Follow-Up A: the speculative lane's read IS the real CLIP
        # source read on the shared monotonic axis (the Gantt must show the
        # actual production read, not only the demand-path fallback).
        try:
            from .gantt_telemetry import register_gantt_span

            register_gantt_span(
                "clip_source_read",
                start_mono_ns=_read_start_mono_ns,
                end_mono_ns=time.monotonic_ns(),
                lane="STORAGE",
                metadata={
                    "path_source": lane.path_source,
                    "files": len(lane.file_paths),
                    "checkpoint_bytes": checkpoint_bytes,
                    "speculative": True,
                },
            )
        except Exception:
            pass
    except Exception as exc:
        result = {
            "ok": False,
            "mode": cfh.MODE_FASTSAFE,
            "reason": f"{type(exc).__name__}: {str(exc)[:200]}",
            "wall_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        }
        for loader, fb in owners:
            try:
                loader.close()
            except Exception:
                pass
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
        _emit("clip_fh_speculative_read_failed", {
            "reason": result["reason"],
            "read_wall_ms": result["wall_ms"],
            "path_source": lane.path_source,
        })
    finally:
        lane.record["result"] = result
        lane.finished_mono_ns = time.monotonic_ns()


def get_speculative_clip_lane(request_id: str) -> Optional["_SpeculativeClipLane"]:
    """Return the live speculative lane for *request_id* (or None)."""
    if not request_id:
        return None
    with _LOCK:
        lane = _LANES.get(request_id)
        if lane is None and request_id != _RESTORE_TIME_KEY:
            lane = _LANES.get(_RESTORE_TIME_KEY)
        return lane


def active_speculative_request_id() -> str:
    """Return the request_id of the single active unconsumed speculative lane.

    The container runs one request at a time, so when exactly one lane exists
    it is the current request's lane.  Returns '' when zero or multiple lanes
    exist (fail-closed — never guesses).  E28: a restore-time lane stored
    under the reserved ``_RESTORE_TIME_KEY`` resolves to itself so the
    demand path can take it even when the plan-receipt reconcile did not
    run (e.g. an execution path that never reaches the reconcile)."""
    with _LOCK:
        active = [rid for rid, lane in _LANES.items() if not lane.cancelled]
        if len(active) == 1:
            return active[0]
        return ""


def resolve_speculative_key(request_id: str) -> str:
    """Resolve the lane key for *request_id*: the request id itself when a
    lane exists under it, else the reserved restore-time key (single-flight
    container).  Returns '' when neither exists."""
    if not request_id:
        return ""
    with _LOCK:
        if request_id in _LANES:
            return request_id
        if _RESTORE_TIME_KEY in _LANES:
            return _RESTORE_TIME_KEY
        return ""


def join_speculative_clip_lane(request_id: str, timeout_s: float = 60.0) -> Optional[dict[str, Any]]:
    """Join the speculative lane (if present) and return its record.

    Returns None when no lane exists or the join fails — the caller then
    runs its normal hydrator.  Never raises.
    """
    lane = get_speculative_clip_lane(request_id)
    if lane is None:
        return None
    try:
        _deadline = time.monotonic() + max(0.0, timeout_s)
        while lane.finished_mono_ns == 0:
            if time.monotonic() >= _deadline:
                break
            time.sleep(0.002)
        return dict(lane.record) if lane.record else None
    except Exception:
        return None


def take_speculative_read(
    request_id: str,
) -> Optional[tuple[list, list, dict]]:
    """Demand-time take: transfer the speculative per-file tensors + owners
    out of the lane (exactly once).  Returns ``(per_file_sds, owners,
    record)`` when a completed, unconsumed lane exists; None otherwise.  The
    caller (the authoritative hydrator) binds + syncs and takes over the
    owners."""
    lane = get_speculative_clip_lane(request_id)
    if lane is None:
        return None
    if lane.cancelled or not lane.owners or not lane.per_file_sds:
        return None
    try:
        if not lane.record.get("result", {}).get("ok"):
            return None
    except Exception:
        return None
    # Resolve the actual store key (request id, or the reserved restore-time
    # key when the lane was never re-keyed at plan receipt).
    key = request_id
    with _LOCK:
        if key not in _LANES:
            if _RESTORE_TIME_KEY in _LANES:
                key = _RESTORE_TIME_KEY
            else:
                return None
        # Re-fetch under the lock; another thread may have taken it.
        lane = _LANES.get(key)
        if lane is None or lane.cancelled or not lane.owners or not lane.per_file_sds:
            return None
        per_file_sds = lane.per_file_sds
        owners = lane.owners
        record = dict(lane.record)
        _LANES.pop(key, None)
        _RESTORE_MANIFEST_DIGESTS.pop(key, None)
    lane.per_file_sds = []
    lane.owners = []
    return per_file_sds, owners, record


def close_speculative_clip_lane(request_id: str) -> None:
    """Close the speculative lane for *request_id* (release GPU owners +
    empty cache).  Idempotent.  E28: also resolves the reserved restore-time
    key when the request id maps to no lane."""
    with _LOCK:
        key = request_id
        if key not in _LANES and _RESTORE_TIME_KEY in _LANES:
            key = _RESTORE_TIME_KEY
        lane = _LANES.pop(key, None)
        _RESTORE_MANIFEST_DIGESTS.pop(key, None)
    if lane is None:
        return
    for loader, fb in lane.owners:
        try:
            loader.close()
        except Exception:
            pass
    lane.owners = []
    lane.per_file_sds = []
    lane.cancelled = True
    try:
        import torch

        torch.cuda.empty_cache()
    except Exception:
        pass
    _signal_unet_release(lane)


def clear_speculative_lanes_for_test() -> None:
    """Test-only: drop every lane and release owners."""
    with _LOCK:
        ids = list(_LANES)
    for rid in ids:
        close_speculative_clip_lane(rid)
    with _LOCK:
        _LANES.clear()


def _drop_lane_locked(request_id: str) -> None:
    lane = _LANES.pop(request_id, None)
    _RESTORE_MANIFEST_DIGESTS.pop(request_id, None)
    if lane is None:
        return
    for loader, fb in lane.owners:
        try:
            loader.close()
        except Exception:
            pass
    lane.owners = []
    lane.per_file_sds = []
    _signal_unet_release(lane)


def speculative_clip_hydration_enabled() -> bool:
    """True when the speculative CLIP hydration lane is eligible."""
    try:
        return _wiring.clip_fast_hydration_enabled() and bool(
            os.environ.get("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION", "1")
        )
    except Exception:
        return False


# ── E28: restore-time earliest launch ─────────────────────────────────────
# The speculative lane is ALSO started at restore-time (as soon as the
# frozen manifest is available) so the direct-GPU CLIP read begins at the
# first legal CUDA-ready instant instead of waiting for plan receipt.  The
# restore-time lane carries a *placeholder* identity (frozen-manifest
# digest); when the real request identity is derived at plan receipt the
# lane is upgraded in place when the manifest is unchanged, or dropped +
# restarted (fail-closed) when the identity differs.

_RESTORE_MANIFEST_DIGESTS: dict[str, str] = {}
"""request_id -> frozen-manifest digest captured at restore-time launch."""

# Reserved single-flight key for the restore-time lane.  The container runs
# one request at a time; the lane is launched at container boot (restore)
# before the request id exists, and the plan-receipt reconcile re-keys it to
# the real request id.  The demand-time fallback also resolves it.
_RESTORE_TIME_KEY = "__restore_time__"


def _restore_manifest_digest(request_id: str) -> str:
    with _LOCK:
        return _RESTORE_MANIFEST_DIGESTS.get(request_id, "")


def start_restore_time_clip_lane(
    *,
    request_id: str = "",
    clip: Any = None,
    cpu_models: Any = None,
    trace: Any = None,
    release_callback: Any = None,
) -> Optional["_SpeculativeClipLane"]:
    """E28: start the speculative CLIP lane at the earliest legal restore-time
    point — the moment the frozen manifest is observable on the restored
    container (usually ~+18-37 ms after remote Python resume).

    The lane does NOT wait for any request-dependent state: no method entry,
    no request arrival, no plan, no graph.  The frozen manifest supplies the
    authoritative absolute source path; the worker waits only on the minimum
    CUDA readiness condition (``torch.cuda.is_initialized()``, bounded) and
    then launches the direct-GPU fastsafetensors read immediately.

    Keying: the lane is stored under the reserved ``_RESTORE_TIME_KEY``
    (the request id is not known at container boot).  At plan receipt
    :func:`reconcile_restore_time_lane` re-keys it to the real request id.

    Returns the lane when started (or already present), else None.  Best-
    effort and never raises.
    """
    key = request_id or _RESTORE_TIME_KEY
    try:
        if not speculative_clip_hydration_enabled():
            return None
    except Exception:
        return None
    try:
        manifest = _frozen_manifest_from_clip(clip)
    except Exception:
        manifest = None
    if manifest is None:
        # file_facts fallback (legacy containers) — still authoritative.
        try:
            paths = _clip_paths_from_file_facts(cpu_models)
            if paths:
                manifest = {"files": [{"path": p} for p in paths], "eligible": True}
        except Exception:
            manifest = None
    if manifest is None or not manifest.get("eligible"):
        return None
    paths = _manifest_absolute_paths(manifest)
    if not paths:
        return None
    digest = _manifest_identity_digest(manifest)
    identity = f"restore:{digest[:16]}" if digest else "restore:nodigest"
    with _LOCK:
        existing = _LANES.get(key)
        if existing is not None:
            return existing
        lane = _SpeculativeClipLane(
            request_id=key,
            identity=identity,
            file_paths=tuple(paths),
            clip_names=(),
            manifest_files=tuple(
                e for e in (manifest or {}).get("files", []) if isinstance(e, dict)
            ),
            manifest=manifest,
            path_source="frozen_manifest",
            started_mono_ns=time.monotonic_ns(),
            release_callback=release_callback,
        )
        _LANES[key] = lane
        _RESTORE_MANIFEST_DIGESTS[key] = digest
    # Restore-time lane-started telemetry.
    if trace is not None:
        try:
            trace.emit("clip_fh_restore_time_lane_started", phase="execution", metadata={
                "request_id": key,
                "identity": identity[:32],
                "path_source": "frozen_manifest",
                "paths": list(paths),
                "lane_start_mono_ns": time.monotonic_ns(),
            })
        except Exception:
            pass
    try:
        from .gantt_telemetry import register_gantt_span

        register_gantt_span(
            "clip_speculative_future_created",
            start_mono_ns=lane.started_mono_ns,
            end_mono_ns=lane.started_mono_ns,
            lane="STORAGE",
            metadata={"kind": "point", "lifecycle": "restore_time"},
        )
    except Exception:
        pass

    def _worker() -> None:
        try:
            _run_speculative_read(lane, trace=trace)
        except Exception:
            pass
        finally:
            _signal_unet_release(lane)

    try:
        threading.Thread(
            target=_worker,
            daemon=True,
            name="comfymodal-restore-time-clip-hydration",
        ).start()
    except Exception:
        with _LOCK:
            _LANES.pop(key, None)
            _RESTORE_MANIFEST_DIGESTS.pop(key, None)
        _signal_unet_release(lane)
        return None
    return lane


def reconcile_restore_time_lane(
    *,
    request_id: str,
    model_key: Any,
    model_spec: Any,
    workflow_hash: str,
    deployment_hash: str,
    custom_node_generation: str,
    trace: Any = None,
    clip: Any = None,
    cpu_models: Any = None,
    release_callback: Any = None,
) -> Optional["_SpeculativeClipLane"]:
    """E28: plan-receipt reconciliation of a restore-time lane.

    Called from the existing plan-receipt speculative-launch site.  When a
    restore-time lane exists AND its frozen manifest digest still matches the
    request's manifest, the lane is re-keyed to the exact request identity
    (demand take then works unchanged).  When the identity diverges the
    restore-time lane is dropped and a fresh request-time lane starts
    (fail-closed).  Returns the reconciled lane or None.
    """
    if not request_id:
        return None
    restore_digest = _restore_manifest_digest(_RESTORE_TIME_KEY)
    manifest = None
    try:
        manifest = _frozen_manifest_from_clip(clip)
    except Exception:
        manifest = None
    current_digest = _manifest_identity_digest(manifest) if manifest is not None else ""
    request_identity = _build_speculative_identity(
        model_key=model_key,
        model_spec=model_spec,
        workflow_hash=workflow_hash,
        deployment_hash=deployment_hash,
        custom_node_generation=custom_node_generation,
    )
    if not request_identity:
        # No request identity derivable: keep whatever lane exists (the
        # demand-time take still verifies the manifest before binding).
        return get_speculative_clip_lane(request_id) or get_speculative_clip_lane(
            _RESTORE_TIME_KEY
        )
    if manifest is not None and current_digest:
        request_identity = f"{request_identity}:mf:{current_digest[:16]}"
    with _LOCK:
        existing = _LANES.get(request_id)
        if existing is not None:
            if existing.identity != request_identity:
                _drop_lane_locked(request_id)
            else:
                existing.release_callback = release_callback or existing.release_callback
                return existing
        restore_lane = _LANES.pop(_RESTORE_TIME_KEY, None)
        _RESTORE_MANIFEST_DIGESTS.pop(_RESTORE_TIME_KEY, None)
        if restore_lane is not None and restore_lane.identity.startswith("restore:"):
            # Only upgrade when the frozen manifest is unchanged (or the
            # restore lane had no digest at all — the manifest now supplies
            # the exact digest).
            if restore_digest and current_digest and restore_digest != current_digest:
                # Manifest changed since restore: drop the stale lane.
                for loader, fb in restore_lane.owners:
                    try:
                        loader.close()
                    except Exception:
                        pass
                restore_lane.owners = []
                restore_lane.per_file_sds = []
                _signal_unet_release(restore_lane)
                restore_lane = None
            else:
                restore_lane.request_id = request_id
                restore_lane.identity = request_identity
                restore_lane.release_callback = (
                    release_callback or restore_lane.release_callback
                )
                _LANES[request_id] = restore_lane
                # If the restore-time read already finished BEFORE the
                # request-time release callback existed (the expected fast
                # case), the CLIP-first/UNET-second release must still fire
                # exactly once — the controller now exists (begin_request ran
                # before this reconcile at plan receipt).
                if restore_lane.unet_release_sent and release_callback is not None:
                    _done = restore_lane
                    _cb = release_callback

                    def _fire() -> None:
                        try:
                            _cb()
                        except Exception:
                            pass

                    threading.Thread(
                        target=_fire, daemon=True, name="comfymodal-late-unet-release"
                    ).start()
                    return restore_lane
                if restore_lane.finished_mono_ns != 0 and release_callback is not None:
                    with _RELEASE_LOCK:
                        if not restore_lane.unet_release_sent:
                            restore_lane.unet_release_sent = True
                            restore_lane.release_callback = None
                            _cb2 = release_callback

                            def _fire2() -> None:
                                try:
                                    _cb2()
                                except Exception:
                                    pass

                            threading.Thread(
                                target=_fire2,
                                daemon=True,
                                name="comfymodal-late-unet-release",
                            ).start()
                return restore_lane
        elif restore_lane is not None:
            # A non-restore lane under the reserved key: drop it (should not
            # happen; fail closed).
            for loader, fb in restore_lane.owners:
                try:
                    loader.close()
                except Exception:
                    pass
            restore_lane.owners = []
            restore_lane.per_file_sds = []
            _signal_unet_release(restore_lane)
    # No lane (or dropped): start a fresh request-time lane via the E25/E26
    # entry point (which handles all the gates + telemetry).
    return _start_speculative_clip_lane(
        request_id=request_id,
        model_key=model_key,
        model_spec=model_spec,
        workflow_hash=workflow_hash,
        deployment_hash=deployment_hash,
        custom_node_generation=custom_node_generation,
        trace=trace,
        clip=clip,
        cpu_models=cpu_models,
        release_callback=release_callback,
    )
