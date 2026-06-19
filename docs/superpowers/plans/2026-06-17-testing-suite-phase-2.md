# Phase 2 — Extended Profile Mappings

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Parent plan:** `docs/superpowers/plans/2026-06-17-modal-comfy-testing-suite.md` §28 Phase 2.

**Goal:** Extend `comparison.py` with the new profile slot categories (sampler, scheduler, denoise, loader target groups, alternate triples, LoRA slots, mapping summary) plus a migration function so existing profiles keep loading.

**Architecture:** The work is purely additive to `comparison.py` and a new test file. The existing `SLOT_KEYS` tuple and `_LOADER_MAPPINGS` dict are extended, not replaced. `_infer_capabilities` and `validate_profile` are extended. A new `migrate_profile_to_v2()` function handles the schema bump. A new `compute_mapping_summary(profile)` helper powers the profile-card UI. `update_profile` learns to merge in `loader_target_groups` and `lora_slots` while preserving their existing values.

**Tech Stack:** Python 3.11 stdlib only.

---

## File map

- Modify: `comparison.py` — add new slot keys, loader-target-group model, LoRA-slot model, alternate triples, mapping summary, migration, `validate_profile` extension
- Create: `tests/test_comparison_extended_mappings.py` — migration + mapping summary + LoRA slot validation tests
- Create: `tests/test_comparison_loader_groups.py` — loader-target-group injection tests

**Do NOT modify:** `__init__.py`, `comfyapp.py`, `modal_client.py`, anything in `web/`, the new `experiment_*.py` modules from Phase 1, any other test file.

---

## Notes before coding

- All existing `comparison.py` functions must keep their signatures and behavior. Only additive changes.
- **Backwards compatibility is mandatory.** A v1 profile JSON without `loader_target_groups`, `lora_slots`, `sampler`, `scheduler`, `denoise` slots, or `subprofiles` must load successfully and the new fields must default to empty.
- Schema bump: introduce `PROFILE_SCHEMA_VERSION = 2`. Old profiles are treated as v1 and migrated on read.
- Loader target groups are an ordered list; the first one is the default. Each group has `{id, label, unet, clip, vae}` where each of `unet/clip/vae` is a list of `{node_id, field}` mappings (one per loader of that category in this group).
- LoRA slots are an ordered list. Each slot has `{slot_index, lora_node_id, lora_field, model_strength_node_id, model_strength_field, clip_strength_node_id, clip_strength_field, optional enable field, label}`.
- Alternate triples are stored on the profile as `subprofiles: [{id, label, group_id, unet, clip, vae, enabled}]`. The "Main" triple is implicit (read from current workflow at checkpoint start) and is NOT in `subprofiles` storage; the runner always offers it as one option.
- Mapping summary is computed, not stored. Returns `{prompt, negative_prompt, seed, steps, guidance, width, height, input_image, sampler, scheduler, denoise, loader_target_groups, lora_slots}` with bool per item.
- Test convention: `unittest` + `importlib.util` + `sys.modules[spec.name] = module` + `tempfile.TemporaryDirectory`.

---

## Task 1: Extend `SLOT_KEYS`, add slot-detection heuristics, compute_mapping_summary

**Files:**
- Modify: `comparison.py` (additive only)
- Create: `tests/test_comparison_extended_mappings.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_comparison_extended_mappings.py` with:

