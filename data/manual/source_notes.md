# Manual Data Provenance Notes

Every manually-digitized / manually-curated artifact in this directory must have an entry here documenting:
- What was produced
- When (date)
- Who (researcher)
- Source URL(s) used
- Digitization method / decisions
- Known approximations or confidence level

## Layers that land here (from config/layers/ manual-flagged YAMLs)

| file | layer_id | format |
|---|---|---|
| `grid_capacity_heatmap.geojson` | `grid_capacity_heatmap` | GeoJSON, polygons with `capacity_tier` 0–3 |
| `airport_ols.geojson` | `airport_ols` | GeoJSON, buffered airport polygons (v1 pragmatic) |
| `military_zones.geojson` | `military_zones` | GeoJSON — only if public data found |
| `announced_dc_projects.geojson` | `announced_dc_projects` | GeoJSON points |
| `subsea_cable_landings.geojson` | `subsea_cable_landings` | GeoJSON points |
| `dh_offtake_tier.csv` | `dh_offtake_tier` | CSV keyed by municipality code |
| `municipal_receptivity.csv` | `municipal_receptivity` | CSV keyed by municipality code |

## Provenance entries

(Researchers append an entry below per artifact produced. Template:)

```
### <filename> — <YYYY-MM-DD> — <researcher name>

Source(s):
- <URL or citation>

Method:
- <brief description of how the data was produced>

Confidence:
- high | medium | low

Known caveats:
- <any approximations, limitations>

Next refresh:
- <YYYY-MM-DD or "on publication of newer source">
```

---

### svk_transmission_lines.gpkg + svk_transmission_substations.gpkg — 2026-05-04 — ketan

Source(s):
- ATOM feed (catalog): https://ext-geodatakatalog-forv.lansstyrelsen.se/PlaneringsKatalogen/GetAtomView?url=https://gis-services.metria.se/svkfeed/svk_topfeed_transmission.xml
- Underlying GML files (zip): served via Metria for Svenska Kraftnät, INSPIRE-compliant.
  - `ElectricityCable_Sweden_EPSG4258.gml` — 433 transmission cables (220 + 400 kV class)
  - `mainStations_Sweden_EPSG4258.gml` — 227 main substations (transmission appurtenances)
  - `poleNetCommon_Sweden_EPSG4258.gml` — 50,269 individual poles (intentionally NOT ingested; too granular for atlas-scale display)

Method:
- Downloaded the zip from the Lantmäteriet / Länsstyrelsen INSPIRE catalog feed (URL above) on 2026-05-04.
- Converted GML → GPKG via `scripts/convert_svk_transmission_gml.py`. Reprojected EPSG:4258 → EPSG:4326. Simplified line geometries with ~5m tolerance for browser rendering. Pre-computed `voltage_kv` (parsed from the populated `operatingVoltage` field; `nominalVoltage` was empty across all 433 features) and `color_rgba` (red for 400 kV class, blue for 220 kV, gray for other) so PyDeck can render directly.
- Voltage distribution after parse: 226 × 220 kV, 196 × 400 kV, plus a few outliers (130, 285, 300, 500 kV — kept with gray default).
- Substation file was unreadable by pyogrio's GML driver ("Geometry type is not supported: -2147483648"); fell back to fiona engine which handled it. The converter tries pyogrio first and falls back automatically.

Confidence:
- high — official Svk INSPIRE feed, structured voltage attribute, no manual digitization

Known caveats:
- `operatingVoltage` is labeled with `uom='volt'` in the source schema but actual values are kV (e.g. 400 means 400 kV not 400 V). The converter's `_parse_voltage_kv` handles both conventions — anything ≥ 1000 is treated as raw volts and divided.
- `nominalVoltage` column exists in the GML schema but is empty across all 433 cable features in this snapshot; `operatingVoltage` is the populated field.
- Svk publishes only the national transmission grid (≥ 220 kV stamnät). The OSM-derived `data/processed/transmission_lines.gpkg` and `data/processed/substations.gpkg` remain the source for regional 130 kV — Svk does NOT replace them.
- Poles GML (50,269 features, 64.7 MB) is intentionally skipped to avoid overloading the browser map. If pole-level data is ever needed for distance characterization, ingest directly into PostGIS rather than the overlay pipeline.
- Source CRS is EPSG:4258 (ETRS89 lat/lon); offset from EPSG:4326 (WGS84) is ~3 m for Sweden — well below the cell-resolution of the atlas (H3 res-8 ≈ 0.86 km²). Re-projection is via standard pyproj pipelines.

Next refresh:
- Quarterly. The Svk stamnät changes on a years timescale; quarterly is conservative. Monitor the ATOM feed checksum or download date for changes.
