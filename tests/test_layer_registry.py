"""Validate the layer registry: every YAML parses, required fields are
present, runtime blocks have the right shape, and the layers known to be
wired in code are all loadable."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.common.layer_registry import (
    distances_with_runtime,
    exclusions_with_runtime,
    load_layers,
    overlay_tiers_with_runtime,
)


REGISTRY = Path("config/layers")


def test_every_yaml_in_registry_loads() -> None:
    layers = load_layers()
    yaml_files = [p for p in REGISTRY.glob("*.yaml") if p.name not in {"_template.yaml", "_index.yaml"}]
    assert len(yaml_files) == len(layers), (
        f"Expected {len(yaml_files)} layer YAMLs to load, got {len(layers)}"
    )


def test_layer_id_matches_filename() -> None:
    layers = load_layers()
    for layer_id, spec in layers.items():
        assert spec.layer_id == layer_id


def test_required_fields_present_on_every_layer() -> None:
    for spec in load_layers().values():
        assert spec.layer_id, spec
        assert spec.category in {"exclusion", "feature", "base"}, spec.category
        assert spec.priority in {"W1", "W2", "W3", "W4"}, spec.priority
        assert spec.status in {"pending_verification", "verified", "blocked", "deferred"}, spec.status


def test_index_yaml_lists_match_registry() -> None:
    """Every active-tier layer in _index.yaml must have a YAML, and every
    YAML in the registry must be listed in _index.yaml. The
    `deferred_or_paid` bucket is exempt: by design those layers have no
    YAMLs yet (their data is paid or otherwise out of v1 scope)."""
    index = yaml.safe_load((REGISTRY / "_index.yaml").read_text(encoding="utf-8"))
    active_listed: set[str] = set()
    deferred_listed: set[str] = set()
    for bucket_name, bucket in index.items():
        if not isinstance(bucket, list):
            continue
        if bucket_name == "deferred_or_paid":
            deferred_listed.update(bucket)
        else:
            active_listed.update(bucket)
    registry_ids = set(load_layers().keys())

    extras_in_index = active_listed - registry_ids
    assert not extras_in_index, f"_index.yaml lists unknown active layers: {extras_in_index}"

    # Registry layers that are also listed under deferred are fine — the
    # index simply documents that we know about them but they are out of
    # v1 scope. Truly missing-from-index layers are the violation.
    missing_in_index = registry_ids - active_listed - deferred_listed
    assert not missing_in_index, f"Registry has YAMLs not in _index.yaml: {missing_in_index}"


def test_exclusion_runtimes_cover_expected_columns() -> None:
    """Every excl_* column the score function references must have a YAML
    with a runtime block, OR be acknowledged as deferred/manual.
    """
    expected = {
        "excl_natura2000",
        "excl_protected",
        "excl_floodplain",
        "excl_heritage",
        "excl_airport",
        "excl_airport_ols",
        "excl_military",
        "excl_steep_slope",
        "excl_seveso",
        "excl_water_protected",
        "excl_urban_industrial",
        "excl_sami_reindeer",
    }
    wired = {s.exclusion_runtime.column for s in exclusions_with_runtime()}
    missing = expected - wired
    assert not missing, f"score function references columns with no registry runtime: {missing}"


def test_distance_runtimes_cover_expected_columns() -> None:
    expected = {
        "dist_substation_400kv_m",
        "dist_substation_130kv_m",
        "dist_transmission_line_m",
    }
    wired: set[str] = set()
    for s in distances_with_runtime():
        for t in s.distance_runtime.targets:
            wired.add(t.column)
    missing = expected - wired
    assert not missing, f"score function references distance columns with no registry runtime: {missing}"


def test_grid_capacity_overlay_is_registered() -> None:
    overlay_ids = {s.layer_id for s in overlay_tiers_with_runtime()}
    assert "grid_capacity_heatmap" in overlay_ids


def test_buffer_strategy_has_buffer_m() -> None:
    for s in exclusions_with_runtime():
        r = s.exclusion_runtime
        if r.strategy == "buffer":
            assert r.buffer_m and r.buffer_m > 0, f"{s.layer_id} buffer strategy missing buffer_m"


def test_load_layers_is_cached() -> None:
    """Sanity: load_layers caches so repeated registry reads in the UI are cheap."""
    a = load_layers()
    b = load_layers()
    assert a is b


@pytest.mark.parametrize("expected_layer_id", [
    "natura_2000",
    "protected_areas",
    "floodplain",
    "heritage",
    "airport",
    "airport_ols",
    "military_zones",
    "slope_gt_10pct",
    "seveso_sites",
    "surface_water_polygons",
    "urban_industrial",
    "sami_reindeer_husbandry",
    "substations",
    "transmission_lines",
    "grid_capacity_heatmap",
])
def test_specific_layer_present(expected_layer_id: str) -> None:
    assert expected_layer_id in load_layers()
