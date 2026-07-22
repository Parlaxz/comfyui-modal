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
-----------
Timestamps are prefixed ``t_`` and stored as epoch seconds (float).

* ``t0_client_press``  – browser captured the click
* ``t1_local_recv``    – local ComfyUI ``/comfymodal/prompt`` route entered
* ``t2_local_dispatch`` – ``_execute_job`` started (just before run_prompt)
* ``t2b_modal_handle_resolved`` – Modal function handle resolved (from cache or lookup)
* ``t2c_modal_call_start`` – Modal remote call initiated
* ``t3_modal_entry``   – Modal ``run_prompt`` method body entered
* ``t3b_validate_done`` – Comfy workflow validation finished
* ``t3c_prep_done``    – input images written, in-process prep complete
* ``t3d_prompt_start`` – ``_execute_in_process``: prompt execution started
* ``t3e_execution_start`` – ``_execute_in_process``: ``executor.execute`` began
* ``t4_clip_load_start`` / ``t4_clip_load_end`` – CLIPLoader load window
* ``t5_text_encode_start`` / ``t5_text_encode_end`` – CLIPTextEncode window
* ``t6_sampler_start`` / ``t6_sampler_end`` – KSampler denoise window
* ``t7_vae_decode_start`` / ``t7_vae_decode_end`` – VAEDecode window
* ``t7b_collect_start`` – ``_collect_in_process_outputs`` began
* ``t8_image_written`` – final image file written by SaveImage
* ``t8b_outputs_collected`` – ``_collect_in_process_outputs`` finished
* ``t9_modal_return`` – Modal ``run_prompt`` returned to the local server (remote timestamp)
* ``t9b_local_result_received`` – Local server received the Modal stream result
* ``t9c_local_history_poll_start`` – Local history polling phase began (legacy route)
* ``t9d_local_history_poll_end`` – Local history polling phase ended
* ``t9e_local_materialize_start`` – Local output file materialization began
* ``t10_local_materialized`` – local ComfyUI server finished materializing output
  files and is about to send execution success to the browser
* ``t10b_local_save_start`` – Local auto-save phase began
* ``t10c_local_save_end`` – Local auto-save phase ended
* ``t10d_local_response_sent`` – Execution success response sent to frontend
* ``t10_browser_recv`` – browser received the response

Modal restore/cold-start cost is the gap ``t3_modal_entry - t2_local_dispatch``
on the very first request to a freshly restored container.  Once a container
is warm, the gap collapses to a few ms.

