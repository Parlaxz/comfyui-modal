"""End-to-end timing trace for a single prompt.

The trace is built incrementally as the prompt moves through:

    browser (t0) → local ComfyUI server (t1, t2) → Modal (t3-t8) → local server
    (t9) → browser (t10)

Each stage captures a wall-clock timestamp in seconds.  Once the prompt
returns to the local server, the trace is summarised in container logs and
returned to the browser in the response body so the UI can render a
human-readable timeline.

A single ``Trace`` instance is per-prompt.  The browser side only knows the
first timestamp; the local ComfyUI server adds the next two; the Modal
container adds the bulk.  Each side appends its own field to a shared dict
that is finally aggregated at the local server.

Field naming
------------
Timestamps are prefixed ``t_`` and stored as epoch seconds (float).

* ``t0_client_press``  – browser captured the click
* ``t1_local_recv``    – local ComfyUI ``/comfymodal/prompt`` route entered
* ``t2_local_dispatch`` – ``_execute_job`` started (just before run_prompt)
* ``t3_modal_entry``   – Modal ``run_prompt`` method body entered
* ``t3b_validate_done`` – Comfy workflow validation finished
* ``t3c_prep_done``    – input images written, in-process prep complete
* ``t4_clip_load_start`` / ``t4_clip_load_end`` – CLIPLoader load window
* ``t5_text_encode_start`` / ``t5_text_encode_end`` – CLIPTextEncode window
* ``t6_sampler_start`` / ``t6_sampler_end`` – KSampler denoise window
* ``t7_vae_decode_start`` / ``t7_vae_decode_end`` – VAEDecode window
* ``t8_image_written`` – final image file written by SaveImage
* ``t8b_outputs_collected`` – ``_collect_in_process_outputs`` finished
* ``t9_modal_return`` – Modal ``run_prompt`` returned to the local server
* ``t10_local_materialized`` – local ComfyUI server finished materializing output
  files and is about to send execution success to the browser
* ``t10_browser_recv`` – browser received the response

Modal restore/cold-start cost is the gap ``t3_modal_entry - t2_local_dispatch``
on the very first request to a freshly restored container.  Once a container
is warm, the gap collapses to a few ms.

Real GPU inference time is the union of ``t4..t7`` (model load → text encode
→ sample → VAE decode).  Comfy graph/node overhead is everything else
between ``t3b`` and ``t8``.
"""

import time
from typing import Any


