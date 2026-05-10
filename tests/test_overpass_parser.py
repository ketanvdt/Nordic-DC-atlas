"""Tests for src/ingest/overpass.py — the parser that turns Overpass
JSON responses into a GeoDataFrame the rest of the pipeline can write
as a GeoPackage.

The parser has had zero tests until now. The natura_2000 path goes
through three different element kinds (way polygon, relation
multipolygon, malformed element to skip) and one of them has been
quietly broken in the past — `_relation_to_multipolygon` builds rings
without checking ring orientation or inner-vs-outer roles. These
tests pin the current contract so future regressions show up.

The fixture at tests/fixtures/overpass_natura2000_sample.json is a
synthetic Overpass response shaped like a real natura_2000 query but
with hand-built coordinates. See the file header for caveats.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import LineString, MultiPolygon, Point, Polygon

from src.ingest.overpass import (
    _element_to_point,
    _relation_to_multipolygon,
    _way_to_geom,
    build_queries,
    elements_to_gdf,
)


FIXTURE_PATH = Path("tests/fixtures/overpass_natura2000_sample.json")


@pytest.fixture(scope="module")
def fixture_payload() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


# ---------------------------------------------------------------------------
# _way_to_geom
# ---------------------------------------------------------------------------


def test_way_to_polygon_closes_open_rings():
    """OSM ways often arrive open (last vertex != first). The parser
    must close them before constructing a Polygon, otherwise shapely
    raises and we silently drop the feature."""
    open_way = {
        "geometry": [
            {"lat": 0.0, "lon": 0.0},
            {"lat": 1.0, "lon": 0.0},
            {"lat": 1.0, "lon": 1.0},
            {"lat": 0.0, "lon": 1.0},
        ]
    }
    geom = _way_to_geom(open_way, out_kind="polygon")
    assert isinstance(geom, Polygon)
    assert geom.is_valid
    # Bounds check: should be the unit square we drew.
    assert geom.bounds == (0.0, 0.0, 1.0, 1.0)


def test_way_to_polygon_rejects_two_point_ways():
    """A 2-point way cannot be a polygon — even after closing, it's a
    degenerate triangle. Fixture element id 1002 exercises this."""
    way = {"geometry": [{"lat": 0.0, "lon": 0.0}, {"lat": 1.0, "lon": 1.0}]}
    assert _way_to_geom(way, out_kind="polygon") is None


def test_way_to_polygon_rejects_empty_geometry():
    """Empty geometry list — fixture element id 1003. Defensive against
    Overpass returning {tags: ..., geometry: []} for filtered-out ways."""
    assert _way_to_geom({"geometry": []}, out_kind="polygon") is None


def test_way_to_line_for_transmission_path():
    """The transmission_lines fetch uses out_kind='line'. Same way
    structure but different geometry type."""
    way = {
        "geometry": [
            {"lat": 59.0, "lon": 18.0},
            {"lat": 59.1, "lon": 18.1},
            {"lat": 59.2, "lon": 18.2},
        ]
    }
    geom = _way_to_geom(way, out_kind="line")
    assert isinstance(geom, LineString)
    assert geom.length > 0


# ---------------------------------------------------------------------------
# _relation_to_multipolygon
# ---------------------------------------------------------------------------


def test_relation_with_two_outer_ways_yields_multipolygon():
    """Stockholm archipelago fixture (relation id 2001) has two outer
    rings. Result must be a MultiPolygon with 2 parts."""
    relation = {
        "members": [
            {
                "type": "way",
                "geometry": [
                    {"lat": 59.40, "lon": 18.60},
                    {"lat": 59.43, "lon": 18.61},
                    {"lat": 59.43, "lon": 18.66},
                    {"lat": 59.40, "lon": 18.66},
                ],
            },
            {
                "type": "way",
                "geometry": [
                    {"lat": 59.50, "lon": 18.70},
                    {"lat": 59.52, "lon": 18.71},
                    {"lat": 59.52, "lon": 18.75},
                    {"lat": 59.50, "lon": 18.75},
                ],
            },
        ]
    }
    geom = _relation_to_multipolygon(relation)
    assert isinstance(geom, MultiPolygon)
    assert len(list(geom.geoms)) == 2


def test_relation_with_single_way_collapses_to_polygon():
    """Single member should collapse to Polygon, not wrap in
    MultiPolygon — matches the parser's current branch and avoids
    `MultiPolygon([single])` overhead in the GPKG."""
    relation = {
        "members": [
            {
                "type": "way",
                "geometry": [
                    {"lat": 0.0, "lon": 0.0},
                    {"lat": 1.0, "lon": 0.0},
                    {"lat": 1.0, "lon": 1.0},
                    {"lat": 0.0, "lon": 1.0},
                ],
            },
        ]
    }
    geom = _relation_to_multipolygon(relation)
    assert isinstance(geom, Polygon)


def test_relation_with_only_node_members_is_dropped():
    """Relation where every member is a node (not a way) yields no
    rings — fixture id 2002. Parser must return None, not an empty
    MultiPolygon (downstream `to_postgis` would choke on those)."""
    relation = {"members": [{"type": "node", "ref": 1, "role": "admin_centre"}]}
    assert _relation_to_multipolygon(relation) is None


# ---------------------------------------------------------------------------
# _element_to_point
# ---------------------------------------------------------------------------


def test_node_to_point():
    geom = _element_to_point({"type": "node", "lon": 18.0, "lat": 59.3})
    assert isinstance(geom, Point)
    assert (geom.x, geom.y) == (18.0, 59.3)


def test_way_substation_uses_center():
    """Substations are ways but get returned with `out center;`. The
    parser should use the centroid hint instead of trying to build a
    polygon."""
    way = {"type": "way", "center": {"lon": 17.5, "lat": 59.0}}
    geom = _element_to_point(way)
    assert isinstance(geom, Point)
    assert (geom.x, geom.y) == (17.5, 59.0)


def test_way_geometry_falls_back_to_centroid_average():
    """When neither node nor center is present but a geometry array
    is, fall back to the arithmetic centroid. Defensive — Overpass
    occasionally returns this shape for `out geom;` substation queries."""
    way = {
        "type": "way",
        "geometry": [
            {"lat": 59.0, "lon": 18.0},
            {"lat": 59.0, "lon": 18.2},
            {"lat": 59.2, "lon": 18.2},
            {"lat": 59.2, "lon": 18.0},
        ],
    }
    geom = _element_to_point(way)
    assert isinstance(geom, Point)
    assert geom.x == pytest.approx(18.1)
    assert geom.y == pytest.approx(59.1)


# ---------------------------------------------------------------------------
# elements_to_gdf — full integration on the fixture
# ---------------------------------------------------------------------------


def test_natura2000_fixture_yields_two_valid_polygons(fixture_payload):
    """The fixture has 5 elements: a valid way polygon (1001), a
    way too short to be a polygon (1002), a relation multipolygon
    with 2 outer rings (2001), a relation with only node members
    (2002), and an empty-geometry way (1003).

    Expected output: 2 geometries — one Polygon (1001) and one
    MultiPolygon (2001). The other three must be filtered out."""
    gdf = elements_to_gdf(fixture_payload["elements"], out_kind="polygon")
    assert len(gdf) == 2
    geom_types = sorted(gdf.geometry.geom_type.tolist())
    assert geom_types == ["MultiPolygon", "Polygon"]
    assert gdf.crs is not None
    assert gdf.crs.to_epsg() == 4326
    # Tags must round-trip
    assert "natura_2000" in gdf["designation"].tolist()
    assert "97" in gdf["protect_class"].fillna("").tolist()


def test_empty_response_returns_empty_gdf_with_correct_crs():
    """Overpass returns {elements: []} for queries that match nothing.
    Downstream `to_file('foo.gpkg')` requires a valid CRS even on
    empty frames — pyogrio errors otherwise."""
    gdf = elements_to_gdf([], out_kind="polygon")
    assert gdf.empty
    assert gdf.crs is not None
    assert gdf.crs.to_epsg() == 4326


# ---------------------------------------------------------------------------
# build_queries — natura_2000 specific
# ---------------------------------------------------------------------------


def test_natura2000_query_targets_both_designation_and_protect_class():
    """OSM tags Natura 2000 sites two ways depending on the editor:
    `designation=natura_2000` (preferred) and
    `boundary=protected_area + protect_class=97` (legacy).
    The query must catch both. If a future refactor accidentally drops
    one, ~30% of Nordic Natura 2000 sites disappear from the GPKG."""
    queries = {q.key: q for q in build_queries()}
    assert "natura2000" in queries
    ql = queries["natura2000"].overpass_ql
    assert 'designation"="natura_2000"' in ql
    assert 'protect_class"="97"' in ql
    # Both ways and relations — OSM mappers use both.
    assert ql.count("way[") >= 2
    assert ql.count("relation[") >= 2