Real GPU inference time is the union of ``t4..t7`` (model load → text encode
→ sample → VAE decode).  Comfy graph/node overhead is everything else
between ``t3b`` and ``t8``.
"""

TRACE_VERSION = "2.0.0"

import copy
import os
import sys
import time
from typing import Any

# Diagnostic: verify the correct timing_trace module is loaded
print(f"[timing_trace] module loaded __file__={__file__} TRACE_VERSION={TRACE_VERSION}", flush=True)
_pyi_path = os.path.dirname(__file__)
if _pyi_path in sys.path:
    print(f"[timing_trace] module directory in sys.path: {_pyi_path}", flush=True)


class Trace:
    """A small bag of named wall-clock timestamps.

    Stored as a plain dict so it can be returned in JSON.  Use the
    ``mark(name)`` helper to record a timestamp and ``summary()`` to
    compute the deltas between any two marked stages.
    """

    __slots__ = ("_t", "_t0", "prompt_id", "_pre_sampler")

    def __init__(self, prompt_id: str = "", t0: float | None = None):
        self.prompt_id = prompt_id
        self._t0 = t0 if t0 is not None else time.time()
        self._t: dict[str, float] = {}
        self._pre_sampler: dict[str, Any] | None = None

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

    def store_pre_sampler_data(self, data: dict[str, Any] | None = None) -> None:
        """Store pre-sampler critical-path operation data for later summary.

        Accepts operation timings, counts, hits, dominant spans, and node
        attribution.  The data dict is stored directly — no deep-copy of
        model objects occurs.  Only numeric timings and metadata strings
        are retained.

        Parameters (all optional, typical keys):
            cache_key_build_ms, cache_lookup_ms, input_resolution_ms,
            model_patch_ms, conditioning_ms, future_wait_ms, lock_wait_ms,
            node_execution_ms, unattributed_ms,
            total_measured_ms, total_wall_ms, residual_ms,
            operation_counts (dict),
            operation_hits (dict),
            dominant_spans (list[dict]),
            node_class_map (dict).
        """
        if data is None:
            return
        # Strip out anything that looks like a model object — only keep
        # numeric timings, strings, dicts of strings/numbers, and lists
        # of such dicts.
        safe: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, (int, float, str, bool)):
                safe[k] = v
            elif isinstance(v, dict):
                safe[k] = {
                    sk: sv for sk, sv in v.items()
                    if isinstance(sv, (int, float, str, bool, type(None)))
                }
            elif isinstance(v, (list, tuple)):
                cleaned: list[dict[str, Any]] = []
                for item in v:
                    if isinstance(item, dict):
                        cleaned.append(
                            {ik: iv for ik, iv in item.items()
                             if isinstance(iv, (int, float, str, bool, type(None)))}
                        )
                    elif isinstance(item, (int, float, str, bool)):
                        cleaned.append({"value": item})
                safe[k] = cleaned
            # Silently drop anything else (model objects, callables, etc.)
        self._pre_sampler = safe

    def pre_sampler_summary(self) -> dict[str, Any]:
        """Return a pre-sampler critical-path summary dict.

        Returns an empty dict when no pre-sampler data has been stored.
        The returned dict has at minimum ``"present"`` set to ``True`` when
        data exists, along with all required operation timing fields and
        measured/residual reconciliation.
        """
        if self._pre_sampler is None:
            return {"pre_sampler_critical_path_ms": {}, "present": False}

        data = self._pre_sampler

        # Required operation timing fields
        op_fields = {
            "cache_key_build_ms",
            "cache_lookup_ms",
            "input_resolution_ms",
            "model_patch_ms",
            "conditioning_ms",
            "future_wait_ms",
            "lock_wait_ms",
            "node_execution_ms",
            "unattributed_ms",
        }
        critical = {}
        for field in op_fields:
            critical[field] = round(float(data.get(field, 0.0) or 0.0), 3)

        # Measured / residual reconciliation
        measured = sum(
            v for k, v in critical.items()
            if k in op_fields and k != "unattributed_ms" and v is not None
        )
        residual = data.get("residual_ms")
        total_wall = data.get("total_wall_ms")
        if residual is None and total_wall is not None and measured > 0:
            unattrib = critical.get("unattributed_ms", 0.0) or 0.0
            known = measured + unattrib
            residual = max(0.0, total_wall - known)

        critical["total_measured_ms"] = round(measured, 3)
        if total_wall is not None:
            critical["total_wall_ms"] = round(float(total_wall), 3)
        if residual is not None:
            critical["residual_ms"] = round(float(residual), 3)

        result: dict[str, Any] = {
            "pre_sampler_critical_path_ms": critical,
            "present": True,
        }

        # Operation counts
        counts = data.get("operation_counts")
        if isinstance(counts, dict) and counts:
            result["pre_sampler_operation_counts"] = dict(counts)

        # Operation hits
        hits = data.get("operation_hits")
        if isinstance(hits, dict) and hits:
            result["pre_sampler_operation_hits"] = dict(hits)

        # Dominant spans with start/end node attribution
        spans = data.get("dominant_spans")
        if isinstance(spans, list):
            result["pre_sampler_dominant_spans"] = list(spans)

        # Node class map
        ncm = data.get("node_class_map")
        if isinstance(ncm, dict):
            result["pre_sampler_node_map"] = dict(ncm)

        return result

    def summary(self) -> dict[str, Any]:
        # NOTE: _trace_dbg.log write removed per Phase 10 — no hot-path debug file I/O.
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
            "trace_version": TRACE_VERSION,
            "stages": dict(t),
            "deltas_ms": {},
            "derived_ms": {},
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
            ("unet_load", "t4b_unet_load_start", "t4b_unet_load_end"),
            ("vae_load", "t4c_vae_load_start", "t4c_vae_load_end"),
            ("image_io", "t8_image_written", "t8b_outputs_collected"),
            ("t8b_to_t9", "t8b_outputs_collected", "t9_modal_return"),
            ("t9_to_t10", "t9_modal_return", t10_key),
            # Phase 2 local timing markers
            ("t9b_to_t9e", "t9b_local_result_received", "t9e_local_materialize_start"),
            ("t9e_to_t10", "t9e_local_materialize_start", "t10_local_materialized"),
            ("t10_to_t10b", "t10_local_materialized", "t10b_local_save_start"),
            ("t10b_to_t10c", "t10b_local_save_start", "t10c_local_save_end"),
            ("t10c_to_t10d", "t10c_local_save_end", "t10d_local_response_sent"),
            ("t9_to_t9b", "t9_modal_return", "t9b_local_result_received"),
            ("t2b_to_t2c", "t2b_modal_handle_resolved", "t2c_modal_call_start"),
        ]
        for key, a, b in pairs:
            d = self.delta_ms(a, b)
            if d is not None:
                out["deltas_ms"][key] = d

        # Derived: sampler phase breakdown from sub-millisecond markers
        sp = self.delta_ms("t6_sampler_start", "t6_sampler_progress_start")
        if sp is not None:
            out["derived_ms"]["sampler_prep_ms"] = sp
        sd = self.delta_ms("t6_sampler_progress_start", "t6_sampler_progress_end")
        if sd is not None:
            out["derived_ms"]["sampler_denoise_ms"] = sd
        st = self.delta_ms("t6_sampler_progress_end", "t6_sampler_end")
        if st is not None:
            out["derived_ms"]["sampler_teardown_ms"] = st

        inference_keys = ("clip_load", "clip_encode", "sampler", "vae_decode", "unet_load", "vae_load")
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

        # Derive additional fields from stages if available
        # NOTE: restore_end_to_prompt_start_ms is computed in run_prompt()
        # only when real restore_end_unix_s exists (cold container).
        prompt_to_sampler = self.delta_ms("t3d_prompt_start", "t6_sampler_start")
        if prompt_to_sampler is not None:
            out["derived_ms"]["prompt_start_to_sampler_start_ms"] = prompt_to_sampler

        sampler_ms = out["deltas_ms"].get("sampler")
        if sampler_ms is not None:
            out["derived_ms"]["sampler_ms"] = sampler_ms

        s_to_outputs = self.delta_ms("t6_sampler_end", "t8b_outputs_collected")
        if s_to_outputs is not None:
            out["derived_ms"]["sampler_end_to_outputs_collected_ms"] = s_to_outputs

        output_total = self.delta_ms("t7b_collect_start", "t8b_outputs_collected")
        if output_total is not None:
            out["derived_ms"]["output_collection_total_ms"] = output_total

        total_exec = self.delta_ms("t3d_prompt_start", "t9_modal_return")
        if total_exec is not None:
            out["derived_ms"]["total_input_execution_ms"] = total_exec

        modal_to_return_ms = out["deltas_ms"].get("modal_to_return")
        if modal_to_return_ms is not None:
            out["derived_ms"]["modal_to_return_ms"] = modal_to_return_ms

        modal_to_browser_ms = out["deltas_ms"].get("modal_to_browser")
        if modal_to_browser_ms is not None:
            out["derived_ms"]["modal_to_browser_ms"] = modal_to_browser_ms

        # Always-computed: modal_entry_to_prompt_start_ms (not restore-dependent)
        modal_entry_to_ps = self.delta_ms("t3_modal_entry", "t3d_prompt_start")
        if modal_entry_to_ps is not None:
            out["derived_ms"]["modal_entry_to_prompt_start_ms"] = modal_entry_to_ps

        # Model wrapper chain: combined wall time for all wrapper/patch nodes
        # that modify the model after loading (CacheDiT, NoiseInjection,
        # ModelSampling, ModelPatch).
        _wrapper_stages = [
            ("cachedit_ms", "t8_cachedit_start", "t8_cachedit_end"),
            ("noise_inject_ms", "t8_noise_inject_start", "t8_noise_inject_end"),
            ("model_sampling_ms", "t4d_model_sampling_start", "t4d_model_sampling_end"),
            ("model_patch_ms", "t4e_model_patch_start", "t4e_model_patch_end"),
        ]
        _wrapper_total = 0.0
        _wrapper_any = False
        for _wn, _ws, _we in _wrapper_stages:
            _wd = self.delta_ms(_ws, _we)
            if _wd is not None:
                out["deltas_ms"][_wn] = _wd
                _wrapper_total += _wd
                _wrapper_any = True
        if _wrapper_any:
            out["derived_ms"]["model_wrapper_chain_ms"] = round(_wrapper_total, 2)

        # Node-level wall times (alias with clearer naming).
        # These measure the node's wall-clock window which may include
        # future/cache resolution, not just pure model I/O.
        cw = out["deltas_ms"].get("clip_load")
        if cw is not None:
            out["derived_ms"]["clip_node_wait_ms"] = cw
        uw = out["deltas_ms"].get("unet_load")
        if uw is not None:
            out["derived_ms"]["unet_node_wait_ms"] = uw
        vw = out["deltas_ms"].get("vae_load")
        if vw is not None:
            out["derived_ms"]["vae_node_wait_ms"] = vw

        # Phase 2: local path timing derived metrics
        _lp_pairs = [
            ("local_prepare_ms", "t1_local_recv", "t2_local_prepared"),
            ("modal_handle_resolve_ms", "t2_local_prepared", "t2b_modal_handle_resolved"),
            ("modal_call_submit_ms", "t2b_modal_handle_resolved", "t2c_modal_call_start"),
            ("modal_queue_or_start_gap_ms", "t2c_modal_call_start", "t3_modal_entry"),
            ("modal_return_to_local_receive_ms", "t9_modal_return", "t9b_local_result_received"),
            ("local_history_poll_ms", "t9c_local_history_poll_start", "t9d_local_history_poll_end"),
            ("local_materialize_ms", "t9e_local_materialize_start", "t10_local_materialized"),
            ("local_save_ms", "t10b_local_save_start", "t10c_local_save_end"),
            ("local_response_send_ms", "t10_local_materialized", "t10d_local_response_sent"),
            ("modal_return_to_browser_ms", "t9_modal_return", t10_key),
            ("client_to_response_sent_ms", "t0_client_press", "t10d_local_response_sent"),
        ]
        for _lpk, _lpa, _lpb in _lp_pairs:
            _lpd = self.delta_ms(_lpa, _lpb)
            if _lpd is not None:
                out["derived_ms"][_lpk] = _lpd

        # Phase 1: dependency validation timing (preserved from upstream enrichment)
        for _dep_key in (
            "dependency_validation_ms", "dependency_total_ms",
            "dependency_pre_key_check_ms", "dependency_baked_manifest_load_ms",
            "dependency_source_root_resolve_ms", "dependency_fingerprint_ms",
            "dependency_cache_key_ms", "dependency_memory_lookup_ms",
            "dependency_sentinel_lookup_ms", "dependency_full_validation_ms",
            "dependency_sentinel_write_ms",
        ):
            _dep_v = t.get(_dep_key)
            if _dep_v is not None:
                out["derived_ms"][_dep_key] = _dep_v

        # Trace metadata: timing_quality / missing_timing_fields
        _exec_required = [
            "t3d_prompt_start", "t3e_execution_start",
            "t6_sampler_start", "t6_sampler_end",
            "t7b_collect_start", "t8b_outputs_collected",
        ]
        _exec_present = [k for k in _exec_required if k in t]
        _exec_missing = [k for k in _exec_required if k not in t]

        # Cold-restore fields are conditional — only required if restore
        # was actually observed on this container.
        _restore_start = t.get("t3_modal_entry")
        _restore_present = _restore_start is not None
        _cold_fields = []
        if _restore_present:
            _cold_fields = ["t3b_validate_done", "t3c_prep_done"]

        _context_fields = []
        for f in _cold_fields:
            if f not in t:
                _context_fields.append(f)

        _optional_fields = [
            "t0_client_press", "t1_local_recv", "t2_local_dispatch",
            "t2b_modal_handle_resolved", "t2c_modal_call_start",
            "t4_clip_load_start", "t4_clip_load_end",
            "t5_text_encode_start", "t5_text_encode_end",
            "t7_vae_decode_start", "t7_vae_decode_end",
            "t8_image_written", "t9_modal_return",
            "t9b_local_result_received", "t9e_local_materialize_start",
            t10_key, "t10b_local_save_start", "t10c_local_save_end",
            "t10d_local_response_sent",
        ]
        _opt_missing = [k for k in _optional_fields if k not in t]

        _missing = _exec_missing + _context_fields + _opt_missing
        out["missing_timing_fields"] = _missing

        _reason_parts = []
        if not _exec_missing and not _context_fields:
            out["timing_quality"] = "complete"
            _reason_parts.append("all_required_fields_present")
        elif len(_exec_present) >= 4:
            out["timing_quality"] = "partial"
            _reason_parts.append(f"missing_exec_fields={_exec_missing}" if _exec_missing else "context_only")
        else:
            out["timing_quality"] = "bad"
            _reason_parts.append(f"cannot_trust_timing:missing_exec={_exec_missing}")
        if _context_fields:
            _reason_parts.append(f"missing_cold_context={_context_fields}")
        if _opt_missing:
            _reason_parts.append(f"optional_missing={_opt_missing}")
        out["timing_quality_reason"] = "; ".join(_reason_parts)

        # Pre-sampler critical path summary (additive, preserves existing keys)
        ps = self.pre_sampler_summary()
        if ps.get("present"):
            for _ps_key, _ps_val in ps.items():
                if _ps_key == "present":
                    continue
                out[_ps_key] = _ps_val

        print(f"[timing_trace] summary: trace_version={out.get('trace_version')} "
              f"quality={out.get('timing_quality')} "
              f"derived_keys={list(out.get('derived_ms', {}).keys())} "
              f"missing={len(out.get('missing_timing_fields', []))}", flush=True)
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
            "t2b_modal_handle_resolved",
            "t2c_modal_call_start",
            "t3_modal_entry",
            "t3b_validate_done",
            "t3c_prep_done",
            "t3d_prompt_start",
            "t3e_execution_start",
            "t4_clip_load_start",
            "t4_clip_load_end",
            "t4b_unet_load_start",
            "t4b_unet_load_end",
            "t4c_vae_load_start",
            "t4c_vae_load_end",
            "t4d_model_sampling_start",
            "t4d_model_sampling_end",
            "t4e_model_patch_start",
            "t4e_model_patch_end",
            "t5_text_encode_start",
            "t5_text_encode_end",
            "t6_sampler_start",
            "t6_sampler_end",
            "t7_vae_decode_start",
            "t7_vae_decode_end",
            "t7b_collect_start",
            "t8_image_written",
            "t8b_outputs_collected",
            "t9_modal_return",
            "t9b_local_result_received",
            "t9c_local_history_poll_start",
            "t9d_local_history_poll_end",
            "t9e_local_materialize_start",
            "t10_local_materialized",
            "t10b_local_save_start",
            "t10c_local_save_end",
            "t10d_local_response_sent",
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
            "unet_load",
            "vae_load",
            "image_io",
            "t8b_to_t9",
            "t9_to_t10",
            "t9_to_t9b",
            "t9b_to_t9e",
            "t9e_to_t10",
            "t10_to_t10b",
            "t10b_to_t10c",
            "t10c_to_t10d",
            "t2b_to_t2c",
            "graph_overhead",
            "inference_total",
            "modal_to_return",
            "modal_to_browser",
            "cachedit_ms",
            "noise_inject_ms",
            "model_sampling_ms",
            "model_patch_ms",
        ]
        delta_parts = [f"{k}={d[k]}ms" for k in delta_keys if k in d and d[k] is not None]
        derived = s.get("derived_ms", {})
        derived_keys = [
            "restore_end_to_prompt_start_ms",
            "prompt_start_to_sampler_start_ms",
            "sampler_ms",
            "sampler_end_to_outputs_collected_ms",
            "output_collection_total_ms",
            "total_input_execution_ms",
            "modal_to_return_ms",
            "model_wrapper_chain_ms",
            "exec_model_load_io_ms",
            "exec_deepcopy_ms",
            "load_model_gpu_ms",
        ]
        derived_keys += [
            "modal_entry_to_prompt_start_ms",
            "clip_node_wait_ms",
            "unet_node_wait_ms",
            "vae_node_wait_ms",
        ]
        derived_keys += [
            "local_prepare_ms",
            "modal_handle_resolve_ms",
            "modal_call_submit_ms",
            "modal_queue_or_start_gap_ms",
            "modal_return_to_local_receive_ms",
            "local_history_poll_ms",
            "local_materialize_ms",
            "local_save_ms",
            "local_response_send_ms",
            "modal_return_to_browser_ms",
            "client_to_response_sent_ms",
        ]
        derived_parts = [f"{k}={derived[k]}ms" for k in derived_keys if k in derived and derived[k] is not None]
        dep_val_ms = derived.get("dependency_validation_ms")
        if dep_val_ms is not None:
            _fp_ms = derived.get("dependency_fingerprint_ms")
            _fp_part = f" fp_ms={_fp_ms}" if _fp_ms is not None else ""
            derived_parts.insert(0, f"cache_layer={s.get('dependency_validation_cache_layer', '?')}")
            derived_parts.insert(0, f"dep_result={s.get('dependency_validation_result', '?')}")
            derived_parts.insert(0, f"dep_val_ms={dep_val_ms}ms{_fp_part}")
        msg = "[comfyui-modal.timing] " + " ".join(parts)
        if delta_parts:
            msg += " | " + " ".join(delta_parts)
        if derived_parts:
            msg += " | " + " ".join(derived_parts)
        return msg


_TRACE_KEYS_FROM_BROWSER = ("t0_client_press", "queue_prompt_start_ms")


def coerce_t0_from_browser(payload: dict | None) -> float | None:
    """Extract a t0 timestamp from a request body if present.

    The browser may send any of the following (checked in priority order):

    * ``queue_prompt_start_ms`` (epoch milliseconds from ``Date.now()`` at
      queue capture) — **preferred** because it is the earliest reliable
      browser timestamp.
    * ``t0_client_press`` (epoch seconds, float) — legacy fallback.
    * ``t0_client_press_ms`` (epoch milliseconds) — legacy fallback.
    * ``t0_perf_ms`` + ``t0_perf_now_ms`` (``performance.now()`` relative
      to ``Date.now()``) — last-resort conversion.
    """
    if not isinstance(payload, dict):
        return None
    # Preferred: queue_prompt_start_ms (epoch ms from browser Date.now())
    raw = payload.get("queue_prompt_start_ms")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw) / 1000.0
    raw = payload.get("t0_client_press")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    raw = payload.get("t0_client_press_ms")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw) / 1000.0
    raw = payload.get("t0_perf_ms")
    raw_now = payload.get("t0_perf_now_ms")
    if (isinstance(raw, (int, float)) and not isinstance(raw, bool)
            and isinstance(raw_now, (int, float)) and not isinstance(raw_now, bool)):
        epoch_ms_at_perf = raw_now - float(raw)
        return epoch_ms_at_perf / 1000.0
    return None


# ── TraceV4 — v4 dual-clock trace extension ────────────────────────────────
# Adds time.time_ns() / time.perf_counter_ns() dual-clock event support
# while preserving full backward compatibility with Trace.

_V4_PROFILE_LEVEL: str = os.environ.get("COMFYMODAL_PROFILE_LEVEL", "summary").strip().lower()
if _V4_PROFILE_LEVEL not in ("off", "summary", "detailed", "trace", "trace_verbose"):
    _V4_PROFILE_LEVEL = "summary"


def get_v4_profile_level() -> str:
    return _V4_PROFILE_LEVEL


def set_v4_profile_level(level: str) -> None:
    global _V4_PROFILE_LEVEL
    level = level.strip().lower()
    if level in ("off", "summary", "detailed", "trace", "trace_verbose"):
        _V4_PROFILE_LEVEL = level


def _v4_profile_enabled(level: str = "summary") -> bool:
    if _V4_PROFILE_LEVEL == "off":
        return False
    order = {"off": 0, "summary": 1, "detailed": 2, "trace": 3, "trace_verbose": 4}
    return order.get(_V4_PROFILE_LEVEL, 0) >= order.get(level, 1)


# ── Canonical v4 event name constants ──────────────────────────────────────
V4_T0_CLIENT_PRESS = "t0_client_press"
V4_T1_LOCAL_BRIDGE_RECEIVED = "t1_local_bridge_received"
V4_T2_LOCAL_MODAL_SUBMIT_START = "t2_local_modal_submit_start"
V4_T2C_FIRST_REMOTE_EVENT_RECEIVED = "t2c_first_remote_event_received"
V4_T3_MODAL_ENTRY = "t3_modal_entry"
V4_T4_PROMPT_START = "t4_prompt_start"
V4_T5_SAMPLER_START = "t5_sampler_start"
V4_T6_SAMPLER_END = "t6_sampler_end"
V4_T6A_VAE_DECODE_START = "t6a_vae_decode_start"
V4_T6B_VAE_DECODE_END = "t6b_vae_decode_end"
V4_T7_OUTPUTS_COLLECTION_START = "t7_outputs_collection_start"
V4_T8_OUTPUTS_COLLECTED = "t8_outputs_collected"
V4_T8F_REMOTE_RETURN_END = "t8f_remote_return_end"
V4_T9_LOCAL_REMOTE_RESULT_RECEIVED = "t9_local_remote_result_received"
V4_T10_LOCAL_MATERIALIZED = "t10_local_materialized"
V4_T10A_LOCAL_RESPONSE_TO_COMFY_START = "t10a_local_response_to_comfy_start"
V4_T10B_LOCAL_RESPONSE_TO_COMFY_END = "t10b_local_response_to_comfy_end"
V4_T11_LOCAL_UI_DONE = "t11_local_ui_done"
V4_RESTORE_START = "restore_start"
V4_RESTORE_END = "restore_end"

_LEGACY_TO_V4: dict[str, str] = {
    "t0_client_press": V4_T0_CLIENT_PRESS,
    "t1_local_recv": V4_T1_LOCAL_BRIDGE_RECEIVED,
    "t2_local_dispatch": V4_T2_LOCAL_MODAL_SUBMIT_START,
    "t3_modal_entry": V4_T3_MODAL_ENTRY,
    "t3d_prompt_start": V4_T4_PROMPT_START,
    "t6_sampler_start": V4_T5_SAMPLER_START,
    "t6_sampler_end": V4_T6_SAMPLER_END,
    "t7_vae_decode_start": V4_T6A_VAE_DECODE_START,
    "t7_vae_decode_end": V4_T6B_VAE_DECODE_END,
    "t7b_collect_start": V4_T7_OUTPUTS_COLLECTION_START,
    "t8b_outputs_collected": V4_T8_OUTPUTS_COLLECTED,
    "t9_modal_return": V4_T8F_REMOTE_RETURN_END,
    "t10_local_materialized": V4_T10_LOCAL_MATERIALIZED,
    "t_restore_start": V4_RESTORE_START,
    "t_restore_end": V4_RESTORE_END,
}


def _get_thread_info() -> dict:
    import threading
    return {
        "pid": os.getpid(),
        "thread_id": threading.get_ident(),
        "thread_name": threading.current_thread().name,
    }


class TraceV4(Trace):
    """v4 dual-clock trace extension.

    Adds ``wall_unix_ns`` (time.time_ns) and ``mono_ns`` (time.perf_counter_ns)
    to every event, along with process/phase/thread metadata.
    Fully backward-compatible with ``Trace`` — inherits ``mark()``, ``summary()``, etc.
    """

    def __init__(self, prompt_id: str = "", t0: float | None = None, process: str = "comfy_internal"):
        super().__init__(prompt_id=prompt_id, t0=t0)
        self.process = process
        self._v4_events: list[dict] = []

    def mark_v4(
        self, name: str, process: str = "", phase: str = "",
        profile_level: str = "summary", **metadata: Any,
    ) -> dict:
        if not _v4_profile_enabled(profile_level):
            return {"name": name}
        proc = process or self.process
        wall_ns = time.time_ns()
        mono_ns = time.perf_counter_ns()
        thread = _get_thread_info()
        event: dict[str, Any] = {
            "name": name,
            "process": proc,
            "phase": phase,
            "wall_unix_ns": wall_ns,
            "mono_ns": mono_ns,
            "pid": thread["pid"],
            "thread_id": thread["thread_id"],
            "thread_name": thread["thread_name"],
        }
        if metadata:
            event["metadata"] = metadata
        self._v4_events.append(event)
        return event

    def mark(self, name: str, t: float | None = None) -> float:
        val = super().mark(name, t)
        v4_name = _LEGACY_TO_V4.get(name, name)
        self.mark_v4(v4_name, phase="timing_trace_legacy", profile_level="trace")
        return val

    def span_start_v4(self, name: str, process: str = "", phase: str = "", **metadata: Any) -> dict:
        return self.mark_v4(f"{name}_start", process=process, phase=phase, **metadata)

    def span_end_v4(self, name: str, process: str = "", phase: str = "", **metadata: Any) -> dict:
        return self.mark_v4(f"{name}_end", process=process, phase=phase, **metadata)

    def to_event_list(self) -> list[dict]:
        return list(self._v4_events)

    def v4_summary(self) -> dict[str, Any]:
        out = {
            "trace_version": "4.0.0",
            "prompt_id": self.prompt_id,
            "events": list(self._v4_events),
            "event_count": len(self._v4_events),
            "process": self.process,
        }
        ps = self.pre_sampler_summary()
        if ps.get("present"):
            out["pre_sampler_critical_path_ms"] = ps.get("pre_sampler_critical_path_ms", {})
            for key in ("pre_sampler_operation_counts", "pre_sampler_operation_hits",
                        "pre_sampler_dominant_spans", "pre_sampler_node_map"):
                val = ps.get(key)
                if val:
                    out[key] = val
        return out

    def pre_sampler_summary(self) -> dict[str, Any]:
        """Return pre-sampler critical-path summary, scanning v4 events too.

        Inherits ``store_pre_sampler_data()`` data from ``Trace``.  When no
        explicit data has been stored, attempts to derive what it can from
        ``_v4_events`` that carry pre-sampler operation metadata.
        """
        # Check for explicitly stored data first
        if self._pre_sampler is not None:
            return super().pre_sampler_summary()

        # Attempt derivation from v4 events
        op_spans: dict[str, float] = {}
        op_counts: dict[str, int] = {}
        op_hits: dict[str, int] = {}
        dominant: list[dict] = []
        node_map: dict[str, str] = {}

        starts: dict[str, dict] = {}
        for ev in self._v4_events:
            name = ev.get("name", "")
            meta = ev.get("metadata") or {}
            if not isinstance(meta, dict):
                meta = {}
            op = meta.get("operation", "")
            if not op:
                continue

            if name.endswith("_start"):
                starts[op] = ev
            elif name.endswith("_end") and op in starts:
                start_ev = starts.pop(op, None)
                if start_ev is not None:
                    dur_ns = ev.get("mono_ns", 0) - start_ev.get("mono_ns", 0)
                    dur_ms = max(0.0, dur_ns / 1_000_000)
                    op_spans[op] = op_spans.get(op, 0.0) + dur_ms
                    op_counts[op] = op_counts.get(op, 0) + 1
                    if meta.get("cache_hit"):
                        op_hits[op] = op_hits.get(op, 0) + 1
                    # Collect node attribution
                    span: dict[str, Any] = {
                        "operation": op,
                        "duration_ms": round(dur_ms, 3),
                    }
                    for attr in ("node_id", "class_type",
                                 "start_node_id", "start_node_class_type",
                                 "end_node_id", "end_node_class_type",
                                 "cache_hit", "reused", "skipped"):
                        val = meta.get(attr)
                        if val is not None and val != "":
                            span[attr] = val
                    if span.get("start_node_id") or span.get("node_id"):
                        dominant.append(span)
                    # Build node map
                    for nid_attr in ("start_node_id", "end_node_id", "node_id"):
                        nid = meta.get(nid_attr, "")
                        ct = meta.get("start_node_class_type" if nid_attr == "start_node_id"
                                      else "end_node_class_type" if nid_attr == "end_node_id"
                                      else "class_type", "")
                        if nid and ct:
                            node_map[nid] = ct

        # If no v4 event data, return empty
        if not op_spans:
            return {"pre_sampler_critical_path_ms": {}, "present": False}

        required = {"cache_key_build_ms", "cache_lookup_ms", "input_resolution_ms",
                     "model_patch_ms", "conditioning_ms", "future_wait_ms",
                     "lock_wait_ms", "node_execution_ms", "unattributed_ms"}
        critical: dict[str, float] = {}
        for op in ("cache_key_build", "cache_lookup", "input_resolution",
                    "model_patch", "conditioning", "future_wait",
                    "lock_wait", "node_execution", "unattributed"):
            critical[f"{op}_ms"] = round(op_spans.get(op, 0.0), 3)

        measured = sum(v for k, v in critical.items() if k in required and k != "unattributed_ms")
        residual = critical.get("unattributed_ms", 0.0)
        critical["total_measured_ms"] = round(measured, 3)
        if residual > 0:
            critical["residual_ms"] = round(residual, 3)

        out: dict[str, Any] = {
            "pre_sampler_critical_path_ms": critical,
            "present": True,
        }
        if op_counts:
            out["pre_sampler_operation_counts"] = dict(op_counts)
        if op_hits:
            out["pre_sampler_operation_hits"] = dict(op_hits)
        if dominant:
            out["pre_sampler_dominant_spans"] = dominant
        if node_map:
            out["pre_sampler_node_map"] = node_map
        return out


# ---------------------------------------------------------------------------
# Shared timing helpers — usable by both normal graph path and Studio.
# ---------------------------------------------------------------------------

# Fields to deep-copy from a Modal result dict when extracting a compact
# timing payload.  Excludes outputs (which may contain base64 image data).
_REMOTE_TIMING_FIELDS: tuple[str, ...] = (
    "trace", "wall_clock_trace", "_wall_clock_summary",
    "_restore_timing", "scheduler_trace",
)

# Diagnostic/conditionally-relevant timing fields included only when present.
_REMOTE_TIMING_DIAG_FIELDS: tuple[str, ...] = (
    "_image_save_diagnostics",
    "timing_quality", "trace_version",
)


def extract_remote_timing_payload(result_data: dict) -> dict:
    """Extract a compact timing payload from a Modal result dict.

    Deep-copies only timing-related fields (``trace``, ``wall_clock_trace``,
    ``_wall_clock_summary``, ``_restore_timing``, ``scheduler_trace``) and
    diagnostic timing fields when present, **excluding** ``outputs`` (which
    may contain base64 image data).

    Returns a flat dict containing only the recognised timing keys, or an
    empty dict if none are present.
    """
    payload: dict = {}
    for key in _REMOTE_TIMING_FIELDS:
        val = result_data.get(key)
        if val is not None:
            payload[key] = copy.deepcopy(val)
    for key in _REMOTE_TIMING_DIAG_FIELDS:
        val = result_data.get(key)
        if val is not None:
            payload[key] = copy.deepcopy(val)
    return payload


# ── Remote trace merger (normal graph path + Studio) ──────────────────────


def merge_remote_trace_into(merged_trace: dict, remote_trace: dict) -> dict:
    """Merge remote trace data into a local trace summary dict **in-place**.

    Designed for both the normal graph path (where ``trace.summary()``
    produces the local summary and the Modal result carries
    ``result["trace"]``) and the Studio path (where a minimal local
    summary is created from server-observed wall-clock data).

    Merger rules (deterministic, never overwrites truthfully local values):

    * ``stages`` — remote stage entries are added only when the key does
      not already exist in the local summary (local materialization stages
      such as ``t9b_*`` / ``t10_*`` are preserved).
    * ``deltas_ms`` — same: local deltas are never overwritten.
    * ``derived_ms`` — same: local derived values are never overwritten.
    * ``restore`` — the full restore dict is deep-copied from remote.
    * Dependency-validation fields — top-level remote keys are copied
      when present (they have no local equivalent).

    Returns the (mutated) ``merged_trace`` dict for convenience.
    """
    if not isinstance(remote_trace, dict):
        return merged_trace

    # ── Merge stages (remote entries only when key is absent locally) ──
    remote_stages = remote_trace.get("stages", {})
    if isinstance(remote_stages, dict):
        local_stages = merged_trace.setdefault("stages", {})
        for k, v in remote_stages.items():
            if k not in local_stages:
                local_stages[k] = v

    # ── Merge deltas_ms ───────────────────────────────────────────────
    remote_deltas = remote_trace.get("deltas_ms", {})
    if isinstance(remote_deltas, dict):
        local_deltas = merged_trace.setdefault("deltas_ms", {})
        for k, v in remote_deltas.items():
            if k not in local_deltas:
                local_deltas[k] = v

    # ── Merge derived_ms ─────────────────────────────────────────────
    remote_derived = remote_trace.get("derived_ms", {})
    if isinstance(remote_derived, dict):
        local_derived = merged_trace.setdefault("derived_ms", {})
        for rdk, rdv in remote_derived.items():
            if rdk not in local_derived:
                local_derived[rdk] = rdv

    # ── Preserve restore timing block ────────────────────────────────
    if "restore" in remote_trace:
        merged_trace["restore"] = copy.deepcopy(remote_trace["restore"])

    # ── Preserve dependency validation fields ────────────────────────
    _DEP_FIELDS = (
        "dependency_validation_ms", "dependency_total_ms",
        "dependency_validation_result", "dependency_validation_cache_layer",
        "dependency_validation_cache_hit", "dependency_validation_reason",
        "dependency_validation_baked_hash", "dependency_validation_current_hash",
        "dependency_validation_changed_nodes",
        "dependency_pre_key_check_ms", "dependency_baked_manifest_load_ms",
        "dependency_source_root_resolve_ms", "dependency_fingerprint_ms",
        "dependency_cache_key_ms", "dependency_memory_lookup_ms",
        "dependency_sentinel_lookup_ms", "dependency_full_validation_ms",
        "dependency_sentinel_write_ms",
    )
    for field in _DEP_FIELDS:
        val = remote_trace.get(field)
        if val is not None:
            merged_trace[field] = val

    return merged_trace
