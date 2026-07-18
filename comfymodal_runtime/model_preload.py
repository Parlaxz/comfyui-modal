"""Measured two-lane UNET/CLIP restore preparation."""

from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from .contracts import ModelRestoreKey, PrefillKey
from .trace import RuntimeTrace


@dataclass
class PreparationDiagnostics:
    unet_started_at: float = 0.0
    unet_completed_at: float = 0.0
    clip_started_at: float = 0.0
    clip_completed_at: float = 0.0
    prefill_started_at: float = 0.0
    prefill_completed_at: float = 0.0
    unet_demanded_at: float = 0.0
    clip_demanded_at: float = 0.0
    prefill_demanded_at: float = 0.0
    unet_wait_ms: float = 0.0
    clip_wait_ms: float = 0.0
    prefill_wait_ms: float = 0.0
    useful_overlap_ms: float = 0.0
    unused_speculation: bool = False
    unet_error: str = ""
    clip_error: str = ""
    prefill_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        for key in ("unet_wait_ms", "clip_wait_ms", "prefill_wait_ms", "useful_overlap_ms"):
            data[key] = round(float(data[key]), 3)
        return data


@dataclass
class RestorePreparation:
    model_key: ModelRestoreKey
    prefill_key: PrefillKey
    unet_future: Future[Any] | None = None
    clip_future: Future[Any] | None = None
    prefill_future: Future[Any] | None = None
    diagnostics: PreparationDiagnostics = field(default_factory=PreparationDiagnostics)


class ModelPreloadCoordinator:
    """Direct coordinator for restore-time UNET and CLIP work."""

    def __init__(
        self,
        *,
        unet_loader: Callable[[ModelRestoreKey], Any] | None = None,
        clip_loader: Callable[[ModelRestoreKey], Any] | None = None,
        prefill_loader: Callable[[PrefillKey, Any], Any] | None = None,
        max_workers: int = 2,
    ) -> None:
        self.unet_loader = unet_loader
        self.clip_loader = clip_loader
        self.prefill_loader = prefill_loader
        self._pool = ThreadPoolExecutor(max_workers=max(1, min(int(max_workers), 2)), thread_name_prefix="comfymodal-restore")
        self._active: RestorePreparation | None = None

    def prepare(
        self,
        model_key: ModelRestoreKey,
        prefill_key: PrefillKey,
        *,
        exact_prefill: bool = True,
        trace: RuntimeTrace | None = None,
    ) -> RestorePreparation:
        preparation = RestorePreparation(model_key=model_key, prefill_key=prefill_key)
        self._active = preparation

        unet_loader = self.unet_loader
        clip_loader = self.clip_loader
        if unet_loader is not None:
            preparation.unet_future = self._submit("unet", lambda: unet_loader(model_key), preparation, trace)
        if clip_loader is not None:
            preparation.clip_future = self._submit("clip", lambda: clip_loader(model_key), preparation, trace)
        prefill_loader = self.prefill_loader
        if exact_prefill and prefill_loader is not None and prefill_key.prompt_bundle_hash:
            def prefill() -> Any:
                clip = self.wait_clip(preparation, trace=trace)
                return prefill_loader(prefill_key, clip)
            preparation.prefill_future = self._submit("prefill", prefill, preparation, trace)
        else:
            preparation.diagnostics.unused_speculation = bool(exact_prefill and self.prefill_loader is None)
        return preparation

    def wait_unet(self, preparation: RestorePreparation | None = None, *, trace: RuntimeTrace | None = None) -> Any:
        prep = preparation or self._require_active()
        return self._wait(prep, "unet", prep.unet_future, trace)

    def wait_clip(self, preparation: RestorePreparation | None = None, *, trace: RuntimeTrace | None = None) -> Any:
        prep = preparation or self._require_active()
        return self._wait(prep, "clip", prep.clip_future, trace)

    def wait_prefill(self, preparation: RestorePreparation | None = None, *, trace: RuntimeTrace | None = None) -> Any:
        prep = preparation or self._require_active()
        return self._wait(prep, "prefill", prep.prefill_future, trace)

    def diagnostics(self, preparation: RestorePreparation | None = None) -> dict[str, Any]:
        return (preparation or self._require_active()).diagnostics.to_dict()

    def close(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=False)

    def _submit(self, name: str, callback: Callable[[], Any], preparation: RestorePreparation, trace: RuntimeTrace | None) -> Future[Any]:
        def run() -> Any:
            started = time.time()
            setattr(preparation.diagnostics, f"{name}_started_at", started)
            if trace:
                trace.emit(f"{name}_prepare_start", phase="restore")
            try:
                result = callback()
                setattr(preparation.diagnostics, f"{name}_completed_at", time.time())
                if trace:
                    trace.emit(f"{name}_prepare_end", phase="restore")
                return result
            except Exception as exc:
                setattr(preparation.diagnostics, f"{name}_error", str(exc))
                setattr(preparation.diagnostics, f"{name}_completed_at", time.time())
                if trace:
                    trace.emit(f"{name}_prepare_end", phase="restore", metadata={"error": str(exc)[:200]})
                raise
        return self._pool.submit(run)

    def _wait(self, preparation: RestorePreparation, name: str, future: Future[Any] | None, trace: RuntimeTrace | None) -> Any:
        demanded = time.time()
        setattr(preparation.diagnostics, f"{name}_demanded_at", demanded)
        if future is None:
            return None
        result = future.result()
        completed = getattr(preparation.diagnostics, f"{name}_completed_at")
        setattr(preparation.diagnostics, f"{name}_wait_ms", max(0.0, (completed - demanded) * 1000.0))
        if name == "unet":
            clip_start = preparation.diagnostics.clip_started_at
            if clip_start and preparation.diagnostics.unet_completed_at:
                preparation.diagnostics.useful_overlap_ms = max(0.0, (preparation.diagnostics.unet_completed_at - clip_start) * 1000.0)
        return result

    def _require_active(self) -> RestorePreparation:
        if self._active is None:
            raise RuntimeError("no active restore preparation")
        return self._active
