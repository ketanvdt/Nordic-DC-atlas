"""Apply exclusion layers from the YAML registry to grid_cells.

The legacy v1 path (this module) is for layers whose ingest is light-weight:
read a GPKG, apply one of {intersects, overlap_50, centroid, buffer}, set the
boolean column. Heavier layers (with staging tables and OSM-specific quirks)
go through `real_ingest.py`. Both modules now read the same registry.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from sqlalchemy import text

from src.common.db import get_engine
from src.common.layer_registry import ExclusionRuntime, exclusions_with_runtime


def apply_exclusion_layer(runtime: ExclusionRuntime) -> str:
    source_path = Path(runtime.source)
    if not source_path.exists():
        return f"[skip] {runtime.column}: missing {source_path}"

    gdf = gpd.read_file(source_path)
    if gdf.empty:
        return f"[skip] {runtime.column}: no features"
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:4326")
    if runtime.strategy == "buffer" and runtime.buffer_m:
        gdf = gdf.to_crs("EPSG:3035")
        gdf["geometry"] = gdf.buffer(runtime.buffer_m)
        gdf = gdf.to_crs("EPSG:4326")

    union = gdf.unary_union
    engine = get_engine()
    column = runtime.column
    if runtime.strategy == "centroid":
        sql = f"""
            UPDATE grid_cells
            SET {column} = ST_Contains(ST_GeomFromText(:geom, 4326), ST_Centroid(geom_4326))
        """
    elif runtime.strategy in {"overlap_50", "buffer"}:
        sql = f"""
            UPDATE grid_cells
            SET {column} =
              ST_Area(ST_Intersection(geom_4326::geography, ST_GeomFromText(:geom, 4326)::geography))
              / NULLIF(ST_Area(geom_4326::geography), 0) >= 0.5
        """
    elif runtime.strategy == "intersects":
        sql = f"""
            UPDATE grid_cells
            SET {column} = ST_Intersects(geom_4326, ST_GeomFromText(:geom, 4326))
        """
    else:
        raise ValueError(f"Unknown strategy: {runtime.strategy}")

    with engine.begin() as conn:
        conn.execute(text(sql), {"geom": union.wkt})
    return f"[applied] {column}"


def exclusion_coverage_report() -> dict[str, float]:
    engine = get_engine()
    columns = [s.exclusion_runtime.column for s in exclusions_with_runtime()]
    report: dict[str, float] = {}
    with engine.begin() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM grid_cells")).scalar_one() or 1
        for column in columns:
            value = conn.execute(text(f"SELECT COUNT(*) FROM grid_cells WHERE {column} = TRUE")).scalar_one()
            report[column] = float(value) / float(total)
    return report


def run_all_exclusions() -> None:
    for spec in exclusions_with_runtime():
        runtime = spec.exclusion_runtime
        assert runtime is not None  # exclusions_with_runtime guarantees this
        msg = apply_exclusion_layer(runtime)
        print(msg)
    coverage = exclusion_coverage_report()
    total_with_hits = sum(1 for v in coverage.values() if v > 0)
    print(f"coverage layers with removals: {total_with_hits}")
    print(coverage)


if __name__ == "__main__":
    run_all_exclusions()
