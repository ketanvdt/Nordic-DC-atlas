"""Refresh grid_cells_normalized and dump a post-ingest sanity report.

Run after `real_ingest.py` or any characterization step that changes `grid_cells`
column values. Verifies that the exclusion and distance features driving the
map actually carry signal (not uniform random noise from the placeholder).
"""
from __future__ import annotations

import json

from sqlalchemy import text

from src.common.db import get_engine


def refresh_mv() -> None:
    with get_engine().begin() as conn:
        conn.execute(text("REFRESH MATERIALIZED VIEW grid_cells_normalized"))


def verify() -> dict:
    engine = get_engine()
    out: dict = {"exclusions": {}, "distances": {}, "seeded": {}}

    with engine.begin() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM grid_cells")).scalar_one()
        out["total_cells"] = int(total)

        for col in ("excl_natura2000", "excl_protected", "excl_airport", "excl_airport_ols",
                    "excl_floodplain", "excl_heritage", "excl_military", "excl_steep_slope",
                    "excl_seveso", "excl_water_protected", "excl_urban_industrial", "excl_sami_reindeer"):
            hit = conn.execute(
                text(f"SELECT COUNT(*) FROM grid_cells WHERE {col} = TRUE")
            ).scalar_one()
            out["exclusions"][col] = int(hit)

        for col in ("dist_substation_400kv_m", "dist_substation_130kv_m", "dist_transmission_line_m"):
            row = conn.execute(text(
                f"SELECT MIN({col})::float AS mn, MAX({col})::float AS mx, "
                f"AVG({col})::float AS mean, STDDEV({col})::float AS std, "
                f"percentile_cont(0.5) WITHIN GROUP (ORDER BY {col}) AS p50 "
                f"FROM grid_cells WHERE {col} IS NOT NULL"
            )).mappings().first()
            out["distances"][col] = dict(row) if row else {}

        for col in ("bidding_zone_price_3y", "grid_capacity_heatmap",
                    "dist_dh_network_m", "dh_readiness_tier"):
            row = conn.execute(text(
                f"SELECT MIN({col})::float AS mn, MAX({col})::float AS mx, "
                f"AVG({col})::float AS mean FROM grid_cells WHERE {col} IS NOT NULL"
            )).mappings().first()
            out["seeded"][col] = dict(row) if row else {}

    return out


def print_verdict(report: dict) -> None:
    print("\n=== verify() ===")
    print(f"total cells: {report['total_cells']:,}")
    print("\nExclusions (TRUE counts):")
    for k, v in report["exclusions"].items():
        status = "real" if v > 0 else "empty"
        print(f"  [{status:5s}] {k:30s} {v:,}")
    print("\nDistance features:")
    for k, v in report["distances"].items():
        mn, mx, mean, std, p50 = v.get("mn", 0), v.get("mx", 0), v.get("mean", 0), v.get("std", 0), v.get("p50", 0)
        # Heuristic: placeholder ranges are bounded hard; real OSM distances can exceed 140km easily.
        suspicion = "placeholder-shaped" if mx and mx <= 140001 and mn and mn >= 9999 and std and std > 30000 else "real-looking"
        print(f"  [{suspicion:17s}] {k:30s} min={mn:8.0f} p50={p50:8.0f} max={mx:8.0f} std={std:7.0f}")
    print("\nSeeded features (profiles):")
    for k, v in report["seeded"].items():
        print(f"  {k:30s} min={v.get('mn'):.3f} max={v.get('mx'):.3f} mean={v.get('mean'):.3f}")


if __name__ == "__main__":
    print("Refreshing grid_cells_normalized...")
    refresh_mv()
    print("done.")
    report = verify()
    print_verdict(report)
    print("\n=== JSON ===")
    print(json.dumps(report, indent=2, default=str))
