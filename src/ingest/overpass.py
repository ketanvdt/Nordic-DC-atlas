from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import httpx
from shapely.geometry import LineString, Point, Polygon, MultiPolygon

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
NORDIC_BBOX = (55.0, 4.5, 72.5, 33.0)  # south, west, north, east
COUNTRY_BBOXES = {
    # south, west, north, east
    "SE": (55.2, 11.0, 69.2, 24.5),
    "NO": (57.9, 4.5, 71.5, 31.0),
    "FI": (59.5, 19.0, 70.2, 32.0),
}


@dataclass(frozen=True)
class OverpassFetch:
    """A single Overpass fetch producing a GeoPackage for downstream characterization."""

    key: str
    overpass_ql: str
    out_kind: str  # "polygon" | "line" | "point"


def _bbox_clause(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    return f"({s},{w},{n},{e})"


def build_queries(bbox: tuple[float, float, float, float] = NORDIC_BBOX) -> list[OverpassFetch]:
    bb = _bbox_clause(bbox)
    return [
        OverpassFetch(
            key="natura2000",
            out_kind="polygon",
            overpass_ql=f"""
                [out:json][timeout:300];
                (
                  way["boundary"="protected_area"]["protect_class"="97"]{bb};
                  relation["boundary"="protected_area"]["protect_class"="97"]{bb};
                  way["designation"="natura_2000"]{bb};
                  relation["designation"="natura_2000"]{bb};
                );
                out geom;
            """,
        ),
        OverpassFetch(
            key="protected",
            out_kind="polygon",
            overpass_ql=f"""
                [out:json][timeout:300];
                (
                  way["boundary"="protected_area"]{bb};
                  relation["boundary"="protected_area"]{bb};
                  way["boundary"="national_park"]{bb};
                  relation["boundary"="national_park"]{bb};
                  way["leisure"="nature_reserve"]{bb};
                  relation["leisure"="nature_reserve"]{bb};
                );
                out geom;
            """,
        ),
        OverpassFetch(
            key="airport",
            out_kind="polygon",
            overpass_ql=f"""
                [out:json][timeout:180];
                (
                  way["aeroway"="aerodrome"]{bb};
                  relation["aeroway"="aerodrome"]{bb};
                );
                out geom;
            """,
        ),
        OverpassFetch(
            key="substations",
            out_kind="point",
            overpass_ql=f"""
                [out:json][timeout:300];
                (
                  node["power"="substation"]{bb};
                  way["power"="substation"]{bb};
                );
                out center;
            """,
        ),
        OverpassFetch(
            key="transmission_lines",
            out_kind="line",
            overpass_ql=f"""
                [out:json][timeout:300];
                (
                  way["power"="line"]["voltage"]{bb};
                );
                out geom;
            """,
        ),
    ]


def _way_to_geom(element: dict, out_kind: str):
    coords = [(pt["lon"], pt["lat"]) for pt in element.get("geometry", [])]
    if len(coords) < 2:
        return None
    if out_kind == "line":
        return LineString(coords)
    # polygon: ensure closed
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    if len(coords) < 4:
        return None
    try:
        return Polygon(coords)
    except Exception:
        return None


def _relation_to_multipolygon(element: dict):
    rings: list[list[tuple[float, float]]] = []
    for member in element.get("members", []):
        if member.get("type") != "way":
            continue
        geom = member.get("geometry") or []
        if not geom:
            continue
        ring = [(pt["lon"], pt["lat"]) for pt in geom]
        if len(ring) >= 3:
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            rings.append(ring)
    polygons: list[Polygon] = []
    for ring in rings:
        try:
            polygons.append(Polygon(ring))
        except Exception:
            continue
    if not polygons:
        return None
    return MultiPolygon(polygons) if len(polygons) > 1 else polygons[0]


def _element_to_point(element: dict):
    if element.get("type") == "node":
        return Point(element["lon"], element["lat"])
    center = element.get("center") or {}
    if "lon" in center and "lat" in center:
        return Point(center["lon"], center["lat"])
    geom = element.get("geometry") or []
    if geom:
        lons = [pt["lon"] for pt in geom]
        lats = [pt["lat"] for pt in geom]
        return Point(sum(lons) / len(lons), sum(lats) / len(lats))
    return None


def elements_to_gdf(elements: Iterable[dict], out_kind: str) -> gpd.GeoDataFrame:
    records: list[dict] = []
    for el in elements:
        tags = el.get("tags") or {}
        geom = None
        etype = el.get("type")
        if out_kind == "point":
            geom = _element_to_point(el)
        elif etype == "way":
            geom = _way_to_geom(el, out_kind)
        elif etype == "relation":
            geom = _relation_to_multipolygon(el) if out_kind == "polygon" else None
        if geom is None or geom.is_empty:
            continue
        records.append({
            "osm_id": el.get("id"),
            "osm_type": etype,
            "name": tags.get("name"),
            "voltage": tags.get("voltage"),
            "operator": tags.get("operator"),
            "designation": tags.get("designation"),
            "protect_class": tags.get("protect_class"),
            "aeroway": tags.get("aeroway"),
            "geometry": geom,
        })
    if not records:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs="EPSG:4326")
    return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")


