from __future__ import annotations

from sqlalchemy import text

from src.common.db import get_engine


def assign_bidding_zones() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE grid_cells
                SET bidding_zone = CASE
                  WHEN country = 'FI' THEN 'FI'
                  WHEN country = 'SE' AND ST_Y(ST_Centroid(geom_4326)) > 66 THEN 'SE1'
                  WHEN country = 'SE' AND ST_Y(ST_Centroid(geom_4326)) > 62 THEN 'SE2'
                  WHEN country = 'SE' AND ST_Y(ST_Centroid(geom_4326)) > 58 THEN 'SE3'
                  WHEN country = 'SE' THEN 'SE4'
                  WHEN country = 'NO' AND ST_Y(ST_Centroid(geom_4326)) > 69 THEN 'NO4'
                  WHEN country = 'NO' AND ST_Y(ST_Centroid(geom_4326)) > 66 THEN 'NO3'
                  WHEN country = 'NO' AND ST_X(ST_Centroid(geom_4326)) < 8 THEN 'NO5'
                  WHEN country = 'NO' AND ST_Y(ST_Centroid(geom_4326)) > 60 THEN 'NO1'
                  WHEN country = 'NO' THEN 'NO2'
                  ELSE bidding_zone
                END
                """
            )
        )


def apply_zone_profiles() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE grid_cells gc
                SET
                  bidding_zone_price_3y = p.price_3y_eur_mwh,
                  grid_capacity_heatmap = p.capacity_score
                FROM power_zone_profiles p
                WHERE p.zone_code = gc.bidding_zone
                """
            )
        )


def run() -> None:
    assign_bidding_zones()
    apply_zone_profiles()
    print("Power layers mapped: bidding_zone + capacity heatmap")


if __name__ == "__main__":
    run()
