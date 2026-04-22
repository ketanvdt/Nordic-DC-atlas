from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import yaml
from sqlalchemy import text

from src.common.db import get_engine


@dataclass
class ExclusionLayer:
    key: str
    strategy: str
    buffer_m: int | None = None


def _load_layers(config_path: str = "config/layers.yaml") -> list[ExclusionLayer]:
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    return [
        ExclusionLayer(
            key=item["key"],
            strategy=item.get("strategy", "overlap_50"),
            buffer_m=item.get("buffer_m"),
        )
        for item in cfg.get("exclusions", [])
    ]


def apply_exclusion_layer(layer: ExclusionLayer) -> None:
    source_path = Path("data/processed") / f"{layer.key}.gpkg"
    if not source_path.exists():
        print(f"[skip] {layer.key}: missing {source_path}")
        return

    gdf = gpd.read_file(source_path)
    if gdf.empty:
        print(f"[skip] {layer.key}: no features")
        return
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:4326")
    if layer.strategy == "buffer" and layer.buffer_m:
        gdf = gdf.to_crs("EPSG:3035")
        gdf["geometry"] = gdf.buffer(layer.buffer_m)
        gdf = gdf.to_crs("EPSG:4326")

    union = gdf.unary_union
    engine = get_engine()
    flag_column = f"excl_{layer.key}"
    sql = None
    if layer.strategy == "centroid":
        sql = f"""
            UPDATE grid_cells
            SET {flag_column} = ST_Contains(ST_GeomFromText(:geom, 4326), ST_Centroid(geom_4326))
        """
    elif layer.strategy in {"overlap_50", "buffer"}:
        sql = f"""
            UPDATE grid_cells
            SET {flag_column} =
              ST_Area(ST_Intersection(geom_4326::geography, ST_GeomFromText(:geom, 4326)::geography))
              / NULLIF(ST_Area(geom_4326::geography), 0) >= 0.5
        """
    else:
        raise ValueError(f"Unknown strategy: {layer.strategy}")

    with engine.begin() as conn:
        conn.execute(text(sql), {"geom": union.wkt})
        print(f"[applied] {layer.key}")


def exclusion_coverage_report() -> dict[str, float]:
    engine = get_engine()
    flags = [
        "excl_natura2000", "excl_protected", "excl_floodplain", "excl_heritage", "excl_airport",
        "excl_airport_ols", "excl_military", "excl_steep_slope", "excl_seveso",
        "excl_water_protected", "excl_urban_industrial", "excl_sami_reindeer",
    ]
    report: dict[str, float] = {}
    with engine.begin() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM grid_cells")).scalar_one() or 1
        for flag in flags:
            value = conn.execute(text(f"SELECT COUNT(*) FROM grid_cells WHERE {flag} = TRUE")).scalar_one()
            report[flag] = float(value) / float(total)
    return report


def run_all_exclusions() -> None:
    for layer in _load_layers():
        apply_exclusion_layer(layer)
    coverage = exclusion_coverage_report()
    total_removed = len([k for k, v in coverage.items() if v > 0])
    print(f"coverage layers with removals: {total_removed}")
    print(coverage)


if __name__ == "__main__":
    run_all_exclusions()
