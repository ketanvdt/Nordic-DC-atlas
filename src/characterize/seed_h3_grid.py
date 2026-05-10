from __future__ import annotations

import json
from pathlib import Path

import h3
from sqlalchemy import text

from src.common.db import get_engine


# Real country outlines clipped to the Nordic study bbox. Built by
# scripts/build_country_outlines.py from Natural Earth 1:50m. Vendored
# in repo so seeding does not require network access.
COUNTRY_OUTLINES_PATH = Path("data/manual/country_outlines.geojson")


def load_country_polygons(path: Path = COUNTRY_OUTLINES_PATH) -> dict[str, dict]:
    """Return {ISO_A2: GeoJSON geometry} for the seeded countries.

    Reads the vendored Natural Earth outline. The file is regenerated
    by scripts/build_country_outlines.py; the seed pipeline never
    fetches at runtime.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"missing {path}. Run `python scripts/build_country_outlines.py` "
            "to vendor it."
        )
    fc = json.loads(path.read_text())
    return {feat["properties"]["ISO_A2"]: feat["geometry"] for feat in fc["features"]}


def seed_grid(resolution: int = 8, batch_size: int = 2000) -> None:
    """Seed grid_cells with H3 cells covering each Nordic country outline.

    Two changes from the bbox-rectangle ancestor of this code:

      1. Geometry is the real country outline (Natural Earth 1:50m,
         clipped to 4-32E / 55-72N to drop Svalbard etc.). Cells over
         ocean and over neighboring countries no longer enter the grid.

      2. Inserts are batched via executemany and committed per chunk.
         The pre-batched form ran one INSERT per cell inside one giant
         transaction, which spent many minutes with nothing visible
         to the DB until commit and rolled back the whole bbox if it
         crashed. Per-batch commits make progress observable and
         partial failures recoverable.

    h3.geo_to_cells handles both Polygon and MultiPolygon GeoJSON, so
    the loader does not need to flatten Norway's archipelago.
    """
    engine = get_engine()
    sql = text(
        """
        INSERT INTO grid_cells (h3_index, country, geom_4326)
        VALUES (:h3, :country, ST_GeomFromGeoJSON(:geom))
        ON CONFLICT (h3_index) DO NOTHING
        """
    )
    polygons = load_country_polygons()
    for country, poly in polygons.items():
        cells = h3.geo_to_cells(poly, resolution)
        rows: list[dict[str, str]] = []
        for cell in cells:
            boundary = h3.cell_to_boundary(cell)
            coords = [[lng, lat] for lat, lng in boundary]
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            geom = {"type": "Polygon", "coordinates": [coords]}
            rows.append({"h3": cell, "country": country, "geom": json.dumps(geom)})
        for start in range(0, len(rows), batch_size):
            chunk = rows[start : start + batch_size]
            with engine.begin() as conn:
                conn.execute(sql, chunk)
        print(f"[seed] {country}: {len(rows):,} cells inserted/skipped")


if __name__ == "__main__":
    seed_grid()
