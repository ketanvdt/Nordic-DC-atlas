from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import streamlit as st


def get_overlay_mtime(path: str) -> float:
    file_path = Path(path)
    return file_path.stat().st_mtime if file_path.exists() else 0.0


def _to_geojson_dict(path: str, simplify_tolerance: float = 0.0) -> dict[str, Any] | None:
    file_path = Path(path)
    if not file_path.exists():
        return None
    gdf = gpd.read_file(file_path)
    if gdf.empty:
        return None
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")
    if simplify_tolerance > 0:
        gdf["geometry"] = gdf.geometry.simplify(simplify_tolerance)
    return gdf.__geo_interface__


@st.cache_data(show_spinner=False)
def load_municipality_overlay(path: str, mtime: float) -> dict[str, Any] | None:
    _ = mtime
    return _to_geojson_dict(path, simplify_tolerance=0.001)


@st.cache_data(show_spinner=False)
def load_roads_overlay(path: str, mtime: float) -> dict[str, Any] | None:
    _ = mtime
    return _to_geojson_dict(path, simplify_tolerance=0.0005)


def _expand_color_rgba(geojson: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert color_rgba CSV string property to a list[int] for PyDeck.

    Svk GPKG stores color_rgba as comma-separated strings (GPKG fields don't
    accept python lists natively). PyDeck's GeoJsonLayer expects an actual
    array when get_*_color references a property. Mutate features in place.
    """
    if not geojson or "features" not in geojson:
        return geojson
    for feat in geojson["features"]:
        props = feat.get("properties") or {}
        raw = props.get("color_rgba")
        if isinstance(raw, str):
            try:
                props["color_rgba"] = [int(x) for x in raw.split(",")]
            except (ValueError, AttributeError):
                props["color_rgba"] = [128, 128, 128, 200]
        feat["properties"] = props
    return geojson


@st.cache_data(show_spinner=False)
def load_svk_transmission_lines_overlay(path: str, mtime: float) -> dict[str, Any] | None:
    _ = mtime
    return _expand_color_rgba(_to_geojson_dict(path, simplify_tolerance=0.0))


@st.cache_data(show_spinner=False)
def load_svk_substations_overlay(path: str, mtime: float) -> dict[str, Any] | None:
    _ = mtime
    return _expand_color_rgba(_to_geojson_dict(path, simplify_tolerance=0.0))
