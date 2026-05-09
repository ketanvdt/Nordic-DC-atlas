"""Apply registry-driven layers to grid_cells.

Reads layer specs from `config/layers/*.yaml` via `src.common.layer_registry`
and dispatches each one to the correct execution path:

- runtime.kind == "exclusion"     → set boolean excl_* column
- runtime.kind == "distance"      → set numeric dist_*_m column
- runtime.kind == "overlay_tier"  → override numeric tier column from manual GeoJSON

The thin in-Python alternative in `src.characterize.exclusions` is retained
for cases where a small source layer doesn't need a staging table; it now
reads from the same registry.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import geopandas as gpd
from sqlalchemy import text

from src.common.db import get_engine
from src.common.layer_registry import (
    DistanceRuntime,
    ExclusionRuntime,
    OverlayTierRuntime,
    distances_with_runtime,
    exclusions_with_runtime,
    overlay_tiers_with_runtime,
)


def _record_source(source_key: str, source_url: str, license_name: str, metadata: dict) -> None:
    """Write an entry into `data_sources` so the freshness panel knows this layer is real."""
    engine = get_engine()
    checksum = f"ingested:{datetime.utcnow().isoformat()}Z"
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO data_sources (source_key, source_url, license, checksum, metadata)
                VALUES (:k, :u, :l, :c, CAST(:m AS JSONB))
                ON CONFLICT (source_key) DO UPDATE SET
                  source_url = EXCLUDED.source_url,
                  license = EXCLUDED.license,
                  checksum = EXCLUDED.checksum,
                  metadata = EXCLUDED.metadata,
                  fetched_at = NOW()
                """
            ),
            {"k": source_key, "u": source_url, "l": license_name, "c": checksum, "m": json.dumps(metadata)},
        )


def _parse_voltage_kv(raw: object) -> int | None:
    """OSM voltage tag is free-text: '132000', '132 kV', '132000;220000', '400000 / 220000'."""
    if raw is None:
        return None
    tokens = re.findall(r"\d+", str(raw))
    if not tokens:
        return None
    max_v = max(int(t) for t in tokens)
    if max_v >= 1000:  # likely volts
        return max_v // 1000
    return max_v  # already kV


def _stage_gdf(engine, table: str, gdf: gpd.GeoDataFrame) -> None:
    """Drop-and-create a staging table in public schema with a single geometry column.

    Server-side ST_MakeValid handles invalid polygons after load; we avoid a
    client-side buffer(0) because it allocates a Shapely polygon per feature
    and explodes memory on large OSM datasets.
    """
    gdf = gdf.to_crs("EPSG:4326") if gdf.crs and gdf.crs.to_epsg() != 4326 else gdf
    gdf = gdf[gdf.geometry.notnull()]
    gdf = gdf[~gdf.geometry.is_empty]
    gdf = gdf[gdf.geometry.is_valid]
    if gdf.empty:
        raise RuntimeError(f"_stage_gdf: no valid geometries to load into {table}")

    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
    gdf[["geometry"]].to_postgis(
        table, engine, if_exists="replace", index=True, index_label="row_id", chunksize=2000
    )
    with engine.begin() as conn:
        conn.execute(text(f'UPDATE "{table}" SET geometry = ST_MakeValid(geometry) WHERE NOT ST_IsValid(geometry)'))
        conn.execute(text(f'DELETE FROM "{table}" WHERE geometry IS NULL OR ST_IsEmpty(geometry)'))
        conn.execute(text(f'CREATE INDEX IF NOT EXISTS "{table}_geom_idx" ON "{table}" USING GIST (geometry)'))
        conn.execute(text(f'ANALYZE "{table}"'))


