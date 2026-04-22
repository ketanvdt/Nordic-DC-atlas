from __future__ import annotations

from sqlalchemy import text

from src.common.db import get_engine


def assert_exclusion_band(min_ratio: float = 0.30, max_ratio: float = 0.50) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM grid_cells")).scalar_one()
        excluded = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM grid_cells
                WHERE excl_natura2000 OR excl_protected OR excl_floodplain OR excl_heritage
                   OR excl_airport OR excl_airport_ols OR excl_military OR excl_steep_slope
                   OR excl_seveso OR excl_water_protected OR excl_urban_industrial OR excl_sami_reindeer
                """
            )
        ).scalar_one()
    ratio = (excluded / total) if total else 0.0
    if ratio < min_ratio or ratio > max_ratio:
        raise AssertionError(f"Excluded ratio {ratio:.3f} outside expected band [{min_ratio}, {max_ratio}]")
    print(f"Exclusion ratio check passed: {ratio:.3f}")


if __name__ == "__main__":
    assert_exclusion_band()
