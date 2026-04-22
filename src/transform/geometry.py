from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from src.common.settings import settings


def reproject_and_clip(input_path: str | Path, output_path: str | Path) -> Path:
    gdf = gpd.read_file(input_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.to_crs("EPSG:3035")

    west, south, east, north = [float(x) for x in settings.study_bbox_4326]
    bbox = gpd.GeoSeries([box(west, south, east, north)], crs="EPSG:4326").to_crs("EPSG:3035").iloc[0]
    clipped = gdf.clip(bbox)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    clipped.to_file(out, driver="GPKG")
    return out