def apply_exclusion(layer_id: str, runtime: ExclusionRuntime) -> dict:
    path = Path(runtime.source)
    if not path.exists():
        return {"layer_id": layer_id, "status": "missing_file", "path": str(path)}
    gdf = gpd.read_file(path)
    if gdf.empty:
        return {"layer_id": layer_id, "status": "empty"}

    engine = get_engine()
    if runtime.strategy == "buffer" and runtime.buffer_m:
        gdf = gdf.to_crs("EPSG:3035")
        gdf["geometry"] = gdf.buffer(runtime.buffer_m)
        gdf = gdf.to_crs("EPSG:4326")

    staging = f"stg_{layer_id}"
    _stage_gdf(engine, staging, gdf)

    flag = runtime.column
    if runtime.strategy == "buffer":
        sql = f"""
        WITH hits AS (
            SELECT DISTINCT g.h3_index
            FROM grid_cells g
            JOIN {staging} s ON ST_Intersects(g.geom_4326, s.geometry)
        )
        UPDATE grid_cells g
        SET {flag} = TRUE
        FROM hits h
        WHERE g.h3_index = h.h3_index
        """
    elif runtime.strategy == "overlap_50":
        sql = f"""
        WITH cell3035 AS (
            SELECT h3_index, ST_Transform(geom_4326, 3035) AS geom, ST_Area(ST_Transform(geom_4326, 3035)) AS cell_area
            FROM grid_cells
        ),
        stage3035 AS (
            SELECT ST_MakeValid(ST_Transform(geometry, 3035)) AS geom FROM {staging}
        ),
        hits AS (
            SELECT
              c.h3_index,
              SUM(ST_Area(ST_Intersection(ST_MakeValid(c.geom), s.geom))) / NULLIF(c.cell_area, 0) AS overlap_ratio
            FROM cell3035 c
            JOIN stage3035 s ON ST_Intersects(c.geom, s.geom)
            GROUP BY c.h3_index, c.cell_area
        )
        UPDATE grid_cells g
        SET {flag} = COALESCE(h.overlap_ratio, 0) >= 0.5
        FROM hits h
        WHERE g.h3_index = h.h3_index
        """
    elif runtime.strategy == "centroid":
        sql = f"""
        UPDATE grid_cells g
        SET {flag} = EXISTS (
            SELECT 1 FROM {staging} s
            WHERE ST_Contains(s.geometry, ST_Centroid(g.geom_4326))
        )
        """
    elif runtime.strategy == "intersects":
        sql = f"""
        WITH hits AS (
            SELECT DISTINCT g.h3_index
            FROM grid_cells g
            JOIN {staging} s ON ST_Intersects(g.geom_4326, s.geometry)
        )
        UPDATE grid_cells g
        SET {flag} = h.h3_index IS NOT NULL
        FROM (SELECT h3_index FROM hits) h
        WHERE g.h3_index = h.h3_index
        """
    else:
        raise ValueError(f"unknown strategy: {runtime.strategy}")

    with engine.begin() as conn:
        conn.execute(text(sql))
        hit_count = conn.execute(
            text(f"SELECT COUNT(*) FROM grid_cells WHERE {flag} = TRUE")
        ).scalar_one()
    _record_source(
        source_key=flag,
        source_url=str(path),
        license_name="see config/layers/" + layer_id + ".yaml",
        metadata={
            "layer_kind": "exclusion",
            "layer_id": layer_id,
            "strategy": runtime.strategy,
            "features": int(len(gdf)),
            "excluded_cells": int(hit_count),
        },
    )
    return {"layer_id": layer_id, "status": "applied", "excluded_cells": int(hit_count), "features": int(len(gdf))}


def apply_distance_layer(layer_id: str, runtime: DistanceRuntime) -> dict:
    path = Path(runtime.source)
    if not path.exists():
        return {"layer_id": layer_id, "status": "missing_file"}
    gdf = gpd.read_file(path)
    if gdf.empty:
        return {"layer_id": layer_id, "status": "empty"}

    if "voltage" in gdf.columns:
        gdf["voltage_kv"] = gdf["voltage"].apply(_parse_voltage_kv)
    else:
        gdf["voltage_kv"] = None

    engine = get_engine()
    results: dict = {"layer_id": layer_id, "features": int(len(gdf)), "columns": {}}

    for target in runtime.targets:
        column = target.column
        band = target.voltage_band_kv
        subset = gdf
        if band is not None:
            lo, hi = band
            subset = gdf[gdf["voltage_kv"].between(lo, hi, inclusive="both")]
        if subset.empty:
            results["columns"][column] = {"status": "no_features_in_voltage_band", "band_kv": band}
            continue

        staging = f"stg_{layer_id}_{column}"
        _stage_gdf(engine, staging, subset[["geometry"]])

        sql = f"""
        WITH nearest AS (
            SELECT
              g.h3_index,
              MIN(ST_Distance(ST_Centroid(g.geom_4326)::geography, s.geometry::geography)) AS dist_m
            FROM grid_cells g
            CROSS JOIN LATERAL (
              SELECT geometry
              FROM {staging}
              ORDER BY {staging}.geometry <-> ST_Centroid(g.geom_4326)
              LIMIT 5
            ) s
            GROUP BY g.h3_index
        )
        UPDATE grid_cells g
        SET {column} = n.dist_m
        FROM nearest n
        WHERE g.h3_index = n.h3_index
        """
        with engine.begin() as conn:
            conn.execute(text(sql))
            stats = conn.execute(
                text(
                    f"SELECT COUNT(*) FILTER (WHERE {column} IS NOT NULL), "
                    f"MIN({column}), AVG({column}), MAX({column}) FROM grid_cells"
                )
            ).first()
        results["columns"][column] = {
            "status": "applied",
            "populated_cells": int(stats[0]),
            "min_m": float(stats[1]) if stats[1] is not None else None,
            "mean_m": float(stats[2]) if stats[2] is not None else None,
            "max_m": float(stats[3]) if stats[3] is not None else None,
            "features_used": int(len(subset)),
        }
        _record_source(
            source_key=column,
            source_url=str(path),
            license_name="see config/layers/" + layer_id + ".yaml",
            metadata={
                "layer_kind": "feature",
                "layer_id": layer_id,
                "voltage_band_kv": list(band) if band else None,
                "features_used": int(len(subset)),
                "populated_cells": int(stats[0]),
            },
        )

    return results


