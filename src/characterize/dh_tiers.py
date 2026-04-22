from __future__ import annotations

from sqlalchemy import text

from src.common.db import get_engine


def apply_dh_tiers(influence_km: float = 35.0) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE grid_cells gc
                SET
                  dh_readiness_tier = nearest.readiness_tier,
                  dist_dh_network_m = nearest.dist_m
                FROM (
                  SELECT
                    ranked.h3_index,
                    ranked.readiness_tier,
                    ranked.dist_m
                  FROM (
                    SELECT
                      g.h3_index,
                      c.readiness_tier,
                      ST_Distance(
                        g.geom_4326::geography,
                        ST_SetSRID(ST_Point(c.lon, c.lat), 4326)::geography
                      ) AS dist_m,
                      ROW_NUMBER() OVER (
                        PARTITION BY g.h3_index
                        ORDER BY ST_Distance(
                          g.geom_4326::geography,
                          ST_SetSRID(ST_Point(c.lon, c.lat), 4326)::geography
                        ) ASC
                      ) AS rn
                    FROM grid_cells g
                    JOIN dh_city_tiers c ON g.country = c.country
                  ) ranked
                  WHERE ranked.rn = 1
                ) nearest
                WHERE gc.h3_index = nearest.h3_index
                  AND nearest.dist_m <= (:influence_km * 1000.0)
                """
            ),
            {"influence_km": influence_km},
        )
        conn.execute(
            text(
                """
                UPDATE grid_cells
                SET dh_readiness_tier = COALESCE(dh_readiness_tier, 0),
                    dist_dh_network_m = COALESCE(dist_dh_network_m, 200000)
                """
            )
        )
    print("DH readiness tiers applied")


if __name__ == "__main__":
    apply_dh_tiers()