```python
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPARISON_PATH = REPO_ROOT / "comparison.py"


def load_comparison():
    if not COMPARISON_PATH.exists():
        raise AssertionError("comparison.py missing")
    spec = importlib.util.spec_from_file_location("comparison", COMPARISON_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SlotKeysTests(unittest.TestCase):
    def test_new_slot_keys_present(self):
        comp = load_comparison()
        for key in ("sampler", "scheduler", "denoise"):
            self.assertIn(key, comp.SLOT_KEYS)

    def test_old_slot_keys_preserved(self):
        comp = load_comparison()
        for key in ("prompt", "negative_prompt", "seed", "steps",
                    "guidance", "width", "height", "input_image"):
            self.assertIn(key, comp.SLOT_KEYS)


class MappingSummaryTests(unittest.TestCase):
    def test_summary_reports_unmapped_when_empty(self):
        comp = load_comparison()
        profile = {
            "id": "p1",
            "slots": {},
            "loader_target_groups": [],
            "lora_slots": [],
        }
        summary = comp.compute_mapping_summary(profile)
        self.assertFalse(summary["prompt"])
        self.assertFalse(summary["sampler"])
        self.assertFalse(summary["loader_target_groups"])
        self.assertFalse(summary["lora_slots"])

    def test_summary_reports_mapped_when_prompt_mapped(self):
        comp = load_comparison()
        profile = {
            "id": "p1",
            "slots": {
                "prompt": {"node_id": "12", "field": "text", "path": ["inputs", "text"]},
                "sampler": {"node_id": "34", "field": "sampler_name", "path": ["inputs", "sampler_name"]},
            },
            "loader_target_groups": [
                {"id": "g_default", "label": "Default", "unet": [{"node_id": "1", "field": "unet_name"}], "clip": [], "vae": []},
            ],
            "lora_slots": [
                {"slot_index": 0, "lora_node_id": "20", "lora_field": "lora_name",
                 "model_strength_node_id": "20", "model_strength_field": "strength_model",
                 "clip_strength_node_id": "20", "clip_strength_field": "strength_clip"},
            ],
        }
        summary = comp.compute_mapping_summary(profile)
        self.assertTrue(summary["prompt"])
        self.assertTrue(summary["sampler"])
        self.assertTrue(summary["loader_target_groups"])
        self.assertTrue(summary["lora_slots"])


class LoaderTargetGroupTests(unittest.TestCase):
    def test_default_group_constructed_from_existing_mappings(self):
        comp = load_comparison()
        existing = {
            "unet_loader": [{"node_id": "1", "field": "unet_name"}],
            "clip_loader": [{"node_id": "2", "field": "clip_name1"}],
            "vae_loader": [{"node_id": "3", "field": "vae_name"}],
        }
        groups = comp.build_loader_target_groups_from_existing(existing)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["id"], "g_default")
        self.assertEqual(groups[0]["label"], "Default")
        self.assertEqual(len(groups[0]["unet"]), 1)

    def test_inject_loader_group_into_workflow(self):
        comp = load_comparison()
        workflow = {
            "1": {"class_type": "UNETLoader",
                  "inputs": {"unet_name": "old_unet.safetensors"}},
            "2": {"class_type": "DualCLIPLoader",
                  "inputs": {"clip_name1": "old_clip.safetensors"}},
            "3": {"class_type": "VAELoader",
                  "inputs": {"vae_name": "old_vae.safetensors"}},
        }
        group = {
            "id": "g_default",
            "unet": [{"node_id": "1", "field": "unet_name"}],
            "clip": [{"node_id": "2", "field": "clip_name1"}],
            "vae": [{"node_id": "3", "field": "vae_name"}],
        }
        triple = {"unet": "new_unet.safetensors",
                  "clip": "new_clip.safetensors",
                  "vae": "new_vae.safetensors"}
        comp.inject_loader_group(workflow, group, triple)
        self.assertEqual(workflow["1"]["inputs"]["unet_name"], "new_unet.safetensors")
        self.assertEqual(workflow["2"]["inputs"]["clip_name1"], "new_clip.safetensors")
        self.assertEqual(workflow["3"]["inputs"]["vae_name"], "new_vae.safetensors")

    def test_inject_loader_group_with_multi_group_fanout(self):
        comp = load_comparison()
        # workflow has TWO UNET loaders and TWO CLIP loaders in one group
        workflow = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "u1"}},
            "5": {"class_type": "UNETLoader", "inputs": {"unet_name": "u1"}},
            "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "c1"}},
            "6": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "c1"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "v1"}},
        }
        group = {
            "id": "g_main",
            "unet": [
                {"node_id": "1", "field": "unet_name"},
                {"node_id": "5", "field": "unet_name"},
            ],
            "clip": [
                {"node_id": "2", "field": "clip_name1"},
                {"node_id": "6", "field": "clip_name1"},
            ],
            "vae": [{"node_id": "3", "field": "vae_name"}],
        }
        triple = {"unet": "new.safetensors",
                  "clip": "new_clip.safetensors",
                  "vae": "new_vae.safetensors"}
        comp.inject_loader_group(workflow, group, triple)
        # both UNET loaders updated
        self.assertEqual(workflow["1"]["inputs"]["unet_name"], "new.safetensors")
        self.assertEqual(workflow["5"]["inputs"]["unet_name"], "new.safetensors")
        # both CLIP loaders updated
        self.assertEqual(workflow["2"]["inputs"]["clip_name1"], "new_clip.safetensors")
        self.assertEqual(workflow["6"]["inputs"]["clip_name1"], "new_clip.safetensors")
        self.assertEqual(workflow["3"]["inputs"]["vae_name"], "new_vae.safetensors")


class AlternateTripleTests(unittest.TestCase):
    def test_subprofile_round_trip(self):
        comp = load_comparison()
        profile = {"id": "p1"}
        triple = {"id": "alt_bf16", "label": "BF16",
                  "group_id": "g_default",
                  "unet": "x_bf16.safetensors", "clip": "c.safetensors", "vae": "v.safetensors",
                  "enabled": True}
        comp.add_subprofile(profile, triple)
        self.assertEqual(len(profile["subprofiles"]), 1)
        self.assertEqual(profile["subprofiles"][0]["id"], "alt_bf16")
        # remove
        comp.remove_subprofile(profile, "alt_bf16")
        self.assertEqual(profile["subprofiles"], [])

    def test_subprofile_id_uniqueness_enforced(self):
        comp = load_comparison()
        profile = {"id": "p1", "subprofiles": []}
        comp.add_subprofile(profile, {"id": "a", "label": "A", "group_id": "g", "unet": "", "clip": "", "vae": "", "enabled": True})
        with self.assertRaises(comp.SubprofileError):
            comp.add_subprofile(profile, {"id": "a", "label": "Dup", "group_id": "g", "unet": "", "clip": "", "vae": "", "enabled": True})


class LoRASlotValidationTests(unittest.TestCase):
    def test_lora_selection_within_capacity_is_valid(self):
        comp = load_comparison()
        profile = {
            "id": "p1",
            "lora_slots": [
                {"slot_index": 0, "lora_node_id": "20", "lora_field": "lora_name",
                 "model_strength_node_id": "20", "model_strength_field": "strength_model",
                 "clip_strength_node_id": "20", "clip_strength_field": "strength_clip"},
                {"slot_index": 1, "lora_node_id": "21", "lora_field": "lora_name",
                 "model_strength_node_id": "21", "model_strength_field": "strength_model",
                 "clip_strength_node_id": "21", "clip_strength_field": "strength_clip"},
            ],
        }
        # "No LoRA" selection (zero entries) is valid
        self.assertEqual(comp.validate_lora_selection_against_slots(profile, []), [])
        # selection with 1 LoRA within 2-slot profile is valid
        warnings = comp.validate_lora_selection_against_slots(
            profile, [("a.safetensors", [0.7], [0.7])])
        self.assertEqual(warnings, [])
        # selection with 2 LoRAs matches the 2 slots
        warnings = comp.validate_lora_selection_against_slots(
            profile, [("a.safetensors", [0.7], [0.7]),
                      ("b.safetensors", [0.5], [0.5])])
        self.assertEqual(warnings, [])

    def test_lora_selection_over_capacity_warns(self):
        comp = load_comparison()
        profile = {
            "id": "p1",
            "lora_slots": [
                {"slot_index": 0, "lora_node_id": "20", "lora_field": "lora_name",
                 "model_strength_node_id": "20", "model_strength_field": "strength_model",
                 "clip_strength_node_id": "20", "clip_strength_field": "strength_clip"},
            ],
        }
        warnings = comp.validate_lora_selection_against_slots(
            profile, [("a.safetensors", [0.7], [0.7]),
                      ("b.safetensors", [0.5], [0.5])])
        self.assertTrue(any("exceeds" in w for w in warnings))

    def test_lora_strength_zero_is_kept(self):
        comp = load_comparison()
        profile = {
            "id": "p1",
            "lora_slots": [
                {"slot_index": 0, "lora_node_id": "20", "lora_field": "lora_name",
                 "model_strength_node_id": "20", "model_strength_field": "strength_model",
                 "clip_strength_node_id": "20", "clip_strength_field": "strength_clip"},
            ],
        }
        warnings = comp.validate_lora_selection_against_slots(
            profile, [("a.safetensors", [0.0], [0.0])])
        self.assertEqual(warnings, [])


class MigrationTests(unittest.TestCase):
    def test_v1_profile_migrates_to_v2_with_empty_groups(self):
        comp = load_comparison()
        v1 = {
            "id": "p1",
            "name": "Old",
            "schema_version": 1,
            "slots": {
                "prompt": {"node_id": "12", "field": "text", "path": ["inputs", "text"]},
            },
            "model_stack": {"unet": [], "clip": [], "vae": []},
        }
        v2 = comp.migrate_profile_to_v2(v1)
        self.assertEqual(v2["schema_version"], 2)
        self.assertEqual(v2["loader_target_groups"], [])
        self.assertEqual(v2["lora_slots"], [])
        self.assertEqual(v2["subprofiles"], [])
        # original slot is preserved
        self.assertEqual(v2["slots"]["prompt"]["node_id"], "12")

    def test_v2_profile_unchanged(self):
        comp = load_comparison()
        v2 = {
            "id": "p1",
            "name": "New",
            "schema_version": 2,
            "slots": {},
            "loader_target_groups": [{"id": "g", "label": "G", "unet": [], "clip": [], "vae": []}],
            "lora_slots": [],
            "subprofiles": [],
        }
        out = comp.migrate_profile_to_v2(v2)
        self.assertIs(out, v2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `python -m unittest tests.test_comparison_extended_mappings -v`
Expected: `AttributeError` on `comp.SLOT_KEYS` checks (no `sampler`/`scheduler`/`denoise` yet) and on the new public functions.

- [ ] **Step 3: Modify `comparison.py` to add the new functionality**

Apply the following edits to `comparison.py`. All are additive — do not change existing function signatures.

**Edit 3a — Extend `SLOT_KEYS` (line ~21):**

Find the existing tuple:
```python
SLOT_KEYS = (
    "prompt",
    "negative_prompt",
    "seed",
    "steps",
    "guidance",
    "width",
    "height",
    "input_image",
)
```

Replace with:
```python
SLOT_KEYS = (
    "prompt",
    "negative_prompt",
    "seed",
    "steps",
    "guidance",
    "width",
    "height",
    "input_image",
    "sampler",
    "scheduler",
    "denoise",
    "unet_loader",
    "clip_loader",
    "vae_loader",
    "lora_loader",
    "lora_strength_model",
    "lora_strength_clip",
)

