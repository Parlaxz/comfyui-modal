"""Reconstruct the exact Gantt render from the captured run spans."""
import json
import sys

sys.path.insert(0, r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal")

p = r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-18_22-54-23\run_0.json"
r = json.load(open(p, encoding="utf-8"))
g = r["result"]["gantt_telemetry"]
spans = g["spans"]
origin = g["origin_ns"]

from comfymodal_runtime.gantt_telemetry import _render_gantt, _pick_scale_ms, LANES

scale = _pick_scale_ms(spans, max_chars=120)
lines = _render_gantt(spans, origin_ns=origin, scale_ms_per_char=scale, title="V2 REMOTE GANTT (reconstructed from captured spans)")
text = "\n".join(lines)
print(text)
print()
print("BLOCK_CHAR_COUNT:", text.count("\u2588"))
print("ORIGIN_NS:", origin)
