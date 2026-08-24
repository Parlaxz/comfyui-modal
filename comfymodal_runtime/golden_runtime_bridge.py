"""R42 Golden runtime bridge — the ONLY integration seam between the
production runtime (comfyapp / modal_app / model_preload /
clip_forward_forensics) and the final Golden QD4 pipeline
(``comfymodal_runtime.golden``).

Design rules (Lane C):

- NARROW INTEGRATION: all Golden orchestration logic lives here.  The app
  files only call ``GoldenRunContext`` methods; they never touch the golden
  package directly.
- FAIL-CLOSED EVERYWHERE: any Golden failure degrades the run (a canonical
  reason string is accumulated) but NEVER crashes the request.  A fallback
  can never be classified nominal.
- NO SLEEPS FOR SCHEDULING: cross-thread coordination uses ``threading.Event``
  bounded waits only.
- NO ENV READS: enablement comes exclusively from the config authority
  (``COMFYMODAL_GOLDEN_PIPELINE`` resolved by ``config_authority.resolve``);
  this module reads no environment variables.
- WINDOWS-SAFE IMPORTS: torch is imported lazily inside functions.

Thread model: one ``GoldenRunContext`` per run, published via module-level
``set_current``/``current``/``clear_current`` (thread-safe, keyed per run).
Producer threads spawned here are daemon threads with bounded event waits so
they can never outlive the request meaningfully.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import threading
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .golden.contracts import (
    DEFAULT_BLOCK_BYTES,
    DestinationKind,
    DestinationPlan,
    DegradedReason,
    ForbiddenOverlapError,
    GoldenError,
    JoinDecision,
    ModelRole,
    OwnershipState,
    QDRangePlan,
    RoleManifest,
)
from .golden.model_owner import GoldenModelOwner
from .golden.pipeline import GoldenPipeline, RoleBinding
from .golden.qd_engine import (
    GoldenQD4Loader,
    QD4EngineConfig,
    parse_safetensors_header,
)
from .golden.resource_scheduler import GoldenResourceScheduler

__all__ = [
    "LedgerBridgeSink",
    "GoldenRunContext",
    "set_current",
    "current",
    "clear_current",
    "enabled_current",
]

# R42: bounded wait for a role source path to be published (event-driven;
# the worker sleeps on a threading.Event, never a scheduling sleep loop).
_UNET_SOURCE_WAIT_S = 10.0

# safetensors dtype string -> torch dtype (resolved lazily; torch import is
# deferred so importing this module stays cheap and Windows-safe).
_SAFETENSORS_DTYPES: Dict[str, str] = {
    "F64": "float64",
    "F32": "float32",
    "F16": "float16",
    "BF16": "bfloat16",
    "I64": "int64",
    "I32": "int32",
    "I16": "int16",
    "I8": "int8",
    "U8": "uint8",
    "BOOL": "bool",
}


def _torch_dtype(dtype_name: str) -> Any:
    import torch  # local import: heavy dependency stays lazy

    attr = _SAFETENSORS_DTYPES.get(str(dtype_name).upper())
    if attr is None:
        raise ValueError(f"unsupported safetensors dtype {dtype_name!r}")
    return getattr(torch, attr)


def _jsonable(value: Any, _depth: int = 0) -> Any:
    """Best-effort JSON-safe projection of ledger metadata values."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if _depth >= 3:
        return str(value)[:200]
    if hasattr(value, "value") and hasattr(type(value), "__members__"):
        return str(getattr(value, "value"))
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v, _depth + 1) for k, v in list(value.items())[:32]}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v, _depth + 1) for v in list(value)[:32]]
    # torch tensors and arbitrary objects: honest summary, never contents.
    shape = getattr(value, "shape", None)
    dtype = getattr(value, "dtype", None)
    if shape is not None:
        return f"<tensor shape={tuple(shape)} dtype={dtype}>"
    return str(value)[:200]


