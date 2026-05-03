"""Convert Svenska Kraftnät INSPIRE-compliant GML transmission grid files to GPKG.

Reads the source GML files from the Svk INSPIRE feed (downloaded via Sweden's
Länsstyrelsen / Metria geodata catalog) and writes per-feature-type GPKG files
to data/processed/. Reprojects EPSG:4258 (ETRS89 lat/lon) to EPSG:4326 (WGS84)
on the way out so PyDeck can render the GeoJSON directly.

Pre-computes a `voltage_kv` numeric column and a `color_rgba` array column from
nominalVoltage / operatingVoltage so the UI can color-code lines without
client-side computation.

Skips poleNetCommon (50,269 individual poles) — too granular for atlas-scale
visualization. If pole-level data is ever needed for distance characterization,
add a separate ingest path that goes directly to PostGIS rather than the
overlay pipeline.

Usage:
    python scripts/convert_svk_transmission_gml.py
    python scripts/convert_svk_transmission_gml.py /path/to/source/dir
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd

DEFAULT_SOURCE_DIR = Path(r"C:\Users\ketan\Downloads\US.TransmissionsnatForEl")
OUTPUT_DIR = Path("data/processed")

SOURCES: tuple[dict, ...] = (
    {
        "name": "lines",
        "filename": "ElectricityCable_Sweden_EPSG4258.gml",
        "out_filename": "svk_transmission_lines.gpkg",
        # ~5m at Sweden's latitude (1 deg lat ~= 111 km, so 0.00005 deg ~= 5.5 m).
        # Removes sub-pixel jitter without visible distortion at any practical zoom.
        "simplify_tolerance_deg": 0.00005,
    },
    {
        "name": "substations",
        "filename": "mainStations_Sweden_EPSG4258.gml",
        "out_filename": "svk_transmission_substations.gpkg",
        "simplify_tolerance_deg": 0.0,  # points don't simplify
    },
)


def _parse_voltage_kv(raw) -> float | None:
    """Parse a GML voltage attribute. May be a string '400' or numeric.

    Returns voltage in kV. The Svk INSPIRE feed labels operatingVoltage with
    uom='volt' but the actual values are in kV (e.g. 400 means 400 kV, not 400 V).
    Treat anything >=1000 as raw volts (defensive for other feeds), otherwise
    pass through as kV.
    """
    if raw is None:
        return None
    try:
        v = float(raw)
    except (ValueError, TypeError):
        return None
    if v >= 1000:
        return v / 1000.0  # volts -> kV
    return v  # already kV (Svk INSPIRE feed convention)


def _voltage_to_color_rgba(voltage_kv: float | None) -> list[int]:
    """Map voltage to PyDeck-friendly RGBA list. Red=400 kV, Blue=220 kV, Gray=other."""
    if voltage_kv is None:
        return [128, 128, 128, 200]
    if voltage_kv >= 380:
        return [220, 50, 50, 220]  # red — 400 kV class
    if voltage_kv >= 200:
        return [50, 100, 220, 220]  # blue — 220 kV class
    return [128, 128, 128, 200]  # gray — anything else


def _read_gml(in_path: Path) -> gpd.GeoDataFrame:
    """Read a GML file via pyogrio first, falling back to fiona on geometry-type errors.

    Pyogrio is faster and the default engine, but it rejects certain INSPIRE GML
    geometry encodings (e.g. mainStations_Sweden raises 'Geometry type is not
    supported: -2147483648' which is OGR's wkbUnknown sentinel). Fiona handles
    these cases via the older OGR GMLAS path.
    """
    try:
        return gpd.read_file(in_path)
    except Exception as exc:
        msg = str(exc)
        if "Geometry type is not supported" not in msg and "geometry" not in msg.lower():
            raise
        print(f"  [pyogrio failed: {exc.__class__.__name__}] retrying with fiona engine")
        return gpd.read_file(in_path, engine="fiona")


def convert_one(source: dict, source_dir: Path) -> Path:
    in_path = source_dir / source["filename"]
    out_path = OUTPUT_DIR / source["out_filename"]

    if not in_path.exists():
        raise FileNotFoundError(f"Source GML not found: {in_path}")

    print(f"[reading] {in_path}")
    gdf = _read_gml(in_path)
    print(f"  {len(gdf)} features, source CRS: {gdf.crs}")

    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")

    tol = source["simplify_tolerance_deg"]
    if tol > 0:
        gdf["geometry"] = gdf.geometry.simplify(tol, preserve_topology=True)

    # Prefer the column that actually has values. The Svk feed populates
    # operatingVoltage but leaves nominalVoltage null; other feeds may differ.
    voltage_source = None
    for candidate in ("operatingVoltage", "nominalVoltage"):
        if candidate in gdf.columns and gdf[candidate].notna().any():
            voltage_source = candidate
            break

    if voltage_source:
        gdf["voltage_kv"] = gdf[voltage_source].apply(_parse_voltage_kv)
        gdf["color_rgba"] = gdf["voltage_kv"].apply(_voltage_to_color_rgba)
        print(
            f"  voltage parsed from '{voltage_source}': "
            f"{gdf['voltage_kv'].notna().sum()}/{len(gdf)} features have a value"
        )
    else:
        # Substations don't always carry voltage; default to gray.
        gdf["voltage_kv"] = None
        gdf["color_rgba"] = [_voltage_to_color_rgba(None)] * len(gdf)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # GPKG fields don't accept python lists directly; serialize color as JSON string
    # for storage, then parse back when loading. The UI loader (overlays.py) will
    # convert it back to a list before handing to PyDeck.
    gdf["color_rgba"] = gdf["color_rgba"].apply(lambda c: ",".join(str(x) for x in c))
    gdf.to_file(out_path, driver="GPKG")
    print(f"[wrote] {out_path}: {len(gdf)} features")
    return out_path


def main(source_dir: Path = DEFAULT_SOURCE_DIR) -> None:
    if not source_dir.exists():
        print(f"ERROR: source directory not found: {source_dir}", file=sys.stderr)
        sys.exit(1)

    for source in SOURCES:
        convert_one(source, source_dir)

    print()
    print("Note: poleNetCommon_Sweden_EPSG4258.gml is intentionally skipped.")
    print("50,269 individual towers — too granular for atlas-scale display.")


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE_DIR
    main(src)
