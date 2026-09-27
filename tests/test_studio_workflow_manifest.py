"""Tests for studio_workflow_manifest (pure module).

Runs with plain ``python tests/test_studio_workflow_manifest.py`` (includes a
``__main__`` harness) and is also pytest-discoverable.
"""

import ast
import os
import sys
import tempfile
import types
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import studio_workflow_manifest as m


# ── Shared helpers ────────────────────────────────────────────────────────


def make_graph():
    return {
        "nodes": [
            {"id": 1, "type": "CLIPTextEncode", "inputs": {"text": "a serene mountain lake"}},
            {"id": 2, "type": "CheckpointLoaderSimple", "inputs": {}},
            {"id": 3, "type": "KSampler", "inputs": {"seed": 42, "steps": 20}},
        ],
        "links": [{"source": 1, "target": 3, "slot": "conditioning"}],
        "extra": {"group_nodes": [], "version": 0.4},
    }


def make_sections():
    workflow_id = "wf_0123456789abcdef"
    version_id = "wv_fedcba9876543210"
    graph = make_graph()
    wf = {
        "workflow_id": workflow_id,
        "version_id": version_id,
        "graph": graph,
        "graph_hash": m.graph_hash(graph),
        "display": {"name": "Test Workflow", "description": "A fixture workflow"},
        "source": {"author": "fixture", "url": "https://example.com/workflows/test"},
    }
    vs = {
        "workflow_version_id": version_id,
        "workflow_id": workflow_id,
        "version_number": 1,
        "immutable": True,
        "graph_hash": m.graph_hash(graph),
        "created_at": "2026-08-14T00:00:00+00:00",
    }
    mp = {
        "mapping_id": "wm_1122334455667788",
        "workflow_version_id": version_id,
        "output_node_id": "3",
        "entries": {
            "positive_prompt": {
                "semantic_role": "positive_prompt",
                "node_id": "1",
                "input_name": "text",
                "output_name": "",
                "kind": "node_input",
                "data_type": "STRING",
                "enum_options": [],
                "minimum": None,
                "maximum": None,
                "step": None,
                "required": True,
                "multiline": True,
                "control_kind": "multiline",
                "display_name": "Positive Prompt",
            },
            "seed": {
                "semantic_role": "seed",
                "node_id": "3",
                "input_name": "seed",
                "output_name": "",
                "kind": "widget",
                "data_type": "INT",
                "enum_options": [],
                "minimum": 0,
                "maximum": 2**32 - 1,
                "step": 1,
                "required": False,
                "multiline": False,
                "control_kind": "integer",
                "display_name": "Seed",
            },
        },
    }
    presets = [
        {
            "preset_id": "wpres_0011223344556677",
            "workflow_version_id": version_id,
            "workflow_id": workflow_id,
            "name": "Default Quality",
            "description": "Quality preset",
            "values": {"positive_prompt": "a cat", "seed": 7, "steps": 25},
            "model_choices": {"model": "sdxl_base.safetensors"},
            "lora_values": {"lora1": 0.7},
            "exposed_controls": ["positive_prompt", "seed", "steps"],
            "recommended_values": {"steps": 25},
            "favorite": True,
            "tags": ["quality", "default"],
            "dropped_controls": ["negative_prompt"],
            "is_default": True,
            "created_at": "2026-08-14T00:00:00+00:00",
            "updated_at": "2026-08-14T00:00:00+00:00",
        }
    ]
    models = [
        {
            "filename": "sdxl_base.safetensors",
            "sha256": "a" * 64,
            "folder": "checkpoints",
            "model_type": "checkpoint",
            "display_name": "SDXL Base",
            "provider": "huggingface",
            "revision": "main",
            "size": 6876255102,
            "source_urls": [
                "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"
            ],
            "role": "checkpoint",
            "compatibility": "sdxl",
        }
    ]
    custom_nodes = [
        {
            "name": "comfyui-something",
            "display_name": "Something Nodes",
            "repo_url": "https://github.com/example/comfyui-something",
            "revision": "3fa4c9d1e2",
            "classes": ["FooNode", "BarNode"],
        }
    ]
    assets = [
        {
            "filename": "preview.png",
            "sha256": "b" * 64,
            "size": 1024,
            "mime_type": "image/png",
            "role": "thumbnail",
        }
    ]
    metadata = {
        "exported_at": "2026-08-14T12:00:00+00:00",
        "exporter": "studio-manifest-tool",
        "note": "free-form metadata is not validated",
    }
    return {
        "workflow": wf,
        "version": vs,
        "mapping": mp,
        "presets": presets,
        "models": models,
        "custom_nodes": custom_nodes,
        "assets": assets,
        "metadata": metadata,
    }