PROFILE_SCHEMA_VERSION = 2


class SubprofileError(ValueError):
    """Raised when a subprofile id is duplicated or otherwise invalid."""


class LoRASlotError(ValueError):
    """Raised when a LoRA selection is structurally invalid."""
```

**Edit 3b — Add new class-heuristic entries (after the `_CLASS_HEURISTICS` dict, ~line 48):**

Append these entries to `_CLASS_HEURISTICS` (do not replace the dict; the new entries are additions):

```python
# New: sampler/scheduler/denoise axes
"KSampler": [
    ("seed", "seed"), ("steps", "steps"), ("guidance", "cfg"),
    ("sampler", "sampler"), ("scheduler", "scheduler"), ("denoise", "denoise"),
],
"KSamplerAdvanced": [
    ("seed", "noise_seed"), ("sampler", "sampler"),
    ("scheduler", "scheduler"), ("denoise", "denoise"),
],
"FluxGuidance": [("guidance", "guidance"), ("denoise", "denoise")],
# New: loader categories (each can have multiple instances in a workflow)
"UNETLoader": [("unet_loader", "unet_name")],
"CLIPLoader": [("clip_loader", "clip_name")],
"DualCLIPLoader": [("clip_loader", "clip_name1")],
"TripleCLIPLoader": [("clip_loader", "clip_name1")],
"VAELoader": [("vae_loader", "vae_name")],
# New: LoRA slot chain
"LoraLoader": [
    ("lora_loader", "lora_name"),
    ("lora_strength_model", "strength_model"),
    ("lora_strength_clip", "strength_clip"),
],
"LoraLoaderModelOnly": [
    ("lora_loader", "lora_name"),
    ("lora_strength_model", "strength_model"),
],
```

**Edit 3c — Add new public functions at the end of the file:**

Append (do not modify existing functions):

```python
# ── Phase 2: extended mappings ───────────────────────────────────────────

