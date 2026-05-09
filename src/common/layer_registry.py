"""Single source of truth for layer metadata.

Every YAML in `config/layers/*.yaml` (excluding `_template.yaml`,
`_index.yaml`, and `README.md`) describes one layer. The optional `runtime`
block maps that layer to the code path that ingests it.

A layer without a `runtime` block is "described but not yet wired" — the
registry still loads it so the freshness panel can show it as missing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


_REGISTRY_DIR = Path("config/layers")
_SKIP_FILES = {"_template.yaml", "_index.yaml"}


@dataclass(frozen=True)
class ExclusionRuntime:
    column: str                          # boolean column on grid_cells, e.g. excl_natura2000
    source: str                          # path to GPKG/GeoJSON/CSV, e.g. data/processed/natura2000.gpkg
    strategy: str                        # intersects | overlap_50 | centroid | buffer
    buffer_m: int | None = None          # required when strategy == "buffer"


@dataclass(frozen=True)
class DistanceTarget:
    column: str                          # numeric column on grid_cells, e.g. dist_substation_400kv_m
    voltage_band_kv: tuple[int, int] | None = None


@dataclass(frozen=True)
class DistanceRuntime:
    targets: tuple[DistanceTarget, ...]
    source: str
    strategy: str = "nearest_distance"


@dataclass(frozen=True)
class OverlayTierRuntime:
    column: str                          # numeric column on grid_cells, e.g. grid_capacity_heatmap
    source: str                          # data/manual/grid_capacity_heatmap.geojson
    tier_property: str                   # GeoJSON feature property carrying the tier (0..tier_max)
    tier_max: int                        # max tier value, used for normalization
    source_tracking_column: str | None = None  # e.g. grid_capacity_source — set to "manual_digitization" when overridden


@dataclass(frozen=True)
class LayerSpec:
    layer_id: str
    category: str                        # exclusion | feature | base
    countries: tuple[str, ...]
    priority: str                        # W1 | W2 | W3 | W4
    exclusion_semantics: str | None
    score_sign: str | int | None
    status: str
    license: str
    native_crs: str
    update_cadence: str
    runtime_kind: str | None = None      # exclusion | distance | overlay_tier | None (not wired)
    exclusion_runtime: ExclusionRuntime | None = None
    distance_runtime: DistanceRuntime | None = None
    overlay_tier_runtime: OverlayTierRuntime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def _parse_runtime(runtime: dict[str, Any]) -> tuple[
    str | None,
    ExclusionRuntime | None,
    DistanceRuntime | None,
    OverlayTierRuntime | None,
]:
    if not runtime:
        return None, None, None, None
    kind = runtime.get("kind")
    if kind == "exclusion":
        return (
            "exclusion",
            ExclusionRuntime(
                column=runtime["column"],
                source=runtime["source"],
                strategy=runtime["strategy"],
                buffer_m=runtime.get("buffer_m"),
            ),
            None,
            None,
        )
    if kind == "distance":
        targets = tuple(
            DistanceTarget(
                column=t["column"],
                voltage_band_kv=tuple(t["voltage_band_kv"]) if t.get("voltage_band_kv") else None,
            )
            for t in runtime["targets"]
        )
        return (
            "distance",
            None,
            DistanceRuntime(
                targets=targets,
                source=runtime["source"],
                strategy=runtime.get("strategy", "nearest_distance"),
            ),
            None,
        )
    if kind == "overlay_tier":
        return (
            "overlay_tier",
            None,
            None,
            OverlayTierRuntime(
                column=runtime["column"],
                source=runtime["source"],
                tier_property=runtime["tier_property"],
                tier_max=int(runtime["tier_max"]),
                source_tracking_column=runtime.get("source_tracking_column"),
            ),
        )
    raise ValueError(f"Unknown runtime.kind: {kind!r}")


def _load_one(path: Path) -> LayerSpec:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} did not parse as a mapping")
    for required in ("layer_id", "category", "priority", "status"):
        if required not in raw:
            raise ValueError(f"{path}: missing required field {required!r}")

    if raw["layer_id"] != path.stem:
        raise ValueError(f"{path}: layer_id {raw['layer_id']!r} must match filename")

    dataset = raw.get("dataset") or {}
    runtime = raw.get("runtime") or {}
    kind, excl_rt, dist_rt, overlay_rt = _parse_runtime(runtime)

    return LayerSpec(
        layer_id=raw["layer_id"],
        category=raw["category"],
        countries=tuple(raw.get("countries") or ()),
        priority=raw["priority"],
        exclusion_semantics=raw.get("exclusion_semantics"),
        score_sign=raw.get("score_sign"),
        status=raw["status"],
        license=str(dataset.get("license", "unknown")),
        native_crs=str(dataset.get("native_crs", "unknown")),
        update_cadence=str(dataset.get("update_cadence", "unknown")),
        runtime_kind=kind,
        exclusion_runtime=excl_rt,
        distance_runtime=dist_rt,
        overlay_tier_runtime=overlay_rt,
        raw=raw,
    )


@lru_cache(maxsize=1)
def load_layers(registry_dir: str = str(_REGISTRY_DIR)) -> dict[str, LayerSpec]:
    base = Path(registry_dir)
    out: dict[str, LayerSpec] = {}
    for path in sorted(base.glob("*.yaml")):
        if path.name in _SKIP_FILES:
            continue
        spec = _load_one(path)
        out[spec.layer_id] = spec
    return out


def exclusions_with_runtime() -> list[LayerSpec]:
    return [s for s in load_layers().values() if s.runtime_kind == "exclusion"]


def distances_with_runtime() -> list[LayerSpec]:
    return [s for s in load_layers().values() if s.runtime_kind == "distance"]


def overlay_tiers_with_runtime() -> list[LayerSpec]:
    return [s for s in load_layers().values() if s.runtime_kind == "overlay_tier"]
