"""FAST_UNIT tests for the golden CLIP stage quant-marker CPU step.

CPU-only, duck-typed fakes (no GPU needed): verifies CUDA-marked
``*.comfy_quant`` descriptors move to CPU, everything else is untouched,
and canonical descriptor-free sources are a strict no-op.
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from comfymodal_runtime import golden_serial as gs


pytestmark = pytest.mark.fast_unit


class _FakeCudaTensor:
    """Duck-typed CUDA tensor: records .to() calls, returns a sentinel."""

    def __init__(self):
        self.moved_to = []
        self.is_cuda = True

    def to(self, device):
        self.moved_to.append(str(device))
        return "CPU_SENTINEL"


class TestCpuQuantMarkersInPlace:
    def test_moves_cuda_descriptors_leaves_weights(self):
        marker = _FakeCudaTensor()
        weight = torch.zeros(4, 4)
        sd = {"layer.weight": weight, "layer.comfy_quant": marker}
        moved = gs._cpu_quant_markers_in_place([sd])
        assert moved == 1
        assert marker.moved_to == ["cpu"]
        assert sd["layer.comfy_quant"] == "CPU_SENTINEL"
        assert sd["layer.weight"] is weight

    def test_cpu_descriptors_untouched(self):
        marker = torch.tensor([1, 2, 3], dtype=torch.uint8)
        sd = {"layer.weight": torch.zeros(2, 2),
              "layer.comfy_quant": marker}
        assert gs._cpu_quant_markers_in_place([sd]) == 0
        assert sd["layer.comfy_quant"] is marker

    def test_descriptor_free_source_is_noop(self):
        sd = {"a.weight": torch.zeros(2, 2),
              "b.weight_scale": torch.tensor(1.0)}
        before = dict(sd)
        assert gs._cpu_quant_markers_in_place([sd]) == 0
        assert sd == before

    def test_never_raises_on_garbage(self):
        assert gs._cpu_quant_markers_in_place(None) == 0
        assert gs._cpu_quant_markers_in_place("nope") == 0
        assert gs._cpu_quant_markers_in_place([None, 42, "x"]) == 0
