from __future__ import annotations

from sqlalchemy import text

from src.common.db import get_engine


# Columns with real ingest paths (see src/characterize/real_ingest.py and power/dh)
# — never blast random() on top of them.
#   - dist_substation_400kv_m / dist_substation_130kv_m / dist_transmission_line_m: OSM real_ingest
#   - bidding_zone_price_3y / grid_capacity_heatmap: power_zone_profiles seed
#   - dist_dh_network_m / dh_readiness_tier: dh_city_tiers seed
#
# Columns still without a real source — populated here with random noise so the
# scoring path works end-to-end. Replace as real feeds come online and remove
# the column from this list.
_PLACEHOLDER_COLUMN_EXPRS: tuple[tuple[str, str], ...] = (
    ("annual_mean_temp_c", "-2 + random() * 10"),
    ("dist_fiber_m", "5000 + random() * 100000"),
    ("dist_surface_water_m", "random() * 20000"),
    ("land_cost_proxy_eur_m2", "5 + random() * 180"),
    ("skilled_workforce_density", "random() * 1.0"),
    ("municipal_receptivity", "CASE WHEN random() > 0.75 THEN -1 WHEN random() > 0.35 THEN 0 ELSE 1 END"),
    ("municipality_code", "country || '-' || floor(random() * 9000 + 1000)::text"),
)


def populate_placeholder_soft_features() -> None:
    """Populate ONLY the columns that don't have a real-data path yet.

    COALESCE guards mean real values already written by real_ingest, power_layers,
    or dh_tiers are never overwritten. Distances to substations / transmission /
    DH cities are deliberately excluded from this placeholder — they have real
    data paths.
    """
    engine = get_engine()
    assignments = ", ".join(
        f"{col} = COALESCE({col}, {expr})" for col, expr in _PLACEHOLDER_COLUMN_EXPRS
    )
    sql = f"UPDATE grid_cells SET {assignments}"
    with engine.begin() as conn:
        conn.execute(text(sql))
    print(
        "Placeholder soft features populated for: "
        + ", ".join(col for col, _ in _PLACEHOLDER_COLUMN_EXPRS)
    )


if __name__ == "__main__":
    populate_placeholder_soft_features()