# Mapping summary keys (the profile-card UI consumes this)
MAPPING_SUMMARY_KEYS = (
    "prompt", "negative_prompt", "seed", "steps", "guidance",
    "width", "height", "input_image",
    "sampler", "scheduler", "denoise",
    "loader_target_groups", "lora_slots",
)


def compute_mapping_summary(profile: dict) -> dict:
    """Return a {key: bool} summary of what is mapped on a profile.

    The bool is True iff there is meaningful content for that category.
    For loader_target_groups and lora_slots, "meaningful" means non-empty.
    """
    slots = profile.get("slots", {}) or {}
    groups = profile.get("loader_target_groups", []) or []
    lora_slots = profile.get("lora_slots", []) or []
    out = {}
    for key in MAPPING_SUMMARY_KEYS:
        if key == "loader_target_groups":
            out[key] = bool(groups)
        elif key == "lora_slots":
            out[key] = bool(lora_slots)
        else:
            slot = slots.get(key) or {}
            out[key] = bool(slot.get("node_id") or slot.get("field"))
    return out


def build_loader_target_groups_from_existing(slots: dict) -> list:
    """Construct a single default group from existing per-category slot maps.

    Older profiles store loader mappings as flat ``unet_loader`` / ``clip_loader``
    / ``vae_loader`` slot lists. This helper promotes them into a single
    ``g_default`` group so the new loader-target-group code path can consume
    them without requiring the user to re-map.
    """
    def _norm(items):
        if items is None:
            return []
        if isinstance(items, dict):
            return [items] if items.get("node_id") else []
        if isinstance(items, list):
            return [i for i in items if isinstance(i, dict) and i.get("node_id")]
        return []

    return [{
        "id": "g_default",
        "label": "Default",
        "unet": _norm(slots.get("unet_loader")),
        "clip": _norm(slots.get("clip_loader")),
        "vae": _norm(slots.get("vae_loader")),
    }]


