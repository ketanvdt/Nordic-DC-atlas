"""Validate the vendored Nordic country outlines used by seed-grid.

These tests run without a database — they only exercise the GeoJSON
file and the loader. The point is to catch regressions in
`scripts/build_country_outlines.py` (or in someone hand-editing the
file) before they reach the seed pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import Point, shape


COUNTRY_OUTLINES_PATH = Path("data/manual/country_outlines.geojson")


@pytest.fixture(scope="module")
def outlines() -> dict[str, dict]:
    """Load the vendored outline as {ISO_A2: GeoJSON geometry}."""
    fc = json.loads(COUNTRY_OUTLINES_PATH.read_text())
    return {feat["properties"]["ISO_A2"]: feat["geometry"] for feat in fc["features"]}


def test_three_countries(outlines):
    assert set(outlines.keys()) == {"SE", "NO", "FI"}


@pytest.mark.parametrize("iso2", ["SE", "NO", "FI"])
def test_geometry_types(outlines, iso2):
    """Each outline must be a (Multi)Polygon — h3.geo_to_cells refuses
    other types and would silently produce zero cells."""
    assert outlines[iso2]["type"] in ("Polygon", "MultiPolygon")


def test_inland_cities_are_inside_their_country(outlines):
    """Sanity check: the outline isn't catastrophically miscoded.

    We deliberately don't use coastal capitals (Stockholm, Oslo,
    Helsinki) because Natural Earth 1:50m generalizes the coastline at
    a scale that can leave them outside the simplified polygon —
    Stockholm sits east of where the 1:50m outline draws the Baltic
    coast. Inland cities are a robust signal that the country body is
    intact."""
    inland_cities = {
        "SE": (17.6357, 59.8586),  # Uppsala
        "NO": (10.4663, 61.1153),  # Lillehammer
        "FI": (23.7610, 61.4978),  # Tampere
    }
    for iso2, (lon, lat) in inland_cities.items():
        geom = shape(outlines[iso2])
        assert geom.contains(Point(lon, lat)), f"{iso2} outline does not contain inland reference city"


def test_svalbard_is_excluded(outlines):
    """Svalbard sits at ~78N. The 4-32E / 55-72N study bbox in the
    build script must clip it from the Norwegian outline. If this
    assertion ever fails, someone changed STUDY_BBOX or removed the
    clip step."""
    geom = shape(outlines["NO"])
    longyearbyen = Point(15.6267, 78.2232)
    assert not geom.contains(longyearbyen), (
        "Norway outline includes Svalbard. Re-run "
        "`python scripts/build_country_outlines.py` and check STUDY_BBOX."
    )


def test_baltic_sea_is_excluded(outlines):
    """A point in the middle of the Baltic Sea (between Sweden and
    Latvia) must NOT be inside any country. The bbox-rectangle seed
    that this file replaces would have included thousands of these
    cells; the regression we're guarding against is exactly that."""
    baltic_midpoint = Point(20.0, 57.0)  # between Gotland and Latvia
    for iso2, geom_dict in outlines.items():
        assert not shape(geom_dict).contains(baltic_midpoint), (
            f"{iso2} contains a point in open Baltic Sea — outline regressed to bbox-style"
        )


def test_loader_matches_file(outlines):
    """seed_h3_grid.load_country_polygons must return the same dict
    we get by reading the file directly. Caches and indirection here
    have bitten us before."""
    from src.characterize.seed_h3_grid import load_country_polygons

    loaded = load_country_polygons()
    assert set(loaded.keys()) == set(outlines.keys())
    for iso2 in outlines:
        # Compare via shapely equality (handles ordering differences in
        # MultiPolygon serialization without forcing a string match).
        assert shape(loaded[iso2]).equals(shape(outlines[iso2]))