class LedgerBridgeSink:
    """Forwards Golden pipeline events into the canonical critical-path ledger.

    - ``emit(event_name, **fields)`` calls
      ``critical_path_ledger.record_event(event_name, mono_ns=..., metadata=...)``
      and NEVER raises (errors are swallowed and counted).
    - Keeps an in-memory ``(name, fields)`` list for tests/diagnostics.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.events: List[Tuple[str, Dict[str, Any]]] = []
        self.error_count = 0

    def emit(self, event_name: str, **fields: Any) -> None:
        name = str(event_name)
        payload = {str(k): _jsonable(v) for k, v in fields.items()}
        try:
            from . import critical_path_ledger as _cpl

            _cpl.record_event(name, mono_ns=time.monotonic_ns(), metadata=payload)
        except Exception:
            with self._lock:
                self.error_count += 1
        finally:
            with self._lock:
                self.events.append((name, dict(payload)))

    def names(self) -> List[str]:
        with self._lock:
            return [name for name, _ in self.events]


def _proc_io_snapshot() -> Dict[str, Any]:
    """Best-effort /proc/self/io snapshot (Linux only; UNOBSERVABLE elsewhere).

    Returns ``{"observable": bool, "rchar": int|None, "read_bytes": int|None}``.
    ``read_bytes`` counts PHYSICAL storage reads for the whole process;
    ``rchar`` counts logical reads (includes page cache hits).
    """
    out: Dict[str, Any] = {"observable": False, "rchar": None, "read_bytes": None}
    try:
        with open("/proc/self/io", "rb") as fh:
            data = fh.read().decode("utf-8", "replace")
        for line in data.splitlines():
            if line.startswith("rchar:"):
                out["rchar"] = int(line.split(":", 1)[1].strip())
            elif line.startswith("read_bytes:"):
                out["read_bytes"] = int(line.split(":", 1)[1].strip())
        out["observable"] = out["read_bytes"] is not None
    except Exception:
        pass
    return out


class GoldenRunContext:
    """Per-run Golden pipeline context owned by the bridge.

    Builds the scheduler + pipeline eagerly (pure stdlib behind the golden
    package) and DEFERS loader construction until a device is known
    (:meth:`get_loader`).  Every public method is fail-closed: exceptions are
    converted into degradation reason strings, never propagated to callers.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        join_timeout_s: float = 120.0,
        block_bytes: int = DEFAULT_BLOCK_BYTES,
    ) -> None:
        self.enabled = bool(enabled)
        self.join_timeout_s = float(join_timeout_s)
        self.block_bytes = int(block_bytes)
        self.ledger_sink = LedgerBridgeSink()
        self.scheduler = GoldenResourceScheduler(ledger_sink=self.ledger_sink)
        self.pipeline = GoldenPipeline(
            self.scheduler, ledger_sink=self.ledger_sink, join_timeout_s=self.join_timeout_s
        )
        self.degradations: List[str] = []
        self.role_paths: Dict[str, str] = {}
        self.role_results: Dict[str, Any] = {}
        self.telemetry: Dict[str, Any] = {"empty_cache_policy": []}
        self._lock = threading.RLock()
        self._loader: Optional[GoldenQD4Loader] = None
        self._manifest_cache: Dict[str, RoleManifest] = {}
        self._restore_ready_done = False
        self._clip_loaded = False
        self._clip_forward_started = False
        self._clip_forward_ended = False
        self._sampling_started_done = False
        self._first_step_done = False
        self._unet_commit_gate = threading.Event()
        self._unet_committed = threading.Event()
        # R42: set when the UNET worker reaches a terminal state (committed,
        # failed, or gave up) so lifecycle hooks can wait bounded instead of
        # guessing whether the commit is still pending.
        self._unet_settled = threading.Event()
        self._unet_owner: Any = None
        # R42: per-role source-publication events.  note_role_source sets the
        # role's event; background workers wait on it (bounded) instead of
        # exiting permanently when the source path lands slightly later.
        self._source_published: Dict[str, threading.Event] = {
            role: threading.Event() for role in ("clip", "unet", "vae")
        }
        self._vae_committed = threading.Event()
        self._vae_owner: Any = None
        self._vae_producer_started = threading.Event()
        self._vae_descriptor_ready = threading.Event()
        self._role_lifecycle: Dict[str, Dict[str, Any]] = {
            role: {"state": "NOT_STARTED", "fallback": False, "fallback_reason": ""}
            for role in ("clip", "unet", "vae")
        }
        # R42: roles whose fallback was REAL (terminal native fallback); their
        # canonical degradation survives clear_role_fallback_degradations.
        self._real_fallback_roles: set = set()
        # R42A: measured (not asserted) native-I/O window between UNET
        # DEVICE_READY and SAMPLING_START.
        self._native_io_window: Optional[Dict[str, Any]] = None
        self.native_io_counters: Dict[str, int] = {
            "native_load_torch_file_calls": 0,
            "native_load_torch_file_bytes": 0,
        }
        # R42A: post-bind storage identity proof state.
        self._unet_bound_ptr_map: Optional[Dict[str, tuple]] = None
        self._unet_bound_model_ref: Any = None
        self._empty_cache_memo: Dict[str, Dict[str, Any]] = {}

    # -- enablement ---------------------------------------------------------

    @property
    def active(self) -> bool:
        return bool(self.enabled)

    # -- loader construction (deferred; needs torch device) ------------------

    def get_loader(self, device: Optional[str] = None) -> GoldenQD4Loader:
        with self._lock:
            if self._loader is not None:
                return self._loader
            backend = None
            if str(device or "").startswith("cuda"):
                try:
                    from .golden.qd_engine import CudaTransferBackend

                    backend = CudaTransferBackend(device or "cuda:0")
                except Exception:
                    backend = None
            if backend is None:
                from .golden.qd_engine import CpuCopyBackend

                backend = CpuCopyBackend()
            self._loader = GoldenQD4Loader(QD4EngineConfig(), backend=backend)
            return self._loader

    # -- manifests / bindings -------------------------------------------------

    def note_role_source(self, role: str, path: str) -> None:
        """Record the safetensors source path for a semantic role."""
        if not self.enabled:
            return
        r = str(role or "").strip().lower()
        if r in ("clip", "unet", "vae") and path:
            with self._lock:
                self.role_paths.setdefault(r, str(path))
                # R42: publish availability so waiting workers wake up.
                self._source_published[r].set()

    def build_manifest(self, path: str, role: ModelRole) -> RoleManifest:
        source_path = os.path.realpath(str(path))
        t0 = time.perf_counter_ns()
        try:
            stat = os.stat(source_path)
            source_size = int(stat.st_size)
            source_mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9)))
        except OSError as exc:
            raise GoldenError(f"manifest source stat failed: {source_path}: {exc}") from exc
        with self._lock:
            cached = self._manifest_cache.get(source_path)
        if cached is not None:
            extra = dict(getattr(cached, "extra", {}) or {})
            if (
                int(extra.get("source_size_bytes", -1)) == source_size
                and int(extra.get("source_mtime_ns", -1)) == source_mtime_ns
            ):
                self.ledger_sink.emit("manifest_lookup_start", role=role.value, source="cache")
                self.ledger_sink.emit(
                    "manifest_lookup_end",
                    role=role.value,
                    source="cache",
                    validate_wall_ms=round((time.perf_counter_ns() - t0) / 1e6, 3),
                    full_sha=False,
                )
                return cached

        # Request-tier manifest construction reads only the safetensors header.
        # The previous implementation hashed every source byte here; on the
        # 12.3 GB UNET that put a multi-second read before method entry and was
        # neither a cheap validation nor a static snapshot operation.
        layout = parse_safetensors_header(source_path)
        plan = QDRangePlan.build(layout, self.block_bytes, buffer_mode="per_tensor")
        layout_payload = {
            "header_bytes": layout.header_bytes,
            "data_start": layout.data_start,
            "file_bytes": layout.file_bytes,
            "tensors": [
                {
                    "name": entry.name,
                    "dtype": entry.dtype,
                    "shape": list(entry.shape),
                    "abs_start": entry.abs_start,
                    "abs_end": entry.abs_end,
                }
                for entry in layout.tensor_map
            ],
        }
        header_fingerprint = hashlib.sha256(
            json.dumps(layout_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        identity_material = {
            "role": role.value,
            "path": source_path,
            "size": source_size,
            "mtime_ns": source_mtime_ns,
            "header_fingerprint": header_fingerprint,
            "block_bytes": self.block_bytes,
        }
        file_sha = hashlib.sha256(
            json.dumps(identity_material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        manifest = RoleManifest(
            role=role,
            model_path=source_path,
            file_sha256=file_sha,
            layout=layout,
            identity_hash=file_sha[:32],
            destination_kind=DestinationKind.PARAMETER_COPY_TARGET,
            qd_range_plan=plan,
            extra={
                "identity_kind": "stat_header_snapshot",
                "source_size_bytes": source_size,
                "source_mtime_ns": source_mtime_ns,
                "header_fingerprint": header_fingerprint,
                "range_plan_fingerprint": hashlib.sha256(
                    json.dumps(
                        {
                            "block_bytes": plan.block_bytes,
                            "data_start": plan.data_start,
                            "data_end": plan.data_end,
                            "blocks": [
                                [block.index, block.file_start, block.file_end]
                                for block in plan.blocks
                            ],
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
            },
        )
        with self._lock:
            self._manifest_cache[source_path] = manifest
            self.telemetry.setdefault("static_manifests", {})[role.value] = {
                "path": source_path,
                "identity_hash": manifest.identity_hash,
                "identity_kind": "stat_header_snapshot",
                "source_size_bytes": source_size,
                "source_mtime_ns": source_mtime_ns,
                "header_fingerprint": header_fingerprint,
                "range_plan_blocks": plan.n_blocks,
                "range_plan_block_bytes": plan.block_bytes,
            }
        self.ledger_sink.emit(
            "manifest_lookup_start", role=role.value, source="runtime_header_stat"
        )
        self.ledger_sink.emit(
            "manifest_lookup_end",
            role=role.value,
            source="runtime_header_stat",
            wall_ms=round((time.perf_counter_ns() - t0) / 1e6, 3),
            full_sha=False,
            header_fingerprint=header_fingerprint[:16],
            blocks=plan.n_blocks,
        )
        return manifest

    def _manifest_for(self, role_value: str) -> Optional[RoleManifest]:
        """Manifest cache lookup normalized on realpath (matches build_manifest keys)."""
        path = self.role_paths.get(role_value)
        if not path:
            return None
        with self._lock:
            return self._manifest_cache.get(os.path.realpath(str(path)))

    def _role_binding(self, role_value: str) -> Optional[RoleBinding]:
        path = self.role_paths.get(role_value)
        if not path:
            return None
        role = ModelRole(role_value)
        manifest = self.build_manifest(path, role)

        def _destination() -> DestinationPlan:
            import torch  # local import

            # UNET commits straight onto the inference device when one exists;
            # CLIP/VAE stay on CPU (their consumers bind CPU views).
            device = "cpu"
            if role_value == "unet" and torch.cuda.is_available():
                device = "cuda"
            buffers = []
            sizes = []
            for entry in sorted(manifest.layout.tensor_map, key=lambda t: t.abs_start):
                nbytes = entry.abs_end - entry.abs_start
                buffers.append(torch.empty(nbytes, dtype=torch.uint8, device=device))
                sizes.append(nbytes)
            return DestinationPlan(
                kind=DestinationKind.PARAMETER_COPY_TARGET,
                buffers=buffers,
                buffer_bytes=sizes,
            )

        return RoleBinding(role=role, manifest=manifest, destination_factory=_destination)

    # -- lifecycle hooks -------------------------------------------------------

    def on_restore_ready(self) -> None:
        """PHASE1 -> PHASE2: minimal restore complete, CLIP QD load legal."""
        if not self.enabled or self._restore_ready_done:
            return
        with self._lock:
            if self._restore_ready_done:
                return
            self._restore_ready_done = True
        try:
            self.pipeline.begin_restore()
            self.pipeline.restore_ready()
        except Exception as exc:  # noqa: BLE001 - fail-closed boundary
            self.add_degradation("golden_restore_ready_error")
            self.ledger_sink.emit("golden_hook_error", hook="restore_ready", error=str(exc)[:200])

    def on_clip_forward_start(self) -> None:
        """PHASE3 entry: CLIP forward begins; UNET prepare overlaps it."""
        if not self.enabled or self._clip_forward_started:
            return
        with self._lock:
            if self._clip_forward_started:
                return
            self._clip_forward_started = True
        try:
            self.pipeline.begin_clip_forward()
            self.pipeline.clip_storage_release_proof()
        except Exception as exc:  # noqa: BLE001
            self.add_degradation("golden_clip_forward_start_error")
            self.ledger_sink.emit("golden_hook_error", hook="clip_forward_start", error=str(exc)[:200])
            return
        thread = threading.Thread(target=self._unet_worker, name="golden-unet-worker", daemon=True)
        thread.start()

    def _unet_worker(self) -> None:
        """Terminal-state wrapper: ALWAYS publishes ``_unet_settled``.

        R42 lifecycle contract: ``on_first_sampler_step`` must know whether
        the UNET commit reached UNET_DEVICE_READY (SAMPLING is only legally
        enterable after it).  Every exit path of the body — success, failure,
        gate timeout, or source-publication timeout — funnels through here.
        """
        try:
            self._unet_worker_body()
        finally:
            self._unet_settled.set()

    def _unet_worker_body(self) -> None:
        """Background PHASE3 prepare + (after forward end) PHASE4 commit."""
        binding: Optional[RoleBinding] = None
        loader: Optional[GoldenQD4Loader] = None
        owner: Optional[GoldenModelOwner] = None
        try:
            # R42 SOURCE RACE FIX: this worker starts at CLIP forward start,
            # but model_preload's graph-loader demand point publishes
            # note_role_source("unet", path) slightly LATER.  Previously the
            # worker exited permanently with unet_manifest_unavailable and
            # nothing could restart it.  Wait (bounded, event-driven) for the
            # publication instead; a genuine absence still degrades after the
            # bounded window.
            if not self._source_published["unet"].wait(timeout=_UNET_SOURCE_WAIT_S):
                self.add_degradation("unet_manifest_unavailable")
                self.ledger_sink.emit(
                    "golden_unet_source_wait_timeout",
                    timeout_s=_UNET_SOURCE_WAIT_S,
                    hook="unet_prepare",
                )
                return
            binding = self._role_binding("unet")
            if binding is None:
                self.add_degradation("unet_manifest_unavailable")
                return
            # Register BEFORE prepare/commit I/O so demand sides can JOIN.
            owner = GoldenModelOwner(ModelRole.UNET, binding.manifest.identity_hash)
            self.pipeline.registry.register(owner)
            loader = self.get_loader()
            self.pipeline.unet_prepare(binding, loader)
        except Exception as exc:  # noqa: BLE001
            self._fail_owner(owner, exc)
            self.record_real_fallback("unet", f"prepare_failure:{type(exc).__name__}")
            self.ledger_sink.emit("golden_hook_error", hook="unet_prepare", error=str(exc)[:200])
            return
        # Bounded wait for the CLIP-forward-end proof (GPU commit becomes
        # legal only after clip_gpu_critical_done).  Daemon thread: a missed
        # proof must not leak the worker forever.
        if not self._unet_commit_gate.wait(timeout=max(1.0, self.join_timeout_s)):
            self._fail_owner(owner, GoldenError("unet_commit_gate_timeout"))
            self.add_degradation("golden_unet_commit_gate_timeout")
            return
        try:
            result, owner = self.pipeline.run_unet_commit(loader, binding, owner=owner)
            with self._lock:
                self._unet_owner = owner
                self.role_results[ModelRole.UNET.value] = result
            self._unet_committed.set()
            # R42A: open the measured native-I/O window at UNET DEVICE_READY.
            self.begin_native_io_window()
        except Exception as exc:  # noqa: BLE001
            self._fail_owner(owner, exc)
            self.record_real_fallback("unet", f"commit_failure:{type(exc).__name__}")
            self.ledger_sink.emit("golden_hook_error", hook="unet_commit", error=str(exc)[:200])

    @staticmethod
    def _fail_owner(owner: Optional[GoldenModelOwner], exc: Exception) -> None:
        """Best-effort FAILED publication; never raises, never double-publishes."""
        if owner is None:
            return
        try:
            if owner.state == OwnershipState.PREPARING:
                owner.publish_failure(exc)
        except Exception:
            pass

    def on_clip_forward_end(self) -> None:
        """PHASE3 exit: CLIP GPU-critical done; UNET commit now legal."""
        if not self.enabled or self._clip_forward_ended:
            return
        with self._lock:
            if self._clip_forward_ended:
                return
            self._clip_forward_ended = True
        try:
            self.pipeline.clip_forward_complete()
            self.pipeline.clip_gpu_critical_done()
        except Exception as exc:  # noqa: BLE001
            self.add_degradation("golden_clip_forward_end_error")
            self.ledger_sink.emit("golden_hook_error", hook="clip_forward_end", error=str(exc)[:200])
            return
        self._unet_commit_gate.set()

    def on_first_sampler_step(self) -> None:
        """First sampler step proven: arm + start the VAE QD demand load."""
        if not self.enabled or self._first_step_done:
            return
        with self._lock:
            if self._first_step_done:
                return
            self._first_step_done = True
        # R42 lifecycle ordering: SAMPLING_STARTED / FIRST_SAMPLER_STEP_PROVEN
        # are only legal once UNET commit reached UNET_DEVICE_READY (phase 5).
        # Wait bounded for the worker to settle; a failed or timed-out commit
        # degrades fail-closed instead of raising illegal transitions.
        if not self._unet_settled.is_set():
            self._unet_settled.wait(timeout=min(_UNET_SOURCE_WAIT_S, max(1.0, self.join_timeout_s)))
        if not self._unet_committed.is_set():
            self.add_degradation("golden_unet_commit_not_ready")
            self.ledger_sink.emit(
                "golden_hook_error",
                hook="first_sampler_step",
                error="unet_commit_not_ready_before_first_sampler_step",
            )
            # R42A: close the measurement window even on this failure path.
            self.end_native_io_window("first_sampler_step_commit_not_ready")
            return
        # R42A: close the measured native-I/O window at sampling start
        # (idempotent; primary close is the sampling_start seam).
        self.end_native_io_window("first_sampler_step")
        try:
            if not self._sampling_started_done:
                self.pipeline.sampling_started()
                self._sampling_started_done = True
            self.pipeline.first_sampler_step_proven()
        except Exception as exc:  # noqa: BLE001
            self.add_degradation("golden_qd_fallback:vae")
            self.ledger_sink.emit("golden_hook_error", hook="first_sampler_step", error=str(exc)[:200])
            return
        thread = threading.Thread(target=self._vae_worker, name="golden-vae-worker", daemon=True)
        thread.start()
        self.ledger_sink.emit("vae_schedule_state", state="first_sampler_step_proven")

    def _vae_worker(self) -> None:
        if self._vae_producer_started.is_set():
            return
        self._vae_producer_started.set()
        existing = self.pipeline.registry.get(ModelRole.VAE)
        if existing is not None and existing.state in (
            OwnershipState.DEVICE_READY,
            OwnershipState.BIND_READY,
            OwnershipState.PUBLISHED,
        ):
            # A demand path may have completed before the lifecycle hook.  It
            # is already the one producer; the hook only publishes readiness.
            self._vae_committed.set()
            return
        try:
            binding = self._role_binding("vae")
            if binding is None:
                self.record_real_fallback("vae", "manifest_unavailable")
                return
            loader = self.get_loader()
            owner = existing
            if owner is None or owner.state in (OwnershipState.RELEASED, OwnershipState.FAILED):
                owner = GoldenModelOwner(ModelRole.VAE, binding.manifest.identity_hash)
            result, owner = self.pipeline.run_role_load(
                ModelRole.VAE, loader, binding, owner=owner
            )
            with self._lock:
                self._vae_owner = owner
                self.role_results[ModelRole.VAE.value] = result
            self._vae_committed.set()
            self.ledger_sink.emit("vae_schedule_state", state="device_ready")
            self._set_role_state("vae", "READY")
        except Exception as exc:  # noqa: BLE001
            self.record_real_fallback("vae", f"producer_failure:{type(exc).__name__}")
            self.ledger_sink.emit("golden_hook_error", hook="vae_qd", error=str(exc)[:200])

    # -- adoption helpers --------------------------------------------------------

    def adopt_unet(self, timeout_s: Optional[float] = None) -> Tuple[JoinDecision, Any]:
        """M-02 demand side: join-or-adopt the Golden UNET owner."""
        timeout = max(0.0, float(timeout_s)) if timeout_s is not None else min(5.0, self.join_timeout_s)
        decision, owner = self.pipeline.registry.join_or_adopt(ModelRole.UNET, timeout)
        if decision == JoinDecision.TIMEOUT:
            self.add_degradation(f"golden_owner_join_timeout:{ModelRole.UNET.value}")
        elif decision == JoinDecision.FAILED:
            self.add_degradation(f"golden_qd_fallback:{ModelRole.UNET.value}")
        elif decision == JoinDecision.ADOPTED:
            self.add_degradation(f"golden_qd_fallback:{ModelRole.UNET.value}")
        return decision, owner

    def join_vae(self, timeout_s: Optional[float] = None) -> Tuple[JoinDecision, Any]:
        """M-03 demand side: join-or-adopt the Golden VAE owner at decode."""
        timeout = max(0.0, float(timeout_s)) if timeout_s is not None else min(30.0, self.join_timeout_s)
        decision, owner = self.pipeline.registry.join_or_adopt(ModelRole.VAE, timeout)
        if decision == JoinDecision.TIMEOUT:
            self.add_degradation(f"golden_owner_join_timeout:{ModelRole.VAE.value}")
        elif decision == JoinDecision.FAILED:
            self.add_degradation(f"golden_qd_fallback:{ModelRole.VAE.value}")
        elif decision == JoinDecision.ADOPTED:
            self.add_degradation(f"golden_qd_fallback:{ModelRole.VAE.value}")
        return decision, owner

    # -- M-02/M-03 payload consumption (materialize + validate + bind) --------

    def _committed_payload_state(self, role_value: str, committed: threading.Event,
                                 owner_holder_attr: str, timeout_s: float) -> Optional[Dict[str, Any]]:
        """Wait for a committed Golden owner and materialize its state dict.

        The owner payload is the committed PARAMETER_COPY_TARGET
        DestinationPlan published by the pipeline; materialization is
        zero-copy dtype views over those buffers.
        """
        if not committed.wait(timeout=max(0.0, float(timeout_s))):
            return None
        with self._lock:
            owner = getattr(self, owner_holder_attr)
            manifest = self._manifest_for(role_value)
        if owner is None or manifest is None:
            return None
        payload = getattr(owner, "payload", None)
        if payload is None:
            return None
        try:
            return materialize_state_dict(payload, manifest.layout)
        except Exception:
            return None

    def unet_payload(self, timeout_s: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """M-02: materialized Golden UNET state dict once DEVICE_READY."""
        timeout = max(0.0, float(timeout_s)) if timeout_s is not None else self.join_timeout_s
        sd = self._committed_payload_state("unet", self._unet_committed, "_unet_owner", timeout)
        if sd is None and not self._unet_committed.is_set():
            self.add_degradation(f"golden_owner_join_timeout:{ModelRole.UNET.value}")
        return sd

    def vae_payload(self, timeout_s: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """M-03: materialized Golden VAE state dict once DEVICE_READY."""
        timeout = max(0.0, float(timeout_s)) if timeout_s is not None else min(30.0, self.join_timeout_s)
        sd = self._committed_payload_state("vae", self._vae_committed, "_vae_owner", timeout)
        if sd is None and not self._vae_committed.is_set():
            self.add_degradation(f"golden_owner_join_timeout:{ModelRole.VAE.value}")
        return sd

    @staticmethod
    def validate_adoption(
        golden_sd: Dict[str, Any], module: Any, *, dtype_cast_ok: bool = False
    ) -> Tuple[bool, Dict[str, Any]]:
        """Exact name/shape/dtype validation of a Golden payload vs a module.

        Checkpoint keys are matched against module parameter/buffer names
        directly first, then after stripping common checkpoint prefixes.
        Strict: any missing/mismatched/unconsumed entry fails nominal.
        With ``dtype_cast_ok``, floating-point dtype differences are
        assignable (cast at bind) instead of hard mismatches.
        """
        prefixes = (
            "model.diffusion_model.", "model.diffusion_",
            "first_stage_model.", "decoder.",
        )
        model_entries: Dict[str, Any] = {}
        for name, tensor in list(module.named_parameters()) + list(module.named_buffers()):
            model_entries[name] = tensor
        stripped: Dict[str, str] = {}
        for key in golden_sd:
            for prefix in prefixes:
                if key.startswith(prefix):
                    stripped[key] = key[len(prefix):]
                    break
        assigned_map: Dict[str, Any] = {}
        consumed: set = set()
        missing: List[str] = []
        mismatched: List[Dict[str, Any]] = []
        cast_count = 0
        for name, tensor in model_entries.items():
            gt = golden_sd.get(name)
            if gt is None:
                alt = next((k for k, v in stripped.items() if v == name), None)
                if alt is not None:
                    gt = golden_sd[alt]
                    consumed.add(alt)
            if gt is None:
                missing.append(name)
                continue
            if tuple(gt.shape) != tuple(tensor.shape):
                mismatched.append({"name": name, "reason": "shape",
                                   "expected": list(tensor.shape), "got": list(gt.shape)})
                continue
            if str(gt.dtype) != str(tensor.dtype):
                def _is_float(dtype: Any) -> bool:
                    s = str(dtype)
                    return s.startswith("torch.float") or "bfloat16" in s

                if dtype_cast_ok and _is_float(gt.dtype) and _is_float(tensor.dtype):
                    assigned_map[name] = gt
                    cast_count += 1
                    continue
                mismatched.append({"name": name, "reason": "dtype",
                                   "expected": str(tensor.dtype), "got": str(gt.dtype)})
                continue
            assigned_map[name] = gt
        unconsumed = [k for k in golden_sd if k not in consumed and k not in assigned_map]
        ok = not missing and not mismatched and not unconsumed
        detail = {
            "ok": ok,
            "assigned_count": len(assigned_map),
            "cast_count": cast_count,
            "missing": missing[:20],
            "mismatched": mismatched[:20],
            "unconsumed": unconsumed[:20],
        }
        return ok, {"detail": detail, "assigned_map": assigned_map}

    @staticmethod
    def bind_state_into_module(assigned_map: Dict[str, Any], module: Any, device: Any = None) -> Dict[str, Any]:
        """Storage-assign Golden tensors into a live module, then one H2D.

        Per-tensor ``param.data = golden_tensor`` is a zero-copy reference
        assignment on CPU — NO second full-model copy.  The single
        unavoidable H2D is the final ``module.to(device)``.
        """
        import torch as _torch  # noqa: F401

        params = dict(module.named_parameters())
        buffers = dict(module.named_buffers())
        assigned = 0
        bytes_assigned = 0
        cast_tensors = 0
        for name, gt in assigned_map.items():
            target = params.get(name)
            if target is None:
                target = buffers.get(name)
            if target is None:
                continue
            if gt.dtype != target.dtype:
                gt = gt.to(target.dtype)
                cast_tensors += 1
            target.data = gt
            assigned += 1
            bytes_assigned += gt.numel() * gt.element_size()
        move_wall_ms = 0.0
        device_str = ""
        if device is not None:
            t0 = time.perf_counter()
            module.to(device)
            move_wall_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            device_str = str(device)
        return {
            "assigned_tensors": assigned,
            "assigned_bytes": bytes_assigned,
            "cast_tensors": cast_tensors,
            "device_move_ms": move_wall_ms,
            "device": device_str,
        }

    def resolve_inference_device(self) -> Any:
        """The device the native path would migrate UNET/VAE to."""
        try:
            import comfy.model_management as _cmm

            fn = getattr(_cmm, "unet_inference_device", None)
            if callable(fn):
                return fn()
            return _cmm.get_torch_device()
        except Exception:
            import torch

            return torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")

    def record_io_uniqueness(self, role: str, **counters: Any) -> None:
        """Per-request model-I/O accounting (not a timing authority)."""
        with self._lock:
            slot = self.telemetry.setdefault("model_io_uniqueness", {}).setdefault(str(role), {})
            slot.update({k: v for k, v in counters.items()})

    def _set_role_state(self, role: str, state: str, **extra: Any) -> None:
        with self._lock:
            slot = self._role_lifecycle.setdefault(
                str(role), {"state": "NOT_STARTED", "fallback": False, "fallback_reason": ""}
            )
            slot.update({"state": str(state), **extra})
            self.telemetry.setdefault("role_lifecycle", {})[str(role)] = dict(slot)

    def record_real_fallback(self, role: str, reason: str) -> None:
        """Record a typed fallback; provisional waits are not hidden as nominal."""
        role_value = str(role)
        fallback_reason = str(reason)
        with self._lock:
            self._real_fallback_roles.add(role_value)
            slot = self._role_lifecycle.setdefault(
                role_value, {"state": "NOT_STARTED", "fallback": False, "fallback_reason": ""}
            )
            slot.update(
                {
                    "state": "FALLBACK",
                    "fallback": True,
                    "fallback_reason": fallback_reason,
                    "native_fallback_executed": True,
                    "terminal_reason": fallback_reason,
                }
            )
            self.telemetry.setdefault("role_lifecycle", {})[role_value] = dict(slot)
        degradation = f"golden_qd_fallback:{role_value}"
        self.add_degradation(degradation)
        self.ledger_sink.emit(
            "golden_real_fallback",
            role=role_value,
            reason=fallback_reason,
            degradation=degradation,
        )

    def clear_role_fallback_degradations(self, role: str) -> None:
        """Remove transient fallback degradations for *role* after the
        Golden path ultimately succeeded.  Without this, bounded-wait or
        retry-path degradation strings (added before the successful attempt)
        permanently poison RuntimeStatus as DEGRADED via
        ``map_degradation_to_reasons`` → ``loader_fallback_{role}``.
        """
        r = str(role).strip()
        with self._lock:
            sticky = r in self._real_fallback_roles
            removable = {
                f"golden_owner_join_timeout:{r}",
                "unet_manifest_unavailable" if r == "unet" else None,
                "vae_manifest_unavailable" if r == "vae" else None,
                "golden_unet_commit_not_ready" if r == "unet" else None,
            }
            if not sticky:
                # A real native fallback stays visible; only provisional
                # strings for this role are cleared.
                removable.add(f"golden_qd_fallback:{r}")
            self.degradations = [d for d in self.degradations if d not in removable]

    # -- R42A structured lifecycle authority --------------------------------

    def terminal_fallback_roles(self) -> List[str]:
        """Roles whose native fallback TERMINALLY executed (sticky truth)."""
        with self._lock:
            return sorted(
                role
                for role, slot in self._role_lifecycle.items()
                if slot.get("native_fallback_executed")
            )

    def role_lifecycle_summary(self) -> Dict[str, Dict[str, Any]]:
        """Per-role lifecycle summary — the SINGLE authority for status.

        Fields: producer_status / bind_status / adoption_status are derived
        from the lifecycle state machine; ``native_fallback_executed`` and
        ``terminal_reason`` carry the sticky terminal truth.
        """
        with self._lock:
            out: Dict[str, Dict[str, Any]] = {}
            for role in ("clip", "unet", "vae"):
                slot = dict(self._role_lifecycle.get(role, {}))
                state = str(slot.get("state", "NOT_STARTED"))
                out[role] = {
                    "producer_status": (
                        "committed" if state in ("DEVICE_READY", "BIND_READY", "PUBLISHED", "ADOPTED") else state
                    ),
                    "bind_status": (
                        "bound" if state in ("BIND_READY", "PUBLISHED", "ADOPTED") else state
                    ),
                    "adoption_status": state,
                    "native_fallback_executed": bool(slot.get("native_fallback_executed")),
                    "terminal_reason": str(slot.get("terminal_reason", "")),
                }
            return out

    def enforce_loader_selection_consistency(self) -> List[str]:
        """Force loader_selection to agree with terminal bridge truth.

        For every terminal-fallback role without a recorded fallback, record
        the native recovery arm.  Returns the reconciled role list.
        """
        reconciled: List[str] = []
        try:
            from . import loader_selection as _ls

            for role in self.terminal_fallback_roles():
                snap = _ls.snapshot().get(role)
                if not isinstance(snap, dict) or not snap.get("fallback_attempted"):
                    _ls.record_observed(
                        role,
                        "native_comfy",
                        fallback_attempted=True,
                        fallback_loader="native_comfy",
                        fallback_reason=f"terminal_bridge_fallback:{self._role_lifecycle.get(role, {}).get('terminal_reason', '')}"[:300],
                    )
                    reconciled.append(role)
        except Exception:
            pass
        return reconciled

    # -- R42A measured native-I/O window (DEVICE_READY -> SAMPLING_START) ---

    def count_native_source_read(self, path: str) -> None:
        """Count one REAL native checkpoint source read (logical seam)."""
        try:
            nbytes = 0
            try:
                nbytes = int(os.path.getsize(str(path)))
            except Exception:
                nbytes = 0
            with self._lock:
                self.native_io_counters["native_load_torch_file_calls"] += 1
                self.native_io_counters["native_load_torch_file_bytes"] += max(0, nbytes)
        except Exception:
            pass

    def begin_native_io_window(self) -> None:
        """Open the post-UNET-ready measurement window (idempotent)."""
        if not self.enabled:
            return
        with self._lock:
            if self._native_io_window is not None:
                return
        snap_io = _proc_io_snapshot()
        cuda_alloc_bytes = None
        try:
            import torch

            if torch.cuda.is_available():
                cuda_alloc_bytes = int(torch.cuda.memory_stats().get("allocated_bytes.all.current", 0))
        except Exception:
            cuda_alloc_bytes = None
        with self._lock:
            self._native_io_window = {
                "opened_at_mono_ns": time.monotonic_ns(),
                "proc_io": snap_io,
                "cuda_allocated_bytes": cuda_alloc_bytes,
                "counters": dict(self.native_io_counters),
            }
        self.ledger_sink.emit(
            "native_post_ready_window_open",
            proc_io_observable=bool(snap_io.get("observable")),
            read_bytes=snap_io.get("read_bytes"),
            rchar=snap_io.get("rchar"),
        )

    def end_native_io_window(self, reason: str) -> None:
        """Close the window and emit MEASURED deltas (idempotent)."""
        with self._lock:
            window = self._native_io_window
            self._native_io_window = None
        if window is None:
            return
        close_io = _proc_io_snapshot()
        counters_close = dict(self.native_io_counters)
        counters_open = dict(window.get("counters", {}))
        cuda_close = None
        try:
            import torch

            if torch.cuda.is_available():
                cuda_close = int(torch.cuda.memory_stats().get("allocated_bytes.all.current", 0))
        except Exception:
            cuda_close = None
        read_bytes_delta = None
        rchar_delta = None
        physical_observable = bool(close_io.get("observable") and window.get("proc_io", {}).get("observable"))
        if physical_observable:
            try:
                rb_o = window["proc_io"].get("read_bytes")
                rb_c = close_io.get("read_bytes")
                rc_o = window["proc_io"].get("rchar")
                rc_c = close_io.get("rchar")
                if rb_o is not None and rb_c is not None:
                    read_bytes_delta = max(0, int(rb_c) - int(rb_o))
                if rc_o is not None and rc_c is not None:
                    rchar_delta = max(0, int(rc_c) - int(rc_o))
            except Exception:
                pass
        identity = {"checked": 0, "changed": 0}
        try:
            model = self._unet_bound_model_ref
            ptr_map = self._unet_bound_ptr_map or {}
            if model is not None and ptr_map:
                named = dict(model.named_parameters())
                named.update(dict(model.named_buffers()))
                for name, old in ptr_map.items():
                    tensor = named.get(name)
                    identity["checked"] += 1
                    if tensor is None or (int(tensor.data_ptr()), str(tensor.device), str(tensor.dtype)) != old:
                        identity["changed"] += 1
        except Exception:
            identity = {"checked": 0, "changed": 0}
        report = {
            "window_reason": str(reason),
            "physical_storage_read_bytes": read_bytes_delta if physical_observable else "UNOBSERVABLE",
            "logical_read_bytes_proc": rchar_delta if physical_observable else "UNOBSERVABLE",
            "native_load_torch_file_calls": counters_close.get("native_load_torch_file_calls", 0)
            - counters_open.get("native_load_torch_file_calls", 0),
            "native_load_torch_file_bytes": counters_close.get("native_load_torch_file_bytes", 0)
            - counters_open.get("native_load_torch_file_bytes", 0),
            "cuda_allocated_bytes_delta": (
                (cuda_close - window.get("cuda_allocated_bytes"))
                if (cuda_close is not None and window.get("cuda_allocated_bytes") is not None)
                else None
            ),
            "param_identity_checked": identity["checked"],
            "param_identity_changed": identity["changed"],
            "wall_ms": round((time.monotonic_ns() - int(window.get("opened_at_mono_ns", time.monotonic_ns()))) / 1e6, 3),
        }
        with self._lock:
            self.telemetry["native_post_ready_io"] = dict(report)
        self.ledger_sink.emit("post_golden_unet_ready_native_io", **report)

    def ensure_vae_load_started(self) -> bool:
        """Arm/start the Golden VAE QD load if not yet committed.

        Used when the VAE source path only becomes known at decode demand:
        the load still runs EXACTLY ONCE through the Golden engine — never a
        second physical read.
        """
        if not self.enabled or self._vae_committed.is_set():
            return False
        if self._role_binding("vae") is None:
            return False
        if self._vae_producer_started.is_set():
            return False
        threading.Thread(target=self._vae_worker, name="golden-vae-worker-demand", daemon=True).start()
        self.ledger_sink.emit("vae_schedule_state", state="producer_armed_at_demand")
        return True

    def vae_descriptor_load(
        self, path: str
    ) -> Optional[Tuple[Dict[str, Any], Optional[dict]]]:
        """Construct a VAE object descriptor without hydrating Golden values.

        ``nodes.VAELoader`` needs a state-dict-shaped object to construct the
        native VAE graph, but it must not wait for the sampler lifecycle event
        that arms the real Golden producer.  Header-derived, uninitialized CPU
        tensors provide the exact names/shapes/dtypes needed for that
        construction; the real values are joined and rebound at VAEDecode.
        No source value bytes are read here and no fallback/degradation is
        recorded for a deferred state.
        """
        started = time.perf_counter_ns()
        self.note_role_source("vae", str(path))
        binding = self._role_binding("vae")
        if binding is None:
            self.record_real_fallback("vae", "manifest_unavailable")
            return None
        with self._lock:
            owner = self.pipeline.registry.get(ModelRole.VAE)
            if owner is None or owner.state in (OwnershipState.RELEASED, OwnershipState.FAILED):
                owner = GoldenModelOwner(ModelRole.VAE, binding.manifest.identity_hash)
                self.pipeline.registry.register(owner)
            elif owner.identity_hash != binding.manifest.identity_hash:
                self.record_real_fallback("vae", "identity_mismatch")
                return None
            self._vae_owner = owner
            self._role_lifecycle["vae"] = {
                "state": "PREPARING",
                "fallback": False,
                "fallback_reason": "",
                "identity_hash": binding.manifest.identity_hash,
                "identity_kind": "stat_header_snapshot",
            }
        import torch

        skeleton = {
            entry.name: torch.empty(
                tuple(int(dim) for dim in entry.shape),
                dtype=_torch_dtype(entry.dtype),
                device="cpu",
            )
            for entry in binding.manifest.layout.tensor_map
        }
        metadata = self._header_metadata(str(path))
        self._vae_descriptor_ready.set()
        self.ledger_sink.emit(
            "vae_descriptor_ready",
            identity=binding.manifest.identity_hash,
            tensor_count=len(skeleton),
            wall_ms=round((time.perf_counter_ns() - started) / 1e6, 3),
            hydration="deferred_until_first_sampler_step",
        )
        return skeleton, metadata

    def bind_vae_payload(self, vae: Any, timeout_s: float = 30.0) -> bool:
        """Join the one Golden VAE producer and bind its CPU views to *vae*."""
        started = time.perf_counter_ns()
        decision, owner = self.join_vae(timeout_s)
        decision_value = str(getattr(decision, "value", decision))
        if decision_value not in ("already_ready", "joined") or owner is None:
            return False
        payload = self.vae_payload(timeout_s=0.0)
        if not payload:
            self.record_real_fallback("vae", "demand_join_empty_payload")
            return False
        module = getattr(vae, "first_stage_model", None)
        if module is None:
            self.record_real_fallback("vae", "missing_first_stage_model")
            return False
        try:
            ok, detail = self.validate_adoption(payload, module, dtype_cast_ok=True)
            if not ok:
                raise GoldenError(f"vae adoption mismatch detail={detail.get('detail', {})}")
            bound = self.bind_state_into_module(detail["assigned_map"], module)
            if bound["assigned_tensors"] != detail["detail"]["assigned_count"]:
                raise GoldenError(
                    f"vae adoption incomplete assigned={bound['assigned_tensors']} "
                    f"expected={detail['detail']['assigned_count']}"
                )
            self._set_role_state("vae", "ADOPTED")
            try:
                from . import loader_selection as _ls

                _ls.record_observed("vae", "golden_qd4")
            except Exception:
                pass
            self.clear_role_fallback_degradations("vae")
            self.ledger_sink.emit(
                "vae_adoption_complete",
                decision=decision_value,
                identity=getattr(owner, "identity_hash", ""),
                assigned_count=bound["assigned_tensors"],
                cast_count=detail["detail"].get("cast_count", 0),
                wall_ms=round((time.perf_counter_ns() - started) / 1e6, 3),
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self.record_real_fallback("vae", f"adoption_failure:{type(exc).__name__}")
            self.ledger_sink.emit("golden_hook_error", hook="vae_adoption", error=str(exc)[:200])
            return False

    def vae_demand_load(
        self, path: str, timeout_s: float = 10.0
    ) -> Optional[Tuple[Dict[str, Any], Optional[dict]]]:
        """M-03 demand-side VAE load: JOIN a live Golden producer, else INLINE-produce.

        Returns ``(state_dict_views, header_metadata_or_None)`` or ``None``.
        NEVER raises: every failure degrades (``golden_qd_fallback:vae`` or
        ``vae_manifest_unavailable``) so the legacy VAE loader can take over.
        """
        try:
            self.note_role_source("vae", str(path))
            binding = self._role_binding("vae")
            if binding is None:
                self.add_degradation("vae_manifest_unavailable")
                print("[v2.golden_vae] demand=fallback reason=manifest_unavailable", flush=True)
                return None
            manifest = binding.manifest
            header_meta = self._header_metadata(str(path))
            existing = self.pipeline.registry.get(ModelRole.VAE)
            if existing is not None and existing.state != OwnershipState.RELEASED:
                decision, owner = self.pipeline.registry.join_or_adopt(
                    ModelRole.VAE, max(0.0, float(timeout_s))
                )
                if (
                    decision in (JoinDecision.JOINED, JoinDecision.ALREADY_READY)
                    and owner is not None
                    and owner.payload is not None
                ):
                    with self._lock:
                        self._vae_owner = owner
                    self._vae_committed.set()
                    print("[v2.golden_vae] demand=served mode=owner_join", flush=True)
                    try:
                        from . import loader_selection as _ls

                        _ls.record_observed("vae", "golden_qd4")
                        self.clear_role_fallback_degradations("vae")
                    except Exception:
                        pass
                    return materialize_state_dict(owner.payload, manifest.layout), header_meta
                # FAILED / TIMEOUT: degrade; caller falls back to legacy load.
                self.record_real_fallback(
                    "vae", f"owner_{str(getattr(decision, 'value', decision))}"
                )
                print(
                    f"[v2.golden_vae] demand=fallback reason=owner_{str(getattr(decision, 'value', decision))}",
                    flush=True,
                )
                return None
            # No live owner: inline producer on THIS thread.
            # R42 SPIN FIX: the previous fixed 0.01s retry loop spun hot
            # through PHASE2 denials (VAE demand arriving while the CLIP
            # transport still holds the storage/H2D domains).  The scheduler
            # now exposes an event-driven phase gate: block until the VAE QD
            # acquisition is phase-legal, then attempt ONCE; transient
            # matrix/exclusive-domain denials re-block on the phase-change
            # event instead of spinning.  Budget unchanged (~15s).
            attempts = 0
            deadline = time.monotonic() + 15.0
            while True:
                remaining = deadline - time.monotonic()
                if not self.scheduler.wait_for_vae_qd_window(timeout_s=max(0.0, remaining)):
                    self.record_real_fallback("vae", "schedule_denied")
                    self.ledger_sink.emit(
                        "golden_vae_schedule_denied",
                        attempts=attempts,
                        phase=str(getattr(self.scheduler.phase, "value", self.scheduler.phase)),
                        reason="vae_qd_window_timeout",
                    )
                    print(
                        "[v2.golden_vae] demand=fallback reason=schedule_denied "
                        f"attempts={attempts}",
                        flush=True,
                    )
                    return None
                try:
                    result, owner = self.pipeline.run_role_load(ModelRole.VAE, self.get_loader(), binding)
                    break
                except ForbiddenOverlapError:
                    attempts += 1
                    if time.monotonic() >= deadline:
                        self.record_real_fallback("vae", "schedule_denied")
                        self.ledger_sink.emit(
                            "golden_vae_schedule_denied",
                            attempts=attempts,
                            phase=str(getattr(self.scheduler.phase, "value", self.scheduler.phase)),
                            reason="overlap_budget_exhausted",
                        )
                        print(
                            "[v2.golden_vae] demand=fallback reason=schedule_denied "
                            f"attempts={attempts}",
                            flush=True,
                        )
                        return None
                    # Transient conflict (e.g. UNET bulk source holds
                    # STORAGE_HEAVY): event-driven slice wait — phase
                    # transitions wake this immediately.
                    self.scheduler.wait_for_phase_change(timeout_s=0.05)
            with self._lock:
                self._vae_owner = owner
                self.role_results[ModelRole.VAE.value] = result
            self._vae_committed.set()
            payload = owner.payload
            if payload is None:
                self.record_real_fallback("vae", "empty_payload")
                print("[v2.golden_vae] demand=fallback reason=empty_payload", flush=True)
                return None
            print("[v2.golden_vae] demand=served mode=inline_producer", flush=True)
            try:
                from . import loader_selection as _ls

                _ls.record_observed("vae", "golden_qd4")
                self.clear_role_fallback_degradations("vae")
            except Exception:
                pass
            return materialize_state_dict(payload, manifest.layout), header_meta
        except Exception as exc:  # noqa: BLE001 - fail-closed boundary
            self.record_real_fallback("vae", f"exception:{type(exc).__name__}")
            self.ledger_sink.emit("golden_hook_error", hook="vae_demand_load", error=str(exc)[:200])
            print(
                f"[v2.golden_vae] demand=fallback reason=exception:{type(exc).__name__}",
                flush=True,
            )
            return None


    # -- M-01: CLIP restore preload through the Golden engine --------------------

    def clip_golden_load(self, path: str, consumer_shim: Any = None) -> Tuple[Any, Any, Dict[str, Any]]:
        """Load a CLIP safetensors through the Golden QD4 engine.

        Returns EXACTLY the ``(state_dict, metadata_or_None, diagnostics)``
        contract of ``comfyapp._load_restore_clip_state_read_bytes``.  On ANY
        failure the recorded degradation ``golden_qd_fallback:clip`` is added
        and ``consumer_shim(path)`` (the legacy read-bytes loader) runs
        instead; when no shim exists the exception propagates (fail-closed).
        """
        try:
            state_dict, metadata, diag = self._golden_clip_load(path)
            try:
                from . import loader_selection as _ls

                _ls.record_observed("clip", "golden_qd4")
                self.clear_role_fallback_degradations("clip")
            except Exception:
                pass
            return state_dict, metadata, diag
        except Exception as exc:  # noqa: BLE001 - fail-closed boundary
            self.record_real_fallback("clip", f"qd_failure:{type(exc).__name__}: {exc}"[:300])
            self.ledger_sink.emit(
                "golden_hook_error", hook="clip_golden_load", error=f"{type(exc).__name__}: {exc}"[:300]
            )
            if callable(consumer_shim):
                return consumer_shim(path)
            raise

    def _golden_clip_load(self, path: str) -> Tuple[Any, Any, Dict[str, Any]]:
        import torch  # local import

        # R42 (MINIMAL_RESTORE flow): the demand seam reaches this method
        # directly from the load_torch_file branch — seed the role binding
        # here or _role_binding("clip") finds nothing and fails closed.
        self.note_role_source("clip", str(path))
        started = time.perf_counter_ns()
        manifest = self.build_manifest(path, ModelRole.CLIP)
        header_meta = self._header_metadata(path)
        binding = self._role_binding("clip")
        if binding is None:  # defensive: manifest built above guarantees this
            raise GoldenError("clip binding unavailable")
        loader = self.get_loader()
        result, _owner = self.pipeline.run_role_load(ModelRole.CLIP, loader, binding)
        with self._lock:
            self.role_results[ModelRole.CLIP.value] = result
            self._clip_loaded = True
        destination = result.destination
        state_dict = materialize_state_dict(destination, manifest.layout)
        wall_ms = round((time.perf_counter_ns() - started) / 1e6, 3)
        diag: Dict[str, Any] = {
            "read_strategy": "golden_qd4",
            "file_size_bytes": manifest.layout.file_bytes,
            "loader_ms": wall_ms,
            "loader_call_ms": wall_ms,
            "decode_ms": wall_ms,
            "temporary_bytes_peak_estimate": 0,
            "metadata_present": header_meta is not None,
            "file_stat_ms": 0.0,
            "file_open_probe_ms": 0.0,
            "cpu_validation_ms": 0.0,
            "cache_registration_ms": 0.0,
            "tensor_count": len(manifest.layout.tensor_map),
            "nested_container_count": 0,
            "non_cpu_tensor_count": 0,
            "rss_before_mb": -1.0,
            "rss_after_loader_mb": -1.0,
            "rss_after_cache_mb": -1.0,
            "rss_loader_delta_mb": -1.0,
            "rss_cache_delta_mb": -1.0,
            "minor_faults_before": -1,
            "minor_faults_after_loader": -1,
            "minor_faults_after_cache": -1,
            "minor_faults_loader_delta": -1,
            "minor_faults_cache_delta": -1,
            "major_faults_before": -1,
            "major_faults_after_loader": -1,
            "major_faults_after_cache": -1,
            "major_faults_loader_delta": -1,
            "major_faults_cache_delta": -1,
            "explicit_device": "cpu",
            "aggregate_gbps": result.telemetry.aggregate_gbps,
            "fraction_time_at_target_qd": result.telemetry.fraction_time_at_target_qd,
        }
        for tensor in state_dict.values():
            if str(getattr(tensor, "device", "cpu")) != "cpu":
                raise GoldenError("golden CLIP load produced non-CPU tensor")
        return state_dict, header_meta, diag

    @staticmethod
    def _header_metadata(path: str) -> Optional[Dict[str, Any]]:
        with open(path, "rb") as fh:
            header_len = struct.unpack("<Q", fh.read(8))[0]
            header_json = fh.read(header_len)
        header = json.loads(header_json.decode("utf-8"))
        meta = header.get("__metadata__")
        return meta if isinstance(meta, dict) else None

    # -- degradation / status mapping ---------------------------------------------

    def add_degradation(self, reason: str) -> None:
        text = str(reason or "").strip()
        if not text:
            return
        with self._lock:
            if text not in self.degradations:
                self.degradations.append(text)

    @staticmethod
    def status_mapping() -> Dict[DegradedReason, str]:
        """Map Golden ``DegradedReason`` values onto canonical reason strings.

        Every mapped string classifies DEGRADED under
        ``runtime_status.build_runtime_status`` and NONE contains a hard/fatal
        marker, so a fallback can NEVER surface as ACCEPTED_NOMINAL/NOMINAL.
        """
        return {
            DegradedReason.QD_HARD_FAILURE_FALLBACK: "golden_qd_fallback:{role}",
            DegradedReason.OWNER_JOIN_TIMEOUT: "golden_owner_join_timeout:{role}",
            DegradedReason.IMMUTABLE_METADATA_ABSENT: "golden_immutable_metadata_absent:{role}",
            DegradedReason.BIND_VALIDATION_FAILED: "golden_bind_invalid:{role}",
        }

    def canonical_reasons(self) -> List[str]:
        return self.status_reasons()

    def status_reasons(self) -> List[str]:
        with self._lock:
            reasons = list(self.degradations)
            # R42A authority guarantee: a TERMINAL native fallback can never
            # vanish from the canonical reason set, no matter which code path
            # cleared provisional strings afterwards.
            for role in self._real_fallback_roles:
                text = f"golden_qd_fallback:{role}"
                if text not in reasons:
                    reasons.append(text)
            return reasons

    # -- telemetry for the run record ---------------------------------------------

    def telemetry_summary(self) -> Dict[str, Any]:
        occupancy: Dict[str, Any] = {}
        prepared: Dict[str, Any] = {}
        cache_contract: Dict[str, Any] = {}
        for role_key, result in self.role_results.items():
            tel = getattr(result, "telemetry", None)
            occupancy[role_key] = {
                "fraction_time_at_target_qd": getattr(tel, "fraction_time_at_target_qd", None),
                "aggregate_gbps": getattr(tel, "aggregate_gbps", None),
                "source_wall_ms": getattr(tel, "source_wall_ms", None),
                "bytes_read": getattr(tel, "bytes_read", None),
            }
            cache_contract[role_key] = {
                "commit_cache_served": getattr(tel, "commit_cache_served", None),
                "commit_read_storage_bytes": getattr(tel, "commit_read_storage_bytes", None),
            }
        for role, source in self.pipeline.prepared_sources.items():
            prepared[role.value] = {
                "block_count": source.block_count,
                "total_bytes": source.total_bytes,
                "prep_wall_ms": source.prep_wall_ms,
                "prep_aggregate_gbps": source.prep_aggregate_gbps,
                "lifecycle_status": source.lifecycle_status,
            }
        with self._lock:
            policy = list(self.telemetry.get("empty_cache_policy", []))
        return {
            "enabled": self.enabled,
            "occupancy": occupancy,
            "prepared_sources": prepared,
            "cache_contract": cache_contract,
            "empty_cache_policy": policy,
            "degradations": self.canonical_reasons(),
            "unet_committed": self._unet_committed.is_set(),
            "vae_committed": self._vae_committed.is_set(),
        }

    # -- M-06: empty-cache policy transition ---------------------------------------

    def empty_cache_policy_transition(self, stage: str, facts: Mapping[str, Any]) -> Dict[str, Any]:
        """Deterministic empty-cache bypass evaluation for one stage.

        Calls ``empty_cache_bypass.evaluate_bypass`` + ``emit_decision`` and
        records ``{considered, executed, reason, headroom facts, wall_ms}``
        into context telemetry.  Same-state inputs always produce the same
        decision (memoized on the canonical fact key).
        """
        from .empty_cache_bypass import bypass_enabled, evaluate_bypass, emit_decision

        started = time.perf_counter_ns()
        fact_payload = {
            "soft_cache_reason": facts.get("soft_cache_reason"),
            "models_unloaded_count": facts.get("models_unloaded_count"),
            "physical_free_bytes": facts.get("physical_free_bytes"),
            "operation_required_bytes": facts.get("operation_required_bytes"),
            "minimum_required_bytes": facts.get("minimum_required_bytes"),
            "allocator_backend": facts.get("allocator_backend"),
            "capture_active": facts.get("capture_active"),
            "custom_allocator_active": facts.get("custom_allocator_active"),
            "custom_pool_active": facts.get("custom_pool_active"),
        }
        memo_key = json.dumps(
            [fact_payload[k] for k in sorted(fact_payload)], sort_keys=True, default=str
        )
        with self._lock:
            memo = self._empty_cache_memo.get(memo_key)
        if memo is not None:
            decision = dict(memo)
        else:
            try:
                decision = evaluate_bypass(enabled=bypass_enabled(), **fact_payload)
            except Exception as exc:  # noqa: BLE001
                decision = {"decision": "native", "eligible": False, "known": False, "error": str(exc)[:200]}
            with self._lock:
                self._empty_cache_memo[memo_key] = dict(decision)
        record = {
            "stage": str(stage),
            "considered": True,
            "executed": bool(decision.get("eligible") is True),
            "reason": str(decision.get("decision")),
            "headroom_ratio": decision.get("headroom_ratio"),
            "physical_free_bytes": decision.get("physical_free_bytes"),
            "required_bytes": decision.get("required_bytes"),
            "wall_ms": round((time.perf_counter_ns() - started) / 1e6, 3),
        }
        try:
            emit_decision({"stage": str(stage), **decision})
        except Exception:
            pass
        with self._lock:
            self.telemetry.setdefault("empty_cache_policy", []).append(record)
        return record


# ---------------------------------------------------------------------------
# Module-level per-run context registry (thread-safe)
# ---------------------------------------------------------------------------

_CONTEXT_LOCK = threading.Lock()
_CONTEXTS: Dict[str, GoldenRunContext] = {}
_DEFAULT_RUN_KEY = "default"


def set_current(ctx: GoldenRunContext, run_key: str = _DEFAULT_RUN_KEY) -> None:
    with _CONTEXT_LOCK:
        _CONTEXTS[str(run_key)] = ctx


def current(run_key: Optional[str] = None) -> Optional[GoldenRunContext]:
    with _CONTEXT_LOCK:
        key = _DEFAULT_RUN_KEY if run_key is None else str(run_key)
        return _CONTEXTS.get(key)


def clear_current(run_key: Optional[str] = None) -> None:
    with _CONTEXT_LOCK:
        key = _DEFAULT_RUN_KEY if run_key is None else str(run_key)
        _CONTEXTS.pop(key, None)


def enabled_current(run_key: Optional[str] = None) -> Optional[GoldenRunContext]:
    ctx = current(run_key)
    return ctx if ctx is not None and ctx.enabled else None


def ensure_current(resolved: Any = None, run_key: str = _DEFAULT_RUN_KEY) -> Optional[GoldenRunContext]:
    """Return the live enabled context, creating + publishing one when the
    config authority enables the pipeline.  Idempotent per run key.

    The Golden timeline starts at RESTORE_READY (CLIP QD4 is a restore-phase
    transport), so the context must exist BEFORE the request entry — the
    restore preload consults it.  Request-entry callers reuse the same
    context instead of creating a second one.
    """
    existing = current(run_key)
    if existing is not None:
        return existing if existing.enabled else None
    try:
        if not golden_enabled(resolved):
            return None
    except Exception:
        return None
    ctx = GoldenRunContext()
    set_current(ctx, run_key)
    return ctx


def golden_enabled(resolved: Any = None) -> bool:
    """Authority-driven enablement for the per-run Golden envelope."""
    try:
        from . import config_authority as _ca

        rc = resolved if resolved is not None else _ca.resolve()
        return bool(rc.get("COMFYMODAL_GOLDEN_PIPELINE"))
    except Exception:
        return False


def map_degradation_to_reasons(degradations: Any) -> List[str]:
    """M-05: canonical reason strings; fallback ⇒ never nominal."""
    items = degradations if isinstance(degradations, (list, tuple, set)) else [degradations]
    mapped: List[str] = []
    for reason in items:
        text = str(reason)
        if text.startswith("golden_qd_fallback:") or text.startswith("golden_owner_join_timeout:"):
            mapped.append(f"loader_fallback_{text.split(':', 1)[1]}")
        else:
            mapped.append(text)
    return mapped


def build_config_truth_block(resolved: Any, ctx: Optional[GoldenRunContext] = None) -> Dict[str, Any]:
    """Five-layer config truth for the run record (R42 contract)."""
    try:
        from . import config_authority as _ca

        observed: Dict[str, Any] = {}
        if resolved is not None:
            observed["COMFYMODAL_GOLDEN_PIPELINE"] = bool(
                resolved.get("COMFYMODAL_GOLDEN_PIPELINE")
            )
        return _ca.build_config_truth(resolved, observed=observed)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Shared tensor materialization (PARAMETER_COPY_TARGET -> named CPU tensors)
# ---------------------------------------------------------------------------


def materialize_state_dict(destination: DestinationPlan, layout: Any) -> Dict[str, Any]:
    """Build ``{tensor_name: torch.Tensor}`` from a PARAMETER_COPY_TARGET
    destination + SafetensorsLayout using zero-copy dtype views.

    Per-tensor mode assigns destination buffer ``i`` to the i-th tensor in
    file order (sorted by absolute offset) — exactly the inverse of the
    ``per_tensor`` QDRangePlan segment mapping.
    """
    import torch  # local import

    if destination.kind != DestinationKind.PARAMETER_COPY_TARGET:
        raise GoldenError(
            f"materialize_state_dict requires PARAMETER_COPY_TARGET (got {destination.kind.value})"
        )
    out: Dict[str, Any] = {}
    entries = sorted(layout.tensor_map, key=lambda t: t.abs_start)
    for idx, entry in enumerate(entries):
        if idx >= len(destination.buffers):
            raise GoldenError(f"destination buffer missing for tensor {entry.name}")
        nbytes = entry.abs_end - entry.abs_start
        buf = destination.buffers[idx]
        flat = buf[:nbytes]
        dtype = _torch_dtype(entry.dtype)
        itemsize = torch.empty((), dtype=dtype).element_size()
        if nbytes % itemsize != 0:
            raise GoldenError(f"tensor {entry.name}: {nbytes} bytes not divisible by {itemsize}")
        view = flat.view(dtype).reshape(tuple(int(s) for s in entry.shape))
        out[entry.name] = view
    return out
