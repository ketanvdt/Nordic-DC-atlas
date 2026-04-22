"""Characterize real ingested layers from data/processed/*.gpkg.

Replaces the random placeholder values in `soft_features.py` for columns that
now have real source data. For the remaining columns we leave NULL rather than
random noise so the UI can truthfully show which features are real.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import json
from datetime import datetime

import geopandas as gpd
from sqlalchemy import text

from src.common.db import get_engine


def _record_source(source_key: str, source_url: str, license_name: str, metadata: dict) -> None:
    """Write an entry into `data_sources` so the freshness panel knows this layer is real."""
    engine = get_engine()
    # Use a dummy checksum for OSM/derived layers since they're tagged by recency, not content.
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


@dataclass(frozen=True)
class ExclusionSource:
    key: str
    gpkg: str
    flag_column: str
    strategy: str  # "overlap_50" | "buffer" | "centroid"
    buffer_m: int | None = None


EXCLUSIONS: tuple[ExclusionSource, ...] = (
    # v1 uses boolean `intersects` for all exclusions — cell overlaps any
    # source polygon => excluded. Rationale: exact area-fraction in reprojected
    # (3035) space has no usable index on the transformed geometry and scales
    # poorly. "Touches a protected area" is already a strong screening signal
    # at H3 res8 (~0.74 km² cells).
    ExclusionSource("natura2000", "data/processed/natura2000.gpkg", "excl_natura2000", "intersects"),
    ExclusionSource("protected", "data/processed/protected.gpkg", "excl_protected", "intersects"),
    ExclusionSource("airport", "data/processed/airport.gpkg", "excl_airport", "buffer", buffer_m=5000),
)


@dataclass(frozen=True)
class DistanceSource:
    key: str
    gpkg: str
    target_columns: tuple[str, ...]
    voltage_filter: dict[str, tuple[int, int] | None]  # column -> (min_kv, max_kv) or None for all


DISTANCES: tuple[DistanceSource, ...] = (
    DistanceSource(
        key="substations",
        gpkg="data/processed/substations.gpkg",
        target_columns=("dist_substation_400kv_m", "dist_substation_130kv_m"),
        voltage_filter={
            "dist_substation_400kv_m": (300, 10_000),
            "dist_substation_130kv_m": (100, 299),
        },
    ),
    DistanceSource(
        key="transmission_lines",
        gpkg="data/processed/transmission_lines.gpkg",
        target_columns=("dist_transmission_line_m",),
        voltage_filter={
            "dist_transmission_line_m": (100, 10_000),  # HV lines ≥ 100 kV
        },
    ),
)


def _parse_voltage_kv(raw: object) -> int | None:
    """OSM voltage tag is free-text: '132000', '132 kV', '132000;220000', '400000 / 220000'."""
    if raw is None:
        return None
    text_raw = str(raw)
    # Pick the largest numeric token in volts, convert to kV.
    import re
    tokens = re.findall(r"\d+", text_raw)
    if not tokens:
        return None
    max_v = max(int(t) for t in tokens)
    if max_v >= 1000:  # likely volts
        return max_v // 1000
    return max_v  # already kV


def _stage_gdf(engine, table: str, gdf: gpd.GeoDataFrame) -> None:
    """Drop-and-create a staging table in public schema with a single geometry column.

    Keeps schema tight — only geometry + id. We reproject to 4326 on the way in.
    Buffer(0) cleanup is only applied to polygonal geometries — applying it to
    points collapses them to empty geometries and wipes the table.
    """
    gdf = gdf.to_crs("EPSG:4326") if gdf.crs and gdf.crs.to_epsg() != 4326 else gdf
    gdf = gdf[gdf.geometry.notnull()]
    gdf = gdf[~gdf.geometry.is_empty]
    # Server-side ST_MakeValid below handles invalid polygons. We avoid a client-side
    # buffer(0) because it allocates ~N Shapely polygons and blows memory on large
    # OSM datasets (41k protected areas = ~1GB WKT).
    gdf = gdf[gdf.geometry.is_valid]
    if gdf.empty:
        raise RuntimeError(f"_stage_gdf: no valid geometries to load into {table}")

    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
    # chunksize keeps peak memory bounded when loading tens of thousands of polygons.
    gdf[["geometry"]].to_postgis(
        table, engine, if_exists="replace", index=True, index_label="row_id", chunksize=2000
    )
    with engine.begin() as conn:
        # OSM polygons from protected_area boundaries can have self-intersections;
        # ST_MakeValid fixes them before spatial joins hit GEOS.
        conn.execute(text(f'UPDATE "{table}" SET geometry = ST_MakeValid(geometry) WHERE NOT ST_IsValid(geometry)'))
        # Drop any features that ended up as empty/non-polygonal after MakeValid.
        conn.execute(text(f'DELETE FROM "{table}" WHERE geometry IS NULL OR ST_IsEmpty(geometry)'))
        conn.execute(text(f'CREATE INDEX IF NOT EXISTS "{table}_geom_idx" ON "{table}" USING GIST (geometry)'))
        conn.execute(text(f'ANALYZE "{table}"'))


def apply_exclusion(source: ExclusionSource) -> dict:
    path = Path(source.gpkg)
    if not path.exists():
        return {"key": source.key, "status": "missing_file", "path": str(path)}
    gdf = gpd.read_file(path)
    if gdf.empty:
        return {"key": source.key, "status": "empty"}

    engine = get_engine()
    if source.strategy == "buffer" and source.buffer_m:
        gdf = gdf.to_crs("EPSG:3035")
        gdf["geometry"] = gdf.buffer(source.buffer_m)
        gdf = gdf.to_crs("EPSG:4326")

    staging = f"stg_{source.key}"
    _stage_gdf(engine, staging, gdf)

    flag = source.flag_column
    if source.strategy == "buffer":
        # Buffer applied in Python above. Fast boolean overlap using the 4326 GIST index.
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
    elif source.strategy == "overlap_50":
        # Overlap fraction in metric CRS. Note: reprojection on join side has no
        # index — only use this for small source layers (<~100 features).
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
    elif source.strategy == "centroid":
        sql = f"""
        UPDATE grid_cells g
        SET {flag} = EXISTS (
            SELECT 1 FROM {staging} s
            WHERE ST_Contains(s.geometry, ST_Centroid(g.geom_4326))
        )
        """
    elif source.strategy == "intersects":
        # Fast boolean flag — no area math. Use for layers where any overlap is
        # enough signal and exact fraction would be GEOS-expensive at scale.
        sql = f"""
        WITH hits AS (
            SELECT DISTINCT g.h3_index
            FROM grid_cells g
            JOIN {staging} s ON ST_Intersects(g.geom_4326, s.geometry)
        )
        UPDATE grid_cells g
        SET {flag} = h.h3_index IS NOT NULL
        FROM (
            SELECT h3_index FROM hits
        ) h
        WHERE g.h3_index = h.h3_index
        """
    else:
        raise ValueError(f"unknown strategy: {source.strategy}")

    with engine.begin() as conn:
        conn.execute(text(sql))
        hit_count = conn.execute(
            text(f"SELECT COUNT(*) FROM grid_cells WHERE {flag} = TRUE")
        ).scalar_one()
    _record_source(
        source_key=flag,
        source_url="https://overpass-api.de/api/interpreter (OSM)",
        license_name="ODbL 1.0 (OpenStreetMap contributors)",
        metadata={"layer_kind": "exclusion", "strategy": source.strategy, "features": int(len(gdf)), "excluded_cells": int(hit_count)},
    )
    return {"key": source.key, "status": "applied", "excluded_cells": int(hit_count), "features": int(len(gdf))}


def apply_distance_layer(source: DistanceSource) -> dict:
    path = Path(source.gpkg)
    if not path.exists():
        return {"key": source.key, "status": "missing_file"}
    gdf = gpd.read_file(path)
    if gdf.empty:
        return {"key": source.key, "status": "empty"}

    # Parse voltage on Python side — avoids SQL-regex nightmare on OSM free-text tags.
    gdf["voltage_kv"] = gdf.get("voltage").apply(_parse_voltage_kv) if "voltage" in gdf.columns else None

    engine = get_engine()
    results: dict = {"key": source.key, "features": int(len(gdf)), "columns": {}}

    for column in source.target_columns:
        lo_hi = source.voltage_filter.get(column)
        subset = gdf
        if lo_hi is not None:
            lo, hi = lo_hi
            subset = gdf[gdf["voltage_kv"].between(lo, hi, inclusive="both")]
        if subset.empty:
            results["columns"][column] = {"status": "no_features_in_voltage_band", "band_kv": lo_hi}
            continue

        staging = f"stg_{source.key}_{column}"
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
            source_url="https://overpass-api.de/api/interpreter (OSM)",
            license_name="ODbL 1.0 (OpenStreetMap contributors)",
            metadata={
                "layer_kind": "feature",
                "voltage_band_kv": list(lo_hi) if lo_hi else None,
                "features_used": int(len(subset)),
                "populated_cells": int(stats[0]),
            },
        )

    return results


def run_all() -> dict:
    report: dict = {"exclusions": [], "distances": []}
    for src in EXCLUSIONS:
        try:
            report["exclusions"].append(apply_exclusion(src))
        except Exception as exc:
            report["exclusions"].append({"key": src.key, "status": "error", "error": repr(exc)})
    for src in DISTANCES:
        try:
            report["distances"].append(apply_distance_layer(src))
        except Exception as exc:
            report["distances"].append({"key": src.key, "status": "error", "error": repr(exc)})
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(run_all(), indent=2))
