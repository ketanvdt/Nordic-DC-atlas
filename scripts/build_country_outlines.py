"""Fetch Nordic country outlines from Natural Earth and vendor them in repo.

Run-once provenance script. The output lives at
data/manual/country_outlines.geojson and is committed so seed-grid does
not require network access.

Source:  Natural Earth 1:50m Cultural Vectors, "Admin 0 - Countries"
         (public domain). Mirrored on GitHub by nvkelso/natural-earth-vector.

Why mirror via GitHub raw rather than naciscdn.org: this sandbox can
reach github.com but not naciscdn.org. The nvkelso mirror is the de
facto canonical copy used by most tools (geopandas pinned it for years).

What this script does, and why:

  1. Filters to SE/NO/FI by ADM0_A3 code, not ISO_A2. Norway's ISO_A2
     in Natural Earth is "-99" (the dispute-resolution sentinel) — see
     the inspection of NAME_LONG / ADM0_A3 we did when first running
     this. ADM0_A3 is the only stable code for all three countries.

  2. Clips each MultiPolygon to a Nordic study bbox (4-32E, 55-72N).
     Reason: Natural Earth's Norway feature includes Svalbard, Jan
     Mayen, and Bouvet Island. Those territories are out of scope
     for v1 siting and would otherwise produce H3 cells in the
     Arctic / South Atlantic. The bbox also caps Sweden/Finland to
     the populated south, which is a no-op there but makes the
     contract explicit.

  3. Simplifies to ~0.01 deg tolerance (~1km). The input is a 3 MB
     GeoJSON; filtering and simplifying gets the vendored file under
     ~300 KB while preserving the outline at the resolution H3 res-8
     cells care about (cell ~0.74 km^2).

The output is a FeatureCollection of 3 features keyed by an ISO_A2
property the seed loader can use directly. We do NOT preserve all the
upstream attributes — they're noise for our purpose and bloat the
diff when the file is regenerated.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import urllib.request

from shapely.geometry import box, mapping, shape


SOURCE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector"
    "/master/geojson/ne_50m_admin_0_countries.geojson"
)

# ADM0_A3 -> our ISO_A2 (Natural Earth's ISO_A2 column is "-99" for Norway).
NORDIC_CODES = {"SWE": "SE", "NOR": "NO", "FIN": "FI"}

# Nordic study bbox: 4-32 lon, 55-72 lat. Trims Svalbard and Bouvet
# from Norway, no-op for Sweden / Finland.
STUDY_BBOX = box(4.0, 55.0, 32.0, 72.0)

SIMPLIFY_TOLERANCE_DEG = 0.01  # ~1 km

OUTPUT_PATH = Path("data/manual/country_outlines.geojson")


def main() -> int:
    print(f"fetching {SOURCE_URL}", file=sys.stderr)
    with urllib.request.urlopen(SOURCE_URL, timeout=60.0) as resp:
        src = json.load(resp)

    out_features = []
    for feat in src["features"]:
        adm0 = feat["properties"].get("ADM0_A3")
        if adm0 not in NORDIC_CODES:
            continue
        iso_a2 = NORDIC_CODES[adm0]
        geom = shape(feat["geometry"])
        clipped = geom.intersection(STUDY_BBOX)
        if clipped.is_empty:
            print(f"  WARNING: {iso_a2} clipped to empty geometry", file=sys.stderr)
            continue
        # Simplify after clipping so simplification doesn't introduce
        # geometry artifacts that fall outside the bbox.
        simplified = clipped.simplify(SIMPLIFY_TOLERANCE_DEG, preserve_topology=True)
        if simplified.is_empty:
            simplified = clipped
        out_features.append(
            {
                "type": "Feature",
                "properties": {"ISO_A2": iso_a2, "name": feat["properties"]["NAME"]},
                "geometry": mapping(simplified),
            }
        )
        print(
            f"  {iso_a2} {feat['properties']['NAME']:8s}  "
            f"input_pts={_count_points(geom):>6}  "
            f"clipped_pts={_count_points(clipped):>6}  "
            f"simplified_pts={_count_points(simplified):>6}",
            file=sys.stderr,
        )

    if len(out_features) != 3:
        print(
            f"ERROR: expected 3 Nordic features, got {len(out_features)}",
            file=sys.stderr,
        )
        return 1

    out = {"type": "FeatureCollection", "features": out_features}
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(out, indent=2))
    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"wrote {OUTPUT_PATH} ({size_kb:.0f} KB)", file=sys.stderr)
    return 0


def _count_points(geom) -> int:
    """Approximate point count for logging — exact number isn't critical."""
    if geom.is_empty:
        return 0
    if geom.geom_type == "Polygon":
        return len(geom.exterior.coords) + sum(len(r.coords) for r in geom.interiors)
    if geom.geom_type == "MultiPolygon":
        return sum(_count_points(p) for p in geom.geoms)
    if geom.geom_type == "GeometryCollection":
        return sum(_count_points(g) for g in geom.geoms)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
