"""Validate that data/manual/grid_capacity_heatmap.geojson reflects the
qualitative facts asserted by the source PDFs in data/raw/.

These tests are the user-visible guard rail for "the digitized data
matches the source documents" — every assertion below cites the PDF the
fact comes from. They run on file content alone (no DB), so they stay in
the standard `pytest -q` lane and execute fast.

When researchers extend the GeoJSON for NO/FI or refine SE polygons,
update / add assertions here to keep documents and data in sync.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


GEOJSON = Path("data/manual/grid_capacity_heatmap.geojson")
RAW_DIR = Path("data/raw")
SOURCE_NOTES = Path("data/manual/source_notes.md")

# Bidding-zone latitude rules used by `src/characterize/power_layers.py`.
# Tests below use these to assert each polygon sits in the right zone.
SE1_LAT_MIN = 66.0
SE2_LAT_MIN = 62.0
SE2_LAT_MAX = 66.0
SE3_LAT_MIN = 58.0
SE3_LAT_MAX = 62.0
SE4_LAT_MAX = 58.0
SE_LON_MIN = 11.0
SE_LON_MAX = 25.0


@pytest.fixture(scope="module")
def doc() -> dict:
    return json.loads(GEOJSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def features(doc) -> list[dict]:
    return doc["features"]


def _bbox(coords: list[list[list[float]]]) -> tuple[float, float, float, float]:
    """Return (lon_min, lat_min, lon_max, lat_max) of a Polygon ring."""
    ring = coords[0]
    lons = [c[0] for c in ring]
    lats = [c[1] for c in ring]
    return min(lons), min(lats), max(lons), max(lats)


def test_geojson_loads_as_feature_collection(doc) -> None:
    assert doc["type"] == "FeatureCollection"
    assert doc["crs"]["properties"]["name"].endswith("4326")


def test_has_expected_feature_ids(features) -> None:
    ids = {f["id"] for f in features}
    assert ids == {
        "se1_ample",
        "se2_ample",
        "se3_constrained",
        "se3_stockholm_malardalen_red",
        "se4_red",
    }


def test_every_feature_has_required_properties(features) -> None:
    required = {
        "region", "country", "capacity_tier", "tier_label",
        "source_pdf", "source_url", "valid_from", "confidence", "notes",
    }
    for f in features:
        missing = required - set(f["properties"].keys())
        assert not missing, f"{f['id']} missing properties: {missing}"


def test_capacity_tiers_in_valid_range(features) -> None:
    for f in features:
        tier = f["properties"]["capacity_tier"]
        assert 0 <= tier <= 3, f"{f['id']} tier {tier} out of [0,3]"


def test_se1_is_ample_per_svk_nup(features) -> None:
    """Svenska kraftnät NUP 2026-2035 frames SE1 (Norrbotten) as a net-export
    region with ample capacity headroom. The polygon must reflect that."""
    f = next(x for x in features if x["id"] == "se1_ample")
    assert f["properties"]["country"] == "SE"
    assert f["properties"]["capacity_tier"] == 3, "SE1 must be tier 3 per Svk NUP framing"
    lon_min, lat_min, _, _ = _bbox(f["geometry"]["coordinates"])
    assert lat_min >= SE1_LAT_MIN - 0.5, f"SE1 polygon dips below the SE1 lat band: {lat_min}"
    assert "svk_natutveckling_nup_2026-2035.pdf" in f["properties"]["source_pdf"]


def test_se2_is_ample_per_svk_nup(features) -> None:
    f = next(x for x in features if x["id"] == "se2_ample")
    assert f["properties"]["country"] == "SE"
    assert f["properties"]["capacity_tier"] == 3
    _, lat_min, _, lat_max = _bbox(f["geometry"]["coordinates"])
    assert SE2_LAT_MIN - 0.5 <= lat_min < SE2_LAT_MAX
    assert SE2_LAT_MIN < lat_max <= SE2_LAT_MAX + 0.5


def test_se3_general_is_constrained_per_svk_north_south_package(features) -> None:
    """Svk's north-south investment package (svenska-kraftnats-investeringspaket-nordsyd.pdf)
    is built specifically to relieve the SE3 deficit. The polygon must
    encode that as tier 1 (constrained) — strictly worse than SE2."""
    f = next(x for x in features if x["id"] == "se3_constrained")
    assert f["properties"]["country"] == "SE"
    assert f["properties"]["capacity_tier"] == 1
    _, lat_min, _, lat_max = _bbox(f["geometry"]["coordinates"])
    assert SE3_LAT_MIN - 0.5 <= lat_min < SE3_LAT_MAX
    assert SE3_LAT_MIN < lat_max <= SE3_LAT_MAX + 0.5
    src = f["properties"]["source_pdf"]
    assert "svenska-kraftnats-investeringspaket-nordsyd.pdf" in src


def test_se3_stockholm_is_red_and_inside_se3_per_dso_plans(features) -> None:
    """Both Vattenfall (vattenfall-eldistributions-natutvecklingsplan-2025-2034.pdf)
    and Ellevio (ellevios-natutvecklingsplan-2025-2034.pdf) put Mälardalen /
    Stockholm at the top of their reinforcement priority lists. The Stockholm
    polygon must be tier 0 AND geographically contained within the SE3
    surround polygon, so MIN(tier) overlay produces the expected hotspot."""
    sthlm = next(x for x in features if x["id"] == "se3_stockholm_malardalen_red")
    surround = next(x for x in features if x["id"] == "se3_constrained")

    assert sthlm["properties"]["capacity_tier"] == 0
    src = sthlm["properties"]["source_pdf"]
    assert "vattenfall-eldistributions-natutvecklingsplan-2025-2034.pdf" in src
    assert "ellevios-natutvecklingsplan-2025-2034.pdf" in src

    sthlm_box = _bbox(sthlm["geometry"]["coordinates"])
    surround_box = _bbox(surround["geometry"]["coordinates"])
    assert sthlm_box[0] >= surround_box[0], "Stockholm polygon must be inside SE3 surround (lon)"
    assert sthlm_box[1] >= surround_box[1], "Stockholm polygon must be inside SE3 surround (lat)"
    assert sthlm_box[2] <= surround_box[2], "Stockholm polygon must be inside SE3 surround (lon)"
    assert sthlm_box[3] <= surround_box[3], "Stockholm polygon must be inside SE3 surround (lat)"


def test_se4_is_red_per_svk_nup_exec_summary(features) -> None:
    """Svk NUP 2026-2035 executive summary identifies SE4 as the largest
    structural net-import deficit. Tier must be 0."""
    f = next(x for x in features if x["id"] == "se4_red")
    assert f["properties"]["country"] == "SE"
    assert f["properties"]["capacity_tier"] == 0
    _, _, _, lat_max = _bbox(f["geometry"]["coordinates"])
    assert lat_max <= SE4_LAT_MAX + 0.5, f"SE4 polygon extends above SE3/SE4 boundary: {lat_max}"
    assert "svk_natutveckling_nup_2026-2035.pdf" in f["properties"]["source_pdf"]


def test_every_cited_pdf_exists_in_data_raw(features) -> None:
    """Every source_pdf cited in a feature must be a real file under data/raw/."""
    available = {p.name for p in RAW_DIR.iterdir() if p.is_file()}
    cited: set[str] = set()
    for f in features:
        for token in str(f["properties"]["source_pdf"]).split(";"):
            name = token.strip()
            if name.endswith(".pdf"):
                cited.add(name)
    missing = cited - available
    assert not missing, f"GeoJSON cites PDFs that are not in data/raw/: {sorted(missing)}"


def test_polygons_stay_within_swedish_bbox(features) -> None:
    """Every SE feature's polygon must fall inside a generous Sweden bounding box."""
    for f in features:
        if f["properties"]["country"] != "SE":
            continue
        lon_min, lat_min, lon_max, lat_max = _bbox(f["geometry"]["coordinates"])
        assert SE_LON_MIN - 1 <= lon_min and lon_max <= SE_LON_MAX + 1, f"{f['id']} lon out of SE bbox"
        assert 54.5 <= lat_min and lat_max <= 70.0, f"{f['id']} lat out of SE bbox"


def test_provenance_block_exists_in_source_notes() -> None:
    """source_notes.md must have an entry for grid_capacity_heatmap.geojson."""
    text = SOURCE_NOTES.read_text(encoding="utf-8")
    assert "### grid_capacity_heatmap.geojson" in text, "Missing provenance entry in source_notes.md"
    # Each PDF cited in the GeoJSON must also appear in the provenance block.
    geo = json.loads(GEOJSON.read_text(encoding="utf-8"))
    cited: set[str] = set()
    for f in geo["features"]:
        for token in str(f["properties"]["source_pdf"]).split(";"):
            name = token.strip()
            if name.endswith(".pdf"):
                cited.add(name)
    for pdf in cited:
        assert pdf in text, f"source_notes.md does not reference cited PDF {pdf}"