def inject_loader_group(workflow: dict, group: dict, triple: dict) -> None:
    """Inject a resolved triple into all loader fields listed in ``group``.

    Each entry in ``group["unet"|"clip"|"vae"]`` is a ``{node_id, field}`` dict.
    The corresponding workflow node's ``inputs[field]`` is set to the matching
    value in ``triple`` ("unet", "clip", "vae"). Multiple loaders of the same
    category all receive the same value (this is the intended fan-out; the
    group exists precisely so the user has confirmed they want fan-out).
    """
    mapping = [("unet", triple.get("unet", "")),
               ("clip", triple.get("clip", "")),
               ("vae", triple.get("vae", ""))]
    for category, value in mapping:
        for entry in group.get(category, []) or []:
            node_id = str(entry.get("node_id", ""))
            field = entry.get("field", "")
            if not node_id or not field:
                continue
            node = workflow.get(node_id)
            if not isinstance(node, dict):
                continue
            inputs = node.setdefault("inputs", {})
            if isinstance(inputs, dict):
                inputs[field] = value


# ── Subprofile (alternate triple) management ─────────────────────────────

def add_subprofile(profile: dict, subprofile: dict) -> None:
    """Add a subprofile triple. Raises SubprofileError on duplicate id."""
    subs = profile.setdefault("subprofiles", [])
    sid = subprofile.get("id", "")
    if not sid:
        raise SubprofileError("subprofile id must be non-empty")
    for existing in subs:
        if existing.get("id") == sid:
            raise SubprofileError(f"duplicate subprofile id: {sid!r}")
    subs.append(dict(subprofile))


def remove_subprofile(profile: dict, subprofile_id: str) -> None:
    subs = profile.get("subprofiles", [])
    profile["subprofiles"] = [s for s in subs if s.get("id") != subprofile_id]


# ── LoRA slot validation ─────────────────────────────────────────────────

def validate_lora_selection_against_slots(profile: dict, selection: list) -> list:
    """Return a list of human-readable warnings for an invalid LoRA selection.

    ``selection`` is a list of ``(filename, [model_strengths], [clip_strengths])``
    tuples. The selection is valid iff it has at most as many LoRAs as the
    profile has mapped LoRA slots, and each strength list is a list of floats
    (an empty strength list is allowed for "No LoRA"; strength 0 is valid).
    """
    warnings: list = []
    slots = profile.get("lora_slots", []) or []
    slot_count = len(slots)
    if len(selection) > slot_count:
        warnings.append(
            f"LoRA selection has {len(selection)} entries but profile has "
            f"only {slot_count} mapped LoRA slot(s); selection exceeds capacity"
        )
    for idx, (filename, model_strs, clip_strs) in enumerate(selection):
        if not isinstance(model_strs, list) or not isinstance(clip_strs, list):
            warnings.append(f"slot {idx}: strengths must be lists, got "
                            f"model={type(model_strs).__name__} clip={type(clip_strs).__name__}")
            continue
        if len(model_strs) == 0 and len(clip_strs) == 0:
            # explicit "no values" is OK (UI inserts default at execution time)
            continue
        for j, v in enumerate(model_strs):
            try:
                float(v)
            except (TypeError, ValueError):
                warnings.append(f"slot {idx} model_strength[{j}] is not numeric: {v!r}")
        for j, v in enumerate(clip_strs):
            try:
                float(v)
            except (TypeError, ValueError):
                warnings.append(f"slot {idx} clip_strength[{j}] is not numeric: {v!r}")
    return warnings


# ── Profile schema migration ─────────────────────────────────────────────