_HEADERS = {
    "User-Agent": "nordic-site-atlas/0.1 (ECODC research build; contact via Verdatir)",
    "Accept": "application/json, */*",
}


def fetch(fetch_spec: OverpassFetch, timeout: float = 360.0) -> gpd.GeoDataFrame:
    last_err: Exception | None = None
    for mirror in OVERPASS_MIRRORS:
        try:
            with httpx.Client(timeout=timeout, headers=_HEADERS) as client:
                resp = client.post(mirror, data={"data": fetch_spec.overpass_ql})
                resp.raise_for_status()
                payload = resp.json()
            return elements_to_gdf(payload.get("elements", []), fetch_spec.out_kind)
        except (httpx.HTTPError, ValueError) as exc:
            last_err = exc
            print(f"[retry] {fetch_spec.key}: {mirror} failed ({exc.__class__.__name__}); trying next mirror")
    assert last_err is not None
    raise last_err


def fetch_per_country(
    key: str,
    tag_clauses: list[str],
    out_kind: str,
    timeout: float = 360.0,
) -> gpd.GeoDataFrame:
    """Run the same tag query separately per country bbox, concatenating results.

    Use for queries too large for a single pan-Nordic call (504s on main mirror).
    """
    frames: list[gpd.GeoDataFrame] = []
    for country, bbox in COUNTRY_BBOXES.items():
        bb = _bbox_clause(bbox)
        parts = []
        for clause in tag_clauses:
            parts.append(f"{clause}{bb};")
        ql = f"[out:json][timeout:300];\n(\n  " + "\n  ".join(parts) + "\n);\nout geom;"
        spec = OverpassFetch(key=f"{key}_{country}", overpass_ql=ql, out_kind=out_kind)
        gdf = fetch(spec, timeout=timeout)
        if not gdf.empty:
            gdf["country_hint"] = country
            frames.append(gdf)
            print(f"[ok-part] {key}/{country}: {len(gdf)} features")
        else:
            print(f"[empty-part] {key}/{country}")
    if not frames:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs="EPSG:4326")
    import pandas as _pd
    return gpd.GeoDataFrame(_pd.concat(frames, ignore_index=True), geometry="geometry", crs="EPSG:4326")


def fetch_and_save(fetch_spec: OverpassFetch, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{fetch_spec.key}.gpkg"
    gdf = fetch(fetch_spec)
    if gdf.empty:
        print(f"[empty] {fetch_spec.key}: no features returned")
    else:
        gdf.to_file(out_path, driver="GPKG")
        print(f"[ok] {fetch_spec.key}: {len(gdf)} features -> {out_path}")
    return out_path