class Trace:
    """A small bag of named wall-clock timestamps.

    Stored as a plain dict so it can be returned in JSON.  Use the
    ``mark(name)`` helper to record a timestamp and ``summary()`` to
    compute the deltas between any two marked stages.
    """

    __slots__ = ("_t", "_t0", "prompt_id")

    def __init__(self, prompt_id: str = "", t0: float | None = None):
        self.prompt_id = prompt_id
        self._t0 = t0 if t0 is not None else time.time()
        self._t: dict[str, float] = {}

    def mark(self, name: str, t: float | None = None) -> float:
        """Record a named timestamp.  Returns the absolute time used."""
        value = t if t is not None else time.time()
        self._t[name] = value
        return value

    def get(self, name: str) -> float | None:
        return self._t.get(name)

    def delta_ms(self, a: str, b: str) -> float | None:
        """Return ``b - a`` in milliseconds, or None if either is missing."""
        ta = self._t.get(a)
        tb = self._t.get(b)
        if ta is None or tb is None:
            return None
        return round((tb - ta) * 1000, 2)

    def since_t0_ms(self, name: str) -> float | None:
        ta = self._t.get(name)
        if ta is None:
            return None
        return round((ta - self._t0) * 1000, 2)

    def fields(self) -> dict[str, float]:
        return dict(self._t)

    def update(self, other: "Trace | dict[str, Any] | None") -> None:
        """Merge another trace's timestamps into this one."""
        if not other:
            return
        if isinstance(other, Trace):
            self._t.update(other._t)
        elif isinstance(other, dict):
            for k, v in other.items():
                if isinstance(k, str) and isinstance(v, (int, float)):
                    self._t[k] = float(v)

    def summary(self) -> dict[str, Any]:
        """Return a dict with absolute timestamps and key delta pairs.

        The deltas are the values most people actually care about:

        * ``network_to_modal``  : t2 → t3 (queue + network + cold restore)
        * ``modal_warmup``      : t3 → t3b (validate, prep)
        * ``clip_load``         : t4
        * ``clip_encode``       : t5
        * ``sampler``           : t6
        * ``vae_decode``        : t7
        * ``graph_overhead``    : t3b → t8 minus (clip_load + clip_encode +
                                          sampler + vae_decode)
        * ``image_io``          : t8 → t8b (output collection)
        * ``modal_to_browser``  : t2 → t10 (full round trip)
        """
        t = self._t
        out: dict[str, Any] = {
            "prompt_id": self.prompt_id,
            "t0": self._t0,
            "stages": dict(t),
            "deltas_ms": {},
        }

        t10_key = "t10_browser_recv" if t.get("t10_browser_recv") is not None else "t10_local_materialized"

        pairs = [
            ("t0_to_t1", "t0_client_press", "t1_local_recv"),
            ("t1_to_t2", "t1_local_recv", "t2_local_dispatch"),
            ("t2_to_t3", "t2_local_dispatch", "t3_modal_entry"),
            ("t3_to_t3b", "t3_modal_entry", "t3b_validate_done"),
            ("t3b_to_t3c", "t3b_validate_done", "t3c_prep_done"),
            ("clip_load", "t4_clip_load_start", "t4_clip_load_end"),
            ("clip_encode", "t5_text_encode_start", "t5_text_encode_end"),
            ("sampler", "t6_sampler_start", "t6_sampler_end"),
            ("vae_decode", "t7_vae_decode_start", "t7_vae_decode_end"),
            ("image_io", "t8_image_written", "t8b_outputs_collected"),
            ("t8b_to_t9", "t8b_outputs_collected", "t9_modal_return"),
            ("t9_to_t10", "t9_modal_return", t10_key),
        ]
        for key, a, b in pairs:
            d = self.delta_ms(a, b)
            if d is not None:
                out["deltas_ms"][key] = d

        inference_keys = ("clip_load", "clip_encode", "sampler", "vae_decode")
        inference_ms = sum(
            out["deltas_ms"].get(k, 0.0) for k in inference_keys
        )
        out["deltas_ms"]["inference_total"] = round(inference_ms, 2)
        if "t3b_to_t8" not in out["deltas_ms"]:
            d = self.delta_ms("t3b_validate_done", "t8_image_written")
            if d is not None:
                out["deltas_ms"]["t3b_to_t8"] = d
                out["deltas_ms"]["graph_overhead"] = round(
                    max(0.0, d - inference_ms), 2
                )
        modal_to_browser = self.delta_ms("t2_local_dispatch", t10_key)
        if modal_to_browser is not None:
            out["deltas_ms"]["modal_to_browser"] = modal_to_browser

        modal_to_return = self.delta_ms("t2_local_dispatch", "t9_modal_return")
        if modal_to_return is not None:
            out["deltas_ms"]["modal_to_return"] = modal_to_return

        remote_total = self.delta_ms("t3_modal_entry", "t9_modal_return")
        if remote_total is not None:
            out["deltas_ms"]["remote_total"] = remote_total
        return out

    def log_line(self) -> str:
        """Return a one-line summary suitable for a container log."""
        s = self.summary()
        parts = [
            f"prompt={s['prompt_id'][:8] or '-'}",
            f"t0={s['stages'].get('t0_client_press', 0):.3f}",
        ]
        order = [
            "t1_local_recv",
            "t2_local_dispatch",
            "t3_modal_entry",
            "t3b_validate_done",
            "t3c_prep_done",
            "t4_clip_load_start",
            "t4_clip_load_end",
            "t5_text_encode_start",
            "t5_text_encode_end",
            "t6_sampler_start",
            "t6_sampler_end",
            "t7_vae_decode_start",
            "t7_vae_decode_end",
            "t8_image_written",
            "t8b_outputs_collected",
            "t9_modal_return",
            "t10_local_materialized",
            "t10_browser_recv",
        ]
        for k in order:
            v = s["stages"].get(k)
            if v is not None:
                parts.append(f"{k}={v - s['t0']:.3f}")
        d = s["deltas_ms"]
        delta_keys = [
            "t0_to_t1",
            "t1_to_t2",
            "t2_to_t3",
            "t3_to_t3b",
            "clip_load",
            "clip_encode",
            "sampler",
            "vae_decode",
            "image_io",
            "t8b_to_t9",
            "t9_to_t10",
            "graph_overhead",
            "inference_total",
            "modal_to_return",
            "modal_to_browser",
        ]
        delta_parts = [f"{k}={d[k]}ms" for k in delta_keys if k in d and d[k] is not None]
        return "[comfyui-modal.timing] " + " ".join(parts) + " | " + " ".join(delta_parts)


_TRACE_KEYS_FROM_BROWSER = ("t0_client_press",)


def coerce_t0_from_browser(payload: dict | None) -> float | None:
    """Extract a t0 timestamp from a request body if present.

    The browser may send either:

    * ``t0_client_press`` (epoch seconds, float) — preferred
    * ``t0_client_press_ms`` (epoch milliseconds) — fallback
    * ``t0_perf_ms`` (performance.now() relative to navigation start) —
      converted using ``Date.now() - performance.now()``
    """
    if not isinstance(payload, dict):
        return None
    raw = payload.get("t0_client_press")
    if isinstance(raw, (int, float)):
        return float(raw)
    raw = payload.get("t0_client_press_ms")
    if isinstance(raw, (int, float)):
        return float(raw) / 1000.0
    raw = payload.get("t0_perf_ms")
    raw_now = payload.get("t0_perf_now_ms")
    if isinstance(raw, (int, float)) and isinstance(raw_now, (int, float)):
        epoch_ms_at_perf = raw_now - float(raw)
        return epoch_ms_at_perf / 1000.0
    return None
