"""Contract tests for generic TextGenerate substitution (never-raise, parity)."""

import os
import sys

import pytest
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comfymodal_runtime import golden_generic_text as ggt


class _FakeConfig:
    def __init__(self, stop_tokens):
        self.stop_tokens = stop_tokens


class _FakeModelNS:
    """Mimics the transformer surface the optimized loop consumes."""

    def __init__(self, script, vocab=64, stop_tokens=(5,)):
        self._script = list(script)
        self._calls = 0
        self.vocab = vocab
        self.config = _FakeConfig(list(stop_tokens))
        self.forward = self._forward
        self.embedded: list[int] = []

    def _forward(self, *args, **kwargs):
        self._calls += 1
        token = self._script[min(self._calls - 1, len(self._script) - 1)]
        x = torch.zeros(1, 1, 8)
        x._next_token = token
        past = kwargs.get("past_key_values")
        return x, None, past

    def embed_tokens(self, ids):
        self.embedded.append(int(ids[0][0]))
        return torch.zeros(1, 1, 8)


class _FakeGen:
    def __init__(self, script, stop_tokens=(5,)):
        self.model = _FakeModelNS(script, stop_tokens=stop_tokens)
        self._script = list(script)

    def init_kv_cache(self, *args, **kwargs):
        return ("kv",)

    def logits(self, x):
        token = getattr(x, "_next_token", 1)
        logits = torch.full((1, 1, 64), -1e9)
        logits[0, 0, token] = 0.0
        return logits

    def sample_token(self, logits, *args, **kwargs):
        return torch.argmax(logits, dim=-1, keepdim=True)


def _reference_native_loop(gen, steps, stop_tokens):
    """Inline copy of upstream BaseGenerate.generate semantics (greedy)."""
    kv = gen.init_kv_cache(1, 8, "cpu", torch.float32)
    embeds = torch.zeros(1, 2, 8)
    out = []
    current = None
    for _ in range(steps):
        x, _, kv = gen.model.forward(
            None, embeds=embeds, attention_mask=None, past_key_values=kv,
            input_ids=current, position_ids=None, embeds_info=None,
        )
        nxt = gen.sample_token(gen.logits(x)[:, -1], 1.0, 0, 1.0, 0.0, 1.0,
                               out, None, do_sample=False)
        tid = nxt[0].item()
        out.append(tid)
        embeds = gen.model.embed_tokens(nxt)
        current = nxt
        if tid in stop_tokens:
            break
    return out


@pytest.mark.parametrize("eos_batch", [1, 3, 8, 64])
def test_loop_parity_with_stop_token(monkeypatch, eos_batch):
    monkeypatch.setenv("COMFYMODAL_V2_TEXT_EOS_BATCH", str(eos_batch))
    script = [1, 2, 3, 5, 9, 9]  # stop token 5 at index 3
    expected = _reference_native_loop(_FakeGen(script), 6, [5])
    gen = _FakeGen(script)
    got = ggt.optimized_generate_ids(
        gen, torch.zeros(1, 2, 8), {"position_ids": None,
                                    "visual_pos_masks": None,
                                    "deepstack": None, "embeds_info": None},
        do_sample=False, max_length=6, temperature=1.0, top_k=0,
        top_p=1.0, min_p=0.0, repetition_penalty=1.0, seed=0,
    )
    assert got == expected == [1, 2, 3, 5]


def test_loop_no_eos_runs_full_length():
    script = [1, 2, 3, 4, 6, 7]
    gen = _FakeGen(script, stop_tokens=(99,))
    got = ggt.optimized_generate_ids(
        gen, torch.zeros(1, 2, 8), {},
        do_sample=False, max_length=6, temperature=1.0, top_k=0,
        top_p=1.0, min_p=0.0, repetition_penalty=1.0, seed=0,
    )
    assert got == script


def test_loop_overshoot_bounded_by_batch(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_V2_TEXT_EOS_BATCH", "4")
    script = [1, 5, 9, 9, 9, 9, 9, 9]
    gen = _FakeGen(script)
    got = ggt.optimized_generate_ids(
        gen, torch.zeros(1, 2, 8), {},
        do_sample=False, max_length=8, temperature=1.0, top_k=0,
        top_p=1.0, min_p=0.0, repetition_penalty=1.0, seed=0,
    )
    assert got == [1, 5]
    # Loop stopped at the first scan at/after the stop token, not max_length.
    assert gen.model._calls <= 4


def test_compose_fails_closed():
    assert ggt.compose_generic_text_generate(
        clip=None, prompt="hi", max_length=8, sampling_mode={},
    )["ok"] is False
    assert ggt.compose_generic_text_generate(
        clip=object(), prompt="hi", max_length=8, sampling_mode={},
    )["ok"] is False


def test_install_off_by_default(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_V2_TEXT_SUBSTITUTION", raising=False)
    assert ggt.install_text_dispatch_substitution(
        trace_emit=None, request_id="r") is None


def test_resolve_generator_finds_nested():
    gen = _FakeGen([1])

    class Clip:
        pass

    clip = Clip()
    clip.cond_stage_model = {"clip": gen}  # mapping branch unsupported
    assert ggt._resolve_generator(object()) is None

    class Wrap:
        pass

    w = Wrap()
    w.cond_stage_model = gen
    assert ggt._resolve_generator(w) is gen
