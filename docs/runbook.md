# Runbook: Nordic Atlas v1

## Refresh cycle

1. `make up`
2. `make migrate`
3. `make ingest`              # download layers whose YAML has a single HTTP download_url
4. `make fetch-osm`           # OSM Overpass: natura2000, protected, airport, substations, transmission_lines
5. `make transform`           # stage data/raw/<layer>.gpkg into data/processed/
6. `make seed-grid`           # H3 cells from data/manual/country_outlines.geojson (Natural Earth, vendored)
7. `make seed-municipalities` # one-shot Nordic ADM2 seed (skip if already seeded)
8. `make characterize`        # power_layers, dh_tiers, soft_features (no-op), real_ingest (registry-driven)
9. `make refresh-norm`
10. `make app`

Step 4 needs network access to `overpass-api.de` (and falls back to two
mirrors). If your environment can't reach them, skip `make fetch-osm`;
the affected layers stay at `state=missing` in the freshness panel
and `state=real` once you can run it. The downstream pipeline picks up
GPKGs the moment they appear under `data/processed/`.

Step 6 used to use bounding-box rectangles per country. It now uses
real Natural Earth 1:50m outlines clipped to the Nordic study bbox,
cutting cell counts ~70% (the bbox version produced ~4M cells across
ocean and foreign territory). Re-run `make country-outlines` if you
need to refresh the vendored GeoJSON from the upstream GitHub mirror.

## Performance notes

- Keep `score_cells` viewport-bounded using bbox arguments in UI queries.
- Do not refresh `grid_cells_normalized` on slider movement.
- Use `top_candidate_cells` for ranking to avoid full result scans in UI.
- Keep GIST index on `geom_4326` and unique index on normalized `h3_index`.

## Data quality checks

- Run `python -m src.characterize.exclusion_qa` to enforce exclusion coverage band.
- Run CRS assertions: `SELECT * FROM assert_geometry_srid();`
- Ensure source freshness metadata in `data_sources` updates for changed checksums.

## Layer registry

All layer metadata lives in `config/layers/*.yaml`. The optional `runtime`
block on each YAML is read by `src.common.layer_registry.load_layers()` and
drives ingest / characterization. Adding a new layer means adding a YAML and
(if it has a code path) a `runtime` block — no Python changes required.

## Known-gap communication

- Score uses NULL (not random) for missing inputs; the per-cell coverage
  fraction is exposed in the UI top-50 table and cell inspector.
- Keep DH/fiber/manual-input quality warnings visible in UI.
- Keep final disclaimer: shortlist needs DSO queue and permitting checks.
