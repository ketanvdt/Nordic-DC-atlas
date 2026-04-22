from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

OUT_DIR = Path("data/processed")
NORDIC_BBOX = (4.5, 54.0, 33.0, 72.5)  # west, south, east, north
ROAD_URL = "https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_roads.zip"
GB_API = "https://www.geoboundaries.org/api/current/gbOpen/{iso}/ADM2/"
ISO_CODES = ["SWE", "NOR", "FIN"]


def _country_code_from_iso3(iso3: str) -> str:
    return {"SWE": "SE", "NOR": "NO", "FIN": "FI"}[iso3]


def _fetch_geojson_url(iso3: str) -> str:
    response = requests.get(GB_API.format(iso=iso3), timeout=30)
    response.raise_for_status()
    payload = response.json()
    url = payload.get("gjDownloadURL")
    if not url:
        raise ValueError(f"No gjDownloadURL for {iso3}")
    return url


def build_municipalities() -> None:
    frames: list[gpd.GeoDataFrame] = []
    for iso3 in ISO_CODES:
        url = _fetch_geojson_url(iso3)
        gdf = gpd.read_file(url).to_crs(4326)
        gdf["country"] = _country_code_from_iso3(iso3)
        gdf["municipality_code"] = gdf.get("shapeID", gdf.get("shapeName"))
        gdf["municipality_name"] = gdf.get("shapeName", gdf.get("shapeID"))
        gdf["overlay_source"] = "geoboundaries_adm2"
        frames.append(gdf[["municipality_code", "municipality_name", "country", "overlay_source", "geometry"]])

    municipalities = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True),
        geometry="geometry",
        crs=4326,
    )
    municipalities.to_file(OUT_DIR / "municipalities.gpkg", driver="GPKG")


def build_roads() -> None:
    roads = gpd.read_file(ROAD_URL).to_crs(4326)
    roads = roads.cx[NORDIC_BBOX[0] : NORDIC_BBOX[2], NORDIC_BBOX[1] : NORDIC_BBOX[3]]
    if roads.empty:
        raise RuntimeError("Natural Earth roads clip returned no rows for Nordic bbox.")

    road_class_col = "type" if "type" in roads.columns else ("fclass" if "fclass" in roads.columns else None)
    if road_class_col:
        roads["road_class"] = roads[road_class_col].astype(str).str.lower()
        keep = roads["road_class"].str.contains("motorway|trunk|primary|secondary", regex=True)
        roads = roads[keep]
    else:
        roads["road_class"] = "unknown"
    roads["overlay_source"] = "natural_earth_10m"
    roads = roads[["road_class", "overlay_source", "geometry"]]
    roads.to_file(OUT_DIR / "roads.gpkg", driver="GPKG")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    build_municipalities()
    build_roads()
    print("Generated authoritative overlays: municipalities.gpkg (geoBoundaries ADM2), roads.gpkg (Natural Earth 10m)")


if __name__ == "__main__":
    main()