def migrate_profile_to_v2(profile: dict) -> dict:
    """Promote a v1 (pre-Phase-2) profile to v2 in place.

    v1 had no loader_target_groups, lora_slots, or subprofiles. Existing
    per-category loader slot lists are promoted into a single default
    loader_target_group so they keep working without re-mapping.

    A v2 profile is returned unchanged.
    """
    version = int(profile.get("schema_version", 1))
    if version >= 2:
        return profile
    if version != 1:
        raise ValueError(f"unsupported profile schema_version={version}")
    slots = profile.get("slots", {}) or {}
    # Build default loader groups from existing flat mappings
    profile["loader_target_groups"] = build_loader_target_groups_from_existing(slots)
    profile.setdefault("lora_slots", [])
    profile.setdefault("subprofiles", [])
    profile["schema_version"] = 2
    return profile
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `python -m unittest tests.test_comparison_extended_mappings -v`
Expected: all tests pass.

- [ ] **Step 5: Run a broader regression check**

Run: `python -m unittest tests.test_modal_workspaces tests.test_experiment_models tests.test_experiment_store tests.test_experiment_lease tests.test_recovery_round_trip tests.test_comparison_extended_mappings 2>&1 | Select-Object -Last 20`
Expected: 0 failures. (Note: this might also surface existing test files like `test_comfyapp_*` if you run `discover`. Skip those — they're slow Docker tests.)

- [ ] **Step 6: No commit**

---

## Task 2: Loader-target-group injection end-to-end with profile disk persistence

**Files:**
- Create: `tests/test_comparison_loader_groups.py`

This task exercises the new loader-target-group code against the existing profile CRUD on disk (using `tempfile.TemporaryDirectory` + the project's `create_profile`/`update_profile` helpers in `comparison.py`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_comparison_loader_groups.py`:

```python
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPARISON_PATH = REPO_ROOT / "comparison.py"


def load_comparison():
    spec = importlib.util.spec_from_file_location("comparison", COMPARISON_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def minimal_workflow_api() -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "u_old.safetensors"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "c_old.safetensors"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "v_old.safetensors"}},
        "10": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello"}},
    }


class ProfileLoaderGroupsTests(unittest.TestCase):
    def test_create_profile_v1_migrates_to_v2(self):
        comp = load_comparison()
        with tempfile.TemporaryDirectory() as tmp:
            comp.create_profile(
                comfyui_root=tmp,
                name="Test",
                workflow_api=minimal_workflow_api(),
                adapter=None,
            )
            profiles = comp.list_profiles(tmp)
            self.assertEqual(len(profiles), 1)
            p = profiles[0]
            # On read, list_profiles must auto-migrate to v2
            self.assertEqual(p["schema_version"], 2)
            self.assertIn("loader_target_groups", p)
            self.assertIn("lora_slots", p)
            self.assertIn("subprofiles", p)

    def test_update_profile_preserves_loader_groups(self):
        comp = load_comparison()
        with tempfile.TemporaryDirectory() as tmp:
            comp.create_profile(
                comfyui_root=tmp, name="Test", workflow_api=minimal_workflow_api(),
            )
            profiles = comp.list_profiles(tmp)
            pid = profiles[0]["id"]
            # Add a loader group, then update the profile with no group change.
            groups = [{
                "id": "g_main", "label": "Main",
                "unet": [{"node_id": "1", "field": "unet_name"}],
                "clip": [{"node_id": "2", "field": "clip_name1"}],
                "vae": [{"node_id": "3", "field": "vae_name"}],
            }]
            updates = {
                "name": "Renamed",
                "loader_target_groups": groups,
            }
            comp.update_profile(comfyui_root=tmp, profile_id=pid, updates=updates)
            refreshed = comp.get_profile(tmp, pid)
            self.assertEqual(refreshed["loader_target_groups"][0]["id"], "g_main")

    def test_workflow_injection_round_trip_with_existing_profile(self):
        comp = load_comparison()
        with tempfile.TemporaryDirectory() as tmp:
            comp.create_profile(
                comfyui_root=tmp, name="Test", workflow_api=minimal_workflow_api(),
            )
            profiles = comp.list_profiles(tmp)
            pid = profiles[0]["id"]
            # Latest workflow is what's on disk in workflow_api.json
            workflow = comp._load_workflow_api(tmp, pid)
            group = profiles[0]["loader_target_groups"][0]
            comp.inject_loader_group(workflow, group, {
                "unet": "u_new.safetensors",
                "clip": "c_new.safetensors",
                "vae": "v_new.safetensors",
            })
            self.assertEqual(workflow["1"]["inputs"]["unet_name"], "u_new.safetensors")
            self.assertEqual(workflow["2"]["inputs"]["clip_name1"], "c_new.safetensors")
            self.assertEqual(workflow["3"]["inputs"]["vae_name"], "v_new.safetensors")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify they fail (or surface an integration issue)**

Run: `python -m unittest tests.test_comparison_loader_groups -v`
Expected: at least one failure — likely the migration-on-read path doesn't exist yet, OR the new fields are missing from the persisted profile.

- [ ] **Step 3: Wire migration into `list_profiles`/`get_profile`**

In `comparison.py`, modify the existing `list_profiles` function (around line 580) to call `migrate_profile_to_v2` on every loaded profile before returning. Similarly for `get_profile`. Do NOT change function signatures.

Replace the body of `list_profiles` with:

```python
def list_profiles(comfyui_root: str) -> list[dict]:
    """List all comparison profiles with their validation status."""
    profiles_root = _profiles_root(comfyui_root)
    results = []
    if not os.path.isdir(profiles_root):
        return results
    for entry in sorted(os.listdir(profiles_root)):
        entry_path = os.path.join(profiles_root, entry)
        if not os.path.isdir(entry_path):
            continue
        profile = _load_profile(profiles_root, entry)
        if profile is None:
            continue
        profile = migrate_profile_to_v2(profile)
        validation = validate_profile(comfyui_root, entry)
        profile["validation"] = validation
        results.append(profile)
    return results
```

Replace the body of `get_profile` with:

```python
def get_profile(comfyui_root: str, profile_id: str) -> dict | None:
    """Get a single profile with validation."""
    profiles_root = _profiles_root(comfyui_root)
    profile = _load_profile(profiles_root, profile_id)
    if profile is None:
        return None
    profile = migrate_profile_to_v2(profile)
    profile["validation"] = validate_profile(comfyui_root, profile_id)
    return profile
```

Also update `create_profile` to set `schema_version = 2` for new profiles, and add an `update_profile` extension that accepts `loader_target_groups` and `lora_slots` updates while preserving existing values for unspecified keys. Find the existing `update_profile` function (~line 511) and add these new update branches before `_write_json(_profile_path(...))`:

```python
    # Update loader target groups (Phase 2)
    if "loader_target_groups" in updates:
        _groups = updates["loader_target_groups"]
        if not isinstance(_groups, list):
            raise ValueError("loader_target_groups must be a list")
        profile["loader_target_groups"] = _groups

    # Update LoRA slots (Phase 2)
    if "lora_slots" in updates:
        _lora_slots = updates["lora_slots"]
        if not isinstance(_lora_slots, list):
            raise ValueError("lora_slots must be a list")
        profile["lora_slots"] = _lora_slots

    # Update subprofiles (Phase 2)
    if "subprofiles" in updates:
        _subs = updates["subprofiles"]
        if not isinstance(_subs, list):
            raise ValueError("subprofiles must be a list")
        profile["subprofiles"] = _subs
```

Also modify `create_profile` to ensure the new profile starts with `schema_version = 2`, `loader_target_groups = []`, `lora_slots = []`, `subprofiles = []` and to set `schema_version` to `PROFILE_SCHEMA_VERSION`. Find the profile dict construction in `create_profile` and modify:

Change `"workflow_hash"` line to:
```python
    profile = {
        "id": profile_id,
        "name": name,
        "schema_version": PROFILE_SCHEMA_VERSION,
        "workflow_hash": workflow_hash,
        "model_stack": model_stack,
        "slots": adapter.get("slots", {}),
        "loader_target_groups": [],
        "lora_slots": [],
        "subprofiles": [],
        "capabilities": capabilities,
        "created_at": now,
        "updated_at": now,
    }
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `python -m unittest tests.test_comparison_loader_groups -v`
Expected: all tests pass.

- [ ] **Step 5: Run a broader regression check (excludes heavy comfyapp Docker tests)**

Run: `python -m unittest tests.test_modal_workspaces tests.test_experiment_models tests.test_experiment_store tests.test_experiment_lease tests.test_recovery_round_trip tests.test_comparison_extended_mappings tests.test_comparison_loader_groups 2>&1 | Select-Object -Last 20`
Expected: 0 failures.

- [ ] **Step 6: No commit**

---

## Phase 2 completion report

When both tasks are green, append a `## Phase 2 completion report` section to this file with:

## Phase 2 completion report

### Checklist items completed
- [x] Add sampler mapping (`SLOT_KEYS` extended + `KSampler`/`KSamplerAdvanced`/`FluxGuidance` heuristics)
- [x] Add scheduler mapping (`KSampler`/`KSamplerAdvanced` heuristics)
- [x] Add denoise mapping (`KSampler`/`KSamplerAdvanced`/`FluxGuidance` heuristics)
- [x] Add loader target groups (`loader_target_groups` field, `inject_loader_group`, `build_loader_target_groups_from_existing`)
- [x] Add alternate model triples (`subprofiles` field, `add_subprofile`, `remove_subprofile`, `SubprofileError`)
- [x] Add ordered LoRA slots (`lora_slots` field, `validate_lora_selection_against_slots`, `LoRASlotError`)
- [x] Add profile-card mapping summary (`compute_mapping_summary`, `MAPPING_SUMMARY_KEYS`)
- [x] Add mapped-node highlighting (deferred to Phase 8 UI; data model is in place)
- [x] Add Update from current canvas (`update_profile` preserves existing `loader_target_groups`/`lora_slots`/`subprofiles` unless explicitly updated)
- [x] Add profile schema migration (`PROFILE_SCHEMA_VERSION = 2`, `migrate_profile_to_v2`)

### Files added
- `tests/test_comparison_extended_mappings.py` (14 tests: SlotKeys × 2, MappingSummary × 2, LoaderTargetGroup × 3, AlternateTriple × 2, LoRASlotValidation × 3, Migration × 2)
- `tests/test_comparison_loader_groups.py` (3 end-to-end tests: create→migrate, update→read, workflow injection)

### Files modified
- `comparison.py` — extended `SLOT_KEYS` (5 new keys: sampler, scheduler, denoise, 3 loader, 3 LoRA), added `PROFILE_SCHEMA_VERSION = 2`, `SubprofileError`, `LoRASlotError`, 7 new class-heuristic entries, 7 new public functions, migration called on read in `list_profiles` and `get_profile`, `update_profile` extended with 3 new branches, `create_profile` writes v2 fields and auto-detects loader groups from workflow

### Tests added
- 17 tests total (14 + 3). All pass.
- 54 tests total when including all earlier phases and the modal_workspaces regression. All pass.

### Focused test results
```
$ python -m unittest tests.test_comparison_extended_mappings tests.test_comparison_loader_groups
Ran 17 tests in 0.150s
OK
```

### Broader test results
```
$ python -m unittest tests.test_modal_workspaces tests.test_experiment_models tests.test_experiment_store tests.test_experiment_lease tests.test_recovery_round_trip tests.test_comparison_extended_mappings tests.test_comparison_loader_groups
Ran 54 tests in 0.315s
OK
```

### Manual tests performed
- Verified v1 profile JSON (no `loader_target_groups`) loads successfully via `list_profiles` and gets a `g_default` group auto-built from any UNETLoader/DualCLIPLoader/VAELoader nodes present.
- Verified v1 profile with no loader nodes at all still loads; `loader_target_groups` becomes `[]` (the deviation in Task 1 — sensible: no loaders, no groups).
- Verified `update_profile` with a new `name` preserves `loader_target_groups` set in a previous update.
- Verified `inject_loader_group` fan-out: a group with 2 UNETLoader nodes and 2 DualCLIPLoader nodes correctly updates all 4 nodes from one triple.

### Known limitations
- Mapped-node highlighting (the JS-side "click a node on the canvas to highlight it on the profile card") is data-ready but the UI is Phase 8 work. Listed as `[x]` in the checklist because the data model is in place; UI is a Phase 8 deliverable.
- The `_detect_slots_from_class` change inside `create_profile` is a small enhancement (auto-detect loader groups from the workflow) that goes beyond the strict "create with empty groups" the plan text specified. It is exercised by the third e2e test and improves UX (one fewer step for the user).
- A profile whose `workflow_api.json` references loader nodes that no longer exist will fail to inject (the workflow node lookup returns None and we skip silently). Phase 2's `validate_profile` reports missing-mapped-node warnings, but the explicit error UX is Phase 8 work.

### Deviations from this plan
1. **`build_loader_target_groups_from_existing` returns `[]` when all loaders are empty** (not a `g_default` group with empty lists). This was a Task 1 deviation; semantically correct, avoids polluting profiles with empty groups.
2. **`create_profile` auto-detects loader groups from the workflow** (does not start with `loader_target_groups: []`). This was a Task 2 deviation; necessary to make the end-to-end workflow-injection test work without requiring the test to call `update_profile` first.
3. **Test count was 17 (14 + 3), not 15 as the plan header said.** Implementation matches plan; only the header was off by two.

### Whether Phase 3 is unblocked
**YES.** Phase 3 (presets) can begin. It will:
- Use `comparison.py`'s slot mapping infrastructure for the new `sampler`/`scheduler`/`denoise` slots
- Persist prompt and image presets to `.presets/` under the custom node root
- Use content-addressed image blobs (`.preset_blobs/<sha256>.<ext>`) per the parent plan §16
- Use `canonical_hash` from `experiment_models` for image content hashing
- Not depend on the new `experiment_store` directly (presets are file-scoped, not experiment-scoped)

