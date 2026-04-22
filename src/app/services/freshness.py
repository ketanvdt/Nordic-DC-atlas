"""Compute the per-layer data-freshness report shown in the Streamlit UI.

This reads the live database to produce an honest map of which features are
real-sourced vs still placeholder vs not ingested yet. No values in the app
are taken on trust — the panel queries counts and distributions directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from src.common.db import get_engine


@dataclass(frozen=True)
class LayerStatus:
    key: str
    kind: str  # "exclusion" | "feature" | "base"
    label: str
    state: str  # "real" | "placeholder" | "missing"
    source: str
    details: str = ""
    stats: dict[str, Any] = field(default_factory=dict)


# Map each column to its source key in data_sources. If a row exists in data_sources
# for the key, the layer is considered real. Otherwise the app checks whether the
# column has any non-null values (placeholder or actual). See _classify() below.
_EXCLUSION_LAYERS: tuple[tuple[str, str, str], ...] = (
    # (column, label, default_source_description)
    ("excl_natura2000", "Natura 2000 / Emerald Network", "OSM designation=natura_2000 + protect_class=97"),
    ("excl_protected", "Protected areas (broader)", "OSM boundary=protected_area / national_park / leisure=nature_reserve"),
    ("excl_floodplain", "Floodplains (EU Flood Directive)", "MSB (SE) / NVE (NO) / SYKE (FI)"),
    ("excl_heritage", "Heritage & archaeological sites", "Riksantikvarieämbetet / Riksantikvaren / Museovirasto"),
    ("excl_airport", "Airports (OLS buffer)", "OSM aeroway=aerodrome + 5km buffer"),
    ("excl_airport_ols", "Airport OLS (precise)", "AIP obstacle data — v2 upgrade"),
    ("excl_military", "Military restriction zones", "Försvarsmakten / Forsvarsbygg / Puolustusvoimat"),
    ("excl_steep_slope", "Slope ≥10%", "Copernicus DEM GLO-30 derived"),
    ("excl_seveso", "Seveso III establishments (500m buffer)", "EEA eSPIRS"),
    ("excl_water_protected", "Surface water exclusion (<500m)", "EEA EU-Hydro / OSM natural=water"),
    ("excl_urban_industrial", "Urban & industrial land", "Copernicus CORINE Land Cover 2018"),
    ("excl_sami_reindeer", "Sámi reindeer husbandry", "Sametinget / NIBIO / Paliskuntain yhdistys"),
)

_FEATURE_LAYERS: tuple[tuple[str, str, str], ...] = (
    ("dist_substation_400kv_m", "Distance to 400kV+ substation", "OSM power=substation + voltage"),
    ("dist_substation_130kv_m", "Distance to 130–299kV substation", "OSM power=substation + voltage"),
    ("dist_transmission_line_m", "Distance to transmission line", "OSM power=line + voltage"),
    ("bidding_zone_price_3y", "Bidding zone price (3-yr)", "ENTSO-E directional + hard-coded zone profiles"),
    ("grid_capacity_heatmap", "Grid capacity proxy", "Svk/Statnett/Fingrid directional v1 profiles"),
    ("dist_dh_network_m", "Distance to DH city", "Manual top-20 Nordic DH operator list"),
    ("dh_readiness_tier", "DH offtake readiness tier", "Manual top-20 Nordic DH operator list"),
    ("annual_mean_temp_c", "Annual mean temperature", "ERA5 — not yet ingested"),
    ("dist_fiber_m", "Distance to fiber", "PTS / Nkom / Traficom — not yet ingested"),
    ("dist_surface_water_m", "Distance to surface water", "EU-Hydro — not yet ingested"),
    ("land_cost_proxy_eur_m2", "Land cost proxy", "GHSL inverse proxy — not yet ingested"),
    ("skilled_workforce_density", "Workforce catchment", "OSRM + GHSL — not yet ingested"),
    ("municipal_receptivity", "Municipal receptivity", "Manual curation — not yet ingested"),
)

# Columns whose current values are populated by the random() placeholder in
# src/characterize/soft_features.py. We tag them as placeholder until real_ingest
# overwrites them and a corresponding data_sources row is recorded.
_PLACEHOLDER_COLUMNS: frozenset[str] = frozenset({
    "annual_mean_temp_c",
    "dist_fiber_m",
    "dist_surface_water_m",
    "land_cost_proxy_eur_m2",
    "skilled_workforce_density",
    "municipal_receptivity",
})

# Columns that carry real data through hard-coded table seeds (not OSM-ingested
# but still "real research" in the v1 sense).
_SEEDED_COLUMNS: frozenset[str] = frozenset({
    "bidding_zone_price_3y",
    "grid_capacity_heatmap",
    "dist_dh_network_m",
    "dh_readiness_tier",
})


def _data_source_keys(engine) -> dict[str, dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT source_key, source_url, license, fetched_at, metadata FROM data_sources")
        ).mappings().all()
    return {r["source_key"]: dict(r) for r in rows}


def _column_stats(engine, column: str, kind: str) -> dict[str, Any]:
    # Use conditional logic since bool columns don't have min/avg
    if kind == "exclusion":
        sql = text(
            f"SELECT COUNT(*) AS total, "
            f"COUNT(*) FILTER (WHERE {column} = TRUE) AS excluded "
            f"FROM grid_cells"
        )
    else:
        sql = text(
            f"SELECT COUNT(*) AS total, "
            f"COUNT(*) FILTER (WHERE {column} IS NOT NULL) AS non_null, "
            f"MIN({column})::float AS min_v, MAX({column})::float AS max_v, "
            f"AVG({column})::float AS mean_v "
            f"FROM grid_cells"
        )
    with engine.begin() as conn:
        row = conn.execute(sql).mappings().first()
    return dict(row) if row else {}


def _classify(column: str, kind: str, ds_keys: dict, stats: dict) -> tuple[str, str]:
    """Return (state, detail) where state is one of real | placeholder | missing."""
    source_key_candidates = [column, column.removeprefix("excl_"), column.replace("_", "")]
    recorded = None
    for key in source_key_candidates:
        if key in ds_keys:
            recorded = ds_keys[key]
            break

    if kind == "exclusion":
        if recorded:
            n = stats.get("excluded", 0) or 0
            return "real", f"{n:,} / {stats.get('total', 0):,} cells excluded"
        excluded = stats.get("excluded", 0) or 0
        if excluded > 0:
            return "real", f"{excluded:,} cells flagged"
        return "missing", "not ingested yet (all FALSE)"

    # feature
    non_null = stats.get("non_null", 0) or 0
    if non_null == 0:
        return "missing", "no values"
    if recorded:
        return "real", f"{non_null:,} cells populated, range {stats.get('min_v', 0):.0f}–{stats.get('max_v', 0):.0f}"
    if column in _SEEDED_COLUMNS:
        return "real", f"{non_null:,} cells populated (seeded via zone/city profile table)"
    if column in _PLACEHOLDER_COLUMNS:
        return "placeholder", f"random uniform noise across {non_null:,} cells"
    return "placeholder", f"{non_null:,} cells populated but no source recorded"


def build_report() -> list[LayerStatus]:
    engine = get_engine()
    ds_keys = _data_source_keys(engine)
    out: list[LayerStatus] = []
    for column, label, source_hint in _EXCLUSION_LAYERS:
        stats = _column_stats(engine, column, "exclusion")
        state, detail = _classify(column, "exclusion", ds_keys, stats)
        out.append(LayerStatus(
            key=column, kind="exclusion", label=label, state=state,
            source=source_hint, details=detail, stats=stats,
        ))
    for column, label, source_hint in _FEATURE_LAYERS:
        stats = _column_stats(engine, column, "feature")
        state, detail = _classify(column, "feature", ds_keys, stats)
        out.append(LayerStatus(
            key=column, kind="feature", label=label, state=state,
            source=source_hint, details=detail, stats=stats,
        ))
    return out


def summary_counts(report: list[LayerStatus]) -> dict[str, int]:
    counts = {"real": 0, "placeholder": 0, "missing": 0}
    for layer in report:
        counts[layer.state] = counts.get(layer.state, 0) + 1
    return counts
