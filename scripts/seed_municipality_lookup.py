"""Seed `municipality_lookup` and assign `grid_cells.municipality_code`
from the geoBoundaries ADM2 polygons that already ship as
`data/processed/municipalities.gpkg` (produced by
`scripts/generate_overlay_baselines.py`).

Without polygons, grid_cells.municipality_code stays NULL and the top-50
candidate names fall back to "Unknown area, <country> (<zone>)". Migration
006 seeds 12 well-known cities for completeness, but they don't match
arbitrary cell codes — this script does.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from sqlalchemy import text

from src.common.db import get_engine


_GPKG = Path("data/processed/municipalities.gpkg")


def main() -> None:
    if not _GPKG.exists():
        print(
            f"Skipping seed: {_GPKG} not found. "
            "Run `python scripts/generate_overlay_baselines.py` first."
        )
        return

    gdf = gpd.read_file(_GPKG).to_crs("EPSG:4326")
    if gdf.empty:
        print(f"Skipping seed: {_GPKG} is empty.")
        return

    required = {"municipality_code", "municipality_name", "country", "geometry"}
    missing = required - set(gdf.columns)
    if missing:
        raise SystemExit(f"municipalities.gpkg missing columns: {sorted(missing)}")

    engine = get_engine()

    # Upsert lookup rows from the GPKG attributes (one row per polygon).
    rows = gdf[["municipality_code", "municipality_name", "country"]].drop_duplicates(
        subset=["municipality_code"]
    )
    with engine.begin() as conn:
        for _, r in rows.iterrows():
            conn.execute(
                text(
                    """
                    INSERT INTO municipality_lookup (municipality_code, municipality_name, country)
                    VALUES (:c, :n, :ctry)
                    ON CONFLICT (municipality_code) DO UPDATE SET
                      municipality_name = EXCLUDED.municipality_name,
                      country = EXCLUDED.country
                    """
                ),
                {"c": r["municipality_code"], "n": r["municipality_name"], "ctry": r["country"]},
            )

    # Stage polygons in PostGIS so we can do the spatial join in SQL.
    staging = "stg_municipalities_adm2"
    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{staging}" CASCADE'))
    gdf[["municipality_code", "geometry"]].to_postgis(
        staging, engine, if_exists="replace", index=True, index_label="row_id"
    )
    with engine.begin() as conn:
        conn.execute(text(f'CREATE INDEX IF NOT EXISTS "{staging}_geom_idx" ON "{staging}" USING GIST (geometry)'))
        conn.execute(text(f'ANALYZE "{staging}"'))
        conn.execute(
            text(
                f"""
                UPDATE grid_cells g
                SET municipality_code = sub.municipality_code
                FROM (
                    SELECT g2.h3_index, MIN(s.municipality_code) AS municipality_code
                    FROM grid_cells g2
                    JOIN "{staging}" s ON ST_Contains(s.geometry, ST_Centroid(g2.geom_4326))
                    GROUP BY g2.h3_index
                ) sub
                WHERE g.h3_index = sub.h3_index
                """
            )
        )
        rowcount = conn.execute(
            text("SELECT COUNT(*) FROM grid_cells WHERE municipality_code IS NOT NULL")
        ).scalar_one()
        total = conn.execute(text("SELECT COUNT(*) FROM grid_cells")).scalar_one()

    print(
        f"municipality_lookup seeded with {len(rows):,} rows. "
        f"grid_cells.municipality_code populated for {rowcount:,} of {total:,} cells."
    )


if __name__ == "__main__":
    main()
