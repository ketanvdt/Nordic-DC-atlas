"""Integration test for `src.characterize.real_ingest.apply_overlay_tier`.

The function stages a manually digitized GeoJSON in PostGIS, runs an
ST_Contains spatial join against grid cell centroids, applies
`MIN(tier)` when polygons overlap, scales the tier to 0–1 by tier_max,
and tags overridden rows with grid_capacity_source = 'manual_digitization'.
This test exercises the whole path end-to-end.

Skipped automatically if DATABASE_URL is not set, so unit-only runs
(`pytest -q` without `make up`) stay fast. To run locally:

    make up && make migrate
    DATABASE_URL=postgresql+psycopg://atlas:atlas@localhost:5432/atlas pytest tests/test_overlay_tier_apply.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

DATABASE_URL = os.getenv("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set; bring up Postgres+PostGIS via `make up && make migrate`.",
)

# Defer heavy imports until after the skipif so unit-only runs don't fail
# at collection time on missing optional deps.
h3 = pytest.importorskip("h3")
geopandas = pytest.importorskip("geopandas")
shapely_geometry = pytest.importorskip("shapely.geometry")
sqlalchemy = pytest.importorskip("sqlalchemy")

from sqlalchemy import text  # noqa: E402

from src.characterize.real_ingest import apply_overlay_tier  # noqa: E402
from src.common.db import get_engine  # noqa: E402
from src.common.layer_registry import OverlayTierRuntime  # noqa: E402


# Four known H3 res-8 cells, two of which sit inside our synthetic
# tier-0 inner polygon, one in only the tier-1 outer polygon, and one
# completely outside both. Centroid coordinates were checked with
# h3.latlng_to_cell().
INNER_LATLON = (59.33, 18.07)   # central Stockholm — inside both polygons
OUTER_LATLON = (59.0, 14.0)     # central Sweden — inside outer only
SE1_LATLON = (67.0, 20.0)       # northern Sweden — outside both polygons
ABROAD_LATLON = (52.0, 4.6)     # Netherlands — outside both polygons

# Synthetic polygons, chosen to be larger than the test points but
# smaller than the country so they don't collide with real data.
OUTER_POLYGON = [
    [12.0, 58.0], [19.5, 58.0], [19.5, 62.0], [12.0, 62.0], [12.0, 58.0],
]
INNER_POLYGON = [
    [16.5, 58.7], [18.7, 58.7], [18.7, 60.2], [16.5, 60.2], [16.5, 58.7],
]


def _h3_cell(lat: float, lon: float) -> str:
    return h3.latlng_to_cell(lat, lon, 8)


def _h3_polygon_wkt(cell: str) -> str:
    """Return WKT polygon for an H3 cell boundary, ring-closed."""
    boundary = [(lon, lat) for lat, lon in h3.cell_to_boundary(cell)]
    if boundary[0] != boundary[-1]:
        boundary.append(boundary[0])
    coords = ", ".join(f"{lon} {lat}" for lon, lat in boundary)
    return f"POLYGON(({coords}))"


@pytest.fixture(scope="module")
def engine():
    return get_engine()


@pytest.fixture
def fixture_cells(engine, tmp_path):
    """Insert four fixture cells into grid_cells, run the overlay against
    a synthetic two-polygon GeoJSON, and tear everything down after the test.
    """
    cells = {
        "inner": _h3_cell(*INNER_LATLON),
        "outer_only": _h3_cell(*OUTER_LATLON),
        "se1_outside": _h3_cell(*SE1_LATLON),
        "abroad": _h3_cell(*ABROAD_LATLON),
    }
    # All four cells are distinct.
    assert len({cells["inner"], cells["outer_only"], cells["se1_outside"], cells["abroad"]}) == 4

    # 1. Insert fixture cells with a known pre-overlay grid_capacity_heatmap
    #    + grid_capacity_source so we can detect (a) cells the overlay
    #    overrode and (b) cells the overlay correctly left alone.
    with engine.begin() as conn:
        for label, cell in cells.items():
            wkt = _h3_polygon_wkt(cell)
            country = "SE" if label != "abroad" else "NL"
            conn.execute(
                text(
                    """
                    INSERT INTO grid_cells (
                      h3_index, country, geom_4326,
                      grid_capacity_heatmap, grid_capacity_source
                    )
                    VALUES (
                      :h3, :country, ST_GeomFromText(:wkt, 4326),
                      :baseline, :baseline_src
                    )
                    ON CONFLICT (h3_index) DO UPDATE SET
                      grid_capacity_heatmap = EXCLUDED.grid_capacity_heatmap,
                      grid_capacity_source  = EXCLUDED.grid_capacity_source,
                      geom_4326             = EXCLUDED.geom_4326,
                      country               = EXCLUDED.country
                    """
                ),
                {
                    "h3": cell,
                    "country": country,
                    "wkt": wkt,
                    "baseline": 0.5,                 # arbitrary baseline, not 0/0.333/0
                    "baseline_src": "bidding_zone",
                },
            )

    # 2. Write synthetic GeoJSON with overlapping polygons.
    geojson = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
        "features": [
            {
                "type": "Feature",
                "id": "outer_constrained",
                "properties": {"capacity_tier": 1, "region": "fixture-outer"},
                "geometry": {"type": "Polygon", "coordinates": [OUTER_POLYGON]},
            },
            {
                "type": "Feature",
                "id": "inner_red",
                "properties": {"capacity_tier": 0, "region": "fixture-inner"},
                "geometry": {"type": "Polygon", "coordinates": [INNER_POLYGON]},
            },
        ],
    }
    geojson_path = tmp_path / "overlay_fixture.geojson"
    geojson_path.write_text(json.dumps(geojson))

    runtime = OverlayTierRuntime(
        column="grid_capacity_heatmap",
        source=str(geojson_path),
        tier_property="capacity_tier",
        tier_max=3,
        source_tracking_column="grid_capacity_source",
    )

    yield cells, runtime, geojson_path

    # 3. Teardown: drop fixture cells and the staging table.
    with engine.begin() as conn:
        for cell in cells.values():
            conn.execute(text("DELETE FROM grid_cells WHERE h3_index = :h"), {"h": cell})
        conn.execute(text('DROP TABLE IF EXISTS "stg_overlay_fixture" CASCADE'))


def test_apply_overlay_tier_min_tier_wins_on_overlap(engine, fixture_cells) -> None:
    """The inner tier-0 polygon overlaps the outer tier-1 polygon. A cell
    inside both must end up with tier=0 (MIN), not tier=1, so the value
    written is 0/3 = 0.0 (not 1/3 = 0.333…)."""
    cells, runtime, _ = fixture_cells

    result = apply_overlay_tier("overlay_fixture", runtime)
    assert result["status"] == "applied", result
    assert result["features"] == 2
    assert result["overridden_cells"] >= 2  # inner + outer_only

    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT grid_capacity_heatmap, grid_capacity_source "
                "FROM grid_cells WHERE h3_index = :h"
            ),
            {"h": cells["inner"]},
        ).first()
    value, source = row
    assert source == "manual_digitization", "Inner cell must be tagged as manual"
    assert value == pytest.approx(0.0, abs=1e-9), (
        f"Inner cell got tier-scaled value {value}, expected 0.0 (MIN of overlapping tiers 0 and 1)"
    )


def test_apply_overlay_tier_outer_only_uses_outer_tier(engine, fixture_cells) -> None:
    """A cell inside the outer polygon but not the inner one gets tier=1,
    written as 1/3 ≈ 0.333."""
    cells, runtime, _ = fixture_cells
    apply_overlay_tier("overlay_fixture", runtime)

    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT grid_capacity_heatmap, grid_capacity_source "
                "FROM grid_cells WHERE h3_index = :h"
            ),
            {"h": cells["outer_only"]},
        ).first()
    value, source = row
    assert source == "manual_digitization"
    assert value == pytest.approx(1.0 / 3.0, abs=1e-9), (
        f"Outer-only cell got {value}, expected {1/3:.6f} (tier 1 / tier_max 3)"
    )


def test_apply_overlay_tier_leaves_outside_cells_alone(engine, fixture_cells) -> None:
    """Cells whose centroid is inside neither polygon must keep their
    pre-overlay value AND pre-overlay source tag — the overlay is
    additive, never destructive."""
    cells, runtime, _ = fixture_cells
    apply_overlay_tier("overlay_fixture", runtime)

    with engine.begin() as conn:
        for label in ("se1_outside", "abroad"):
            row = conn.execute(
                text(
                    "SELECT grid_capacity_heatmap, grid_capacity_source "
                    "FROM grid_cells WHERE h3_index = :h"
                ),
                {"h": cells[label]},
            ).first()
            value, source = row
            assert value == pytest.approx(0.5, abs=1e-9), (
                f"Outside cell {label} value changed from baseline 0.5 to {value}"
            )
            assert source == "bidding_zone", (
                f"Outside cell {label} source flipped to {source!r}; should still be 'bidding_zone'"
            )


def test_apply_overlay_tier_records_data_source(engine, fixture_cells) -> None:
    """Every successful overlay run should upsert a data_sources row keyed
    by the column name so the freshness panel knows the layer is real."""
    _, runtime, _ = fixture_cells
    apply_overlay_tier("overlay_fixture", runtime)

    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT metadata FROM data_sources WHERE source_key = :k"
            ),
            {"k": "grid_capacity_heatmap"},
        ).first()
    assert row is not None, "apply_overlay_tier must record a data_sources row"
    metadata = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    assert metadata.get("strategy") == "overlay_tier"
    assert metadata.get("layer_id") == "overlay_fixture"
    assert metadata.get("features") == 2


def test_apply_overlay_tier_is_idempotent(engine, fixture_cells) -> None:
    """Running the overlay twice in a row produces the same end state.
    Important because real_ingest.run_all() runs as part of `make
    characterize`, which contributors will re-run after small data
    edits."""
    cells, runtime, _ = fixture_cells

    first = apply_overlay_tier("overlay_fixture", runtime)
    second = apply_overlay_tier("overlay_fixture", runtime)

    assert first["overridden_cells"] == second["overridden_cells"]

    with engine.begin() as conn:
        rows = {
            label: conn.execute(
                text(
                    "SELECT grid_capacity_heatmap, grid_capacity_source "
                    "FROM grid_cells WHERE h3_index = :h"
                ),
                {"h": cells[label]},
            ).first()
            for label in cells
        }
    assert rows["inner"][0] == pytest.approx(0.0, abs=1e-9)
    assert rows["outer_only"][0] == pytest.approx(1.0 / 3.0, abs=1e-9)
    assert rows["inner"][1] == "manual_digitization"
    assert rows["outer_only"][1] == "manual_digitization"
    assert rows["se1_outside"][0] == pytest.approx(0.5, abs=1e-9)
    assert rows["se1_outside"][1] == "bidding_zone"