def apply_overlay_tier(layer_id: str, runtime: OverlayTierRuntime) -> dict:
    """Override a numeric column with a tier value from a manual GeoJSON.

    Each cell whose centroid falls inside a feature in the GeoJSON gets its
    `runtime.column` set to (feature[runtime.tier_property] / runtime.tier_max),
    so the value lands on the same 0–1 scale the scoring engine expects.
    Cells outside any polygon are left as set by other characterization steps
    (e.g., the bidding-zone profile baseline for grid_capacity_heatmap).

    If `runtime.source_tracking_column` is set, it is updated to
    "manual_digitization" for overridden cells so the UI can show provenance.
    """
    path = Path(runtime.source)
    if not path.exists():
        return {"layer_id": layer_id, "status": "missing_file", "path": str(path)}
    gdf = gpd.read_file(path)
    if gdf.empty:
        return {"layer_id": layer_id, "status": "empty"}
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:4326")
    if runtime.tier_property not in gdf.columns:
        return {"layer_id": layer_id, "status": "missing_tier_property", "expected": runtime.tier_property}

    engine = get_engine()
    staging = f"stg_{layer_id}"
    # Stage geometry + tier as separate columns. _stage_gdf only ships geometry,
    # so we do this manually here.
    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{staging}" CASCADE'))
    gdf[["geometry", runtime.tier_property]].to_postgis(
        staging, engine, if_exists="replace", index=True, index_label="row_id"
    )
    with engine.begin() as conn:
        conn.execute(
            text(f'UPDATE "{staging}" SET geometry = ST_MakeValid(geometry) WHERE NOT ST_IsValid(geometry)')
        )
        conn.execute(text(f'CREATE INDEX IF NOT EXISTS "{staging}_geom_idx" ON "{staging}" USING GIST (geometry)'))
        conn.execute(text(f'ANALYZE "{staging}"'))

    column = runtime.column
    tier_max = runtime.tier_max
    tier_col = runtime.tier_property
    src_col = runtime.source_tracking_column

    set_clauses = [f"{column} = sub.tier::DOUBLE PRECISION / {tier_max}.0"]
    if src_col:
        set_clauses.append(f"{src_col} = 'manual_digitization'")
    set_sql = ", ".join(set_clauses)

    sql = f"""
    WITH cell_tier AS (
        SELECT g.h3_index, MIN(s."{tier_col}")::INT AS tier
        FROM grid_cells g
        JOIN "{staging}" s ON ST_Contains(s.geometry, ST_Centroid(g.geom_4326))
        GROUP BY g.h3_index
    )
    UPDATE grid_cells g
    SET {set_sql}
    FROM cell_tier sub
    WHERE g.h3_index = sub.h3_index
    """
    with engine.begin() as conn:
        conn.execute(text(sql))
        overridden = conn.execute(
            text(
                f"SELECT COUNT(*) FROM grid_cells WHERE {src_col} = 'manual_digitization'"
                if src_col
                else f"SELECT COUNT(*) FROM grid_cells WHERE {column} IS NOT NULL"
            )
        ).scalar_one()

    _record_source(
        source_key=column,
        source_url=str(path),
        license_name="see config/layers/" + layer_id + ".yaml",
        metadata={
            "layer_kind": "feature",
            "layer_id": layer_id,
            "strategy": "overlay_tier",
            "features": int(len(gdf)),
            "overridden_cells": int(overridden),
        },
    )
    return {
        "layer_id": layer_id,
        "status": "applied",
        "overridden_cells": int(overridden),
        "features": int(len(gdf)),
    }


def run_all() -> dict:
    report: dict = {"exclusions": [], "distances": [], "overlay_tiers": []}
    for spec in exclusions_with_runtime():
        try:
            report["exclusions"].append(apply_exclusion(spec.layer_id, spec.exclusion_runtime))
        except Exception as exc:
            report["exclusions"].append({"layer_id": spec.layer_id, "status": "error", "error": repr(exc)})
    for spec in distances_with_runtime():
        try:
            report["distances"].append(apply_distance_layer(spec.layer_id, spec.distance_runtime))
        except Exception as exc:
            report["distances"].append({"layer_id": spec.layer_id, "status": "error", "error": repr(exc)})
    for spec in overlay_tiers_with_runtime():
        try:
            report["overlay_tiers"].append(apply_overlay_tier(spec.layer_id, spec.overlay_tier_runtime))
        except Exception as exc:
            report["overlay_tiers"].append({"layer_id": spec.layer_id, "status": "error", "error": repr(exc)})
    return report


if __name__ == "__main__":
    print(json.dumps(run_all(), indent=2))