def make_manifest(**overrides):
    sections = make_sections()
    sections.update(overrides)
    manifest = {
        "manifest_version": m.MANIFEST_SCHEMA_VERSION,
        "workflow": sections["workflow"],
        "version": sections["version"],
        "mapping": sections["mapping"],
        "presets": sections["presets"],
        "models": sections["models"],
        "custom_nodes": sections["custom_nodes"],
        "assets": sections["assets"],
        "metadata": sections["metadata"],
    }
    return manifest


def reverse_dict(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: reverse_dict(o[k]) for k in reversed(list(o))}
    if isinstance(o, list):
        return [reverse_dict(v) for v in o]
    return o


def expect_error(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except m.ManifestValidationError:
        return
    raise AssertionError("expected ManifestValidationError from %r" % func.__name__)


# ── Tests ─────────────────────────────────────────────────────────────────


def test_minimal_valid_manifest():
    s = make_sections()
    minimal = {
        "manifest_version": m.MANIFEST_SCHEMA_VERSION,
        "workflow": s["workflow"],
        "version": s["version"],
        "mapping": s["mapping"],
    }
    m.validate_manifest(minimal)  # must not raise
    parsed = m.parse_manifest(minimal)
    assert set(parsed) == set(m.ROOT_SECTIONS)
    for name in ("presets", "models", "custom_nodes", "assets"):
        assert parsed[name] == []
    assert parsed["metadata"] == {}
    assert parsed["manifest_version"] == 1


def test_full_manifest():
    man = make_manifest()
    m.validate_manifest(man)
    assert man["metadata"]["exported_at"] == "2026-08-14T12:00:00+00:00"
    assert man["workflow"]["display"]["name"] == "Test Workflow"
    assert man["workflow"]["source"]["author"] == "fixture"
    parsed = m.parse_manifest(m.canonical_json(man))
    assert parsed == m.canonicalize(man)
    assert parsed["presets"][0]["is_default"] is True
    assert parsed["models"][0]["sha256"] == "a" * 64
    assert parsed["models"][0]["size"] == 6876255102
    assert parsed["custom_nodes"][0]["classes"] == ["FooNode", "BarNode"]
    assert parsed["assets"][0]["role"] == "thumbnail"


def test_deterministic_serialization():
    man1 = make_manifest()
    man2 = reverse_dict(man1)
    assert m.canonical_json(man1) == m.canonical_json(man2)


def test_deterministic_hash():
    man1 = make_manifest()
    man2 = reverse_dict(man1)
    h1 = m.manifest_hash(man1)
    assert h1 == m.manifest_hash(man2)
    assert len(h1) == 64
    assert h1 == h1.lower()
    changed = make_manifest()
    changed["workflow"]["graph"]["nodes"][0]["inputs"]["text"] = "something else"
    changed["workflow"]["graph_hash"] = m.graph_hash(changed["workflow"]["graph"])
    assert m.manifest_hash(changed) != h1
    meta = make_manifest()
    meta["metadata"] = {"exported_at": "different-timestamp"}
    assert m.manifest_hash(meta) != h1  # metadata changes hash by default
    assert m.manifest_hash(meta, include_metadata=False) == m.manifest_hash(man1, include_metadata=False)


def test_round_trip_parse_serialize():
    man = make_manifest()
    parsed = m.parse_manifest(m.canonical_json(man))
    assert parsed == m.canonicalize(man)
    assert m.canonical_json(parsed) == m.canonical_json(man)
    from_dict = m.parse_manifest(man)
    assert from_dict == parsed
    from_bytes = m.parse_manifest(m.canonical_json(man).encode("utf-8"))
    assert from_bytes == parsed


def test_immutable_version_identity_preserved():
    man = make_manifest()
    vid = man["version"]["workflow_version_id"]
    parsed = m.parse_manifest(m.canonical_json(man))
    assert parsed["version"]["workflow_version_id"] == vid
    assert parsed["workflow"]["version_id"] == vid
    bad = make_manifest()
    bad["workflow"]["version_id"] = "wv_0000000000000000"
    expect_error(m.validate_manifest, bad)


def test_mapping_preserved():
    man = make_manifest()
    man["mapping"]["entries"]["guidance"] = {
        "semantic_role": "guidance",
        "node_id": "8",
        "input_name": "guidance_scale",
        "output_name": "",
        "kind": "widget",
        "data_type": "FLOAT",
        "enum_options": [],
        "minimum": 1.0,
        "maximum": 30.0,
        "step": 0.1,
        "required": False,
        "multiline": False,
        "control_kind": "number",
        "display_name": "Guidance",
        "extension_future_field": {"nested": [1, 2, 3]},
    }
    man["mapping"]["entries"]["positive_prompt"]["extension_meta"] = "x"
    parsed = m.parse_manifest(m.canonical_json(man))
    assert parsed["mapping"]["entries"] == m.canonicalize(man)["mapping"]["entries"]
    assert parsed["mapping"]["entries"]["guidance"]["extension_future_field"] == {"nested": [1, 2, 3]}
    assert parsed["mapping"]["entries"]["positive_prompt"]["extension_meta"] == "x"


def test_multiple_presets():
    man = make_manifest()
    vid = man["version"]["workflow_version_id"]
    man["presets"].extend(
        [
            {
                "preset_id": "wpres_9900000000000001",
                "workflow_version_id": vid,
                "name": "Fast",
                "values": {"steps": 12},
            },
            {
                "preset_id": "wpres_9900000000000002",
                "workflow_version_id": vid,
                "name": "Cinematic",
                "values": {"cfg": 5.0},
            },
        ]
    )
    m.validate_manifest(man)
    parsed = m.parse_manifest(m.canonical_json(man))
    assert len(parsed["presets"]) == 3
    assert [p["preset_id"] for p in parsed["presets"]] == [
        "wpres_0011223344556677",
        "wpres_9900000000000001",
        "wpres_9900000000000002",
    ]


def test_default_preset():
    man = make_manifest()  # exactly one is_default True -> valid
    m.validate_manifest(man)
    bad = make_manifest()
    vid = bad["version"]["workflow_version_id"]
    bad["presets"].append(
        {
            "preset_id": "wpres_9900000000000003",
            "workflow_version_id": vid,
            "name": "Also Default",
            "is_default": True,
        }
    )
    expect_error(m.validate_manifest, bad)


def test_incomplete_preset_preserved():
    man = make_manifest()
    vid = man["version"]["workflow_version_id"]
    man["presets"] = [
        {"preset_id": "wpres_bare1234567890", "workflow_version_id": vid, "name": "Bare Preset"}
    ]
    m.validate_manifest(man)
    parsed = m.parse_manifest(m.canonical_json(man))
    assert set(parsed["presets"][0].keys()) == {"preset_id", "workflow_version_id", "name"}
    assert "is_default" not in parsed["presets"][0]
    assert "values" not in parsed["presets"][0]
    assert "description" not in parsed["presets"][0]


def test_model_references():
    man = make_manifest()
    m.validate_manifest(man)
    parsed = m.parse_manifest(m.canonical_json(man))
    model = parsed["models"][0]
    assert model["filename"] == "sdxl_base.safetensors"
    assert model["sha256"] == "a" * 64
    assert model["size"] == 6876255102
    assert model["source_urls"] == [
        "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"
    ]
    assert model["compatibility"] == "sdxl"
    assert model["role"] == "checkpoint"


def test_same_filename_different_hashes():
    man = make_manifest()
    man["models"].append(
        {"filename": "sdxl_base.safetensors", "sha256": "c" * 64, "size": 100}
    )
    m.validate_manifest(man)
    parsed = m.parse_manifest(m.canonical_json(man))
    hashes = [mod["sha256"] for mod in parsed["models"] if mod["filename"] == "sdxl_base.safetensors"]
    assert hashes == ["a" * 64, "c" * 64]


def test_custom_node_repo_commit():
    man = make_manifest()
    assert man["custom_nodes"][0]["repo_url"]
    assert man["custom_nodes"][0]["revision"]
    parsed = m.parse_manifest(m.canonical_json(man))
    assert parsed["custom_nodes"][0]["repo_url"] == man["custom_nodes"][0]["repo_url"]
    assert parsed["custom_nodes"][0]["revision"] == man["custom_nodes"][0]["revision"]
    bad = make_manifest()
    del bad["custom_nodes"][0]["revision"]
    expect_error(m.validate_manifest, bad)
    bad2 = make_manifest()
    bad2["custom_nodes"][0]["repo_url"] = "  https://github.com/example/whitespace  "
    expect_error(m.validate_manifest, bad2)


def test_missing_dependency_allowed():
    man = make_manifest()
    man["models"] = [{"filename": "ghost.safetensors"}]  # valid: no hash required
    man["custom_nodes"] = [
        {
            "name": "ghost-nodes",
            "repo_url": "https://github.com/ghost/ghost-nodes",
            "revision": "abc123def456",
        }
    ]
    m.validate_manifest(man)  # validate never checks disk/library
    rd = m.check_readiness(man)
    assert rd["ready"] is False
    assert rd["missing"] == ["models: ghost.safetensors (missing hash)"]
    # readiness is purely structural: a custom node without repo/revision is
    # reported too, even on a dict that was never validated.
    raw = {"custom_nodes": [{"name": "ghost-nodes"}]}
    rd2 = m.check_readiness(raw)
    assert rd2["ready"] is False
    assert rd2["missing"] == ["custom_nodes: ghost-nodes (missing repo/revision)"]


def test_unsupported_manifest_version_rejected():
    for v in (2, 0, "1", True):
        man = make_manifest()
        man["manifest_version"] = v
        expect_error(m.validate_manifest, man)


def test_malformed_mapping_rejected():
    man = make_manifest()
    man["mapping"]["entries"] = []
    expect_error(m.validate_manifest, man)
    man = make_manifest()
    man["mapping"]["entries"] = {"seed": "not-a-dict"}
    expect_error(m.validate_manifest, man)
    man = make_manifest()
    man["mapping"]["workflow_version_id"] = "wv_0000000000000000"
    expect_error(m.validate_manifest, man)
    man = make_manifest()
    man["mapping"]["entries"] = {"": {"node_id": "1"}}
    expect_error(m.validate_manifest, man)


def test_duplicate_preset_id_rejected():
    man = make_manifest()
    dup = dict(man["presets"][0])
    dup["name"] = "Second preset"
    dup["is_default"] = False
    man["presets"].append(dup)
    expect_error(m.validate_manifest, man)


def test_duplicate_dependency_identity_rejected():
    man = make_manifest()
    dup_model = dict(man["models"][0])
    dup_model["size"] = 999  # same filename + same sha256 -> duplicate identity
    man["models"].append(dup_model)
    expect_error(m.validate_manifest, man)
    man = make_manifest()
    dup_cn = dict(man["custom_nodes"][0])
    dup_cn["name"] = "different-name"
    man["custom_nodes"].append(dup_cn)  # same (repo_url, revision) pair
    expect_error(m.validate_manifest, man)


def test_executable_workflow_json_preserved():
    man = make_manifest()
    parsed = m.parse_manifest(m.canonical_json(man))
    assert parsed["workflow"]["graph"] == m.canonicalize(man)["workflow"]["graph"]
    assert m.graph_hash(parsed["workflow"]["graph"]) == parsed["workflow"]["graph_hash"]
    assert parsed["workflow"]["graph_hash"] == man["workflow"]["graph_hash"]


def test_unknown_executable_content_treated_as_data():
    man = make_manifest()
    man["workflow"]["graph"] = {
        "nodes": [
            {"id": 1, "type": "CLIPTextEncode", "inputs": {"text": "日本語プロンプト"}},
            {"id": 2, "type": "Nested", "nested": {"a": [1, {"b": None, "c": [[], [1, 2]]}], "unicode": "ünïcødé"}},
        ],
        "links": [],
        "null_thing": None,
        "deep": [1, [2, [3, [4]]]],
        "mixed": {"int": 5, "float": 1.5, "str": "x", "bool": True, "null": None, "list": [True, None, "y"]},
    }
    man["workflow"]["graph_hash"] = m.graph_hash(man["workflow"]["graph"])
    m.validate_manifest(man)
    parsed = m.parse_manifest(m.canonical_json(man))
    assert parsed["workflow"]["graph"] == m.canonicalize(man)["workflow"]["graph"]
    assert parsed["workflow"]["graph"] == man["workflow"]["graph"]


def test_no_side_effects():
    # (a) AST-scan the module source for forbidden identifiers.
    src = (Path(__file__).resolve().parents[1] / "studio_workflow_manifest.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden = (
        "subprocess", "importlib", "urllib", "socket", "os", "sys", "pathlib",
        "eval", "exec", "__import__", "open",
    )
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
    for f in forbidden:
        assert f not in names, "forbidden identifier %r found in module source" % f

    # (b) full pipeline inside a temp cwd must not touch the filesystem.
    with tempfile.TemporaryDirectory() as td:
        before = os.listdir(td)
        old = os.getcwd()
        try:
            os.chdir(td)
            man = m.build_manifest(**make_sections())
            m.validate_manifest(man)
            s = m.canonical_json(man)
            p = m.parse_manifest(s)
            m.manifest_hash(p)
            m.manifest_hash(p, include_metadata=False)
            m.graph_hash(make_graph())
            m.check_readiness(p)
        finally:
            os.chdir(old)
        assert os.listdir(td) == before

    # (c) module namespace exposes only stdlib modules.
    known = ("json", "hashlib", "re", "copy", "math", "typing")
    for name, value in vars(m).items():
        if isinstance(value, types.ModuleType):
            assert value.__name__ in known, "unexpected module import: %r" % value.__name__


# ── __main__ harness (plain python run, module definition order) ──────────


if __name__ == "__main__":
    import traceback

    failed = 0
    total = 0
    for name in list(globals()):
        if name.startswith("test_") and callable(globals()[name]):
            total += 1
            try:
                globals()[name]()
            except Exception:
                failed += 1
                print("FAIL %s" % name)
                traceback.print_exc()
            else:
                print("PASS %s" % name)
    print("== %d/%d passed ==" % (total - failed, total))
    sys.exit(1 if failed else 0)
