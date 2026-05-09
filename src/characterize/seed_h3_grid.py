from __future__ import annotations

import json

import h3
from sqlalchemy import text

from src.common.db import get_engine


COUNTRY_POLYGONS = {
    "SE": {"type": "Polygon", "coordinates": [[[11.0, 55.2], [24.5, 55.2], [24.5, 69.2], [11.0, 69.2], [11.0, 55.2]]]},
    "NO": {"type": "Polygon", "coordinates": [[[4.5, 57.9], [31.0, 57.9], [31.0, 71.5], [4.5, 71.5], [4.5, 57.9]]]},
    "FI": {"type": "Polygon", "coordinates": [[[19.0, 59.5], [32.0, 59.5], [32.0, 70.2], [19.0, 70.2], [19.0, 59.5]]]},
}


def seed_grid(resolution: int = 8, batch_size: int = 2000) -> None:
    """Seed grid_cells with H3 cells covering the Nordic study bbox.

    Earlier revisions ran one INSERT per cell inside a single transaction.
    At resolution 8 the bbox produces ~30k cells per country, so the round
    trips dominated and the function ran for many minutes with nothing
    visible to the DB until commit. Now we batch via psycopg's
    `executemany` (~30s end-to-end on a local container) and commit one
    country at a time so progress is observable.
    """
    engine = get_engine()
    sql = text(
        """
        INSERT INTO grid_cells (h3_index, country, geom_4326)
        VALUES (:h3, :country, ST_GeomFromGeoJSON(:geom))
        ON CONFLICT (h3_index) DO NOTHING
        """
    )
    for country, poly in COUNTRY_POLYGONS.items():
        cells = h3.geo_to_cells(poly, resolution)
        rows: list[dict[str, str]] = []
        for cell in cells:
            boundary = h3.cell_to_boundary(cell)
            coords = [[lng, lat] for lat, lng in boundary]
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            geom = {"type": "Polygon", "coordinates": [coords]}
            rows.append({"h3": cell, "country": country, "geom": json.dumps(geom)})
        # Commit per-batch so a long-running seed shows progress and a
        # crash in the middle doesn't roll back work for the whole bbox.
        for start in range(0, len(rows), batch_size):
            chunk = rows[start : start + batch_size]
            with engine.begin() as conn:
                conn.execute(sql, chunk)
        print(f"[seed] {country}: {len(rows):,} cells inserted/skipped")


if __name__ == "__main__":
    seed_grid()
