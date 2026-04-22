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


def seed_grid(resolution: int = 8) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        for country, poly in COUNTRY_POLYGONS.items():
            cells = h3.geo_to_cells(poly, resolution)
            for cell in cells:
                boundary = h3.cell_to_boundary(cell)
                coords = [[lng, lat] for lat, lng in boundary]
                if coords[0] != coords[-1]:
                    coords.append(coords[0])
                geom = {"type": "Polygon", "coordinates": [coords]}
                conn.execute(
                    text(
                        """
                        INSERT INTO grid_cells (h3_index, country, geom_4326)
                        VALUES (:h3, :country, ST_GeomFromGeoJSON(:geom))
                        ON CONFLICT (h3_index) DO NOTHING
                        """
                    ),
                    {"h3": cell, "country": country, "geom": json.dumps(geom)},
                )


if __name__ == "__main__":
    seed_grid()
