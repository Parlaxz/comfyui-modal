"""Phase-5 style-companion tests: studio_workflow_run._sanitize_studio_style.

Provenance only: the companion never alters execution. A malformed
companion fails loudly; absent means a plain prompt run.
"""
import pytest

pytestmark = pytest.mark.fast_unit

from studio_workflow_run import _sanitize_studio_style


def _valid():
    return {
        "id": "golden-hour-wide",
        "title": "Golden Hour Wide",
        "fragment": "wide film frame, warm low sun",
        "user_prompt": "a lighthouse",
        "catalog_version": 1,
    }


def test_style_none_means_plain_run():
    assert _sanitize_studio_style(None) == (None, None)


def test_style_not_object_errors():
    style, error = _sanitize_studio_style("golden-hour-wide")
    assert style is None
    assert error and "object" in error


def test_style_requires_id_and_fragment():
    style, error = _sanitize_studio_style({"id": "  ", "fragment": "x"})
    assert style is None and error
    style, error = _sanitize_studio_style({"id": "x", "fragment": "  "})
    assert style is None and error


def test_style_valid_shape_strips_unknown_keys():
    raw = dict(_valid())
    raw["injected"] = "drop me"
    style, error = _sanitize_studio_style(raw)
    assert error is None
    assert style == {
        "id": "golden-hour-wide",
        "title": "Golden Hour Wide",
        "fragment": "wide film frame, warm low sun",
        "user_prompt": "a lighthouse",
        "catalog_version": 1,
        "set": "",
    }


def test_style_rejects_bad_types():
    style, error = _sanitize_studio_style(
        {"id": "x", "fragment": "y", "title": 5, "user_prompt": ""}
    )
    assert style is None and error
    style, error = _sanitize_studio_style(
        {"id": "x", "fragment": "y", "title": "", "user_prompt": "", "catalog_version": True}
    )
    assert style is None and error


def test_style_set_preserved_as_provenance():
    raw = dict(_valid())
    raw["set"] = "curated"
    style, error = _sanitize_studio_style(raw)
    assert error is None
    assert style["set"] == "curated"
    # Unknown keys are still stripped alongside a valid set.
    raw["injected"] = "drop me"
    style, error = _sanitize_studio_style(raw)
    assert error is None
    assert style["set"] == "curated"
    assert "injected" not in style


def test_style_set_missing_means_plain_curated_shape():
    # Back-compat: companions written before the set field stay valid and
    # normalize to an empty set rather than failing.
    style, error = _sanitize_studio_style(_valid())
    assert error is None
    assert style["set"] == ""


def test_style_set_must_be_string():
    style, error = _sanitize_studio_style(dict(_valid(), set=5))
    assert style is None and error
    style, error = _sanitize_studio_style(dict(_valid(), set="  curated  "))
    assert error is None
    assert style["set"] == "curated"
